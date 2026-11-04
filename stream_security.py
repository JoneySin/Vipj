"""🔐 Signed (HMAC) stream links.

The `/watch` and `/download` links created by the web UI (and the bot's /stream buttons)
carry `e` (expiry) + `s` (signature). Guessing a random message id therefore cannot
stream a file from BIN_CHANNEL.

Secret: the `STREAM_SECRET` env var (recommended); when it is missing, the value is
derived from `BOT_TOKEN`. Changing the secret invalidates every existing link immediately.
"""

import base64
import hashlib
import hmac
import time
from os import environ

from info import BOT_TOKEN

_SECRET = hashlib.sha256(
    b"fsv1-stream-link:" + (environ.get("STREAM_SECRET") or BOT_TOKEN).encode()
).digest()

USER_LINK_TTL = 24 * 3600          # links obtained from the Telegram bot (1 day)
STREAM_TTL = 6 * 3600              # "Play / Stream" links from web search (6 hours)
MAX_LINK_TTL = 365 * 24 * 3600     # upper limit for any custom link


def _sig(mid: int, exp: int) -> str:
    mac = hmac.new(_SECRET, f"{int(mid)}:{int(exp)}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:16]).decode().rstrip("=")


def sign_params(mid: int, ttl=STREAM_TTL) -> str:
    """Query string ``e=..&s=..``. ``ttl=None`` => never expires (e=0)."""
    if ttl is not None:
        ttl = max(60, min(int(ttl), MAX_LINK_TTL))
    exp = 0 if ttl is None else int(time.time()) + ttl
    return f"e={exp}&s={_sig(mid, exp)}"


def verify(mid: int, exp, sig) -> bool:
    try:
        exp = int(exp)
    except (TypeError, ValueError):
        return False
    if exp < 0 or (exp and exp < time.time()):
        return False
    return hmac.compare_digest(_sig(mid, exp), str(sig or ""))


# ======================================================================
# 🔁 LIVE SECRET (⚙️ /admin → Environment → STREAM_SECRET)
# ======================================================================

import logging as _logging

_log = _logging.getLogger(__name__)


def refresh_secret() -> bool:
    """`STREAM_SECRET` badla jaaye to naye secret se links banao.

    Purane links (jo purane secret se sign hue the) bina kisi warning ke expire ho jaate hain —
    panel confirm screen par yahi likha hai. `STREAM_SECRET` khaali = `BOT_TOKEN` se derive.
    """
    global _SECRET, USER_LINK_TTL, STREAM_TTL

    import info as _info

    secret = str(getattr(_info, "STREAM_SECRET", "") or "").strip()
    try:
        ttl_web = int(getattr(_info, "WEB_STREAM_TTL", STREAM_TTL))
    except (TypeError, ValueError):
        ttl_web = STREAM_TTL
    try:
        ttl_delete = int(getattr(_info, "PM_FILE_DELETE_TIME", USER_LINK_TTL))
    except (TypeError, ValueError):
        ttl_delete = USER_LINK_TTL

    _SECRET = hashlib.sha256(
        b"fsv1-stream-link:" + (secret or _info.BOT_TOKEN).encode()
    ).digest()
    # /watch + /download links free kiye jaate hain by default 6 ghante ke liye.
    # Agar admin `PM_FILE_DELETE_TIME` 6 ghante se zyada rakhta hai (file PM me itni der
    # rehti hai), to links ki umar bhi utni hi rakhni chahiye — warna file rahegi
    # par link mar jayega.
    STREAM_TTL = min(max(ttl_web, ttl_delete, 60), MAX_LINK_TTL)
    USER_LINK_TTL = STREAM_TTL
    _log.info(f"[stream] secret refreshed (ttl={STREAM_TTL}s)")
    return True
