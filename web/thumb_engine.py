"""📸 REAL THUMBNAIL + TRUE METADATA ENGINE — fsv1 का serial extraction.

Storage model (Koyeb free / 512 MB RAM) **जैसा पहले था, वैसा ही**:
  * MongoDB   → सिर्फ Telegram thumbnail का **file_id string**
                `thumb_url: "TG_ID:<file_id>"` (v5 जैसा), या `"NO_THUMB"`। कोई
                image bytes नहीं।
  * Server RAM → कोई thumbnail cache नहीं। सिर्फ़ चल रही request के दौरान
                transient buffer; response भेजते ही free।
  * Browser   → `/api/thumb` `ETag` + `Cache-Control` + 304, poster ब्राउज़र
                की अपनी cache में।

v5 (`JoneySin/v5`) से सीखा, fsv1 के अपने ढंग से:

  * **पहली बार thumbnail निकालते समय rate limit न लगे इसलिए एक-एक करके** —
    पूरे process में `_probe_lock` के कारण किसी भी समय सिर्फ़ **एक**
    `send_cached_media()` चलता है, और हर probe के बीच 1.2–3.0s का random
    anti-flood gap (`plugins/warmup.py`)।
  * `/api/thumb` 21 parallel probes नहीं खोलता: single-worker **queue** + browser
    `retry=true` (v5 का `reloadThumb` pattern)।
  * **FLOOD_WAIT / 420** → `wait of N seconds` parse (या `FloodWait.value`),
    `sleep(N + extra)` करके 5 attempts तक retry।
  * 🆕 **/warmup_thumbs = thumbnail + असली metadata एक ही probe में**: उसी
    `send_cached_media` msg से (और ज़रूरत पर file के bytes से) duration /
    width / height / quality / mime / size / type निकालकर DB में `$set`।
    `media_probe.py` Telegram के अक्सर-झूठे `1280×720` attributes की जगह
    container header की सच्ची dimensions लिखता है।
  * 🆕 **कोई फ़र्ज़ी "NO IMAGE" thumbnail DB में NEVER save**: candidate bytes
    download → `web/image_validate.py` से magic/dimensions/variance/markers
    check → Telegram `send_photo` से permanent re-upload (v5 warmup का तरीका)।
    जो pass न हो उसे reject करके `NO_THUMB` mark करते हैं, placeholder कभी
    `TG_ID:` नहीं बनता। Admin का `thumb_source:"web"` poster कभी overwrite नहीं।
"""

import asyncio
import io
import logging
import random
import re
import zlib

import info as _info
from info import (
    BIN_CHANNEL,
    THUMB_FETCH_CONCURRENCY,
    THUMB_PROBE_GAP_MIN,
    THUMB_PROBE_GAP_MAX,
    THUMB_PROBE_ATTEMPTS,
    THUMB_FLOOD_EXTRA,
)
from utils import temp
from database.ia_filterdb import collection, update_file_meta
from media_probe import META_V, build_media_meta, probe_telegram_media
from web.image_validate import validate_thumb

logger = logging.getLogger(__name__)

# v5 का THUMBNAIL_STORAGE_CHANNEL fsv1 में CATALOG_STORAGE_CHANNEL है (default BIN)
_STORAGE_CHANNEL = getattr(_info, "CATALOG_STORAGE_CHANNEL", BIN_CHANNEL)
_MIN_THUMB_BYTES = int(getattr(_info, "THUMB_MIN_BYTES", 512))
_MIN_THUMB_DIM = int(getattr(_info, "THUMB_MIN_DIM", 48))
_MIN_THUMB_STDDEV = float(getattr(_info, "THUMB_MIN_STDDEV", 6.0))

# ── Concurrency control (कोई thumbnail data यहाँ store नहीं होता) ──────────
# पहले से ज्ञात TG_ID वाली फाइलों के download के लिए सीमित concurrency
_download_sem = asyncio.Semaphore(THUMB_FETCH_CONCURRENCY)
# ⚠️ FIRST-TIME PROBE: एक समय में सिर्फ़ EK file (v5 warmup "single-bot safe")
_probe_lock = asyncio.Lock()
_probe_queue: asyncio.Queue = asyncio.Queue()
_queued = set()                 # fid — duplicate enqueue रोकने के लिए
_MAX_QUEUE = 2000
_worker_task = None
# fid -> asyncio.Task: identical concurrent requests एक ही download share करें
_INFLIGHT = {}
_STATS = {"done": 0, "ok": 0, "no_thumb": 0, "failed": 0,
          "rejected": 0, "meta": 0}


def image_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def thumb_version(fid: str, thumb_ref: str = "") -> str:
    """v5 की तरह पूरे thumb_url का hash — thumbnail बदले तो URL/ETag बदले।"""
    raw = f"{fid}:{thumb_ref}"
    return f"{zlib.crc32(raw.encode('utf-8')):08x}"


def thumb_id_from_doc(doc) -> str:
    """DB doc से Telegram thumbnail file_id (v5 `TG_ID:` + legacy alias)।

    `NO_THUMB` = permanently no-poster ⇒ कोई ID नहीं।
    """
    doc = doc or {}
    raw = str(doc.get("thumb_url") or "")
    if raw.startswith("TG_ID:"):
        return raw[len("TG_ID:"):]
    if raw == "NO_THUMB":
        return ""
    return str(doc.get("thumb_file_id") or "")


def is_no_thumb(doc) -> bool:
    return str((doc or {}).get("thumb_url") or "") == "NO_THUMB"


def invalidate_thumb(fid: str) -> None:
    """✏️ Admin ने custom poster बदला → in-flight download/probe पुराना न लौटाए।"""
    if not fid:
        return
    _INFLIGHT.pop(f"dl:{fid}", None)
    _queued.discard(fid)


def thumb_queue_state() -> dict:
    """/stats / /api/db_stats और `/warmup_thumbs` report का हल्का snapshot."""
    return {
        "queued": len(_queued),
        "done": _STATS["done"],
        "ok": _STATS["ok"],
        "no_thumb": _STATS["no_thumb"],
        "failed": _STATS["failed"],
        "rejected": _STATS["rejected"],
        "meta": _STATS["meta"],
    }


async def thumb_state(fid: str) -> str:
    """/api/thumb के 404 पर हल्का status ('queued' ⇒ browser retry करे)।"""
    doc = await _read_doc(fid)
    if doc is None:
        return "missing"                 # DB में नहीं है ⇒ बेकार Telegram call न करें
    if is_no_thumb(doc):
        return "no-thumb"
    if fid in _queued:
        return "queued"
    if thumb_id_from_doc(doc):
        # unverified lock = index-time ID, अभी validate होना बाकी है
        if not doc.get("thumb_verified"):
            enqueue_probe(fid, force=True)
            return "queued"
        return "ready"
    return "queued" if enqueue_probe(fid) else "missing"


# ─────────────────────────────────────────────────────────────
# 🛡️ v5-style FLOOD_WAIT handling
# ─────────────────────────────────────────────────────────────
def flood_wait_seconds(err) -> int:
    """FloodWait exception (`e.value`) या error string से wait seconds निकालो।"""
    value = getattr(err, "value", None)
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    text = str(err)
    upper = text.upper()
    if "FLOOD_WAIT" not in upper and "420" not in text and "FLOOD" not in upper:
        return 0
    m = re.search(r"wait of (\d+) seconds?", text)
    return int(m.group(1)) if m else 20


async def _backoff(err, default: float = 2.0):
    wait = flood_wait_seconds(err)
    await asyncio.sleep((wait + THUMB_FLOOD_EXTRA) if wait else default)


async def _delete_later(message_id: int, delay: int = 5):
    """v5 की delete-queue जैसा — probe msg को BIN_CHANNEL से हटा दो (non-blocking)।"""
    await asyncio.sleep(delay)
    try:
        await temp.BOT.delete_messages(BIN_CHANNEL, message_id)
    except Exception:
        pass


def _valid_thumb_ref(tid) -> bool:
    """v5 warmup की strict ID validation: string, >20 chars, कोई NO_THUMB marker नहीं।"""
    return (
        isinstance(tid, str)
        and len(tid.strip()) > 20
        and "NO_THUMB" not in tid.upper()
    )


def _extract_media(msg):
    """msg से media object + **सारे** thumbnail file_id (बड़े पहले)।

    Telegram कभी-कभी पहली thumb placeholder होती है और दूसरी असली frame,
    इसलिए सिर्फ़ `thumbs[0]` पर भरोसा नहीं करते।
    """
    media = getattr(msg, msg.media.value, None) if msg and getattr(msg, "media", None) else None
    ids, seen = [], set()
    for obj in (media, getattr(msg, "video", None),
                getattr(msg, "document", None), getattr(msg, "animation", None)):
        for thumb in (getattr(obj, "thumbs", None) or []):
            tid = getattr(thumb, "file_id", None)
            if tid and tid not in seen:
                seen.add(tid)
                ids.append(tid)
    photo = getattr(msg, "photo", None)
    if photo:
        for size in reversed(getattr(photo, "sizes", None) or []):
            tid = getattr(size, "file_id", None)
            if tid and tid not in seen:
                seen.add(tid)
                ids.append(tid)
        tid = getattr(photo, "file_id", None)
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(tid)
    ids.reverse()                    # Telegram thumbs छोटे→बड़े; असली बड़ी पहले
    return media, ids


async def _download_thumb(thumb_file_id: str):
    """Telegram से thumbnail bytes — कहीं store नहीं, सीधे return।"""
    bot = getattr(temp, "BOT", None)
    if not bot or not thumb_file_id:
        return None
    for attempt in range(3):
        try:
            async with _download_sem:
                buf = await bot.download_media(thumb_file_id, in_memory=True)
            if not buf:
                return None
            data = buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)
            return data or None
        except Exception as e:
            if attempt == 2:
                logger.debug(f"thumb download failed for {thumb_file_id[:16]}: {e}")
                return None
            await _backoff(e, default=1.5)
    return None


async def _upload_thumb(data: bytes) -> str:
    """✅ v5 warmup: validate की हुई image को storage channel पर fresh upload।

    Telegram `send_photo` खुद सच्ची image ही accept करता है ⇒ ये ID permanent
    होती है (transient thumb file_reference expire नहीं होती)। Fail-soft: bot
    में method न हो तो validated original ID ही use होगी।
    """
    bot = getattr(temp, "BOT", None)
    if not bot or not data:
        return ""
    try:
        buf = io.BytesIO(data)
        buf.name = "poster.png" if data.startswith(b"\x89PNG") else "poster.jpg"
        msg = await bot.send_photo(chat_id=_STORAGE_CHANNEL, photo=buf)
        photo = getattr(msg, "photo", None)
        sizes = getattr(photo, "sizes", None) if photo else None
        tid = sizes[-1].file_id if sizes else getattr(photo, "file_id", "")
        return str(tid or "")
    except Exception as e:
        logger.debug(f"[thumb] permanent re-upload skipped: {str(e)[:80]}")
        return ""


async def _real_thumb_bytes(thumb_ids):
    """हर candidate download + validate → `(bytes, info)` या `(None, {})`।

    जो भी fake / "NO IMAGE" / blank / tiny placeholder हो उसे reject करते हैं;
    `_STATS['rejected']` में गिनते हैं ताकि `/warmup_thumbs` report में दिखे।
    """
    for tid in thumb_ids:
        if not _valid_thumb_ref(tid):
            _STATS["rejected"] += 1
            continue
        data = await _download_thumb(tid)
        if not data:
            continue
        ok, info = validate_thumb(
            data,
            min_bytes=_MIN_THUMB_BYTES,
            min_dim=_MIN_THUMB_DIM,
            min_stddev=_MIN_THUMB_STDDEV,
        )
        if not ok:
            _STATS["rejected"] += 1
            logger.info(f"[thumb] rejected fake poster ({info['reason']}): {tid[:16]}")
            continue
        return data, {"ref": tid, **info}
    return None, {}


async def get_image_bytes(telegram_file_id: str):
    """📷 Public wrapper — posts/actors के `TG_ID:` images के लिए।"""
    return await _download_thumb(telegram_file_id)


async def _read_doc(fid: str):
    return await asyncio.to_thread(
        collection.find_one, {"_id": fid},
        {"thumb_url": 1, "thumb_file_id": 1, "thumb_verified": 1,
         "thumb_source": 1, "meta_v": 1, "quality": 1, "file_name": 1},
    )


def _meta_version(doc) -> int:
    try:
        return int(doc.get("meta_v") or 0)
    except (TypeError, ValueError):
        return 0


async def probe_file(fid: str, force: bool = False):
    """🖼️ EK file: **असली thumbnail + सच्ची metadata** — v5 warmup जैसा serial.

    `_probe_lock` पूरे process में एक समय में सिर्फ़ एक `send_cached_media`
    चलने देता है, probe के बीच anti-flood gap रहता है। DB में सिर्फ़ ID
    (`TG_ID:` / `NO_THUMB`) + metadata (`duration/quality/...`) जाती है।
    Fake placeholder कभी save नहीं होती — `NO_THUMB` mark हो जाती है।
    """
    if not fid or len(fid) > 512:
        return None

    async with _probe_lock:
        probed = False
        try:
            doc = await _read_doc(fid) or {}
            raw = str(doc.get("thumb_url") or "")
            custom = str(doc.get("thumb_source") or "") == "web"   # admin poster सुरक्षित
            verified = bool(doc.get("thumb_verified"))

            need_meta = force or _meta_version(doc) < META_V
            need_thumb = force or (
                (not raw.startswith("TG_ID:") and raw != "NO_THUMB")
                or (raw.startswith("TG_ID:") and not verified)
            )
            if custom:
                need_thumb = False        # custom poster कभी overwrite न करें

            if not need_meta and not need_thumb:
                if raw.startswith("TG_ID:"):
                    return await _download_thumb(raw[len("TG_ID:"):])
                return None

            bot = getattr(temp, "BOT", None)
            if bot is None:
                return None

            for attempt in range(THUMB_PROBE_ATTEMPTS):
                msg = None
                try:
                    msg = await bot.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
                    probed = True
                except Exception as e:
                    wait = flood_wait_seconds(e)
                    logger.warning(
                        f"[thumb probe] {fid[:16]} attempt {attempt + 1}: "
                        f"{str(e)[:90]}" + (f" → sleeping {wait + THUMB_FLOOD_EXTRA}s" if wait else "")
                    )
                    await _backoff(e)
                    continue

                media, thumb_ids = _extract_media(msg)
                file_name = str(doc.get("file_name") or "")
                meta = {}

                # 1️⃣ सच्ची metadata — उसी msg से + file bytes probe (free backfill)
                if need_meta and media:
                    try:
                        probed_meta = await probe_telegram_media(
                            bot, media, file_name=file_name,
                            file_size=int(doc.get("file_size") or 0),
                        )
                    except Exception as e:
                        logger.debug(f"[probe] {fid[:16]} media probe skipped: {e}")
                        probed_meta = {}
                    meta.update(build_media_meta(media, probed_meta, file_name, doc))
                    need_meta = False       # अगले attempt में range fetch दोबारा नहीं

                # 2️⃣ असली thumbnail — validate + permanent re-upload
                #    कोई candidate न हो / सब fake हों ⇒ तुरंत NO_THUMB mark
                #    (5 बार वही placeholder download करना बेकार है)।
                data, info = (None, {})
                if need_thumb:
                    data, info = await _real_thumb_bytes(thumb_ids)
                    if data:
                        permanent = await _upload_thumb(data)
                        chosen = permanent or info["ref"]
                        meta.update({
                            "thumb_url": f"TG_ID:{chosen}",
                            "thumb_file_id": chosen,
                            "thumb_verified": True,
                            "thumb_source": "probe",
                            "is_thumb_permanent": bool(permanent),
                            "thumb_width": info["width"],
                            "thumb_height": info["height"],
                        })
                    else:
                        meta.update({
                            "thumb_url": "NO_THUMB", "thumb_file_id": "",
                            "thumb_verified": False, "thumb_source": "",
                            "is_thumb_permanent": False,
                        })

                if meta:
                    await update_file_meta(fid, meta)
                    if "meta_v" in meta:
                        _STATS["meta"] += 1

                asyncio.create_task(_delete_later(getattr(msg, "id", 0)))

                if not need_thumb:
                    return None                    # सिर्फ़ metadata backfill था
                if data:
                    _STATS["ok"] += 1
                    return data
                # Telegram के पास सिर्फ़ fake/placeholder था ⇒ DB में कुछ नहीं save
                _STATS["no_thumb"] += 1
                return None

            # send_cached_media हर attempt में fail हुआ ⇒ network/flood issue,
            # इसे NO_THUMB mark नहीं करते (अगली बार फिर कोशिश होगी)।
            _STATS["failed"] += 1
            return None
        finally:
            _STATS["done"] += 1
            # ⏱️ v5 warmup जैसा 1.2–3.0s random anti-flood gap (सिर्फ़ probe के बाद)
            if probed:
                await asyncio.sleep(random.uniform(THUMB_PROBE_GAP_MIN, THUMB_PROBE_GAP_MAX))


# ─────────────────────────────────────────────────────────────
# 🔄 SINGLE-WORKER QUEUE — "एक एक करके थंबनेल निकले"
# ─────────────────────────────────────────────────────────────
def _ensure_worker():
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_queue_worker())


async def _queue_worker():
    """Queue से एक समय में एक file; बाकी sab wait करते हैं (no parallel burst)।"""
    while True:
        fid, force = await _probe_queue.get()
        try:
            await probe_file(fid, force=force)
        except Exception as e:
            logger.warning(f"[thumb queue] {fid[:16]} failed: {e}")
        finally:
            _queued.discard(fid)
            _probe_queue.task_done()


def enqueue_probe(fid: str, force: bool = False) -> bool:
    """First-time / stale-ID वाली फाइल को serial queue में डालो (non-blocking)।"""
    if not fid or len(fid) > 512:
        return False
    if fid in _queued or len(_queued) >= _MAX_QUEUE:
        return False
    _queued.add(fid)
    _probe_queue.put_nowait((fid, force))
    _ensure_worker()
    return True


async def get_thumb(fid: str, retry: bool = False):
    """Poster bytes या None. कोई persistent RAM cache नहीं।

    * `TG_ID:` मौजूद → सीधे download (identical requests एक task share करते हैं)
    * `NO_THUMB`     → तुरंत None, कोई Telegram call नहीं (v5 जैसा)
    * ID नहीं है      → serial queue में डालो, अभी 404; browser `retry=true` से
                       थोड़ी देर बाद poster ले लेगा (एक-एक करके)
    * 🆕 stored ID अगर fake/blank निकले → serve नहीं, force re-probe
    """
    if not fid or len(fid) > 512:
        return None

    doc = await _read_doc(fid)
    if doc is None:
        return None                      # unknown file_id ⇒ कोई probe/queue नहीं
    if is_no_thumb(doc):
        return None
    # Admin का intentional custom poster (`thumb_source:"web"`) Telegram ने
    # `send_photo` से पहले ही validate कर लिया — उसे size/variance से न रोकें।
    custom = str(doc.get("thumb_source") or "") == "web"
    thumb_file_id = thumb_id_from_doc(doc)

    if thumb_file_id:
        key = f"dl:{fid}"
        task = None if retry else _INFLIGHT.get(key)
        if task is None or task.done():
            task = asyncio.ensure_future(_download_thumb(thumb_file_id))
            _INFLIGHT[key] = task

            def _cleanup(_t, k=key, t=task):
                if _INFLIGHT.get(k) is t:
                    _INFLIGHT.pop(k, None)

            task.add_done_callback(_cleanup)
        data = await asyncio.shield(task)
        if data:
            ok = True if custom else validate_thumb(
                data, min_bytes=_MIN_THUMB_BYTES,
                min_dim=_MIN_THUMB_DIM, min_stddev=_MIN_THUMB_STDDEV,
            )[0]
            if ok:
                return data
            # 💾 DB में फ़र्ज़ी poster मिला → उसे हटाकर दोबारा असली निकालो
            _STATS["rejected"] += 1
            await update_file_meta(fid, {
                "thumb_url": "", "thumb_file_id": "",
                "thumb_verified": False,
            })
            enqueue_probe(fid, force=True)
            return None
        # file_reference पुराना/expired → fresh probe (भी एक-एक करके)
        enqueue_probe(fid, force=True)
        return None

    # 🆕 FIRST TIME: 21 parallel Telegram calls की जगह एक serial queue
    enqueue_probe(fid)
    return None
