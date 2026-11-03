import asyncio
import time
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.users_chats_db import db
from utils import (
    broadcast_messages,
    groups_broadcast_messages,
    temp,
    get_readable_time,
)
from info import ADMINS

lock = asyncio.Lock()

# ======================================================
# 🛑 CANCEL CALLBACK
# ======================================================

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(_, query):
    _, target = query.data.split("#")
    if target == "users":
        temp.USERS_CANCEL = True
        await query.message.edit("🛑 Cancelling user broadcast…")
    elif target == "groups":
        temp.GROUPS_CANCEL = True
        await query.message.edit("🛑 Cancelling group broadcast…")


# ======================================================
# 📢 USER BROADCAST (SEGMENTED)
# ======================================================

@Client.on_message(
    filters.command(
        ["broadcast_all", "broadcast_premium", "broadcast_free", "pin_broadcast"]
    )
    & filters.user(ADMINS)
    & filters.reply
)
async def user_broadcast(bot, message):
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is already running.")

    pin = message.command[0] == "pin_broadcast"
    mode = message.command[0]

    all_users = await db.get_all_users()

    # --- segmentation ---
    if mode == "broadcast_premium":
        users = [u for u in all_users if u.get("status", {}).get("premium")]
    elif mode == "broadcast_free":
        users = [u for u in all_users if not u.get("status", {}).get("premium")]
    else:
        users = all_users

    total = len(users)
    if not users:
        return await message.reply("❌ No users found for this broadcast.")

    status = await message.reply_text("🚀 Broadcasting started…")
    b_msg = message.reply_to_message

    start_time = time.time()
    done = success = failed = removed = 0

    async with lock:
        for batch in [users[i:i + 25] for i in range(0, total, 25)]:
            if temp.USERS_CANCEL:
                temp.USERS_CANCEL = False
                break

            results = await asyncio.gather(
                *[
                    broadcast_messages(int(u["id"]), b_msg, pin)
                    for u in batch
                ],
                return_exceptions=True
            )

            for u, res in zip(batch, results):
                done += 1
                if res == "Success":
                    success += 1
                else:
                    failed += 1
                    removed += 1
                    await db.delete_user(int(u["id"]))

            if done % 100 == 0:
                btn = [[InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#users")]]
                await status.edit(
                    f"📣 <b>Broadcasting…</b>\n\n"
                    f"👥 Total: <code>{total}</code>\n"
                    f"✅ Success: <code>{success}</code>\n"
                    f"❌ Failed: <code>{failed}</code>\n"
                    f"🧹 Removed inactive: <code>{removed}</code>\n"
                    f"📊 Progress: <code>{done}/{total}</code>\n"
                    f"⏱ Time: {get_readable_time(time.time() - start_time)}",
                    reply_markup=InlineKeyboardMarkup(btn),
                )

            await asyncio.sleep(0.4)

    await status.edit(
        f"✅ <b>Broadcast Completed</b>\n\n"
        f"👥 Target users: <code>{total}</code>\n"
        f"✅ Success: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>\n"
        f"🧹 Inactive removed: <code>{removed}</code>\n"
        f"⏱ Duration: {get_readable_time(time.time() - start_time)}"
    )


# ======================================================
# 📡 GROUP BROADCAST
# ======================================================

@Client.on_message(
    filters.command(["grp_broadcast", "pin_grp_broadcast"])
    & filters.user(ADMINS)
    & filters.reply
)
async def group_broadcast(bot, message):
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is running.")

    pin = message.command[0] == "pin_grp_broadcast"
    groups = await db.get_all_chats()
    total = len(groups)

    if not groups:
        return await message.reply("❌ No groups found.")

    status = await message.reply_text("🚀 Group broadcast started…")
    b_msg = message.reply_to_message

    start_time = time.time()
    done = success = failed = 0

    async with lock:
        for batch in [groups[i:i + 15] for i in range(0, total, 15)]:
            if temp.GROUPS_CANCEL:
                temp.GROUPS_CANCEL = False
                break

            results = await asyncio.gather(
                *[
                    groups_broadcast_messages(int(g["id"]), b_msg, pin)
                    for g in batch
                ],
                return_exceptions=True
            )

            for res in results:
                done += 1
                if res == "Success":
                    success += 1
                else:
                    failed += 1

            if done % 30 == 0:
                btn = [[InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#groups")]]
                await status.edit(
                    f"📡 <b>Group Broadcast…</b>\n\n"
                    f"💬 Total: <code>{total}</code>\n"
                    f"✅ Success: <code>{success}</code>\n"
                    f"❌ Failed: <code>{failed}</code>\n"
                    f"📊 Progress: <code>{done}/{total}</code>\n"
                    f"⏱ Time: {get_readable_time(time.time() - start_time)}",
                    reply_markup=InlineKeyboardMarkup(btn),
                )

            await asyncio.sleep(1)

    await status.edit(
        f"✅ <b>Group Broadcast Completed</b>\n\n"
        f"💬 Total groups: <code>{total}</code>\n"
        f"✅ Success: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>\n"
        f"⏱ Duration: {get_readable_time(time.time() - start_time)}"
    )
