"""📸 REAL THUMBNAIL ENGINE

Telegram हर video/document message के साथ असली thumbnail (frame) भेजता है।
Index के समय उसका ``file_id`` DB में save हो जाता है (`save_file`). पुरानी
फाइलों के लिए यह engine BIN_CHANNEL में एक temporary cached-media message
भेजकर thumbnail निकालता है और DB में backfill कर देता है — अगली बार सीधे
`download_media()` से poster मिल जाता है।

Read order: RAM LRU → MongoDB (`file_thumbs`) → Telegram (`download_media`
/ `send_cached_media` backfill) → वापस RAM + DB में save.

RAM-bounded LRU + per-file asyncio.Lock (ek hi file ke 10 parallel <img>
requests → sirf 1 Telegram call) + FloodWait retry.
"""

import asyncio
import logging
import re
import time
import zlib
from collections import OrderedDict

from info import BIN_CHANNEL, THUMB_CACHE_ITEMS, STORE_THUMBS_IN_DB
from utils import temp
from database.ia_filterdb import (
    collection, update_file_meta,
    save_thumb_bytes, get_thumb_bytes, delete_thumb_bytes,
)

logger = logging.getLogger(__name__)

_MISS = object()
_CACHE_MAX_BYTES = 24 * 1024 * 1024     # 24 MB तक ही RAM में posters
_NO_THUMB_TTL = 300                     # "no thumb" जल्दी re-check हो
_OK_TTL = 6 * 3600                      # मिली हुई image 6 घंटे cache

_semaphore = asyncio.Semaphore(6)
_locks = {}


class _LRU:
    def __init__(self, max_items, max_bytes):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.data = OrderedDict()   # fid -> (bytes|None, ts, size)
        self.bytes = 0

    def get(self, fid):
        hit = self.data.get(fid)
        if hit is None:
            return _MISS
        value, ts, size = hit
        ttl = _NO_THUMB_TTL if value is None else _OK_TTL
        if time.time() - ts > ttl:
            self.pop(fid)
            return _MISS
        self.data.move_to_end(fid)
        return value

    def put(self, fid, value):
        self.pop(fid)
        size = len(value) if value else 0
        self.data[fid] = (value, time.time(), size)
        self.bytes += size
        while len(self.data) > self.max_items or self.bytes > self.max_bytes:
            old = next(iter(self.data))
            self.pop(old)

    def pop(self, fid):
        old = self.data.pop(fid, None)
        if old:
            self.bytes -= old[2]
        return old


_cache = _LRU(THUMB_CACHE_ITEMS, _CACHE_MAX_BYTES)


def image_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def thumb_version(fid: str, thumb_file_id: str = "") -> str:
    """Thumbnail बदलने पर browser cache bust करने के लिए ``v`` param."""
    raw = f"{fid}:{thumb_file_id}"
    return f"{zlib.crc32(raw.encode('utf-8')):08x}"


async def _delete_later(message_id: int, delay: int = 30):
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
    bot = getattr(temp, "BOT", None)
    if not bot or not thumb_file_id:
        return None
    for attempt in range(2):
        try:
            buf = await bot.download_media(thumb_file_id, in_memory=True)
            if not buf:
                return None
            data = buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)
            return data or None
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                logger.debug(f"thumb download failed: {e}")
    return None


async def _probe_and_backfill(fid: str):
    """पुरानी फाइलों के लिए Telegram से thumb निकालो → (bytes, thumb_file_id)।"""
    bot = getattr(temp, "BOT", None)
    if bot is None:
        return None, ""
    async with _semaphore:
        for attempt in range(3):
            try:
                msg = await bot.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
            except Exception as e:
                text = str(e)
                m = re.search(r"wait of (\d+) seconds?", text)
                wait = min(int(m.group(1)), 20) if m else 2
                await asyncio.sleep(wait + 1)
                continue

            media, thumb_file_id = _extract_media(msg)
            meta = {}
            if thumb_file_id:
                meta["thumb_file_id"] = thumb_file_id
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
            if meta:
                await update_file_meta(fid, meta)
            asyncio.create_task(_delete_later(msg.id))

            if thumb_file_id:
                return await _download_thumb(thumb_file_id), thumb_file_id
            return None, ""
    return None, ""


async def get_thumb(fid: str, retry: bool = False):
    """Poster bytes ya None. ``retry=True`` RAM cache हटाकर Telegram से fresh लाता है
    (और DB की image भी overwrite कर देता है)।

    क्रम: RAM → MongoDB → Telegram. DB में साथ में ``thumb_file_id`` भी store है,
    इसलिए thumbnail बदलने पर पुरानी image कभी serve नहीं होती।
    """
    if not fid or len(fid) > 512:
        return None
    if retry:
        _cache.pop(fid)

    cached = _cache.get(fid)
    if cached is not _MISS:
        return cached

    lock = _locks.setdefault(fid, asyncio.Lock())
    try:
        async with lock:
            cached = _cache.get(fid)
            if cached is not _MISS:
                return cached

            doc = await asyncio.to_thread(
                collection.find_one, {"_id": fid}, {"thumb_file_id": 1}
            )
            thumb_file_id = str((doc or {}).get("thumb_file_id") or "")

            data = None
            # 1️⃣ DB में पहले से असली image है? (restart पर यही काम आता है)
            if STORE_THUMBS_IN_DB and not retry:
                saved, saved_tid = await get_thumb_bytes(fid)
                if saved and saved_tid == thumb_file_id:
                    data = saved

            # 2️⃣ नहीं है → Telegram से लाओ (index-time id या lazy backfill)
            if data is None:
                if thumb_file_id:
                    data = await _download_thumb(thumb_file_id)
                if data is None:
                    data, new_tid = await _probe_and_backfill(fid)
                    if new_tid:
                        thumb_file_id = new_tid

                # 3️⃣ मिली हुई असली image DB में भी save करो
                if data and STORE_THUMBS_IN_DB:
                    await save_thumb_bytes(fid, data, thumb_file_id)

            _cache.put(fid, data)
            return data
    finally:
        _locks.pop(fid, None)


async def drop_thumb(fid: str):
    """Thumbnail बदलने/फाइल delete होने पर RAM + DB दोनों से हटाओ।"""
    _cache.pop(fid)
    await delete_thumb_bytes(fid)
