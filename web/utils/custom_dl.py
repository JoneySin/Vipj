import math

from hydrogram.types import Message
from hydrogram import Client, utils, raw
from hydrogram.session import Session, Auth
from hydrogram.errors import AuthBytesInvalid
from hydrogram.file_id import FileId, FileType, ThumbnailSource

from utils import temp


# ======================================================
# ⚡ CHUNK HELPERS (SAFE)
# ======================================================

async def chunk_size(length: int) -> int:
    """
    Calculate optimal chunk size for streaming.
    Safe for edge cases.
    """
    if length <= 0:
        return 256 * 1024  # fallback 256KB

    return (
        2 ** max(
            min(math.ceil(math.log2(length / 1024)), 10),
            2
        ) * 1024
    )


async def offset_fix(offset: int, chunksize: int) -> int:
    """
    Align offset to chunk boundary.
    """
    return offset - (offset % chunksize)


# ======================================================
# 📡 TELEGRAM CUSTOM STREAMER
# ======================================================

class TGCustomYield:
    """
    Custom Telegram file streamer with DC support.
    """

    def __init__(self):
        self.main_bot = temp.BOT

    # --------------------------------------------------
    # 📄 FILE PROPERTIES
    # --------------------------------------------------
    @staticmethod
    async def generate_file_properties(msg) -> FileId:
        # media_info cache may already hold a decoded FileId (so we do not call
        # Telegram get_messages() again on every Range request).
        if isinstance(msg, FileId):
            return msg
        media = getattr(msg, msg.media.value, None)
        return FileId.decode(media.file_id)

    # --------------------------------------------------
    # 🌍 MEDIA SESSION (DC HANDLING)
    # --------------------------------------------------
    async def generate_media_session(self, client: Client, msg: Message) -> Session:
        data = await self.generate_file_properties(msg)

        media_session = client.media_sessions.get(data.dc_id)

        if media_session:
            return media_session

        # ---- DIFFERENT DC ----
        if data.dc_id != await client.storage.dc_id():
            media_session = Session(
                client,
                data.dc_id,
                await Auth(
                    client,
                    data.dc_id,
                    await client.storage.test_mode()
                ).create(),
                await client.storage.test_mode(),
                is_media=True
            )
            await media_session.start()

            for _ in range(3):
                exported_auth = await client.invoke(
                    raw.functions.auth.ExportAuthorization(
                        dc_id=data.dc_id
                    )
                )
                try:
                    await media_session.send(
                        raw.functions.auth.ImportAuthorization(
                            id=exported_auth.id,
                            bytes=exported_auth.bytes
                        )
                    )
                    break
                except AuthBytesInvalid:
                    continue
            else:
                await media_session.stop()
                raise AuthBytesInvalid

        # ---- SAME DC ----
        else:
            media_session = Session(
                client,
                data.dc_id,
                await client.storage.auth_key(),
                await client.storage.test_mode(),
                is_media=True
            )
            await media_session.start()

        client.media_sessions[data.dc_id] = media_session
        return media_session

    # --------------------------------------------------
    # 📍 FILE LOCATION
    # --------------------------------------------------
    @staticmethod
    async def get_location(file_id: FileId):
        if file_id.file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id,
                    access_hash=file_id.chat_access_hash
                )
            elif file_id.chat_access_hash == 0:
                peer = raw.types.InputPeerChat(
                    chat_id=-file_id.chat_id
                )
            else:
                peer = raw.types.InputPeerChannel(
                    channel_id=utils.get_channel_id(file_id.chat_id),
                    access_hash=file_id.chat_access_hash
                )

            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG
            )

        if file_id.file_type == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size
            )

        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=file_id.thumbnail_size
        )

    # --------------------------------------------------
    # 🎬 STREAM FILE (RANGE SUPPORT)
    # --------------------------------------------------
    async def yield_file(
        self,
        media_msg: Message,
        offset: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        chunk_size: int
    ):
        client = self.main_bot
        data = await self.generate_file_properties(media_msg)
        media_session = await self.generate_media_session(client, media_msg)
        location = await self.get_location(data)

        current_part = 1

        r = await media_session.send(
            raw.functions.upload.GetFile(
                location=location,
                offset=offset,
                limit=chunk_size
            )
        )

        if not isinstance(r, raw.types.upload.File):
            return

        while current_part <= part_count:
            chunk = r.bytes
            if not chunk:
                break

            # ⚠️ FIX: the final chunk used to be sent in full (not trimmed to
            # last_part_cut), making the Range response larger than the declared
            # Content-Length and stalling player seeks. The last part is now trimmed too.
            if part_count == 1:
                yield chunk[first_part_cut:last_part_cut]
                break

            if current_part == 1:
                yield chunk[first_part_cut:]
            elif current_part == part_count:
                yield chunk[:last_part_cut]
            else:
                yield chunk

            if len(chunk) < chunk_size:        # EOF: the file ends here
                break

            offset += chunk_size
            current_part += 1
            if current_part > part_count:
                break

            r = await media_session.send(
                raw.functions.upload.GetFile(
                    location=location,
                    offset=offset,
                    limit=chunk_size
                )
            )
            if not isinstance(r, raw.types.upload.File):
                break
