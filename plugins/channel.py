import asyncio
from hydrogram import Client, filters
from hydrogram.errors import (
    FloodWait,
    MessageNotModified,
    ReactionInvalid,
    ChatWriteForbidden
)

from info import INDEX_CHANNELS, LOG_CHANNEL
from database.ia_filterdb import (
    save_file,
    update_file_caption,
    detect_quality
)

# 🔥 Import manual index cancel flag
try:
    from plugins.index import CANCEL_INDEX
except:
    CANCEL_INDEX = {}

# ─────────────────────────────────────────────
# MEDIA FILTER
# ─────────────────────────────────────────────
media_filter = (filters.video | filters.document)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

async def safe_react(message, emoji: str):
    try:
        await message.react(emoji)
        return True
    except ReactionInvalid:
        return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await message.react(emoji)
            return True
        except:
            return False
    except Exception:
        return False


async def safe_log(client, text: str):
    if not LOG_CHANNEL:
        return False
    try:
        await client.send_message(LOG_CHANNEL, text)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.send_message(LOG_CHANNEL, text)
            return True
        except:
            return False
    except (ChatWriteForbidden, Exception):
        return False


def get_media_info(message):
    try:
        media = message.document or message.video
        if not media or not getattr(media, "file_id", None):
            return None
        return media
    except:
        return None


def format_file_size(size_bytes: int) -> str:
    try:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return "Unknown"
    except:
        return "Unknown"

# ─────────────────────────────────────────────
# 📥 AUTO INDEX (LIVE POSTS ONLY)
# ─────────────────────────────────────────────

@Client.on_message(filters.chat(INDEX_CHANNELS) & media_filter, group=10)
async def index_new_file(bot, message):
    # 🛑 Skip if manual indexing running for this channel
    if CANCEL_INDEX.get(message.chat.id) is False:
        return

    media = get_media_info(message)
    if not media:
        return

    try:
        caption = message.caption or ""
        quality = detect_quality(media.file_name, caption)
        file_size = getattr(media, "file_size", 0)

        status = await save_file(media, quality=quality)

        emoji_map = {
            "suc": "✅",
            "dup": "♻️",
            "err": "❌",
            "skip": "⏭",
        }

        await safe_react(message, emoji_map.get(status, "❓"))

        await safe_log(
            bot,
            f"📥 **Auto Index**\n\n"
            f"📄 `{media.file_name}`\n"
            f"📊 `{format_file_size(file_size)}`\n"
            f"🎞 `{quality}`\n"
            f"✅ `{status}`\n"
            f"💬 `{message.chat.title}`"
        )

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        await safe_react(message, "❌")

# ─────────────────────────────────────────────
# ✏️ CAPTION EDIT
# ─────────────────────────────────────────────

@Client.on_edited_message(filters.chat(INDEX_CHANNELS) & media_filter, group=11)
async def update_caption(bot, message):
    media = get_media_info(message)
    if not media:
        return

    try:
        new_caption = message.caption or ""
        quality = detect_quality(media.file_name, new_caption)

        updated = await update_file_caption(
            media.file_id,
            new_caption,
            quality
        )

        await safe_react(message, "✏️" if updated else "⚠️")

    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        await safe_react(message, "❌")

# ─────────────────────────────────────────────
# 🗑️ DELETE LOG
# ─────────────────────────────────────────────

@Client.on_deleted_messages(filters.chat(INDEX_CHANNELS), group=12)
async def handle_deleted_files(bot, messages):
    try:
        await safe_log(
            bot,
            f"🗑️ **Deleted Messages**\nCount: `{len(messages)}`"
        )
    except:
        pass
