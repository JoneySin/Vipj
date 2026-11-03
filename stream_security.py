"""🔐 Signed (HMAC) stream links.

Web UI (aur bot ke /stream buttons) se banne wale /watch aur /download links
me `e` (expiry) + `s` (signature) hote hain. Isse koi bhi random message-id
guess karke BIN_CHANNEL ki file stream nahi kar sakta.

Secret: env ``STREAM_SECRET`` (recommended), nahi mila to ``BOT_TOKEN`` se
derive hota hai. Secret badalne par saare purane links turant band ho jaate hain.
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

USER_LINK_TTL = 24 * 3600          # Telegram bot se milne wali link (1 din)
STREAM_TTL = 6 * 3600              # web search ke "Play / Stream" links (6 ghante)
MAX_LINK_TTL = 365 * 24 * 3600     # kisi bhi custom link ki upper limit


def _sig(mid: int, exp: int) -> str:
    mac = hmac.new(_SECRET, f"{int(mid)}:{int(exp)}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:16]).decode().rstrip("=")


def sign_params(mid: int, ttl=STREAM_TTL) -> str:
    """Query string ``e=..&s=..``. ``ttl=None`` => kabhi expire nahi (e=0)."""
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
