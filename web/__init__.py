# web/__init__.py

from aiohttp import web
from web.stream_routes import routes


# ======================================================
# 🌐 WEB APP
# ======================================================

def create_app():
    app = web.Application()

    # routes
    app.add_routes(routes)

    return app


web_app = create_app()
