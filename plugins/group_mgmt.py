import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import ChatPermissions
from database.users_chats_db import db

# =========================
# CONFIG
# =========================
MAX_WARNS = 3
AUTO_MUTE_TIME = 600  # 10 minutes

# =========================
# HELPERS
# =========================

async def is_admin(client, chat_id, user_id):
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        )
    except:
        return False

async def warn_user(user_id, chat_id):
    data = await db.get_warn(user_id, chat_id) or {"count": 0}
    data["count"] += 1
    await db.set_warn(user_id, chat_id, data)
    return data["count"]

async def reset_warn(user_id, chat_id):
    await db.clear_warn(user_id, chat_id)

# =========================
# ADMIN MODERATION (REPLY)
# =========================

@Client.on_message(filters.group & filters.reply & filters.command("mute"))
async def mute_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    user = message.reply_to_message.from_user
    until = datetime.utcnow() + timedelta(seconds=AUTO_MUTE_TIME)
    await client.restrict_chat_member(
        message.chat.id,
        user.id,
        ChatPermissions(),
        until_date=until
    )
    await message.reply(f"🔇 {user.mention} has been muted")

@Client.on_message(filters.group & filters.reply & filters.command("unmute"))
async def unmute_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    user = message.reply_to_message.from_user
    await client.restrict_chat_member(
        message.chat.id,
        user.id,
        ChatPermissions(can_send_messages=True)
    )
    await message.reply(f"🔊 {user.mention} has been unmuted")

@Client.on_message(filters.group & filters.reply & filters.command("ban"))
async def ban_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    user = message.reply_to_message.from_user
    await client.ban_chat_member(message.chat.id, user.id)
    await message.reply(f"🚫 {user.mention} has been banned")

@Client.on_message(filters.group & filters.reply & filters.command("warn"))
async def warn_cmd(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    user = message.reply_to_message.from_user
    warns = await warn_user(user.id, message.chat.id)
    await message.reply(f"⚠️ {user.mention} warned ({warns}/{MAX_WARNS})")

@Client.on_message(filters.group & filters.reply & filters.command("resetwarn"))
async def resetwarn_cmd(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    user = message.reply_to_message.from_user
    await reset_warn(user.id, message.chat.id)
    await message.reply(f"♻️ Warnings reset for {user.mention}")

# =========================
# BLACKLIST SYSTEM
# =========================

@Client.on_message(filters.group & filters.command("addblacklist"))
async def add_blacklist(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    if len(message.command) < 2:
        return

    word = message.text.split(None, 1)[1].lower()
    data = await db.get_settings(message.chat.id) or {}

    blacklist = data.get("blacklist", [])
    blacklist.append(word)

    data["blacklist"] = list(set(blacklist))
    data.setdefault("blacklist_warn", True)
    await db.update_settings(message.chat.id, data)

@Client.on_message(filters.group & filters.command("removeblacklist"))
async def remove_blacklist(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    if len(message.command) < 2:
        return

    word = message.text.split(None, 1)[1].lower()
    data = await db.get_settings(message.chat.id) or {}
    blacklist = data.get("blacklist", [])

    if word in blacklist:
        blacklist.remove(word)
        data["blacklist"] = blacklist
        await db.update_settings(message.chat.id, data)

@Client.on_message(filters.group & filters.command("blacklist"))
async def view_blacklist(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return

    data = await db.get_settings(message.chat.id) or {}
    blacklist = data.get("blacklist", [])

    if not blacklist:
        return await message.reply("📭 Blacklist is empty")

    await message.reply("\n".join(f"• `{w}`" for w in blacklist))

@Client.on_message(filters.group & filters.command("blacklistwarn"))
async def blacklistwarn(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    if len(message.command) < 2:
        return

    data = await db.get_settings(message.chat.id) or {}
    data["blacklist_warn"] = message.command[1] == "on"
    await db.update_settings(message.chat.id, data)

@Client.on_message(filters.group & filters.text)
async def blacklist_filter(client, message):
    if not message.from_user:
        return
    if await is_admin(client, message.chat.id, message.from_user.id):
        return

    data = await db.get_settings(message.chat.id) or {}
    blacklist = data.get("blacklist", [])
    warn_on = data.get("blacklist_warn", True)
    text = message.text.lower()

    for word in blacklist:
        if (word.endswith("*") and text.startswith(word[:-1])) or (word in text):
            await message.delete()
            if warn_on:
                await warn_user(message.from_user.id, message.chat.id)
            return

# =========================
# DLINK (DELAYED DELETE)
# =========================

@Client.on_message(filters.group & filters.command("dlink"))
async def add_dlink(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return

    args = message.text.split()
    delay = 300  # default 5 min
    index = 1

    if len(args) > 2 and args[1][-1] in ("m", "h") and args[1][:-1].isdigit():
        delay = int(args[1][:-1]) * (60 if args[1][-1] == "m" else 3600)
        index = 2

    word = " ".join(args[index:]).lower()
    data = await db.get_settings(message.chat.id) or {}
    dlink = data.get("dlink", {})

    dlink[word] = delay
    data["dlink"] = dlink
    await db.update_settings(message.chat.id, data)

@Client.on_message(filters.group & filters.command("removedlink"))
async def remove_dlink(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return

    word = message.text.split(None, 1)[1].lower()
    data = await db.get_settings(message.chat.id) or {}
    dlink = data.get("dlink", {})

    dlink.pop(word, None)
    data["dlink"] = dlink
    await db.update_settings(message.chat.id, data)

@Client.on_message(filters.group & filters.command("dlinklist"))
async def dlink_list(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return

    data = await db.get_settings(message.chat.id) or {}
    dlink = data.get("dlink", {})

    if not dlink:
        return await message.reply("📭 Dlink list is empty")

    await message.reply(
        "\n".join(f"• `{k}` → {v//60}m" for k, v in dlink.items())
    )

@Client.on_message(filters.group & filters.text)
async def silent_dlink_handler(client, message):
    data = await db.get_settings(message.chat.id) or {}
    dlink = data.get("dlink", {})
    text = message.text.lower()

    for word, delay in dlink.items():
        if (word.endswith("*") and text.startswith(word[:-1])) or (word in text):
            await asyncio.sleep(delay)
            try:
                await message.delete()
            except:
                pass
            return

# =========================
# ANTI BOT PROTECTION
# =========================

@Client.on_message(filters.new_chat_members)
async def anti_bot(client, message):
    for user in message.new_chat_members:
        if user.is_bot and not await is_admin(client, message.chat.id, message.from_user.id):
            await client.ban_chat_member(message.chat.id, user.id)

# =========================
# HELP COMMAND (GROUP ADMIN ONLY)
# =========================

@Client.on_message(filters.group & filters.command("help"))
async def help_command(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return

    help_text = (
        "🛠️ **Admin Help Menu**\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "👮 **Moderation (Reply Required):**\n"
        "🔇 `/mute` – Mute a user (10 minutes)\n"
        "🔊 `/unmute` – Unmute a user\n"
        "🚫 `/ban` – Ban a user from group\n"
        "⚠️ `/warn` – Give a warning\n"
        "♻️ `/resetwarn` – Reset user warnings\n\n"

        "🚫 **Blacklist System:**\n"
        "➕ `/addblacklist <word/link>` – Add to blacklist\n"
        "➖ `/removeblacklist <word/link>` – Remove from blacklist\n"
        "📃 `/blacklist` – View blacklist\n"
        "⚙️ `/blacklistwarn on | off` – Warn on blacklist match\n\n"

        "⏱️ **Delayed Delete (DLINK):**\n"
        "🕒 `/dlink <word>` – Delete after 5 minutes\n"
        "🕒 `/dlink 10m <word>` – Delete after 10 minutes\n"
        "🕒 `/dlink 1h <word>` – Delete after 1 hour\n"
        "🗑️ `/removedlink <word>` – Remove delayed delete rule\n"
        "📃 `/dlinklist` – View delayed delete list\n\n"

        "🤖 **Auto Protection:**\n"
        "• Anti-bot system is enabled\n"
        "• Only admins can add bots\n\n"

        "⚠️ **Notes:**\n"
        "• Admin commands work only in groups\n"
        "• Some commands must be used as a reply\n"
        "• `/help` is admin-only\n"
    )

    await message.reply(help_text)
