# web/__init__.py
#
# 🌐 WEB APP
#   stream_routes  → /, /watch/<id>, /download/<id> (signed + Range streaming)
#   auth_routes    → /login, /register, OTP, /logout (cookie sessions)
#   search_routes  → /search, /api/search, /api/thumb, /api/stream
#   catalog_routes → /posts, /actors, /post/<id>, /actor/<id> + generic JSON API
#   stats_routes   → /stats, /api/db_stats (v5 जैसा "Database Stats")
#   profile_routes → /profile, /api/update_profile (v5 जैसा "Profile Settings")
#
# v5 जैसा web experience — sidebar (Home / Posts / Actors / Database Stats /
# Profile Settings / Sign Out), पर fsv1 के पुराने bot links के अनुकूल।
# Posts + Actors v5 की अलग-अलग 1400 lines की जगह एक shared catalog engine से।

from aiohttp import web

# ⚠️ नाम `_`-prefixed रखे हैं: वरना `web.search_routes` पैकेज attribute
# RouteTableDef से overwrite हो जाता है और `import web.search_routes` टूटता है।
from web.stream_routes import routes as _stream_routes
from web.auth_routes import auth_routes as _auth_routes
from web.search_routes import search_routes as _search_routes
from web.catalog_routes import catalog_routes as _catalog_routes
from web.stats_routes import stats_routes as _stats_routes
from web.profile_routes import profile_routes as _profile_routes


def create_app():
    app = web.Application(client_max_size=100 * 1024 * 1024)

    app.add_routes(_stream_routes)
    app.add_routes(_auth_routes)
    app.add_routes(_search_routes)
    app.add_routes(_catalog_routes)
    app.add_routes(_stats_routes)
    app.add_routes(_profile_routes)

    return app


web_app = create_app()
