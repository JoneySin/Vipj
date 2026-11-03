import asyncio
import time
import logging
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_settings, get_size, temp, is_premium


# ======================================================
# CONFIG
# ======================================================
GRACE_PERIOD = timedelta(minutes=30)
RESEND_EXPIRE_TIME = 60  # seconds

# Track active deletion tasks
active_tasks = {}


# ======================================================
# PREMIUM CHECK WITH GRACE PERIOD
# ======================================================
async def has_premium_or_grace(user_id: int) -> bool:
    """Check if user is admin or has premium with grace period"""
    if user_id in ADMINS:
        return True

    plan = await db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        return False

    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    return bool(expire and datetime.utcnow() <= expire + GRACE_PERIOD)


# ======================================================
# FILE BUTTON HANDLER (GROUP)
# ======================================================
@Client.on_callback_query(filters.regex(r"^file#"))
async def file_button_handler(client: Client, query: CallbackQuery):
    """Handle file button clicks in groups"""
    _, file_id = query.data.split("#", 1)

    # Get file details
    file = await get_file_details(file_id)
    if not file:
        return await query.answer("❌ File not found", show_alert=True)

    uid = query.from_user.id
    group_id = query.message.chat.id
    
    # Get group settings
    settings = await get_settings(group_id)
    
    # ========================================
    # PREMIUM CHECK (Bot Admin or Premium User)
    # ========================================
    is_user_premium = await has_premium_or_grace(uid)
    
    # Premium users (Bot Admin + Premium) get direct PM link
    if is_user_premium:
        await query.answer(
            url=f"https://t.me/{temp.U_NAME}?start=file_{group_id}_{file_id}"
        )
        return
    
    # ========================================
    # NON-PREMIUM: Show Premium Required Message
    # ========================================
    text = (
        "🔒 <b>Premium Required</b>\n\n"
        "PM search is only available for premium users.\n\n"
        "💎 Get unlimited search access\n"
        "⚡ Faster responses\n"
        "🎯 Priority support\n\n"
        "Upgrade now to unlock this feature!"
    )
    
    btn = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💰 Buy / Renew Premium",
                callback_data="buy_premium"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Close",
                callback_data="close_data"
            )
        ]
    ])
    
    # Send premium required message
    await query.message.reply_text(
        text,
        reply_markup=btn,
        quote=True
    )
    
    await query.answer(
        "🔒 Premium required for PM file access",
        show_alert=True
    )


# ======================================================
# START FILE DELIVERY (PM)
# ======================================================
@Client.on_message(
    filters.private &
    filters.command("start") &
    filters.regex(r"file_"),
    group=1  # Higher priority
)
async def start_file_delivery(client: Client, message):
    """Handle /start file_ commands in PM"""
    try:
        # Parse file command
        _, grp_id, file_id = message.text.split("_", 2)
        grp_id = int(grp_id)
    except Exception:
        return

    uid = message.from_user.id
    
    # ========================================
    # PREMIUM CHECK (Bot Admin or Premium)
    # ========================================
    is_user_premium = await has_premium_or_grace(uid)
    
    if not is_user_premium:
        # Non-premium user tried to access file directly
        text = (
            "🔒 <b>Premium Required</b>\n\n"
            "Direct file access is only available for premium users.\n\n"
            "💎 Get unlimited search access\n"
            "⚡ Faster responses\n"
            "🎯 Priority support\n\n"
            "Upgrade now to unlock this feature!"
        )
        
        btn = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💰 Buy / Renew Premium",
                    callback_data="buy_premium"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="close_data"
                )
            ]
        ])
        
        await message.reply_text(text, reply_markup=btn)
        
        # Delete /start command
        try:
            await message.delete()
        except:
            pass
        return
    
    # ========================================
    # DELIVER FILE TO PREMIUM USER
    # ========================================
    # Cancel previous file task for this user
    user_task_key = f"user_{uid}"
    if user_task_key in active_tasks:
        active_tasks[user_task_key].cancel()

    # Create new delivery task
    task = asyncio.create_task(
        deliver_file(client, uid, grp_id, file_id)
    )
    active_tasks[user_task_key] = task

    # Cleanup callback
    def cleanup_task(t):
        active_tasks.pop(user_task_key, None)
    
    task.add_done_callback(cleanup_task)

    # Delete /start command
    try:
        await message.delete()
    except:
        pass


# ======================================================
# SCHEDULE FILE DELETION
# ======================================================
async def schedule_file_deletion(client, sent_msg, uid, file_id):
    """Schedule auto-deletion of file message"""
    msg_id = sent_msg.id
    
    # Check if temp.FILES exists
    if not hasattr(temp, 'FILES'):
        temp.FILES = {}
    
    # Track in temp storage
    temp.FILES[msg_id] = {
        "owner": uid,
        "file_id": file_id,
        "expire": int(time.time()) + PM_FILE_DELETE_TIME
    }
    
    try:
        # Wait for expiry
        await asyncio.sleep(PM_FILE_DELETE_TIME)
        
        # Remove from tracking
        data = temp.FILES.pop(msg_id, None)
        if not data:
            return
        
        # Delete the file message
        try:
            await sent_msg.delete()
        except:
            pass
        
        # Send resend button
        resend = await client.send_message(
            uid,
            "⌛ <b>File expired</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔁 Resend File",
                    callback_data=f"resend#{file_id}"
                )]
            ])
        )
        
        # Auto-delete resend button
        await asyncio.sleep(RESEND_EXPIRE_TIME)
        try:
            await resend.delete()
        except:
            pass
            
    except asyncio.CancelledError:
        # Task cancelled, cleanup
        temp.FILES.pop(msg_id, None)
        raise


# ======================================================
# CORE FILE DELIVERY
# ======================================================
async def deliver_file(client, uid, grp_id, file_id):
    """Deliver file to premium user in PM"""
    try:
        # Get file details
        file = await get_file_details(file_id)
        if not file:
            return

        # Verify premium status again (security check)
        if not await has_premium_or_grace(uid):
            text = (
                "🔒 <b>Premium Required</b>\n\n"
                "This file is only accessible to premium users.\n\n"
                "💎 Get unlimited search access\n"
                "⚡ Faster responses\n"
                "🎯 Priority support\n\n"
                "Upgrade now to unlock this feature!"
            )
            
            btn = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "💰 Buy / Renew Premium",
                        callback_data="buy_premium"
                    )
                ]
            ])
            
            await client.send_message(uid, text, reply_markup=btn)
            return

        # Get group settings (for additional checks)
        settings = await get_settings(grp_id) if grp_id else {}

        # Build caption
        file_name = (file.get("file_name") or "").strip()
        file_caption = (file.get("caption") or "").strip()

        if not file_caption or file_caption == file_name:
            caption = file_name
        else:
            caption = f"{file_name}\n\n{file_caption}"

        # Build buttons
        buttons = []
        if IS_STREAM:
            buttons.append([
                InlineKeyboardButton(
                    "▶️ Watch / Download",
                    callback_data=f"stream#{file_id}"
                )
            ])
        buttons.append([
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ])

        markup = InlineKeyboardMarkup(buttons)

        # Send file
        sent = await client.send_cached_media(
            chat_id=uid,
            file_id=file_id,
            caption=caption,
            protect_content=PROTECT_CONTENT,
            reply_markup=markup
        )

        # Schedule deletion
        deletion_task = asyncio.create_task(
            schedule_file_deletion(client, sent, uid, file_id)
        )
        
        # Track deletion task
        task_key = f"delete_{sent.id}"
        active_tasks[task_key] = deletion_task
        
        # Cleanup callback
        def cleanup_deletion(t):
            active_tasks.pop(task_key, None)
        
        deletion_task.add_done_callback(cleanup_deletion)
        
    except Exception as e:
        logging.error(f"Error delivering file: {e}")


# ======================================================
# RESEND HANDLER
# ======================================================
@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(client, query: CallbackQuery):
    """Handle resend file button"""
    file_id = query.data.split("#", 1)[1]
    uid = query.from_user.id

    # Verify premium status
    if not await has_premium_or_grace(uid):
        return await query.answer(
            "🔒 Premium required to resend files",
            show_alert=True
        )

    await query.answer()
    
    # Delete resend message
    try:
        await query.message.delete()
    except:
        pass

    # Resend file
    asyncio.create_task(deliver_file(client, uid, 0, file_id))
