"""📸 REAL THUMBNAIL ENGINE — DB में सिर्फ ID, bytes सिर्फ browser cache में।

Storage model (Koyeb free / 512 MB RAM के लिए):
  * MongoDB   → सिर्फ Telegram thumbnail का **file_id string**
                `thumb_url: "TG_ID:<file_id>"` (v5 जैसा)। कोई image bytes नहीं।
  * Server RAM → **कोई thumbnail cache नहीं**। न LRU, न dict, न disk।
                सिर्फ़ चल रही request के दौरान ~10–60 KB transient buffer,
                response भेजते ही free।
  * Browser   → `/api/thumb` `ETag` + `Cache-Control: private, max-age=...`
                भेजता है, इसलिए poster **उसी साइट/ब्राउज़र की memory/disk cache**
                में रहता है; दोबारा खोलने पर server/Telegram call ही नहीं लगती
                (`If-None-Match` → 304)।

पुरानी फाइलों के लिए `send_cached_media()` से सिर्फ **ID** DB में backfill होती है।
एक ही file के 21 parallel `<img>` requests एक ही in-flight fetch share करते हैं —
ये कोई cache नहीं, request खत्म होते ही result हट जाता है।
"""

import asyncio
import logging
import re
import zlib

from info import BIN_CHANNEL, THUMB_FETCH_CONCURRENCY
from utils import temp
from database.ia_filterdb import collection, update_file_meta

logger = logging.getLogger(__name__)

# सिर्फ़ concurrency control — कोई thumbnail data यहाँ store नहीं होता
_semaphore = asyncio.Semaphore(THUMB_FETCH_CONCURRENCY)
# fid -> asyncio.Task (सिर्फ़ चल रही request; done callback तुरंत हटा देता है)
_INFLIGHT = {}


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
    """DB doc से Telegram thumbnail file_id (v5 `TG_ID:` + legacy alias)।"""
    doc = doc or {}
    raw = str(doc.get("thumb_url") or "")
    if raw.startswith("TG_ID:"):
        return raw[len("TG_ID:"):]
    return str(doc.get("thumb_file_id") or "")


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
    """Telegram से thumbnail की bytes लाओ — कहीं store नहीं, सीधे return।"""
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
    """पुरानी फाइलों के लिए Telegram से ID निकालो → (bytes, thumb_file_id)।

    DB में वापस **सिर्फ ID string** (`thumb_url`) लिखी जाती है, image नहीं।
    """
    bot = getattr(temp, "BOT", None)
    if bot is None:
        return None, ""
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
            meta["thumb_url"] = f"TG_ID:{thumb_file_id}"   # v5 format
            meta["thumb_file_id"] = thumb_file_id          # legacy alias
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


async def _fetch_once(fid: str):
    """Telegram से poster लाओ। कोई module-level cache नहीं — bytes सीधे caller को।"""
    doc = await asyncio.to_thread(
        collection.find_one, {"_id": fid}, {"thumb_url": 1, "thumb_file_id": 1}
    )
    thumb_file_id = thumb_id_from_doc(doc)

    # ⚠️ Semaphore सिर्फ़ यहाँ एक बार — nested acquisition से deadlock न हो।
    async with _semaphore:
        # 1️⃣ index-time पर save किया हुआ ID → सीधे Telegram से thumbnail
        data = await _download_thumb(thumb_file_id) if thumb_file_id else None

        # 2️⃣ पुरानी/बिना-ID वाली फाइल → probe करके DB में सिर्फ ID backfill
        if data is None:
            data, _new_id = await _probe_and_backfill(fid)
    return data


async def get_thumb(fid: str, retry: bool = False):
    """Poster bytes या None. कोई persistent RAM cache नहीं।

    सिर्फ़ एक ही समय में आई identical requests को एक fetch share करने दिया जाता
    है (`_INFLIGHT`); task खत्म होते ही entry और result दोनों free हो जाते हैं।
    """
    if not fid or len(fid) > 512:
        return None

    task = None if retry else _INFLIGHT.get(fid)
    if task is None or task.done():
        task = asyncio.ensure_future(_fetch_once(fid))
        _INFLIGHT[fid] = task

        def _cleanup(_t, f=fid, t=task):
            if _INFLIGHT.get(f) is t:      # retry ने नया task रखा हो तो पुराना न हटाए
                _INFLIGHT.pop(f, None)

        task.add_done_callback(_cleanup)
    return await asyncio.shield(task)
