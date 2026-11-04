"""⚙️ Runtime environment (settings) store.

`/admin` → ⚙️ Environment (ya PM me `/env`) se poora bot ka environment dekha aur
badla ja sakta hai — bool (`true/false`), number aur text.

Kaise kaam karta hai
--------------------
* `SPECS` — **ek hi jagah** par saare env ki list (naam, type, default, limits, hint).
* `env_manager.get(name)` — **abhi chal rahi** (effective) value. Code isi ko padhta hai,
  isliye badlav turant lagu hota hai — restart ki zaroorat nahi.
* `env_manager.set(name, raw)` — validate → MongoDB (`bot_env`) me save → live apply →
  `.env` file me mirror. Panel ka badlav restart ke baad bhi rehta hai (start par
  `load()` dobara apply kar deta hai) aur host env var ko override karta hai.
* `env_manager.reset(name)` — panel ka badlav hata kar host env / default par wapas.

Sirf wahi variables badle ja sakte hain jo `settable=True` hain (jaise `ADMINS`,
`API_ID`, `BOT_TOKEN`, `URL` — ye deployment ke hain, panel se nahi).
"""

import asyncio
import html
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import info

logger = logging.getLogger(__name__)

# `info.py` (aur `bot.py`) jis folder me hain — `.env` wahin likhi jaati hai
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")

# Bot start hote waqt host env me maujood keys (panel ka "env" source label)
BOOT_ENV_KEYS = set(os.environ)


# ======================================================================
# 🗂️ CATEGORIES
# ======================================================================

CATEGORIES: Dict[str, Tuple[str, str]] = {
    "secrets": ("🔐", "Secrets &amp; Access"),
    "bot": ("⚙️", "Bot &amp; Channels"),
    "premium": ("💎", "Premium"),
    "files": ("🎬", "Files &amp; Streaming"),
    "web": ("🌐", "Web"),
    "thumbs": ("🖼️", "Thumbnails"),
}
CATEGORY_ORDER = ["secrets", "bot", "premium", "files", "web", "thumbs"]


# ======================================================================
# 📋 SPECS — saare environment variables ki single source of truth
# ======================================================================

@dataclass(frozen=True)
class Spec:
    name: str
    kind: str                 # bool | int | float | text | list
    category: str
    label: str = ""           # chhota, insaani naam
    hint: str = ""            # kya karta hai (panel me dikhta hai)
    default: object = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Tuple[str, ...] = ()
    max_len: int = 300
    settable: bool = True     # panel se badla ja sakta hai?
    secret: bool = False      # value chhupani hai?
    boot: str = "env"         # env | auto  (auto = doosri env se banti hai)
    warn: str = ""            # confirm screen par warning

    @property
    def kind_label(self) -> str:
        return {"bool": "true / false", "int": "number", "float": "number",
                "text": "text", "list": "list"}[self.kind]


SPECS: Tuple[Spec, ...] = (
    # ---------------- 🔐 Secrets & Access ----------------
    Spec("API_ID", "int", "secrets", "Telegram API ID", "Host env se aata hai",
         settable=False, secret=True),
    Spec("API_HASH", "text", "secrets", "Telegram API hash", "Host env se aata hai",
         settable=False, secret=True),
    Spec("BOT_TOKEN", "text", "secrets", "Bot token", "Host env se aata hai",
         settable=False, secret=True),
    Spec("DATA_DATABASE_URL", "text", "secrets", "MongoDB URL",
         "Files / users / premium / env-overrides sabhi collections isi DB me",
         settable=False, secret=True),
    Spec("DATABASE_NAME", "text", "secrets", "Database name", "MongoDB database",
         default="bot_db", settable=False),
    Spec("COLLECTION_NAME", "text", "secrets", "Files collection", "Indexed files",
         default="files", settable=False),
    Spec("STREAM_SECRET", "text", "secrets", "Stream link secret",
         "`/watch` + `/download` links ki HMAC key. Khaali = BOT_TOKEN se banti hai.",
         settable=True, secret=True,
         warn="Badalne par purane saare stream/download links turant expire ho jaate hain."),

    # ---------------- ⚙️ Bot & Channels ----------------
    Spec("URL", "text", "bot", "Public URL", "Web app ka base URL",
         settable=False),
    Spec("PORT", "int", "bot", "Web port", "Host env se aata hai",
         default=80, settable=False),
    Spec("ADMINS", "list", "bot", "Admins",
         "`/admin` panel + admin commands sirf inhi IDs ke liye",
         settable=False),
    Spec("LOG_CHANNEL", "int", "bot", "Log channel", "Bot logs / actions yahan jaate hain",
         settable=False),
    Spec("BIN_CHANNEL", "int", "bot", "Bin channel", "Files isi channel se serve hote hain",
         settable=False),
    Spec("CATALOG_STORAGE_CHANNEL", "int", "bot", "Catalog storage channel",
         "Post/Actor covers. Khaali = BIN_CHANNEL.", boot="auto", settable=False),
    Spec("INDEX_CHANNELS", "list", "bot", "Index channels",
         "In channels ki files auto-index hoti hain", settable=False),
    Spec("INDEX_LOG_CHANNEL", "int", "bot", "Index log channel",
         "Khaali = LOG_CHANNEL", settable=False),
    Spec("ADMIN_MODE", "bool", "bot", "Admin mode",
         "OFF = admins ko file delivery/stream nahi milta aur rate-limit exemption hadata hai (maintenance). `/env` khud hamesha chalta rehta hai.",
         default=True,
         warn="OFF karne par admins files deliver nahi kar payenge (panel se turant wapas ON ho sakta hai)."),
    Spec("MAX_BTN", "int", "bot", "Default results", "Bot search me per-page results",
         default=8, min_value=1, max_value=50),
    Spec("USE_CAPTION_FILTER", "bool", "bot", "Search captions",
         "ON = caption ke text par bhi search", default=True),

    # ---------------- 💎 Premium ----------------
    Spec("IS_PREMIUM", "bool", "premium", "Premium system",
         "OFF = sabhi users ko free access (PM search + files). UPI_ID/UPI_NAME set na ho to khud OFF rehta hai.",
         default=True,
         warn="OFF karne par bina premium ke sabhi users files search/download kar sakenge."),
    Spec("PRE_DAY_AMOUNT", "int", "premium", "Price per day (₹)",
         "Premium pricing", default=10, min_value=1, max_value=100000),
    Spec("UPI_ID", "text", "premium", "UPI ID", "Payment ke liye", settable=True),
    Spec("UPI_NAME", "text", "premium", "UPI name", "Payment ke liye", settable=True),
    Spec("RECEIPT_SEND_USERNAME", "text", "premium", "Receipt username",
         "Payment screenshot kis ko bhejein", settable=True),

    # ---------------- 🎬 Files & Streaming ----------------
    Spec("IS_STREAM", "bool", "files", "Stream buttons",
         "ON = file ke saath \"▶️ Watch / Download\" button", default=True),
    Spec("PROTECT_CONTENT", "bool", "files", "Protect content",
         "ON = forward/save band (Telegram protect_content)", default=False),
    Spec("PM_FILE_DELETE_TIME", "int", "files", "File delete time (sec)",
         "PM me bheji file itne second baad delete", default=3600,
         min_value=30, max_value=604800),
    Spec("ALLOW_UNSIGNED_LINKS", "bool", "files", "Allow unsigned links",
         "ON = bina signature ke purane `/watch/<id>` links chalein",
         default=False,
         warn="OFF rakhna safe hai — ON karne par koi bhi message id se file stream kar sakta hai."),

    # ---------------- 🌐 Web ----------------
    Spec("WEB_SESSION_TTL", "int", "web", "Login cookie TTL (sec)",
         "Web login kitni der chale", default=7 * 24 * 3600,
         min_value=300, max_value=365 * 24 * 3600),
    Spec("WEB_STREAM_TTL", "int", "web", "Stream link TTL (sec)",
         "Web player link ki umar", default=6 * 3600,
         min_value=60, max_value=365 * 24 * 3600),
    Spec("MAX_WEB_RESULTS", "int", "web", "Results per page",
         "Web search page size (3×N grid)", default=21, min_value=1, max_value=100),

    # ---------------- 🖼️ Thumbnails ----------------
    Spec("THUMB_BROWSER_CACHE", "int", "thumbs", "Browser cache (sec)",
         "Poster browser cache max-age", default=7 * 24 * 3600,
         min_value=0, max_value=365 * 24 * 3600),
    Spec("THUMB_FETCH_CONCURRENCY", "int", "thumbs", "Download concurrency",
         "Ek saath kitne thumbnails (TG_ID wale)", default=6,
         min_value=1, max_value=20),
    Spec("THUMB_PROBE_GAP_MIN", "float", "thumbs", "Probe gap min (sec)",
         "First-time probe ke beech anti-flood gap", default=1.2,
         min_value=0, max_value=60),
    Spec("THUMB_PROBE_GAP_MAX", "float", "thumbs", "Probe gap max (sec)",
         "First-time probe ke beech anti-flood gap", default=3.0,
         min_value=0, max_value=60),
    Spec("THUMB_PROBE_ATTEMPTS", "int", "thumbs", "Probe attempts",
         "Per file max send_cached_media attempts", default=5,
         min_value=1, max_value=10),
    Spec("THUMB_FLOOD_EXTRA", "int", "thumbs", "FloodWait buffer (sec)",
         "Telegram ke FLOOD_WAIT me extra wait", default=10,
         min_value=0, max_value=600),
    Spec("THUMB_MIN_BYTES", "int", "thumbs", "Min thumb bytes",
         "Chhoti (fake) image reject", default=512,
         min_value=0, max_value=1048576),
    Spec("THUMB_MIN_DIM", "int", "thumbs", "Min thumb size (px)",
         "1×1 / 16×16 pixels reject", default=48,
         min_value=1, max_value=4096),
    Spec("THUMB_MIN_STDDEV", "float", "thumbs", "Min thumb variance",
         "Blank \"NO IMAGE\" card reject", default=6.0,
         min_value=0, max_value=100),
)

SPEC_MAP: Dict[str, Spec] = {s.name: s for s in SPECS}
SPEC_INDEX: Dict[str, int] = {s.name: i for i, s in enumerate(SPECS)}

# Panel reset ka aakhri fallback: code me define kiya gaya default
ENV_DEFAULTS: Dict[str, object] = {s.name: s.default for s in SPECS}


# ======================================================================
# 🧰 PARSING / VALIDATION
# ======================================================================

class EnvError(ValueError):
    """Invalid environment value (panel me friendly message dikhta hai)."""


_TRUE = {"true", "yes", "1", "enable", "enabled", "on", "y", "haan", "ha"}
_FALSE = {"false", "no", "0", "disable", "disabled", "off", "n", "nahi"}


def parse_bool(raw: str) -> bool:
    low = str(raw).strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    raise EnvError("Sirf <b>true</b> ya <b>false</b> bhejein (on/off, 1/0 bhi chalega).")


def _parse_number(spec: Spec, raw: str):
    text = str(raw).strip().replace(",", "").replace("_", "")
    try:
        value = int(text) if spec.kind == "int" else float(text)
    except ValueError:
        raise EnvError(f"{spec.name} ek {spec.kind_label} hai — jaise <code>"
                       f"{spec.default!r}</code>.")
    if spec.min_value is not None and value < spec.min_value:
        raise EnvError(f"{spec.name} kam se kam <code>{_num(spec.min_value)}</code> hona chahiye.")
    if spec.max_value is not None and value > spec.max_value:
        raise EnvError(f"{spec.name} zyada se zyada <code>{_num(spec.max_value)}</code> tak ho sakta hai.")
    return value


def _num(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def env_text(spec: Spec, value) -> str:
    """Value → woh text jo `.env` / env var me jaata hai."""
    if spec.kind == "bool":
        return "True" if value else "False"
    if spec.kind == "int":
        return str(int(value))
    if spec.kind == "float":
        return f"{float(value):g}"
    if spec.kind == "list":
        return " ".join(str(v) for v in (value or []))
    return str(value)


def parse_input(spec: Spec, raw: str):
    """Panel / command se aaya text → validated value."""
    text = "" if raw is None else str(raw).strip()

    # "KEEP" = purani (host env) value hi rakho — secrets ke liye
    if text.upper() == "KEEP":
        if not spec.secret:
            raise EnvError("`KEEP` sirf secret variables ke liye hai.")
        return BOOT_VALUES.get(spec.name, spec.default)

    if spec.kind == "bool":
        return parse_bool(text)
    if spec.kind in ("int", "float"):
        return _parse_number(spec, text)

    if spec.choices and text not in spec.choices:
        raise EnvError("Allowed: " + ", ".join(f"<code>{c}</code>" for c in spec.choices))
    if len(text) > spec.max_len:
        raise EnvError(f"Value {spec.max_len} characters se lambi hai.")
    return text


# ======================================================================
# 🖊️ STORE
# ======================================================================

class EnvManager:
    """MongoDB-backed override + live apply."""

    def __init__(self):
        self._override: Dict[str, object] = {}
        self._meta: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self.loaded = False
        self.last_error = ""

    # ---------------------------------------------------------------- read
    def get(self, name: str):
        """Effective value (panel override > info.py / host env > default)."""
        if name in self._override:
            return self._override[name]
        spec = SPEC_MAP.get(name)
        if spec is None:
            return None
        return getattr(info, name, spec.default)

    def has_override(self, name: str) -> bool:
        return name in self._override

    def meta(self, name: str) -> dict:
        return self._meta.get(name, {})

    def source(self, name: str) -> str:
        """`panel` | `auto` | `env` | `default`"""
        if name in self._override:
            return "panel"
        spec = SPEC_MAP.get(name)
        if spec is None:
            return "default"
        if spec.boot == "auto":
            return "auto"
        if name in BOOT_ENV_KEYS and os.environ.get(name, "").strip():
            return "env"
        return "default"

    def override_count(self) -> int:
        return len(self._override)

    # --------------------------------------------------------------- write
    async def ensure_loaded(self) -> bool:
        if self.loaded:
            return True
        async with self._lock:
            if self.loaded:
                return True
            await self._load_from_db()
            self.loaded = True
        return True

    async def _load_from_db(self) -> None:
        from database.users_chats_db import db          # late import (info ready)

        try:
            rows = await db.get_env_overrides()
        except Exception as e:                          # DB down ⇒ defaults hi chalenge
            self.last_error = str(e)
            logger.warning(f"[env] overrides load nahi hue: {e}")
            return

        for row in rows or []:
            name = row.get("_id")
            spec = SPEC_MAP.get(name)
            if spec is None or not spec.settable:
                continue
            try:
                value = parse_input(spec, row.get("value"))
            except EnvError as e:
                logger.warning(f"[env] {name} skip — {e}")
                continue
            self._override[name] = value
            self._meta[name] = {
                "by": row.get("by"),
                "updated_at": row.get("updated_at"),
                "history": row.get("history") or [],
            }
            self._apply(spec, value)

        if self._override:
            logger.info(f"[env] {len(self._override)} panel overrides applied: "
                        + ", ".join(sorted(self._override)))

    async def set(self, name: str, raw: str, by: int = 0,
                  old_text: str = "") -> Tuple[bool, str]:
        """Validate → DB → live apply → `.env`. Returns (ok, message)."""
        spec = SPEC_MAP.get(name)
        if spec is None:
            return False, f"❌ Unknown variable <code>{html.escape(name)}</code>"
        if not spec.settable:
            return False, (f"🔒 <code>{name}</code> deployment ka variable hai — "
                           "panel se nahi badal sakte.")

        await self.ensure_loaded()
        try:
            value = parse_input(spec, raw)
        except EnvError as e:
            return False, f"❌ {e}"

        stored = env_text(spec, value)
        async with self._lock:
            from database.users_chats_db import db
            try:
                await db.set_env_override(name, stored, by=by, old=old_text)
            except Exception as e:
                logger.error(f"[env] save fail {name}: {e}")
                return False, f"❌ Save nahi hua ({e}) — badlav cancel."

            self._override[name] = value
            self._meta[name] = {"by": by, "updated_at": time.time()}
            self._apply(spec, value)
            self._write_env_file()

        logger.info(f"[env] {name} = {'***' if spec.secret else stored} (admin {by})")
        return True, f"✅ <code>{name}</code> ab <b>{render_value(name)}</b> hai."

    async def reset(self, name: str) -> Tuple[bool, str]:
        """Panel override hatao → host env / default par wapas."""
        spec = SPEC_MAP.get(name)
        if spec is None:
            return False, f"❌ Unknown variable <code>{html.escape(name)}</code>"
        await self.ensure_loaded()
        async with self._lock:
            from database.users_chats_db import db
            try:
                await db.delete_env_override(name)
            except Exception as e:
                return False, f"❌ DB se delete nahi hua ({e})"

            self._override.pop(name, None)
            self._meta.pop(name, None)
            original = BOOT_VALUES.get(name, spec.default)
            self._apply(spec, original)
            self._write_env_file()

        return True, f"♻️ <code>{name}</code> default par set: <b>{render_value(name)}</b>"

    # ------------------------------------------------------------ internals
    def _apply(self, spec: Spec, value) -> None:
        """Live value: `info.<NAME>` patch (code isi ko padhta hai) + side effects."""
        try:
            setattr(info, spec.name, value)
        except Exception as e:
            logger.warning(f"[env] info.{spec.name} set nahi hua: {e}")
            return

        # --- live side effects (jo value import ke waqt cache karte hain) ---
        if spec.name == "IS_PREMIUM":
            try:
                from utils import temp
                temp.PREMIUM.clear()          # premium cache = stale, saaf karo
            except Exception:
                pass
        elif spec.name == "STREAM_SECRET":
            try:
                import stream_security
                stream_security.refresh_secret()
            except Exception:
                pass

    def _write_env_file(self) -> None:
        """Panel ki values `.env` me mirror ho jaati hain (gitignored)."""
        lines = [
            "# ⚙️ fsv1 — panel se set kiye gaye environment",
            f"# last write: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "# (bot start par MongoDB se bhi apply hote hain; delete karne se reset nahi hoga)",
        ]
        for name in sorted(self._override):
            spec = SPEC_MAP[name]
            if spec.secret and str(self._override[name]) == "":
                continue
            lines.append(f"{name}={env_text(spec, self._override[name])}")
        try:
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            logger.warning(f"[env] .env likhi nahi ja saki: {e}")

    # --------------------------------------------------------------- render
    def value_text(self, name: str) -> str:
        """Panel me dikhne wala (secret = masked) text."""
        spec = SPEC_MAP[name]
        value = self.get(name)
        if spec.secret:
            return mask_secret(name, value)
        return plain_text(spec, value)

    def source_label(self, name: str) -> str:
        return {"panel": "panel", "auto": "auto", "env": "env",
                "default": "default"}[self.source(name)]


# ----------------------------------------------------------------------
# 🖼️ display helpers
# ----------------------------------------------------------------------

def plain_text(spec: Spec, value) -> str:
    if spec.kind == "bool":
        return "True" if value else "False"
    if spec.kind == "list":
        items = list(value or [])
        return " ".join(str(v) for v in items) if items else "—"
    if spec.kind in ("int", "float"):
        return _num(value) if value is not None else "—"
    text = str(value or "")
    if not text:
        return "—"
    if spec.choices:
        return text
    return text


def mask_secret(name: str, value) -> str:
    """Secret ko itna hi dikhao jitna pehchaanne ke liye kaafi ho."""
    text = str(value or "")
    if not text:
        return "— (khaali)"
    if name == "DATA_DATABASE_URL":
        # mongodb+srv://user:pass@host/db → host tak hi dikhao
        rest = text.split("://", 1)[-1]
        host = rest.split("@", 1)[-1]
        return f"mongodb://***@{host}"
    if name in ("API_HASH", "BOT_TOKEN", "STREAM_SECRET"):
        if len(text) <= 10:
            return "•" * len(text)
        return f"{text[:4]}…{text[-4:]}"
    if name == "API_ID":
        return str(text)
    return "••••••••"


def render_value(name: str) -> str:
    """HTML-escaped value text (message ke liye)."""
    spec = SPEC_MAP.get(name)
    if spec is None:
        return "—"
    return html.escape(env_manager.value_text(name))


# ======================================================================
# 🌍 GLOBAL INSTANCE
# ======================================================================

env_manager = EnvManager()

# Bot start hote waqt `info` me maujood values (host env / code default).
# `KEEP` aur `reset()` isi par wapas jaate hain; `info.py` ke end se bharta hai.
BOOT_VALUES: Dict[str, object] = dict(ENV_DEFAULTS)


def info_ready() -> None:
    """`info.py` ke end se call hota hai — tab values asli hain."""
    global BOOT_VALUES
    BOOT_VALUES = {s.name: getattr(info, s.name, s.default) for s in SPECS}


