"""📸 REAL THUMBNAIL ENGINE — v5 (JoneySin/v5) जैसा first-time extraction.

Storage model (Koyeb free / 512 MB RAM के लिए) **जैसा पहले था, वैसा ही**:
  * MongoDB   → सिर्फ Telegram thumbnail का **file_id string**
                `thumb_url: "TG_ID:<file_id>"` (v5 जैसा), या `"NO_THUMB"`। कोई
                image bytes नहीं।
  * Server RAM → कोई thumbnail cache नहीं। सिर्फ़ चल रही request के दौरान
                transient buffer; response भेजते ही free।
  * Browser   → `/api/thumb` `ETag` + `Cache-Control` + 304, poster ब्राउज़र
                की अपनी cache में।

🆕 v5 से port किया गया EXTRACTION logic (`web/search_api.py` + `plugins/warmup.py`):

  * **पहली बार thumbnail निकालते समय rate limit न लगे इसलिए एक-एक करके** —
    पूरे process में `_probe_lock` के कारण किसी भी समय सिर्फ़ **एक**
    `send_cached_media()` चलता है, और हर probe के बीच 1.2–3.0s का random
    anti-flood gap (बिल्कुल v5 के warmup engine जैसा)।
  * `/api/thumb` अब 21 parallel probes नहीं खोलता: पहली बार वाली फाइल को
    single-worker background **queue** में डालकर तुरंत 404 देता है; browser
    `retry=true&t=...` (v5 का `reloadThumb` pattern) से धीरे-धीरे retry करता
    है — posters एक-एक करके अपने आप आ जाते हैं।
  * **FLOOD_WAIT / 420** → `wait of N seconds` parse (या `FloodWait.value`),
    `sleep(N + extra)` करके 5 attempts तक retry — v5 जैसा ही।
  * ID DB में lock हो जाती है (`TG_ID:...`) तो अगली बार सिर्फ़ `download_media`
    (probe नहीं)। जिस फाइल में thumbnail ही नहीं है उसे `NO_THUMB` mark कर
    दिया जाता है ताकि बार-बार Telegram call न जाए (v5 warmup जैसा)।
  * उसी एक `send_cached_media` msg से duration / mime / width / height / size
    free में backfill (v5 के lazy backfill जैसा) और msg 5s बाद delete।
"""

import asyncio
import logging
import random
import re
import zlib

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

logger = logging.getLogger(__name__)

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
_STATS = {"done": 0, "ok": 0, "no_thumb": 0, "failed": 0}


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

    `NO_THUMB` = v5 warmup की तरह permanently no-poster ⇒ कोई ID नहीं।
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


def thumb_queue_state() -> dict:
    """/stats / /api/db_stats के लिए हल्का progress snapshot."""
    return {
        "queued": len(_queued),
        "done": _STATS["done"],
        "ok": _STATS["ok"],
        "no_thumb": _STATS["no_thumb"],
        "failed": _STATS["failed"],
    }


async def thumb_state(fid: str) -> str:
    """/api/thumb के 404 पर हल्का status ('queued' ⇒ browser retry करे)।"""
    doc = await _read_doc(fid)
    if doc is None:
        return "missing"                 # DB में नहीं है ⇒ बेकार Telegram call न करें
    if is_no_thumb(doc):
        return "no-thumb"
    # stale ID का force re-probe चल रहा हो तो "ready" न बोलें
    if fid in _queued:
        return "queued"
    if thumb_id_from_doc(doc):
        return "ready"
    return "queued" if enqueue_probe(fid) else "missing"


# ─────────────────────────────────────────────────────────────
# 🛡️ v5-style FLOOD_WAIT handling
# ─────────────────────────────────────────────────────────────
def flood_wait_seconds(err) -> int:
    """FloodWait exception (`e.value`) या error string से wait seconds निकालो।

    v5 `web/search_api.py`: `"FLOOD_WAIT" in err_text or "420" in err_text`
    → `re.search(r'wait of (\\d+) second', ...)`; v5 `plugins/warmup.py`:
    `wait_sec = e.value + 10`. दोनों यहाँ एक साथ handle होते हैं।
    """
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


def _extract_media(msg):
    media = getattr(msg, msg.media.value, None) if msg and msg.media else None
    thumbs = getattr(media, "thumbs", None) or []
    return media, (thumbs[0].file_id if thumbs else None)


async def _download_thumb(thumb_file_id: str):
    """Telegram से thumbnail bytes — कहीं store नहीं, सीधे return।

    v5 के 5-attempt retry जैसा FloodWait backoff, पर सिर्फ़ known IDs के लिए
    (probe नहीं — probe नीचे serialized है)।
    """
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


async def _read_doc(fid: str):
    return await asyncio.to_thread(
        collection.find_one, {"_id": fid},
        {"thumb_url": 1, "thumb_file_id": 1},
    )


async def probe_file(fid: str, force: bool = False):
    """🖼️ EK file का thumbnail निकालो — v5 के warmup engine जैसा sequential.

    `_probe_lock` पूरे process में एक समय में सिर्फ़ एक `send_cached_media`
    चलने देता है, और probe के बीच anti-flood gap रहता है। इसलिए पहली बार
    21 नई फाइलें एक साथ खुलने पर भी Telegram rate limit नहीं लगता।
    DB में सिर्फ ID (`TG_ID:` / `NO_THUMB`) + free meta backfill होती है।
    """
    if not fid or len(fid) > 512:
        return None

    async with _probe_lock:
        probed = False
        try:
            doc = await _read_doc(fid)
            raw = str((doc or {}).get("thumb_url") or "")
            if not force:
                # v5: पहले से locked ID हो तो probe की ज़रूरत नहीं
                if raw.startswith("TG_ID:"):
                    return await _download_thumb(raw[len("TG_ID:"):])
                if raw == "NO_THUMB":
                    return None

            bot = getattr(temp, "BOT", None)
            if bot is None:
                return None

            for attempt in range(THUMB_PROBE_ATTEMPTS):
                msg = None
                try:
                    # 1️⃣ वही msg जिससे thumb_id + meta दोनों मिलते हैं (v5 जैसा)
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

                media, thumb_file_id = _extract_media(msg)
                meta = {}
                if thumb_file_id:
                    meta["thumb_url"] = f"TG_ID:{thumb_file_id}"   # v5 format → अगली बार probe नहीं
                    meta["thumb_file_id"] = thumb_file_id          # legacy alias
                else:
                    meta["thumb_url"] = "NO_THUMB"                 # v5 warmup: बार-बार न उठाएँ
                if media:
                    for key, attr in (
                        ("duration", "duration"), ("mime_type", "mime_type"),
                        ("width", "width"), ("height", "height"),
                        ("file_size", "file_size"),
                    ):
                        val = getattr(media, attr, None)
                        if val:
                            meta[key] = int(val) if isinstance(val, (int, float)) else val
                    meta["file_type"] = "video" if getattr(msg, "video", None) else "document"
                await update_file_meta(fid, meta)
                asyncio.create_task(_delete_later(msg.id))

                if not thumb_file_id:
                    _STATS["no_thumb"] += 1
                    return None

                data = await _download_thumb(thumb_file_id)
                if data:
                    _STATS["ok"] += 1
                    return data
                # bytes नहीं मिले → अगले attempt में fresh file_reference लें
                await asyncio.sleep(2)

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
    """
    if not fid or len(fid) > 512:
        return None

    doc = await _read_doc(fid)
    if doc is None:
        return None                      # unknown file_id ⇒ कोई probe/queue नहीं
    if is_no_thumb(doc):
        return None
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
            return data
        # file_reference पुराना/expired → fresh probe (भी एक-एक करके)
        enqueue_probe(fid, force=True)
        return None

    # 🆕 FIRST TIME: 21 parallel Telegram calls की जगह एक serial queue
    enqueue_probe(fid)
    return None
