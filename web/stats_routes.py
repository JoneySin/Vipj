"""📊 Database Stats — JoneySin/v5 के `web/stats_routes.py` जैसा stats page.

* v5 की तरह sidebar में "Database Stats" admin-only लिंक, cards में counters.
* पहले `/search` की meta लाइन में "🆕 Recently Added — N files" जो गिनती
  दिखती थी, अब यहीं "Database Stats" में दिखती है (वही `get_recent_files()`
  वाला total — कोई नया/अलग count नहीं)।
* fsv1 के PyMongo (sync) helpers `asyncio.to_thread()` से चलते हैं ताकि
  bot का event loop block न हो।
"""

import asyncio
import logging
import time

from aiohttp import web

from info import PORT
from utils import temp
from database.ia_filterdb import db_count_documents, get_recent_files, collection
from database.users_chats_db import db as user_db, web_db
from web.web_assets import get_auth, app_page

logger = logging.getLogger(__name__)
stats_routes = web.RouteTableDef()


# v5 के stats JS जैसा count-up animation
_STATS_JS = """<script>
(function(){
  function countUp(el, target, duration){
    var start=performance.now();
    requestAnimationFrame(function step(now){
      var p=Math.min((now-start)/duration,1);
      el.textContent=Math.floor((1-Math.pow(1-p,3))*target).toLocaleString('en-IN');
      if(p<1)requestAnimationFrame(step);
    });
  }
  document.querySelectorAll('[data-count]').forEach(function(el){
    setTimeout(function(){countUp(el, parseFloat(el.dataset.count), 900);},
               parseFloat(el.dataset.delay||'0'));
  });
  document.querySelectorAll('.anim-card').forEach(function(el,i){
    el.style.animationDelay=(i*0.07)+'s';
  });
})();
</script>"""


async def _safe(awaitable, default):
    """एक DB counter fail हो तो पूरा stats पेज न गिरे (v5 जैसा fail-safe)।"""
    try:
        return await awaitable
    except Exception as e:
        logger.debug(f"Stats counter skipped: {e}")
        return default


def _count(coll, query=None) -> int:
    if coll is None:
        return 0
    return coll.count_documents(query or {})


async def _stats_numbers():
    """ek hi jagah se saare counters — page aur /api/db_stats dono यहीं से।"""
    total_files = await _safe(asyncio.to_thread(db_count_documents), 0)

    # 🆕 वही "Recently Added" count जो पहले search page की meta लाइन में था:
    # get_recent_files() का `total` = Recently Added grid में कुल फाइलें।
    _, _, recent_files = await _safe(get_recent_files(0, 1), ([], "", 0))
    recent_files = recent_files or total_files

    bot_users = await _safe(user_db.total_users_count(), 0)
    premium_users = len(await _safe(user_db.get_premium_users(), []))
    web_accounts = await _safe(asyncio.to_thread(_count, web_db.col), 0)
    thumbnails = await _safe(
        asyncio.to_thread(_count, collection, {"thumb_url": {"$exists": True}}), 0
    )
    return {
        "total_files": total_files,
        "recent_files": recent_files,
        "bot_users": bot_users,
        "premium_users": premium_users,
        "web_accounts": web_accounts,
        "thumbnails": thumbnails,
    }


def _uptime() -> str:
    started = getattr(temp, "START_TIME", 0) or 0
    if not started:
        return "Starting…"
    secs = max(0, int(time.time() - started))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"


@stats_routes.get("/stats")
async def stats_page(req):
    role, tg_id = await get_auth(req)
    if not role:
        return web.HTTPFound("/login")
    # v5 में "Database Stats" tab सिर्फ़ admin को दिखता है
    if role != "admin":
        return web.HTTPFound("/search")

    s = await _stats_numbers()

    body = f'''<div class="main" style="padding-top:36px;">
  <div class="stat-title anim-card">📊 Database Stats</div>
  <div class="stat-lead anim-card">v5 जैसा database overview — "Recently Added" फाइलों की गिनती अब यहीं दिखती है, search पेज की meta लाइन में नहीं।</div>

  <div class="stat-hero anim-card">
    <div class="stat-hero-label">🆕 Recently Added Files</div>
    <div class="stat-hero-num" data-count="{s['recent_files']}" data-delay="0">{s['recent_files']:,}</div>
    <div class="stat-hero-sub">खाली search पर "Recently Added" grid में मौजूद कुल फाइलें · <a href="/search" style="color:var(--red)">Home / Search →</a></div>
  </div>

  <div class="stat-grid">
    <div class="st-card anim-card"><div class="st-bar" style="background:#3399ff"></div>
      <div class="st-label">Total Files in Database</div>
      <div class="st-val" style="color:#3399ff" data-count="{s['total_files']}" data-delay="100">{s['total_files']:,}</div>
      <div class="st-sub">Indexed media documents</div></div>

    <div class="st-card anim-card"><div class="st-bar" style="background:#9933ff"></div>
      <div class="st-label">🖼️ Cached Thumbnails</div>
      <div class="st-val" style="color:#9933ff" data-count="{s['thumbnails']}" data-delay="160">{s['thumbnails']:,}</div>
      <div class="st-sub">Files with a Telegram poster reference</div></div>

    <div class="st-card anim-card"><div class="st-bar" style="background:#00d2c4"></div>
      <div class="st-label">🌐 Web Accounts</div>
      <div class="st-val" style="color:#00d2c4" data-count="{s['web_accounts']}" data-delay="220">{s['web_accounts']:,}</div>
      <div class="st-sub">Registered email logins</div></div>

    <div class="st-card anim-card"><div class="st-bar" style="background:#ff9933"></div>
      <div class="st-label">🤖 Bot Users</div>
      <div class="st-val" style="color:#ff9933" data-count="{s['bot_users']}" data-delay="280">{s['bot_users']:,}</div>
      <div class="st-sub">Active database records</div></div>

    <div class="st-card anim-card"><div class="st-bar" style="background:var(--gold)"></div>
      <div class="st-label">💎 Premium Users</div>
      <div class="st-val" style="color:var(--gold)" data-count="{s['premium_users']}" data-delay="340">{s['premium_users']:,}</div>
      <div class="st-sub">Active premium plans</div></div>

    <div class="st-card anim-card"><div class="st-bar" style="background:#28a745"></div>
      <div class="st-label">🟢 Server Uptime</div>
      <div class="st-val" style="color:#28a745;font-size:22px">{_uptime()}</div>
      <div class="st-sub">Port {PORT} · worker operational</div></div>
  </div>
</div>{_STATS_JS}'''

    return app_page(
        "Database Stats - Fast Finder", body,
        tg_id=tg_id, role=role, active_tab="stats",
    )


@stats_routes.get("/api/db_stats")
async def api_db_stats(req):
    """JSON counters — v5 के /api/db_stats जैसा हल्का endpoint."""
    role, _ = await get_auth(req)
    if not role:
        return web.json_response({"error": "Login required", "login": "/login"}, status=401)
    if role != "admin":
        return web.json_response({"error": "Admins only"}, status=403)
    return web.json_response(await _stats_numbers())
