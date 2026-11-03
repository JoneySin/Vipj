import os
import aiohttp
import asyncio
import time
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from info import ADMINS
from utils import is_premium

# Config
MAX_FILE_SIZE = 100 * 1024 * 1024
UPLOAD_STATE = {}

# Upload Sites Info
SITES_INFO = {
    "gofile": {"name": "GoFile", "icon": "🟢", "desc": "Fast Stream"},
    "catbox": {"name": "Catbox", "icon": "🟠", "desc": "Permanent"},
    "tmpfiles": {"name": "TmpFiles", "icon": "🔵", "desc": "1 Hour"},
    "fileio": {"name": "File.io", "icon": "🟡", "desc": "One Download"}
}

# UI Buttons
def site_buttons(uid):
    state = UPLOAD_STATE.get(uid, {})
    selected = state.get("site", "gofile")
    
    buttons = []
    for key, info in SITES_INFO.items():
        check = "✅" if key == selected else ""
        buttons.append([InlineKeyboardButton(
            f"{info['icon']} {info['name']} {check}",
            callback_data=f"site#{key}"
        )])
    
    buttons.append([InlineKeyboardButton("🚀 Upload", callback_data="do_upload")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    return InlineKeyboardMarkup(buttons)

# Progress Tracker
class Progress:
    def __init__(self, total, msg):
        self.total = total
        self.sent = 0
        self.start = time.time()
        self.msg = msg
        self.last = 0

    async def update(self, size):
        self.sent += size
        now = time.time()
        if now - self.last < 2:
            return
        
        elapsed = now - self.start
        if elapsed < 1:
            return
            
        percent = (self.sent / self.total) * 100
        speed = (self.sent / elapsed) / 1024
        eta = int((self.total - self.sent) / (speed * 1024 + 1))
        
        try:
            await self.msg.edit(
                f"⚡ **Uploading...**\n\n"
                f"📊 {percent:.1f}%\n"
                f"🚀 {speed:.1f} KB/s\n"
                f"⏳ {eta}s left"
            )
            self.last = now
        except:
            pass

# Upload to GoFile
async def upload_gofile(file_path):
    async with aiohttp.ClientSession() as session:
        # Get server
        async with session.get("https://api.gofile.io/servers") as r:
            if r.status != 200:
                return None
            data = await r.json()
            server = data["data"]["servers"][0]["name"]
        
        # Upload
        url = f"https://{server}.gofile.io/uploadFile"
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename=os.path.basename(file_path))
            
            async with session.post(url, data=data) as r:
                if r.status != 200:
                    return None
                result = await r.json()
                if result.get("status") == "ok":
                    return result["data"]["downloadPage"]
    return None

# Upload to Catbox
async def upload_catbox(file_path):
    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("reqtype", "fileupload")
            data.add_field("fileToUpload", f, filename=os.path.basename(file_path))
            
            async with session.post("https://catbox.moe/user/api.php", data=data) as r:
                if r.status == 200:
                    link = await r.text()
                    return link.strip() if link else None
    return None

# Upload to TmpFiles
async def upload_tmpfiles(file_path):
    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename=os.path.basename(file_path))
            
            async with session.post("https://tmpfiles.org/api/v1/upload", data=data) as r:
                if r.status == 200:
                    result = await r.json()
                    if result.get("status") == "success":
                        url = result["data"]["url"]
                        return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    return None

# Upload to File.io
async def upload_fileio(file_path):
    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename=os.path.basename(file_path))
            
            async with session.post("https://file.io", data=data) as r:
                if r.status == 200:
                    result = await r.json()
                    if result.get("success"):
                        return result["link"]
    return None

# Upload Handler
async def do_upload(file_path, site, msg):
    uploaders = {
        "gofile": upload_gofile,
        "catbox": upload_catbox,
        "tmpfiles": upload_tmpfiles,
        "fileio": upload_fileio
    }
    
    uploader = uploaders.get(site)
    if not uploader:
        return None
    
    try:
        link = await uploader(file_path)
        return link
    except Exception as e:
        return None

# /upload Command
@Client.on_message(filters.command("upload") & filters.private)
async def upload_cmd(bot, message):
    uid = message.from_user.id
    
    if uid not in ADMINS and not await is_premium(uid, bot):
        return await message.reply("❌ Premium only")
    
    if not message.reply_to_message or not message.reply_to_message.media:
        return await message.reply("❗ Reply to a file with /upload")
    
    media = message.reply_to_message
    file = media.document or media.video or media.audio
    size = getattr(file, "file_size", 0)
    
    if size > MAX_FILE_SIZE:
        return await message.reply(f"❌ File too large (Max: {MAX_FILE_SIZE/1024/1024:.0f}MB)")
    
    if uid in UPLOAD_STATE and UPLOAD_STATE[uid].get("uploading"):
        return await message.reply("⚠️ Already uploading")
    
    UPLOAD_STATE[uid] = {
        "media": media,
        "site": "gofile",
        "uploading": False
    }
    
    await message.reply(
        f"📤 **Select Upload Site**\n\n"
        f"📁 Size: {size/1024/1024:.1f} MB\n"
        f"📝 Name: `{getattr(file, 'file_name', 'file')}`",
        reply_markup=site_buttons(uid)
    )

# Callback Handler
@Client.on_callback_query(filters.regex("^(site#|do_upload|cancel)"))
async def callback_handler(bot, query: CallbackQuery):
    uid = query.from_user.id
    state = UPLOAD_STATE.get(uid)
    
    if not state:
        return await query.answer("❌ Session expired", True)
    
    data = query.data
    
    # Site Selection
    if data.startswith("site#"):
        site = data.split("#")[1]
        state["site"] = site
        info = SITES_INFO[site]
        
        await query.message.edit_reply_markup(site_buttons(uid))
        await query.answer(f"{info['icon']} {info['name']} - {info['desc']}", True)
        return
    
    # Cancel
    if data == "cancel":
        UPLOAD_STATE.pop(uid, None)
        await query.message.edit("❌ Cancelled")
        return
    
    # Upload
    if data == "do_upload":
        if state.get("uploading"):
            return await query.answer("⚠️ Already uploading", True)
        
        state["uploading"] = True
        await query.message.edit("📥 Downloading...")
        
        asyncio.create_task(start_upload(bot, query.message, uid))

# Main Upload Task
async def start_upload(bot, msg, uid):
    state = UPLOAD_STATE.get(uid)
    if not state:
        return
    
    file_path = None
    
    try:
        media = state["media"]
        site = state["site"]
        site_info = SITES_INFO[site]
        
        # Download
        file_path = await media.download()
        if not file_path or not os.path.exists(file_path):
            return await msg.edit("❌ Download failed")
        
        # Upload
        await msg.edit(f"⚡ Uploading to {site_info['name']}...")
        link = await do_upload(file_path, site, msg)
        
        if not link:
            return await msg.edit(f"❌ Upload to {site_info['name']} failed")
        
        # Success with button
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Open Link", url=link)
        ]])
        
        await msg.edit(
            f"✅ **Upload Complete**\n\n"
            f"📤 Site: {site_info['icon']} {site_info['name']}\n"
            f"🔗 Link: `{link}`",
            reply_markup=btn,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)[:100]}")
    
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        UPLOAD_STATE.pop(uid, None)

# Cancel Command
@Client.on_message(filters.command("cancel_upload") & filters.private)
async def cancel_cmd(_, message):
    uid = message.from_user.id
    UPLOAD_STATE.pop(uid, None)
    await message.reply("✅ Cancelled")
