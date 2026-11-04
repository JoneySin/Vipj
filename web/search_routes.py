"""🔍 Web file search + 📸 real thumbnails + ▶ signed streaming links.

Login के बाद `/search` पर:
  * `/api/search`  → DB (text + regex) search, "Recently Added" भी
  * `/api/thumb`   → असली Telegram thumbnail (cache + backfill)
  * `/api/stream`  → BIN_CHANNEL में cached media → signed /watch + /download link
"""

import html
import logging
import time
from urllib.parse import quote

from aiohttp import web

from info import (
    BIN_CHANNEL,
    MAX_WEB_RESULTS,
    WEB_STREAM_TTL,
    THUMB_BROWSER_CACHE,
)
from utils import temp, get_size
from database.ia_filterdb import (
    get_search_results,
    get_recent_files,
    get_file_details,
)
from web.group_routes import group_cards, filter_group_cards
from stream_security import sign_params
from web.web_assets import get_auth, search_page, vcard_meta
from web.thumb_engine import get_thumb, image_content_type, thumb_version, thumb_state

logger = logging.getLogger(__name__)
search_routes = web.RouteTableDef()

# file_id -> (BIN_CHANNEL message_id, expiry). Ek hi file par baar-baar
# click karne par nayi message na bhej kar purani signed link re-sign होती है।
_STREAM_CACHE = {}

# ── Group / UnGroup filter ─────────────────────────────────────────
# अब groups **permanent** हैं (`database/group_db.py`): DB में group_id/num,
# members, auto_keys, excluded. Title key भी उसी module में एक जगह से आती है,
# इसलिए search filter, scan-all और नई-quality auto-join एक ही नियम चलाते हैं।
# बड़े DB पर पूरा scan न हो इसलिए Group/UnGroup पेज पर अधिकतम इतने docs.
_GROUP_SCAN_LIMIT = 500


async def _group_page(q: str, offset: int, limit: int, mode: str):
    """Group / UnGroup — पेज = **cards**, group membership पूरे query set पर।

    सिर्फ़ file_name/_id/quality जैसा हल्का metadata पढ़ता है — कोई image
    bytes, कोई server-side thumbnail/RAM cache नहीं. Saved groups के सारे
    members `group_cards()` DB से लाता है, चाहे वे scan में न हों।
    """
    if q:
        scan, _, _ = await get_search_results(q, 0, _GROUP_SCAN_LIMIT)
    else:
        scan, _, _ = await get_recent_files(0, _GROUP_SCAN_LIMIT)
    cards = await group_cards([_result(d) for d in scan], normalize=_result)
    # Permanent group में अलग-अलग नाम की files हो सकती हैं → title-count से
    # नहीं, बल्कि तैयार group/single card से फ़िल्टर करो.
    matched = filter_group_cards(cards, mode)
    total = len(matched)
    page = matched[offset:offset + limit]
    next_offset = str(offset + limit) if offset + limit < total else ""
    return page, next_offset, total


def _thumb_url(doc) -> str:
    fid = str(doc.get("_id") or "")
    # v5 की तरह पूरे thumb_url ("TG_ID:...") का hash — ID बदले तो URL भी बदले
    thumb_ref = str(doc.get("thumb_url") or doc.get("thumb_file_id") or "")
    v = thumb_version(fid, thumb_ref)
    return f"/api/thumb?file_id={quote(fid, safe='')}&v={v}"


def _result(doc) -> dict:
    """🎴 card payload = shared `vcard_meta()` + इस page के extra fields."""
    out = vcard_meta(doc)
    out["thumb"] = _thumb_url(doc)
    out["caption"] = str(doc.get("caption") or "")[:300]
    return out


def _unauthorized():
    return web.json_response(
        {"error": "Login required", "login": "/login"}, status=401
    )


# ───────────────────────── PAGES ─────────────────────────
@search_routes.get("/search")
async def search_page_handler(req):
    role, tg_id = await get_auth(req)
    if not role:
        return web.HTTPFound("/login")
    return search_page(tg_id, role)


# ─────────────────────── SEARCH API ───────────────────────
@search_routes.get("/api/search")
async def api_search(req):
    role, tg_id = await get_auth(req)
    if not role:
        return _unauthorized()

    q = (req.query.get("q") or "").strip()
    try:
        offset = max(0, int(req.query.get("offset", "0")))
    except ValueError:
        offset = 0
    try:
        limit = max(1, min(int(req.query.get("limit", MAX_WEB_RESULTS)), MAX_WEB_RESULTS))
    except ValueError:
        limit = MAX_WEB_RESULTS

    group_mode = (req.query.get("group") or "all").strip().lower()
    if group_mode not in ("all", "group", "ungroup"):
        group_mode = "all"
    try:
        if group_mode != "all":
            # पहले से grouped cards (offset = card index)
            results, next_offset, total = await _group_page(q, offset, limit, group_mode)
        else:
            if q:
                docs, next_offset, total = await get_search_results(q, offset, limit)
            else:
                docs, next_offset, total = await get_recent_files(offset, limit)
            # 🎴 Permanent groups + same-title buckets → group-first cards.
            # Saved group के सारे members DB से आते हैं, offset raw-file रहता है.
            results = await group_cards([_result(d) for d in docs], normalize=_result)
    except Exception as e:
        logger.error(f"Web search failed (q={q!r}, group={group_mode}): {e}")
        return web.json_response({"error": "Search temporarily unavailable"}, status=500)

    return web.json_response({
        "results": results,
        "total": total,
        "next_offset": next_offset,
        "query": q,
        "group": group_mode,
        "is_admin": role == "admin",
    })


# ─────────────────────── THUMBNAIL API ───────────────────────
@search_routes.get("/api/thumb")
async def api_thumb(req):
    role, _ = await get_auth(req)
    if not role:
        return web.Response(status=401)

    fid = req.query.get("file_id", "")
    if not fid:
        return web.Response(status=400)
    retry = req.query.get("retry", "false").lower() == "true"

    # 🧠 Browser cache: server पर कोई RAM/DB cache नहीं। Poster ब्राउज़र की
    # अपनी memory/disk में रहेगा; `v` (thumb_url का hash) बदले तो ETag बदलेगा।
    etag = f'"{req.query.get("v") or thumb_version(fid)}"'
    cache_headers = {
        "Cache-Control": f"private, max-age={THUMB_BROWSER_CACHE}",
        "ETag": etag,
    }
    if req.headers.get("If-None-Match") == etag and not retry:
        return web.Response(status=304, headers=cache_headers)

    data = await get_thumb(fid, retry=retry)
    if not data:
        # 🆕 v5 जैसा serial warmup: पहली बार ID अभी निकल रही है (एक-एक करके)।
        # 404 cache न हो, browser को पता चले कि थोड़ी देर बाद retry करना है।
        state = await thumb_state(fid)
        headers = {"Cache-Control": "no-store", "X-Thumb-State": state}
        if state in ("queued", "missing"):
            headers["Retry-After"] = "2"
        return web.Response(status=404, headers=headers)

    return web.Response(
        body=data,
        content_type=image_content_type(data),
        headers={
            "Content-Disposition": 'inline; filename="poster.jpg"',
            **cache_headers,
        },
    )


# ──────────────────── STREAM LINK PIPELINE ────────────────────
def _prune_stream_cache():
    if len(_STREAM_CACHE) <= 500:
        return
    now = time.time()
    for k in [k for k, v in _STREAM_CACHE.items() if v[1] <= now]:
        _STREAM_CACHE.pop(k, None)
    while len(_STREAM_CACHE) > 500:
        _STREAM_CACHE.pop(next(iter(_STREAM_CACHE)), None)


async def _tunnel_stream(fid: str, doc: dict) -> dict:
    """BIN_CHANNEL में file भेजकर signed watch/download URLs बनाओ।"""
    now = time.time()
    hit = _STREAM_CACHE.get(fid)
    if hit and hit[1] > now + 60:
        msg_id, expiry = hit
    else:
        bot = getattr(temp, "BOT", None)
        if bot is None:
            raise RuntimeError("Bot is still starting, please retry in a moment")
        msg = await bot.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
        msg_id = int(msg.id)
        expiry = now + WEB_STREAM_TTL
        _STREAM_CACHE[fid] = (msg_id, expiry)
        _prune_stream_cache()

    ttl = max(60, int(expiry - now))
    signed = sign_params(msg_id, ttl)
    poster = _thumb_url(doc)
    watch = f"/watch/{msg_id}?{signed}&poster={quote(poster, safe='')}"
    download = f"/download/{msg_id}?{signed}"
    return {
        "file_id": fid,
        "name": str(doc.get("file_name") or "Untitled"),
        "watch": watch,
        "download": download,
        "stream": download,          # <video src> के लिए यही Range-enabled URL
        "poster": poster,
        "expires_in": ttl,
    }


@search_routes.post("/api/stream")
async def api_stream(req):
    role, _ = await get_auth(req)
    if not role:
        return _unauthorized()
    try:
        data = await req.json()
    except Exception:
        data = dict(req.query)
    fid = str(data.get("file_id") or "").strip()
    if not fid:
        return web.json_response({"error": "Missing file_id"}, status=400)

    doc = await get_file_details(fid)
    if not doc:
        return web.json_response({"error": "File not found in database"}, status=404)

    try:
        return web.json_response(await _tunnel_stream(fid, doc))
    except Exception as e:
        logger.error(f"Stream setup failed for {fid[:16]}: {e}")
        return web.json_response(
            {"error": "Stream link नहीं बन सकी। थोड़ी देर बाद फिर ट्राय करें।"},
            status=503,
        )


@search_routes.get("/setup_stream")
async def setup_stream(req):
    """/setup_stream?file_id=... — GET shortcut (v5-style shareable links)."""
    role, _ = await get_auth(req)
    if not role:
        return web.HTTPFound("/login")
    fid = str(req.query.get("file_id") or "").strip()
    doc = await get_file_details(fid) if fid else None
    if not doc:
        return web.Response(text="❌ File not found", status=404)
    try:
        urls = await _tunnel_stream(fid, doc)
    except Exception as e:
        return web.Response(text=f"❌ {html.escape(str(e))}", status=503)
    target = urls["download"] if req.query.get("mode") == "download" else urls["watch"]
    return web.HTTPFound(target)
