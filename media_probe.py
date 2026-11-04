"""🎯 TRUE MEDIA PROBE — `/warmup_thumbs` के लिए **असली** metadata.

GitHub reference (`JoneySin/v5` → `media_probe.py` + `web/search_api.py`) से सीखा:
Telegram के `width` / `height` / `duration` attributes **uploader** लिखता है
(DocumentAttributeVideo) और अक्सर बिना probe किए default `1280×720` भर दिए जाते
हैं। यानी DB में वो values झूठी हो सकती हैं। इसलिए fsv1 अब MP4 / MKV / AVI के
**असली bytes** (container header) से resolution + duration निकालता है और वही
`quality` derive करके DB में save करता है।

fsv1 का अपना रूप (v5 की verbatim copy नहीं):
  * सिर्फ़ **एक** `collection`, string `_id` — कोई `COLLECTIONS` / `ObjectId` /
    `META_SCHEMA_VERSION` migration नहीं।
  * pure-Python parsers → कोई binary dependency नहीं (Koyeb 512 MB पर हल्का)।
    `ffprobe` सिर्फ़ optional, fail-soft fallback है।
  * पूरी file download नहीं — सिर्फ़ शुरू के ~2 MB (और ज़रूरत पर आख़िरी ~4 MB,
    `moov`-at-end वाले MP4 के लिए) Telegram range से आते हैं।
  * हर चीज़ fail-soft: probe fail → Telegram attributes (पुराना behaviour)।
    Probe की वजह से thumbnail / warmup कभी रुकता नहीं।

Public API:
  `should_probe(media, file_name)`        → video-ish है या नहीं
  `probe_bytes(head, tail, file_name)`    → {'w','h','duration'} (pure, testable)
  `probe_telegram_media(bot, media, ...)` → async version (range fetch)
  `build_media_meta(media, probed, ...)`  → DB में `$set` करने लायक dict
"""

import asyncio
import json
import logging
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Tunables ───────────────────────────────────────────────────────────────
HEAD_MB = 2
TAIL_MB = 4
FETCH_TIMEOUT = 30
FFPROBE_TIMEOUT = 12
META_V = 1                       # बढ़ाने पर warmup metadata दोबारा probe करेगा

# sanity bounds — corrupt header DB में ज़हर न घोले
_MIN_W, _MAX_W = 16, 7680        # 8K तक
_MIN_H, _MAX_H = 16, 4320
_MAX_DURATION_SEC = 2 * 86400    # 2 दिन से लंबी "movie" झूठ है

VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".m4v", ".mov", ".avi", ".webm",
    ".ts", ".m2ts", ".flv", ".wmv", ".mpg", ".mpeg",
})


# ── Gating ─────────────────────────────────────────────────────────────────
def file_ext(file_name) -> str:
    """`Movie.mkv` और cleaned `Movie mkv` दोनों से extension (lowercase)।

    fsv1 का `clean_text()` file name में `.` को space कर देता है, इसलिए सिर्फ़
    `rsplit('.')` पर भरोसा करना गलत है।
    """
    name = str(file_name or "").strip().lower()
    if not name:
        return ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1].strip()
        if ext and " " not in ext:
            return ext
    last = name.rsplit(None, 1)[-1] if name.split() else ""
    return last if ("." + last) in VIDEO_EXTS else ""


def should_probe(media, file_name="") -> bool:
    """सिर्फ़ video-ish media पर probe (PDF/MP3 पर bandwidth बर्बाद नहीं)।

    Class name पर अकेले भरोसा नहीं — Telegram `Document` में छिपी video का
    `mime_type` और cleaned file name का extension भी देखते हैं (stub/plain
    objects पर भी यही काम करता है)।
    """
    if media is None:
        return False
    if isinstance(media, dict):
        mime = str(media.get("mime_type") or "").lower()
        own_name = media.get("file_name") or ""
    else:
        mime = str(getattr(media, "mime_type", "") or "").lower()
        own_name = getattr(media, "file_name", "") or ""
    if mime.startswith("video/"):
        return True
    kind = type(media).__name__.lower()
    if kind in ("video", "animation", "videonote", "video_note"):
        return True
    if kind == "document" and mime.startswith("application/octet-stream"):
        return True
    return ("." + file_ext(file_name or own_name)) in VIDEO_EXTS


def sane_wh(w, h):
    try:
        w, h = int(w or 0), int(h or 0)
    except (TypeError, ValueError):
        return 0, 0
    if _MIN_W <= w <= _MAX_W and _MIN_H <= h <= _MAX_H:
        return w, h
    return 0, 0


def sane_duration(value):
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return int(round(seconds)) if 0 < seconds <= _MAX_DURATION_SEC else 0


def quality_from_dimensions(w, h) -> str:
    """असली height से standard quality bucket — fsv1 के filter keys जैसे।"""
    try:
        h = int(h or 0)
    except (TypeError, ValueError):
        return ""
    for floor, label in (
        (2160, "2160p"), (1440, "1440p"), (1080, "1080p"),
        (720, "720p"), (480, "480p"), (360, "360p"), (240, "240p"),
    ):
        if h >= floor:
            return label
    return ""


# ── MP4 / MOV / M4V (ISO BMFF boxes) ────────────────────────────────────────
def _iter_boxes(buf, start, end):
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(buf[pos:pos + 4], "big")
        typ = bytes(buf[pos + 4:pos + 8])
        hdr = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = int.from_bytes(buf[pos + 8:pos + 16], "big")
            hdr = 16
        elif size == 0:
            size = end - pos
        if typ == b"uuid":
            hdr += 16
        if size < hdr or size <= 0:
            return
        ps, pe = pos + hdr, min(pos + size, end)
        yield typ, ps, pe
        if pos + size >= end:
            return
        pos += size


def _mvhd_duration(payload):
    if len(payload) < 20:
        return 0
    try:
        if payload[0] == 1:
            if len(payload) < 32:
                return 0
            scale = int.from_bytes(payload[20:24], "big")
            ticks = int.from_bytes(payload[24:32], "big")
        else:
            scale = int.from_bytes(payload[12:16], "big")
            ticks = int.from_bytes(payload[16:20], "big")
    except Exception:
        return 0
    return (ticks / scale) if scale > 0 and ticks > 0 else 0


def _tkhd_dimensions(payload):
    """trak header से display width/height; 90°/270° rotation पर swap।"""
    if len(payload) < 84:
        return 0, 0
    off = 88 if payload[0] == 1 else 76
    if len(payload) < off + 8:
        return 0, 0
    w = int(round(int.from_bytes(payload[off:off + 4], "big") / 65536))
    h = int(round(int.from_bytes(payload[off + 4:off + 8], "big") / 65536))
    moff = off - 36
    try:
        a = int.from_bytes(payload[moff:moff + 4], "big", signed=True)
        b = int.from_bytes(payload[moff + 4:moff + 8], "big", signed=True)
        c = int.from_bytes(payload[moff + 12:moff + 16], "big", signed=True)
        d = int.from_bytes(payload[moff + 16:moff + 20], "big", signed=True)
        if a == 0 and d == 0 and b != 0 and c != 0:
            w, h = h, w
    except Exception:
        pass
    return w, h


def _parse_moov_payload(buf, start, end, out):
    for typ, ps, pe in _iter_boxes(buf, start, end):
        if typ == b"mvhd":
            dur = _mvhd_duration(buf[ps:pe])
            if dur and not out.get("duration"):
                out["duration"] = dur
        elif typ == b"trak":
            w = h = 0
            is_video = True
            for t2, s2, e2 in _iter_boxes(buf, ps, pe):
                if t2 == b"tkhd":
                    w, h = _tkhd_dimensions(buf[s2:e2])
                elif t2 == b"mdia":
                    for t3, s3, e3 in _iter_boxes(buf, s2, e2):
                        if t3 == b"hdlr" and len(buf[s3:e3]) >= 12:
                            is_video = bytes(buf[s3 + 8:s3 + 12]) == b"vide"
                            break
            if is_video and w and h and not (out.get("w") and out.get("h")):
                out["w"], out["h"] = w, h


def _probe_mp4(head, tail):
    out = {}
    # `moov` head में (faststart) या tail में (moov-at-end) कहीं भी हो सकता है
    for buf in (head, tail):
        if not buf:
            continue
        idx = buf.find(b"moov")
        while idx >= 4:
            box_start = idx - 4
            for typ, ps, pe in _iter_boxes(buf, box_start, len(buf)):
                if typ == b"moov":
                    _parse_moov_payload(buf, ps, pe, out)
                    break
            if out.get("w") and out.get("h") and out.get("duration"):
                return out
            idx = buf.find(b"moov", idx + 1)
    return out


# ── MKV / WebM (EBML) ──────────────────────────────────────────────────────
_EBML_MASTERS = frozenset({
    0x18538067,  # Segment
    0x1549A966,  # Info
    0x1654AE6B,  # Tracks
    0xAE,        # TrackEntry
    0xE0,        # Video
    0x6D80,      # ContentEncodings
})


def _read_vint(buf, pos, end, keep_marker):
    if pos >= end:
        return None
    first = buf[pos]
    length, mask = 1, 0x80
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8 or pos + length > end:
        return None
    value = first if keep_marker else (first & (mask - 1))
    for byte in buf[pos + 1:pos + length]:
        value = (value << 8) | byte
    unknown = (not keep_marker) and value == (1 << (7 * length)) - 1
    return value, length, unknown


def _ebml_uint(buf, start, end):
    return int.from_bytes(buf[start:min(end, start + 8)], "big") if end > start else 0


def _ebml_float(buf, start, end):
    n = min(end - start, 8)
    if n not in (4, 8):
        return 0.0
    try:
        return struct.unpack(">f" if n == 4 else ">d", buf[start:start + n])[0]
    except Exception:
        return 0.0


def _walk_ebml(buf, pos, end, st, depth=0):
    while pos + 2 <= end and depth <= 6:
        idv = _read_vint(buf, pos, end, True)
        if not idv:
            return
        eid, idlen, _ = idv
        szv = _read_vint(buf, pos + idlen, end, False)
        if not szv:
            return
        size, szlen, unknown = szv
        ps = pos + idlen + szlen
        pe = end if unknown else min(ps + size, end)
        if pe <= ps and not unknown:
            return
        if eid in _EBML_MASTERS:
            _walk_ebml(buf, ps, pe, st, depth + 1)
        elif eid == 0x2AD7B1:                       # TimecodeScale (ns)
            st["scale"] = _ebml_uint(buf, ps, pe) or 1_000_000
        elif eid == 0x4489:                         # Duration (scale units)
            st["duration_raw"] = _ebml_float(buf, ps, pe)
        elif eid in (0xB0, 0x54B0) and not st.get("w"):
            st["w"] = _ebml_uint(buf, ps, pe)
        elif eid in (0xBA, 0x54BA) and not st.get("h"):
            st["h"] = _ebml_uint(buf, ps, pe)
        if unknown:
            return
        pos = pe


def _probe_mkv(head):
    st = {}
    _walk_ebml(head, 0, len(head), st)
    out = {}
    w, h = sane_wh(st.get("w"), st.get("h"))
    if w and h:
        out["w"], out["h"] = w, h
    raw = st.get("duration_raw") or 0
    if raw and raw > 0:
        seconds = raw * (st.get("scale") or 1_000_000) / 1e9
        out["duration"] = sane_duration(seconds)
    return {k: v for k, v in out.items() if v}


# ── AVI (RIFF hdrl) ────────────────────────────────────────────────────────
def _probe_avi(head):
    out = {}
    i = head.find(b"avih")
    if i >= 0 and i + 24 <= len(head):
        p = i + 4
        usec = int.from_bytes(head[p:p + 4], "little")
        frames = int.from_bytes(head[p + 16:p + 20], "little")
        out["duration"] = sane_duration(usec * frames / 1e6) if usec and frames else 0
    i = head.find(b"strf")
    if i >= 0 and i + 16 <= len(head):
        p = i + 4
        w = abs(int.from_bytes(head[p + 4:p + 8], "little", signed=True))
        h = abs(int.from_bytes(head[p + 8:p + 12], "little", signed=True))
        w, h = sane_wh(w, h)
        if w and h:
            out["w"], out["h"] = w, h
    return {k: v for k, v in out.items() if v}


# ── Optional ffprobe fallback (rare containers / टेढ़े headers) ──────────────
def ffprobe_head(head):
    if not head or len(head) < 1024 or not shutil.which("ffprobe"):
        return {}
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as fh:
            fh.write(head)
            path = fh.name
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, timeout=FFPROBE_TIMEOUT,
        )
        info = json.loads(proc.stdout or b"{}")
        out = {}
        fmt = info.get("format") or {}
        if fmt.get("duration"):
            out["duration"] = sane_duration(fmt["duration"])
        for stream in info.get("streams") or []:
            if stream.get("codec_type") == "video" or (stream.get("width") and stream.get("height")):
                w, h = sane_wh(stream.get("width"), stream.get("height"))
                if w and h:
                    out["w"], out["h"] = w, h
                    break
        return {k: v for k, v in out.items() if v}
    except Exception as e:
        logger.debug(f"[probe] ffprobe fallback skipped: {str(e)[:80]}")
        return {}
    finally:
        if path:
            try:
                import os
                os.unlink(path)
            except Exception:
                pass


def probe_bytes(head, tail=None, file_name="") -> dict:
    """Head/tail bytes → {'w','h','duration'} (सिर्फ़ sane values)।"""
    head, tail = head or b"", tail or b""
    if not head:
        return {}
    ext = file_ext(file_name)
    is_mp4 = (len(head) >= 12 and bytes(head[4:8]) == b"ftyp") or ext in ("mp4", "m4v", "mov")
    is_mkv = head[:4] == b"\x1a\x45\xdf\xa3" or ext in ("mkv", "webm")
    is_avi = head[:4] == b"RIFF" and bytes(head[8:12]) == b"AVI "

    if is_mp4:
        out = _probe_mp4(head, tail)
    elif is_mkv:
        out = _probe_mkv(head)
    elif is_avi:
        out = _probe_avi(head)
    else:
        out = {}

    if not (out.get("w") and out.get("h")):
        fb = ffprobe_head(head)
        for key, val in fb.items():
            if val and not out.get(key):
                out[key] = val
    out["w"], out["h"] = sane_wh(out.get("w"), out.get("h"))
    out["duration"] = sane_duration(out.get("duration"))
    return {k: v for k, v in out.items() if v}


# ── Telegram range fetch (पूरी file कभी download नहीं) ───────────────────────
async def fetch_range(bot, file_ref, file_size, offset_mb, chunks_mb, timeout=FETCH_TIMEOUT):
    """`client.get_file()` से [offset_mb, offset_mb+chunks_mb) MB slice।

    hydrogram lazy-import है (sandbox / tests में न हो तो चुपचाप b'' लौटता है)।
    FloodWait caller तक जाता है; बाकी सब fail-soft — जो bytes मिले वही काफ़ी हैं।
    """
    if not bot or not file_ref or chunks_mb <= 0:
        return b""
    try:
        from hydrogram.file_id import FileId
        fid = FileId.decode(file_ref)
    except Exception:
        return b""
    out = bytearray()
    cap = chunks_mb * 1024 * 1024

    async def _collect():
        async for chunk in bot.get_file(
            fid, file_size=file_size or 0,
            limit=chunks_mb, offset=offset_mb,
        ):
            if not chunk:
                break
            out.extend(chunk)
            if len(out) >= cap:
                break

    try:
        await asyncio.wait_for(_collect(), timeout=timeout)
    except Exception as e:
        logger.debug(f"[probe] range fetch partial ({offset_mb}MB): {str(e)[:80]}")
    return bytes(out)


def _merge(base, extra):
    out = dict(base or {})
    for key, val in (extra or {}).items():
        if val and not out.get(key):
            out[key] = val
    return out


async def probe_telegram_media(bot, media, file_name="", file_size=0,
                               head_mb=HEAD_MB, tail_mb=TAIL_MB) -> dict:
    """पूरा pipeline: head → pure parsers → (MP4: tail) → ffprobe fallback।

    Fail होने पर `{}` = "पता नहीं चला, Telegram attributes use करो"।
    """
    if not should_probe(media, file_name):
        return {}
    file_ref = getattr(media, "file_id", None)
    size = int(file_size or getattr(media, "file_size", 0) or 0)
    if not file_ref:
        return {}
    try:
        head = await fetch_range(bot, file_ref, size, 0, head_mb)
    except Exception:
        return {}
    if not head:
        return {}
    out = probe_bytes(head, None, file_name)
    if out.get("w") and out.get("h"):
        return out

    ext = file_ext(file_name)
    is_mp4 = (len(head) >= 12 and bytes(head[4:8]) == b"ftyp") or ext in ("mp4", "m4v", "mov")
    if is_mp4 and size > (head_mb + 1) * 1024 * 1024:
        offset_mb = max(0, size // (1024 * 1024) - tail_mb)
        try:
            tail = await fetch_range(bot, file_ref, size, offset_mb, tail_mb)
        except Exception:
            tail = b""
        if tail:
            out = _merge(out, probe_bytes(head, tail, file_name))
    return out


# ── DB payload (fsv1 का single-collection `$set` dict) ───────────────────────
def build_media_meta(media, probed=None, file_name="", doc=None) -> dict:
    """Telegram attributes + probed ground truth → DB fields.

    Probed width/height/duration हमेशा attribute से **ज़्यादा भरोसेमंद** हैं,
    इसलिए mile तो वही लिखते हैं। `quality` असली height से derive होती है —
    filename वाला guess सिर्फ़ fallback है।
    """
    doc = doc or {}
    media = media or {}
    get = lambda key, default=0: getattr(media, key, default) if not isinstance(media, dict) else media.get(key, default)

    w = int(get("width", 0) or 0)
    h = int(get("height", 0) or 0)
    duration = int(get("duration", 0) or 0)
    probed = probed or {}
    pw, ph = sane_wh(probed.get("w"), probed.get("h"))
    if pw and ph:
        w, h = pw, ph
    pdur = sane_duration(probed.get("duration"))
    if pdur:
        duration = pdur
    w, h = sane_wh(w, h)
    duration = sane_duration(duration)

    # ⚠️ quality सिर्फ़ **probed** (असली bytes) dimensions से derive करते हैं।
    # Telegram attributes भी uploader के लिखे हो सकते हैं, इसलिए probe fail होने
    # पर DB में पहले से saved / filename वाला quality label बरकरार रखते हैं।
    quality = quality_from_dimensions(w, h) if (pw and ph) else ""
    if not quality:
        saved = str(doc.get("quality") or "")
        quality = saved if saved and saved.lower() != "unknown" else ""
    if not quality:
        try:
            from database.ia_filterdb import detect_quality
            quality = detect_quality(file_name) or "unknown"
        except Exception:
            quality = "unknown"

    kind = type(media).__name__.lower()
    mime = str(get("mime_type", "") or "")
    if kind in ("video", "animation", "videonote", "video_note"):
        file_type = "video"
    elif mime.startswith("video/"):
        file_type = "video"
    elif mime.startswith("audio/"):
        file_type = "audio"
    else:
        file_type = "document"

    payload = {
        "width": w,
        "height": h,
        "duration": duration,
        "quality": quality,
        "mime_type": mime,
        "file_type": file_type,
        "meta_v": META_V,
        "probed_at": datetime.utcnow(),
    }
    size = int(get("file_size", 0) or 0)
    if size > 0:
        payload["file_size"] = size
    return payload
