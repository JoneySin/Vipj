# web/__init__.py
#
# 🌐 WEB APP
#   stream_routes  → /, /watch/<id>, /download/<id> (signed + Range streaming)
#   auth_routes    → /login, /register, OTP, /logout (cookie sessions)
#   search_routes  → /search, /api/search, /api/thumb, /api/stream
#
# v5 जैसा web experience, पर fsv1 के पुराने bot links के अनुकूल।

from aiohttp import web

# ⚠️ नाम `_`-prefixed रखे हैं: वरना `web.search_routes` पैकेज attribute
# RouteTableDef से overwrite हो जाता है और `import web.search_routes` टूटता है।
from web.stream_routes import routes as _stream_routes
from web.auth_routes import auth_routes as _auth_routes
from web.search_routes import search_routes as _search_routes


def create_app():
    app = web.Application(client_max_size=100 * 1024 * 1024)

    app.add_routes(_stream_routes)
    app.add_routes(_auth_routes)
    app.add_routes(_search_routes)

    return app


web_app = create_app()
