"""✏️ Web **File Editor** — `JoneySin/v5` के "Edit Title Metadata" का fsv1 रूप.

v5 `/api/edit_name` + `/api/upload_thumb` + `/api/delete` में ये editable थे:

* `file_name` — टाइटल
* `caption` — Search Tags (text index में जाता है)
* `target_collection` — 🟢 Primary / 🔵 Cloud / 🟠 Archive (v5 में अलग DB collections)
* Poster thumbnail — Cropper.js से 16:9 crop → Telegram storage channel → `TG_ID:`
* Delete file

fsv1 में एक ही MongoDB collection है, इसलिए **verbatim copy नहीं** किया:

* "Move to collection" → whitelisted `section` field + `/api/search?section=…`
  (`database.ia_filterdb.get_files_by_section`) — document copy/delete नहीं।
* Cropper.js CDN → **बिल्कुल dependency-free** built-in 16:9 canvas crop (UI में)।
* Upload `CATALOG_STORAGE_CHANNEL` पर, bytes DB/RAM में कभी नहीं — सिर्फ़ `TG_ID:`
  string, और `thumb_version()` का hash browser cache bust करता है।
* Extra fsv1 chips भी editable: `quality`, `duration`, `width`×`height`.
* कोई `window.location.reload()` — JSON response से card in-place update.

सारे endpoints **admin-only** हैं और हर `$set` key whitelist से होकर जाती है।
"""

import io
import logging
import re
from urllib.parse import quote

from aiohttp import web

import info as _info
from info import BIN_CHANNEL
from utils import temp, get_size
from database import ia_filterdb as ia
from web.web_assets import get_auth
from web.thumb_engine import thumb_version, invalidate_thumb, enqueue_probe

logger = logging.getLogger(__name__)
file_edit_routes = web.RouteTableDef()

_STORAGE_CHANNEL = getattr(_info, "CATALOG_STORAGE_CHANNEL", BIN_CHANNEL)
_MAX_UPLOAD = 5 * 1024 * 1024
_SECTIONS = frozenset({"primary", "cloud", "archive"})
_QUALITY_RE = re.compile(r"^[A-Za-z0-9 +.\-]{0,16}$")
_RES_RE = re.compile(r"^(\d{1,5})[x×](\d{1,5})$", re.I)


def _json(data, status=200):
    return web.json_response(data, status=status)


def _clean(value, limit=300) -> str:
    """Control chars / NUL हटाओ — UI `textContent` और DB दोनों के लिए सुरक्षित।"""
    text = str(value or "").strip()
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)
    return text[:limit]


def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _parse_duration(value):
    """`1:36:22`, `14:48`, `600` (seconds) → int; गलत input → None."""
    t = str(value or "").strip()
    if not t:
        return 0
    if t.isdigit():
        return min(int(t), 10_000_000)
    parts = t.replace("：", ":").split(":")
    if len(parts) not in (2, 3) or any(not p.strip().isdigit() for p in parts):
        return None
    n = [int(p) for p in parts]
    secs = n[-1] + n[-2] * 60 + (n[-3] * 3600 if len(n) == 3 else 0)
    return min(secs, 10_000_000)


def _parse_res(value):
    """`1920×1080` / `1280x720` → (w, h); खाली → (0, 0); गलत → None."""
    t = str(value or "").strip().replace(" ", "")
    if not t:
        return 0, 0
    m = _RES_RE.match(t)
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    return (w, h) if w <= 8192 and h <= 8192 else None


def _is_image(raw: bytes) -> bool:
    return bool(raw) and (
        raw.startswith(b"\xff\xd8\xff")
        or raw.startswith(b"\x89PNG\r\n\x1a\n")
        or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    )


def _public_file(doc) -> dict:
    """`/search` के `_result()` जैसा safe projection + editor-only fields."""
    doc = doc or {}
    fid = str(doc.get("_id") or "")
    w = int(doc.get("width") or 0)
    h = int(doc.get("height") or 0)
    thumb_ref = str(doc.get("thumb_url") or doc.get("thumb_file_id") or "")
    v = thumb_version(fid, thumb_ref)
    return {
        "file_id": fid,
        "name": str(doc.get("file_name") or "Untitled"),
        "caption": str(doc.get("caption") or "")[:1000],
        "quality": str(doc.get("quality") or ""),
        "duration": _fmt_duration(doc.get("duration")),
        "duration_seconds": int(doc.get("duration") or 0),
        "res": f"{w}×{h}" if w and h else "",
        "width": w,
        "height": h,
        "size": get_size(doc.get("file_size") or 0),
        "section": str(doc.get("section") or "primary"),
        "thumb": f"/api/thumb?file_id={quote(fid, safe='')}&v={v}",
        "v": v,
        "custom_thumb": (
            str(doc.get("thumb_url") or "").startswith("TG_ID:")
            and str(doc.get("thumb_source") or "") == "web"
        ),
    }


async def _admin(req):
    role, _ = await get_auth(req)
    return role == "admin"


def _denied():
    return _json({"ok": False, "error": "Admins only"}, 403)


def _file_id(value) -> str:
    fid = str(value or "").strip()
    # Telegram file_ids + fsv1 short ids; URL/control chars reject
    return fid[:512] if re.fullmatch(r"[A-Za-z0-9_\-=]{1,512}", fid) else ""


# ───────────────────────── READ ─────────────────────────
@file_edit_routes.get("/api/file/meta")
async def api_file_meta(req):
    if not await _admin(req):
        return _denied()
    fid = _file_id(req.query.get("id"))
    if not fid:
        return _json({"ok": False, "error": "Invalid file id"}, 400)
    doc = await ia.get_file_meta(fid)
    if not doc:
        return _json({"ok": False, "error": "File not found"}, 404)
    return _json({"ok": True, "file": _public_file(doc)})


# ───────────────────────── EDIT ─────────────────────────
@file_edit_routes.post("/api/file/edit")
async def api_file_edit(req):
    if not await _admin(req):
        return _denied()
    try:
        data = await req.json()
    except Exception:
        return _json({"ok": False, "error": "Bad JSON"}, 400)
    fid = _file_id(data.get("file_id"))
    if not fid:
        return _json({"ok": False, "error": "Invalid file id"}, 400)

    name = _clean(data.get("name"), 300)
    if not name:
        return _json({"ok": False, "error": "File name खाली नहीं हो सकता"}, 400)
    quality = _clean(data.get("quality"), 16)
    if quality and not _QUALITY_RE.match(quality):
        return _json({"ok": False, "error": "Quality value गलत है"}, 400)
    section = str(data.get("section") or "primary").strip().lower()
    if section not in _SECTIONS:
        return _json({"ok": False, "error": "Unknown section"}, 400)
    duration = _parse_duration(data.get("duration"))
    if duration is None:
        return _json({"ok": False, "error": "Duration `H:MM:SS` में लिखें"}, 400)
    res = _parse_res(data.get("res"))
    if res is None:
        return _json({"ok": False, "error": "Resolution `1920×1080` में लिखें"}, 400)

    existing = await ia.get_file_meta(fid)
    if not existing:
        return _json({"ok": False, "error": "File not found"}, 404)

    fields = {
        "file_name": name,
        "caption": _clean(data.get("caption"), 1000),
        "quality": quality,
        "duration": duration,
        "width": res[0],
        "height": res[1],
        "section": section,
    }
    doc = await ia.update_file_fields(fid, fields)
    if not doc:
        return _json({"ok": False, "error": "Save नहीं हुआ"}, 500)
    return _json({"ok": True, "file": _public_file(doc)})


# ─────────────────── CUSTOM POSTER THUMBNAIL ───────────────
@file_edit_routes.post("/api/file/thumb")
async def api_file_thumb(req):
    if not await _admin(req):
        return _denied()
    try:
        data = await req.post()
        fid = _file_id(data.get("file_id"))
        part = data.get("image")
        raw = part.file.read() if part is not None and hasattr(part, "file") else b""
    except Exception as e:
        return _json({"ok": False, "error": f"Bad upload: {e}"}, 400)
    if not fid or not raw:
        return _json({"ok": False, "error": "file_id या image नहीं मिली"}, 400)
    if len(raw) > _MAX_UPLOAD or not _is_image(raw):
        return _json({"ok": False, "error": "सिर्फ़ JPG/PNG/WEBP, अधिकतम 5 MB"}, 400)

    doc = await ia.get_file_meta(fid)
    if not doc:
        return _json({"ok": False, "error": "File not found"}, 404)
    bot = getattr(temp, "BOT", None)
    if bot is None:
        return _json({"ok": False, "error": "Bot अभी ready नहीं"}, 503)

    try:
        buf = io.BytesIO(raw)
        buf.name = "poster.jpg"
        msg = await bot.send_photo(chat_id=_STORAGE_CHANNEL, photo=buf)
        photo = getattr(msg, "photo", None)
        sizes = getattr(photo, "sizes", None) if photo else None
        thumb_fid = sizes[-1].file_id if sizes else getattr(photo, "file_id", "")
    except Exception as e:
        logger.warning(f"file thumb upload failed: {e}")
        return _json({"ok": False, "error": "Telegram upload fail हुआ"}, 502)
    if not thumb_fid:
        return _json({"ok": False, "error": "Thumbnail file_id नहीं मिला"}, 502)

    thumb_ref = "TG_ID:" + str(thumb_fid)
    updated = await ia.update_file_fields(fid, {
        "thumb_url": thumb_ref,
        "thumb_file_id": str(thumb_fid),
        "thumb_source": "web",
        "is_thumb_permanent": True,
    })
    if not updated:
        return _json({"ok": False, "error": "Save नहीं हुआ"}, 500)
    invalidate_thumb(fid)     # पुराना in-flight download न लौटे
    out = _public_file(updated)
    return _json({"ok": True, "file": out, "thumb": out["thumb"], "v": out["v"]})


@file_edit_routes.post("/api/file/thumb_reset")
async def api_file_thumb_reset(req):
    """🔄 Custom poster हटाकर Telegram की original thumbnail दोबारा निकालो।"""
    if not await _admin(req):
        return _denied()
    try:
        data = await req.json()
    except Exception:
        return _json({"ok": False, "error": "Bad JSON"}, 400)
    fid = _file_id(data.get("file_id"))
    if not fid or not await ia.get_file_meta(fid):
        return _json({"ok": False, "error": "File not found"}, 404)
    updated = await ia.update_file_fields(fid, {
        "thumb_url": "", "thumb_file_id": "", "thumb_source": "",
        "is_thumb_permanent": False,
    })
    if not updated:
        return _json({"ok": False, "error": "Reset नहीं हुआ"}, 500)
    invalidate_thumb(fid)
    enqueue_probe(fid, force=True)     # serial queue — एक-एक करके, rate-limit safe
    out = _public_file(updated)
    return _json({"ok": True, "file": out, "thumb": out["thumb"],
                  "v": out["v"], "queued": True})


# ───────────────────────── DELETE ─────────────────────────
@file_edit_routes.post("/api/file/delete")
async def api_file_delete(req):
    if not await _admin(req):
        return _denied()
    try:
        data = await req.json()
    except Exception:
        return _json({"ok": False, "error": "Bad JSON"}, 400)
    fid = _file_id(data.get("file_id"))
    if not fid:
        return _json({"ok": False, "error": "Invalid file id"}, 400)
    if not await ia.delete_file_by_id(fid):
        return _json({"ok": False, "error": "File not found"}, 404)
    invalidate_thumb(fid)
    return _json({"ok": True, "deleted": fid})
