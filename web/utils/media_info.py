"""BIN_CHANNEL message ka metadata cache.

Pehle har /download (Range) request par Telegram se `get_messages` hota tha
(100-300 ms) — video seek karte waqt baar-baar. Ab file_id / size / naam /
mime 5 मिनट तक cache me rehte hain, aur ek saath aayi kai Range requests
ek hi Telegram call share karti hain.

* TTL छोटा (5 min) है ताकि file_reference पुराना न हो।
"""

import asyncio
import logging
import time
from collections import OrderedDict

from hydrogram.file_id import FileId

from info import BIN_CHANNEL
from utils import temp

logger = logging.getLogger(__name__)

_TTL = 300
_MAX = 256
_CACHE = OrderedDict()      # message_id -> (monotonic_ts, MediaInfo)
_INFLIGHT = {}              # message_id -> asyncio.Task


class MediaInfo:
    __slots__ = ("file_id", "file_id_obj", "file_size", "file_name", "mime_type", "is_video")

    def __init__(self, file_id, file_id_obj, file_size, file_name, mime_type, is_video):
        self.file_id = file_id
        self.file_id_obj = file_id_obj
        self.file_size = file_size
        self.file_name = file_name
        self.mime_type = mime_type
        self.is_video = is_video


async def _fetch(message_id):
    msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
    media = getattr(msg, msg.media.value, None) if msg and msg.media else None
    if not media:
        return None
    info = MediaInfo(
        file_id=media.file_id,
        file_id_obj=FileId.decode(media.file_id),
        file_size=getattr(media, "file_size", None) or 0,
        file_name=getattr(media, "file_name", None),
        mime_type=getattr(media, "mime_type", None),
        is_video=bool(getattr(msg, "video", None)),
    )
    _CACHE[message_id] = (time.monotonic(), info)
    _CACHE.move_to_end(message_id)
    while len(_CACHE) > _MAX:
        _CACHE.popitem(last=False)
    return info


async def get_media_info(message_id):
    """MediaInfo ya None (file nahi mili / media nahi hai)."""
    hit = _CACHE.get(message_id)
    if hit and time.monotonic() - hit[0] < _TTL:
        _CACHE.move_to_end(message_id)
        return hit[1]

    task = _INFLIGHT.get(message_id)
    if task is None:
        task = asyncio.ensure_future(_fetch(message_id))
        _INFLIGHT[message_id] = task
        task.add_done_callback(lambda _t, _m=message_id: _INFLIGHT.pop(_m, None))
    return await asyncio.shield(task)
