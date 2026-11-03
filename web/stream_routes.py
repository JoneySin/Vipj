import math
import secrets
import mimetypes

from aiohttp import web
from info import BIN_CHANNEL
from utils import temp
from web.utils.custom_dl import TGCustomYield, chunk_size, offset_fix
from web.utils.render_template import media_watch

routes = web.RouteTableDef()


# ======================================================
# 🌐 ROOT + SEARCH PAGE (UPTIME SAFE)
# ======================================================
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Search Files</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0f172a;
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .box {{
                background: #020617;
                padding: 25px;
                border-radius: 10px;
                width: 100%;
                max-width: 400px;
                box-shadow: 0 0 15px rgba(0,0,0,0.6);
            }}
            h2 {{
                text-align: center;
                margin-bottom: 20px;
            }}
            input {{
                width: 100%;
                padding: 12px;
                border-radius: 6px;
                border: none;
                outline: none;
                margin-bottom: 12px;
                font-size: 16px;
            }}
            button {{
                width: 100%;
                padding: 12px;
                border-radius: 6px;
                border: none;
                background: #2563eb;
                color: white;
                font-size: 16px;
                cursor: pointer;
            }}
            button:hover {{
                background: #1d4ed8;
            }}
            .footer {{
                margin-top: 15px;
                text-align: center;
                font-size: 12px;
                opacity: 0.7;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <h2>🔎 Search Files</h2>
            <input id="q" type="text" placeholder="Enter movie / series name">
            <button onclick="go()">Search in Telegram</button>
            <div class="footer">Service is running ✔️</div>
        </div>

        <script>
            function go() {{
                const q = document.getElementById("q").value.trim();
                if (!q) return;
                window.location.href =
                    "https://t.me/{temp.U_NAME}?start=search_" +
                    encodeURIComponent(q);
            }}
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


# ======================================================
# ▶️ WATCH PAGE
# ======================================================
@routes.get("/watch/{message_id}")
async def watch_handler(request):
    try:
        message_id = int(request.match_info["message_id"])
        return web.Response(
            text=await media_watch(message_id),
            content_type="text/html"
        )
    except Exception:
        return web.Response(
            text="<h1>Something went wrong</h1>",
            content_type="text/html"
        )


# ======================================================
# ⬇️ DOWNLOAD ROUTE
# ======================================================
@routes.get("/download/{message_id}")
async def download_handler(request):
    try:
        message_id = int(request.match_info["message_id"])
        return await media_download(request, message_id)
    except Exception:
        return web.Response(
            text="<h1>Something went wrong</h1>",
            content_type="text/html"
        )


# ======================================================
# 📦 MEDIA STREAM
# ======================================================
async def media_download(request, message_id: int):
    range_header = request.headers.get("Range", None)

    media_msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
    media = getattr(media_msg, media_msg.media.value, None)
    file_size = media.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = request.http_range.stop or file_size - 1

    req_length = until_bytes - from_bytes

    new_chunk_size = await chunk_size(req_length)
    offset = await offset_fix(from_bytes, new_chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = (until_bytes % new_chunk_size) + 1
    part_count = math.ceil(req_length / new_chunk_size)

    body = TGCustomYield().yield_file(
        media_msg,
        offset,
        first_part_cut,
        last_part_cut,
        part_count,
        new_chunk_size
    )

    file_name = media.file_name or f"{secrets.token_hex(2)}.bin"
    mime_type = media.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"

    resp = web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }
    )

    if resp.status == 200:
        resp.headers["Content-Length"] = str(file_size)

    return resp
