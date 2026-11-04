"""🌐 Routes for the unified Catalog (Posts + Directory profiles).

v5 में इसके लिए अलग `post_routes.py` (publish/update/delete/photo/search/single)
और `actor_routes.py` (create/avatar/gallery/social/delete/search/profile) थे —
कुल ~18 endpoints, हर एक अपना auth check और अपना response format।

यहाँ **एक** generic JSON API है:

| Method | Path | काम |
|---|---|---|
| GET | `/posts`, `/actors` | catalog pages (sidebar से) |
| GET | `/post/{id}`, `/actor/{id}` | detail page |
| GET | `/api/catalog/{kind}` | list (`q`, `category`, `offset`, `limit`) या `?id=` single |
| POST | `/api/catalog/{kind}/save` | create + edit — **एक ही endpoint** (admin) |
| POST | `/api/catalog/{kind}/delete` | delete (admin) |
| POST | `/api/catalog/upload` | image → Telegram → `TG_ID:` (admin) |
| GET | `/api/catalog/photo` | `TG_ID:` image bytes (वही serial-safe download engine) |

सभी writes admin-only, सभी input `catalog.normalize()` से sanitize, और कोई
server-generated HTML string नहीं (client render करता है)।
"""

import io
import logging
import re

from aiohttp import web

import info as _info
from info import BIN_CHANNEL
from utils import temp

# Optional dedicated channel (info.py में default = BIN_CHANNEL)।
_STORAGE_CHANNEL = getattr(_info, "CATALOG_STORAGE_CHANNEL", BIN_CHANNEL)
from web.web_assets import get_auth
from web.catalog import (
    CATALOGS,
    normalize,
    build_listing_page,
    build_detail_page,
)
from web.thumb_engine import get_image_bytes, image_content_type
from database.catalog_db import store

logger = logging.getLogger(__name__)
catalog_routes = web.RouteTableDef()

_MAX_UPLOAD = 5 * 1024 * 1024


def _json(data, status=200):
    return web.json_response(data, status=status)


def _kind(req):
    kind = req.match_info.get("kind", "")
    return kind if kind in CATALOGS else None


def _clean_id(value) -> str:
    """Ids सिर्फ़ short hex-ish — URLs और Mongo `_id` दोनों के लिए सुरक्षित।"""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:32]


def _safe_item(kind, item):
    """DB में पुराना/raw doc हो तो भी output हमेशा sanitized schema का हो।"""
    clean = normalize(kind, item)
    clean.update({
        "id": item.get("id", ""),
        "created_at": item.get("created_at", 0),
        "updated_at": item.get("updated_at", 0),
    })
    return clean


# ─────────────────────────────────────────────────────────────
# 🖼️ Specific endpoints पहले register (/{kind} से पहले, वरना वो खा जाएगा)
# ─────────────────────────────────────────────────────────────
@catalog_routes.get("/api/catalog/photo")
async def api_photo(req):
    """`TG_ID:<file_id>` → image bytes. उसी throttle/FloodWait-safe engine से।"""
    role, _ = await get_auth(req)
    if not role:
        return web.Response(status=401)
    fid = (req.query.get("id") or "").strip()
    if not fid or len(fid) > 512:
        return web.Response(status=400)
    data = await get_image_bytes(fid)
    if not data:
        return web.Response(status=404, headers={"Cache-Control": "no-store"})
    return web.Response(
        body=data,
        content_type=image_content_type(data),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@catalog_routes.post("/api/catalog/upload")
async def api_upload(req):
    """Cover/avatar upload → Telegram → permanent `TG_ID:` (v5 जैसा, पर बिना reload)।

    Bot ready न हो तो client साफ़ error दिखाकर URL paste का option देता है।
    """
    role, _ = await get_auth(req)
    if role != "admin":
        return _json({"ok": False, "error": "Admins only"}, 403)
    try:
        data = await req.post()
        field = data.get("image")
        if not field or not hasattr(field, "file"):
            return _json({"ok": False, "error": "No image"}, 400)
        raw = field.file.read()
    except Exception as e:
        return _json({"ok": False, "error": f"Bad upload: {e}"}, 400)
    if not raw or len(raw) > _MAX_UPLOAD:
        return _json({"ok": False, "error": "Image खाली है या 5 MB से बड़ी है"}, 400)

    bot = getattr(temp, "BOT", None)
    if bot is None:
        return _json({"ok": False, "error": "Bot अभी ready नहीं — image URL paste करें"}, 503)
    try:
        buf = io.BytesIO(raw)
        buf.name = "cover.jpg"
        msg = await bot.send_photo(chat_id=_STORAGE_CHANNEL, photo=buf)
        photo = getattr(msg, "photo", None)
        if not photo:
            raise RuntimeError("Telegram ने photo नहीं लौटाई")
        sizes = getattr(photo, "sizes", None)
        fid = sizes[-1].file_id if sizes else photo.file_id
        if not fid:
            raise RuntimeError("file_id नहीं मिला")
        return _json({"ok": True, "value": f"TG_ID:{fid}"})
    except Exception as e:
        logger.warning(f"catalog upload failed: {e}")
        return _json({"ok": False, "error": str(e)[:120]}, 502)


# ─────────────────────────────────────────────────────────────
# 📄 Pages
# ─────────────────────────────────────────────────────────────
async def _listing(req, kind):
    role, tg_id = await get_auth(req)
    if not role:
        return web.HTTPFound("/login")
    return build_listing_page(kind, role, tg_id)


async def _detail(req, kind, item_id):
    role, tg_id = await get_auth(req)
    if not role:
        return web.HTTPFound("/login")
    item = await store.get_item(kind, _clean_id(item_id))
    if not item:
        return web.Response(text="❌ Entry not found", status=404)
    return build_detail_page(kind, role, tg_id, _safe_item(kind, item))


@catalog_routes.get("/posts")
async def posts_page(req):
    return await _listing(req, "posts")


@catalog_routes.get("/actors")
async def actors_page(req):
    return await _listing(req, "actors")


@catalog_routes.get("/post/{id}")
async def post_detail(req):
    return await _detail(req, "posts", req.match_info["id"])


@catalog_routes.get("/actor/{id}")
async def actor_detail(req):
    return await _detail(req, "actors", req.match_info["id"])


# ─────────────────────────────────────────────────────────────
# 🔌 Generic JSON API
# ─────────────────────────────────────────────────────────────
@catalog_routes.get("/api/catalog/{kind}")
async def api_list(req):
    role, _ = await get_auth(req)
    if not role:
        return _json({"error": "Login required", "login": "/login"}, 401)
    kind = _kind(req)
    if not kind:
        return _json({"error": "Unknown catalog"}, 404)

    # ?id= → deep-link edit के लिए single item
    single = _clean_id(req.query.get("id"))
    if single:
        item = await store.get_item(kind, single)
        return _json({
            "items": [_safe_item(kind, item)] if item else [],
            "total": 1 if item else 0,
            "has_next": False,
        })

    q = (req.query.get("q") or "").strip()
    category = (req.query.get("category") or "all").strip()
    try:
        offset = max(0, int(req.query.get("offset", "0")))
        limit = max(1, min(int(req.query.get("limit", "20")), 60))
    except ValueError:
        offset, limit = 0, 20

    items, has_next = await store.list_items(kind, q, category, offset, limit)
    total = await store.count(kind, q, category)
    return _json({
        "items": [_safe_item(kind, it) for it in items],
        "total": total,
        "has_next": has_next,
        "offset": offset,
        "limit": limit,
    })


async def _read_payload(req):
    try:
        return await req.json()
    except Exception:
        try:
            return dict(await req.post())
        except Exception:
            return {}


@catalog_routes.post("/api/catalog/{kind}/save")
async def api_save(req):
    """✨ Create + Edit एक ही endpoint (v5 में 2 अलग wizard + 2 API थे)।"""
    role, _ = await get_auth(req)
    if role != "admin":
        return _json({"ok": False, "error": "Admins only"}, 403)
    kind = _kind(req)
    if not kind:
        return _json({"ok": False, "error": "Unknown catalog"}, 404)

    payload = await _read_payload(req)
    clean = normalize(kind, payload)
    if not clean["title"]:
        return _json({"ok": False, "error": "Title ज़रूरी है"}, 400)
    item = await store.save_item(
        kind, clean, _clean_id(payload.get("id")),
        allow_create=bool(payload.get("restore")),
    )
    if not item:
        return _json({"ok": False, "error": "Entry नहीं मिली"}, 404)
    return _json({"ok": True, "item": _safe_item(kind, item)})


@catalog_routes.post("/api/catalog/{kind}/delete")
async def api_delete(req):
    role, _ = await get_auth(req)
    if role != "admin":
        return _json({"ok": False, "error": "Admins only"}, 403)
    kind = _kind(req)
    if not kind:
        return _json({"ok": False, "error": "Unknown catalog"}, 404)
    payload = await _read_payload(req)
    item_id = _clean_id(payload.get("id"))
    if not item_id:
        return _json({"ok": False, "error": "Missing id"}, 400)
    return _json({"ok": await store.delete_item(kind, item_id)})
