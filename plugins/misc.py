import time
import sys
import platform

from hydrogram import Client, filters, enums
from hydrogram.errors import UserNotParticipant
from utils import temp
from info import IS_PREMIUM


# ======================================================
# 🆔 ID COMMAND (PM + GROUP | USER + STICKER | ADMIN BADGE)
# ======================================================

@Client.on_message(filters.command("id"))
async def get_id(client, message):

    reply = message.reply_to_message

    # ---------- USER TARGET ----------
    user = (
        reply.from_user
        if reply and reply.from_user
        else message.from_user
    )

    # ---------- ADMIN BADGE ----------
    badge = "👤 Member"
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        try:
            member = await message.chat.get_member(user.id)
            if member.status == enums.ChatMemberStatus.OWNER:
                badge = "👑 Owner"
            elif member.status in (
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.ADMIN
            ):
                badge = "🛡 Admin"
        except Exception:
            pass

    # ---------- USER INFO ----------
    text = (
        "🆔 <b>ID INFORMATION</b>\n\n"
        f"👤 <b>Name:</b> {user.first_name or ''} {user.last_name or ''}\n"
        f"🦹 <b>User ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>Username:</b> @{user.username if user.username else 'N/A'}\n"
        f"🌐 <b>DC ID:</b> <code>{user.dc_id or 'Unknown'}</code>\n"
        f"🤖 <b>Bot:</b> {'Yes' if user.is_bot else 'No'}\n"
        f"{badge}\n"
        f"🔗 <b>Profile:</b> <a href='tg://user?id={user.id}'>Open</a>\n"
    )

    # ---------- CHAT & MESSAGE INFO ----------
    text += (
        "\n💬 <b>CHAT & MESSAGE INFO</b>\n\n"
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"🏷 <b>Chat Type:</b> <code>{message.chat.type.name}</code>\n"
        f"📩 <b>Message ID:</b> <code>{message.id}</code>\n"
    )

    # ---------- GROUP INFO ----------
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        text += (
            "\n👥 <b>GROUP INFORMATION</b>\n\n"
            f"📛 <b>Title:</b> {message.chat.title}\n"
            f"🆔 <b>Group ID:</b> <code>{message.chat.id}</code>\n"
            f"🔗 <b>Username:</b> @{message.chat.username if message.chat.username else 'N/A'}\n"
        )

    # ---------- STICKER INFO ----------
    if reply and reply.sticker:
        st = reply.sticker
        text += (
            "\n🎭 <b>STICKER INFORMATION</b>\n\n"
            f"🆔 <b>File ID:</b> <code>{st.file_id}</code>\n"
            f"📦 <b>Set Name:</b> <code>{st.set_name or 'N/A'}</code>\n"
            f"🔖 <b>Emoji:</b> {st.emoji or 'N/A'}\n"
            f"📐 <b>Size:</b> {st.width}×{st.height}\n"
            f"🎞 <b>Animated:</b> {'Yes' if st.is_animated else 'No'}\n"
            f"🧩 <b>Video:</b> {'Yes' if st.is_video else 'No'}\n"
        )

    await message.reply_text(
        text,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )


# ======================================================
# 🏓 PING
# ======================================================

@Client.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    start = time.time()
    msg = await message.reply_text("🏓 Pinging…")
    end = time.time()

    await msg.edit_text(
        f"🏓 <b>Pong!</b>\n\n⚡ <code>{int((end - start) * 1000)} ms</code>",
        parse_mode=enums.ParseMode.HTML
    )


# ======================================================
# 🤖 BOT INFO
# ======================================================

@Client.on_message(filters.command("botinfo"))
async def bot_info(client, message):
    uptime = int(time.time() - temp.START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60

    text = (
        f"🤖 <b>BOT INFO</b>\n\n"
        f"⏱️ Uptime: <code>{h}h {m}m</code>\n"
        f"🐍 Python: <code>{sys.version.split()[0]}</code>\n"
        f"⚙️ Platform: <code>{platform.system()}</code>\n"
        f"📦 Library: <code>Hydrogram</code>\n"
        f"💎 Premium System: <code>{'ON' if IS_PREMIUM else 'OFF'}</code>\n"
        f"🚀 Mode: <code>Ultra-Pro</code>"
    )

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


# ======================================================
# 🕒 LAST ONLINE HELPER
# ======================================================

def last_online(user):
    if user.is_bot:
        return "🤖 Bot"
    if user.status == enums.UserStatus.ONLINE:
        return "🟢 Online"
    if user.status == enums.UserStatus.RECENTLY:
        return "Recently"
    if user.status == enums.UserStatus.LAST_WEEK:
        return "Within last week"
    if user.status == enums.UserStatus.LAST_MONTH:
        return "Within last month"
    if user.status == enums.UserStatus.LONG_AGO:
        return "Long time ago"
    if user.status == enums.UserStatus.OFFLINE:
        return user.last_online_date.strftime("%d %b %Y, %I:%M %p")
    return "Unknown"
