"""⚙️ /admin → Environment — poore bot ka environment PM se dekho aur badlo.

Kya milta hai
-------------
* `/admin` panel me **⚙️ Environment** button (dashboard ke saath hi).
* PM me `/env` — same panel, par text ke roop me:
      /env                  → panel (buttons)
      /env all              → saare variables ek saath (value + source)
      /env get IS_PREMIUM   → ek variable ki detail
      /env set IS_PREMIUM false
      /env reset IS_PREMIUM
* Har value **turant** live hoti hai (restart nahi), MongoDB me save hoti hai aur
  `.env` me mirror hoti hai — isliye restart / redeploy ke baad bhi bani rehti hai.
* Secrets (BOT_TOKEN, API_HASH, DATA_DATABASE_URL) sirf masked dikhte hain aur
  panel se badle nahi ja sakte; deployment ke vars (ADMINS, BIN_CHANNEL, URL …) bhi read-only.

Boolean badalne ka tareeqa: variable kholo → **✅ Set True / ❌ Set False** →
confirm → Apply. Ya seedha `/env set IS_PREMIUM false`.
"""

import html
import time
import logging
from datetime import datetime

from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from hydrogram.errors import ListenerTimeout, MessageNotModified, MessageIdInvalid

from info import ADMINS
from env_store import (
    CATEGORIES,
    CATEGORY_ORDER,
    SPECS,
    SPEC_MAP,
    EnvError,
    env_manager,
    env_text,
    mask_secret,
    parse_input,
    plain_text,
)
from utils import temp

logger = logging.getLogger(__name__)

# ======================================================
# 🧠 STATE (RAM only)
# ======================================================

INPUT_TIMEOUT = 5 * 60           # text input ka intezaar
PENDING_TTL = 5 * 60             # confirm screen ka token
MAX_TEXT = 3800                  # ek Telegram message ke andar


def _state(name, default):
    if not hasattr(temp, name):
        setattr(temp, name, default)
    return getattr(temp, name)


# ======================================================
# 🛡 HELPERS
# ======================================================

def _is_admin(user_id) -> bool:
    return bool(user_id) and user_id in ADMINS


async def safe_answer(query, text="", alert=False):
    try:
        await query.answer(text or None, show_alert=alert)
    except Exception:
        pass


async def show(msg, text, markup=None):
    """Edit (ya naya bhej) — panel button dabane par message edit hota hai."""
    if msg is None:
        return msg
    try:
        return await msg.edit(
            text, reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except (MessageNotModified, MessageIdInvalid):
        return msg
    except Exception as e:
        logger.debug(f"[env] edit failed ({type(e).__name__}) → naya message")
    try:
        return await msg.reply(
            text, reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"[env] panel send failed: {e}")
        return msg


def ago(ts) -> str:
    if not ts:
        return "?"
    try:
        d = max(0, int(time.time() - float(ts)))
    except (TypeError, ValueError):
        return "?"
    if d < 60:
        return f"{d}s pehle"
    if d < 3600:
        return f"{d // 60}m pehle"
    if d < 86400:
        return f"{d // 3600}h pehle"
    return f"{d // 86400}d pehle"


def dot(spec) -> str:
    if not spec.settable:
        return "🔒"
    if spec.kind == "bool":
        return "🟢" if env_manager.get(spec.name) else "🔴"
    return "🔧"


def shown(spec) -> str:
    """Screen par dikhne wala value (secrets masked)."""
    value = env_manager.get(spec.name)
    if spec.secret:
        return mask_secret(spec.name, value)
    return plain_text(spec, value)


def short(text, limit=38) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def esc(text) -> str:
    return html.escape(str(text))


def src_badge(name) -> str:
    src = env_manager.source(name)
    if src == "panel":
        meta = env_manager.meta(name)
        by = f" · admin {meta['by']}" if meta.get("by") else ""
        return f"📝 <i>panel{by} · {ago(meta.get('updated_at'))}</i>"
    if src == "auto":
        return "⚙️ <i>auto (doosri env se)</i>"
    if src == "env":
        return "☁️ <i>host env</i>"
    return "◻️ <i>default</i>"


def btn(text, data) -> InlineKeyboardButton:
    return InlineKeyboardButton(text[:64], callback_data=data[:64])


def close_btn() -> InlineKeyboardButton:
    return btn("❌ Close", "close_data")


def group_title(key) -> str:
    icon, title = CATEGORIES.get(key, ("📦", key))
    return f"{icon} {title}"


def specs_in(key):
    return [s for s in SPECS if s.category == key]


# ======================================================
# 🧾 TEXT BUILDERS
# ======================================================

def index_text() -> str:
    overrides = [n for n in SPEC_MAP if env_manager.has_override(n)]
    settable = [s for s in SPECS if s.settable]
    locked = len(SPECS) - len(settable)

    lines = [
        "⚙️ <b>ENVIRONMENT MANAGER</b>",
        "",
        "<i>Bot ka poora environment — yahin se dekho aur badlo.</i>",
        "<i>Badlav turant live hota hai, restart ki zaroorat nahi.</i>",
        "",
        f"🗂 <b>Variables</b> : <code>{len(SPECS)}</code>  "
        f"(✏️ settable <code>{len(settable)}</code> · 🔒 locked <code>{locked}</code>)",
        f"📝 <b>Panel overrides</b> : <code>{len(overrides)}</code>"
        + (f" → {esc(', '.join(sorted(overrides)[:6]))}" if overrides else ""),
        f"🛠 <b>Admin mode</b> : {'✅ ON' if env_manager.get('ADMIN_MODE') else '⛔️ OFF'}",
        f"💎 <b>Premium</b> : {'ON' if env_manager.get('IS_PREMIUM') else 'OFF (sab free)'}",
        "",
        "Ek group kholiye, ya PM me <code>/env all</code> bhejiye:",
    ]
    return "\n".join(lines)


def index_buttons(page: int = 0) -> InlineKeyboardMarkup:
    rows = []
    for key in CATEGORY_ORDER:
        items = specs_in(key)
        mark = "📝 " if any(env_manager.has_override(s.name) for s in items) else ""
        rows.append([btn(f"{group_title(key)}  {mark}{len(items)}", f"env_cat:{key}:0")])
    rows.append([
        btn("📋 Poora env (text)", "env_all:"),
        btn("🔄 Refresh", "envhome"),
    ])
    rows.append([close_btn()])
    return InlineKeyboardMarkup(rows)


def category_page(key: str, page: int = 0):
    items = specs_in(key)
    if not items:
        return "❌ Group khaali hai.", InlineKeyboardMarkup([[btn("🔙 Groups", "envhome")]])

    per_page = 6
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(int(page), pages - 1))
    chunk = items[page * per_page: (page + 1) * per_page]

    lines = [
        f"{group_title(key)}   <i>({page + 1}/{pages})</i>",
        "",
        "<i>Variable par tap karke value badliye.</i>",
        "",
    ]
    for spec in chunk:
        lines.append(
            f"{dot(spec)} <code>{spec.name}</code> = <b>{esc(short(shown(spec), 34))}</b>  {src_badge(spec.name)}"
        )
        if spec.hint:
            lines.append(f"     <i>{esc(short(spec.hint, 70))}</i>")
    if not any(s.settable for s in chunk):
        lines.append("\n🔒 <i>Is group ke variables deployment ke hain — read-only.</i>")

    rows = [[btn(f"{dot(s)} {s.name}", f"env_set:{s.name}:{page}")] for s in chunk]

    nav = []
    if pages > 1:
        nav.append(btn("◀️", f"env_cat:{key}:{max(0, page - 1)}"))
        nav.append(btn(f"{page + 1}/{pages}", f"env_cat:{key}:{page}"))
        nav.append(btn("▶️", f"env_cat:{key}:{min(pages - 1, page + 1)}"))
        rows.append(nav)
    rows.append([btn("🔄 Refresh", f"env_cat:{key}:{page}")])
    rows.append([btn("🔙 Groups", "envhome"), close_btn()])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def var_page(name: str, page: int = 0, note: str = ""):
    spec = SPEC_MAP[name]
    value = env_manager.get(name)
    shown_value = mask_secret(name, value) if spec.secret else plain_text(spec, value)

    lines = [f"⚙️ <b>{spec.name}</b>", f"<i>{esc(spec.label)}</i>", ""]
    if note:
        lines += [note, ""]
    lines += [
        f"Current : <b>{esc(short(shown_value, 120))}</b>",
        f"Source  : {src_badge(name)}",
        f"Type    : <code>{spec.kind_label}</code>",
    ]
    if spec.kind != "bool" and not spec.secret:
        lines.append(f"Default : <code>{esc(short(plain_text(spec, _info_default(name)), 60))}</code>")
    if spec.min_value is not None or spec.max_value is not None:
        lo = "—" if spec.min_value is None else spec.min_value
        hi = "—" if spec.max_value is None else spec.max_value
        lines.append(f"Range   : <code>{esc(lo)} … {esc(hi)}</code>")
    if spec.secret:
        lines.append("<i>🔐 Secret — sirf shuruaat/aakhir dikhta hai.</i>")
    if spec.warn:
        lines += ["", f"⚠️ <i>{esc(spec.warn)}</i>"]
    if spec.hint:
        lines += ["", f"ℹ️ <i>{esc(spec.hint)}</i>"]

    rows = []
    if not spec.settable:
        lines += ["", "🔒 <b>Read-only</b> — ye value deployment (host env) se aati hai."]
        rows.append([btn("🔙 Back", f"env_cat:{spec.category}:{page}")])
        rows.append([close_btn()])
        return "\n".join(lines), InlineKeyboardMarkup(rows)

    if spec.kind == "bool":
        lines += ["", "<i>Naya value chuniye — phir confirm karna hoga.</i>"]
        rows.append([
            btn("✅ Set True", f"env_val:{name}:True:{page}"),
            btn("❌ Set False", f"env_val:{name}:False:{page}"),
        ])
    else:
        lines += ["", "<i>✏️ Change dabakar naya value bhejiye (ya <code>/env set "
                    f"{name} &lt;value&gt;</code>).</i>"]
        rows.append([btn("✏️ Change", f"env_edit:{name}:{page}")])
        if spec.kind == "text" and str(value or "").strip():
            rows.append([btn("🧹 Clear (khaali karo)", f"env_val:{name}::" + f"{page}")])

    if env_manager.has_override(name):
        rows.append([btn("♻️ Reset (default par)", f"env_reset:{name}:{page}")])
    rows.append([btn("🔙 Back", f"env_cat:{spec.category}:{page}"), close_btn()])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _info_default(name):
    from env_store import BOOT_VALUES, ENV_DEFAULTS
    return BOOT_VALUES.get(name, ENV_DEFAULTS.get(name, ""))


def new_token(name: str, raw_value: str, page: int) -> str:
    """Confirm screen ke liye chhota token (callback_data 64-byte limit)."""
    pending = _state("ENV_PENDING", {})
    now = time.time()
    # purane tokens saaf karo (warna dict badhti rahegi)
    for k, v in list(pending.items()):
        if now - v.get("at", 0) > PENDING_TTL:
            pending.pop(k, None)
    token = f"{int(now * 1000) % 100000:05d}{len(pending) % 10}"
    pending[token] = {"name": name, "value": raw_value, "page": page, "at": now}
    return token


def confirm_page(name: str, raw_value: str, page: int):
    spec = SPEC_MAP[name]
    try:
        value = parse_input(spec, raw_value)
        error = ""
    except EnvError as e:
        value, error = None, str(e)

    if error:
        lines = [f"❌ <b>{spec.name}</b> — {error}", "", "Dobara koshish kariye:"]
        rows = [[btn("🔙 Back", f"env_set:{name}:{page}")], [close_btn()]]
        return "\n".join(lines), InlineKeyboardMarkup(rows)

    new_text = mask_secret(name, value) if spec.secret else plain_text(spec, value)
    old_text = mask_secret(name, env_manager.get(name)) if spec.secret \
        else plain_text(spec, env_manager.get(name))

    lines = [
        "⚠️ <b>CONFIRM CHANGE</b>",
        "",
        f"Variable : <code>{spec.name}</code>",
        f"Current  : <b>{esc(short(old_text, 90))}</b>",
        f"New      : <b>{esc(short(new_text, 90))}</b>",
        f"Source   : {src_badge(name)}",
    ]
    if spec.warn:
        lines += ["", f"⚠️ <i>{esc(spec.warn)}</i>"]
    lines += ["", "<i>Apply dabane par turant lagu hoga (restart nahi).</i>"]

    token = new_token(name, raw_value, page)
    rows = [
        [btn("✅ Apply", f"env_apply:{token}"), btn("❌ Cancel", f"env_set:{name}:{page}")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ======================================================
# 📤 FULL ENV (text) — /env all
# ======================================================

def full_env_chunks(include_locked=True) -> list:
    lines = [
        "⚙️ <b>FULL ENVIRONMENT</b>",
        f"<i>{datetime.utcnow().strftime('%d %b %Y, %H:%M')} UTC · "
        f"{env_manager.override_count()} panel override</i>",
        "<i>Change: <code>/env set NAME VALUE</code></i>",
    ]
    for key in CATEGORY_ORDER:
        items = [s for s in specs_in(key) if include_locked or s.settable]
        if not items:
            continue
        lines += ["", f"<b>{group_title(key)}</b>"]
        for spec in items:
            lines.append(
                f"{dot(spec)} <code>{spec.name}</code> = "
                f"<b>{esc(short(shown(spec), 46))}</b>  <i>({env_manager.source(spec.name)})</i>"
            )

    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_TEXT:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def env_text_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn("⚙️ Panel", "envhome"), btn("🔄 Refresh", "env_all:")],
        [close_btn()],
    ])


# ======================================================
# 🚀 /admin → ⚙️ Environment (shared entry)
# ======================================================

async def send_index(bot, query, toast="⚙️ Environment panel"):
    text = index_text()
    await show(query.message, text, index_buttons())
    await safe_answer(query, toast)


# ======================================================
# 🔌 ENV PANEL CALLBACKS
# ======================================================

@Client.on_callback_query(filters.regex(r"^env(home$|_|all:)"))
async def env_callbacks(bot, query: CallbackQuery):
    if not _is_admin(query.from_user.id):
        return await safe_answer(query, "❌ Admins only", True)

    # panel purana hai (bot restart hua → pending tokens gaye)
    data = query.data or ""

    if data == "envhome":
        await show(query.message, index_text(), index_buttons())
        return await safe_answer(query, "🔄 Refreshed")

    if data.startswith("env_all:"):
        chunks = full_env_chunks()
        await safe_answer(query, f"📋 {len(chunks)} message(s)")
        for i, chunk in enumerate(chunks):
            markup = env_text_buttons() if i == len(chunks) - 1 else None
            try:
                if i == 0:
                    await query.message.edit(
                        chunk, reply_markup=markup,
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                else:
                    await query.message.reply(
                        chunk, reply_markup=markup,
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
            except Exception:
                pass
        return

    parts = data.split(":")
    action = parts[0]

    # ─── group page ───
    if action == "env_cat":
        key = parts[1] if len(parts) > 1 else "bot"
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        text, markup = category_page(key, page)
        await show(query.message, text, markup)
        return await safe_answer(query)

    # ─── ek variable ───
    if action == "env_set":
        name, page = parts[1], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        if name not in SPEC_MAP:
            return await safe_answer(query, "❌ Unknown variable", True)
        text, markup = var_page(name, page)
        await show(query.message, text, markup)
        return await safe_answer(query)

    # ─── bool value / clear → confirm ───
    if action == "env_val":
        name = parts[1]
        page = int(parts[-1]) if parts[-1].isdigit() else 0
        raw = ":".join(parts[2:-1]) if len(parts) > 3 else ""
        if name not in SPEC_MAP:
            return await safe_answer(query, "❌ Unknown variable", True)
        text, markup = confirm_page(name, raw, page)
        await show(query.message, text, markup)
        return await safe_answer(query, "Confirm kariye")

    # ─── text input maango ───
    if action == "env_edit":
        name = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        if name not in SPEC_MAP:
            return await safe_answer(query, "❌ Unknown variable", True)
        await safe_answer(query)
        return await ask_value(bot, query.message, name, page, reply_to=query.message)

    # ─── confirm → apply ───
    if action == "env_apply":
        token = parts[1] if len(parts) > 1 else ""
        pending = _state("ENV_PENDING", {})
        item = pending.pop(token, None)
        if not item:
            return await safe_answer(query, "⌛️ Purana panel — dobara kholiye", True)
        name, raw, page = item["name"], item["value"], item["page"]
        spec = SPEC_MAP[name]
        old_raw = env_text(spec, env_manager.get(name))
        ok, message = await env_manager.set(
            name, raw, by=query.from_user.id, old_text=old_raw
        )
        text, markup = var_page(name, page, note=message)
        await show(query.message, text, markup)
        await safe_answer(query, "✅ Applied" if ok else "❌ Failed", alert=not ok)
        if ok:
            await log_change(bot, query.from_user, name, raw, old=old_raw)
        return

    # ─── reset ───
    if action == "env_reset":
        name = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        if name not in SPEC_MAP:
            return await safe_answer(query, "❌ Unknown variable", True)
        old_raw = env_text(SPEC_MAP[name], env_manager.get(name))
        ok, message = await env_manager.reset(name)
        text, markup = var_page(name, page, note=message)
        await show(query.message, text, markup)
        await safe_answer(query, "♻️ Reset" if ok else "❌ Failed", alert=not ok)
        if ok:
            await log_change(bot, query.from_user, name, "RESET", old=old_raw)
        return

    await safe_answer(query)


async def log_change(bot, user, name, raw, old=None):
    """Admin actions LOG_CHANNEL me — audit trail."""
    from info import LOG_CHANNEL
    spec = SPEC_MAP.get(name)
    if not spec or not LOG_CHANNEL:
        return
    value = "♻️ reset (default)" if raw == "RESET" else (
        "•••" if spec.secret else esc(raw))
    old_text = "" if old is None else (
        "•••" if spec.secret else esc(old))
    try:
        await bot.send_message(
            LOG_CHANNEL,
            "⚙️ <b>Environment changed</b>\n\n"
            f"👤 Admin: {esc(getattr(user, 'first_name', '') or '')} "
            f"(<code>{getattr(user, 'id', '')}</code>)\n"
            f"🔧 Var: <code>{name}</code>\n"
            + (f"⬅️ Purana: <b>{old_text}</b>\n" if old_text else "")
            + f"➡️ Value: <b>{value}</b>\n"
            f"🕒 {datetime.utcnow().strftime('%d %b %Y, %I:%M %p')} UTC",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        pass


# ======================================================
# ⌨️ VALUE INPUT (button se "Change")
# ======================================================

async def ask_value(bot, message, name, page=0, reply_to=None):
    spec = SPEC_MAP[name]
    hint = {
        "bool": "<code>true</code> / <code>false</code>",
        "int": "ek number (jaise <code>8</code>)",
        "float": "ek decimal number (jaise <code>1.2</code>)",
    }.get(spec.kind, "naya text")

    prompt = (
        f"✏️ <b>{name}</b> ka naya value bhejiye — {hint}\n\n"
        f"Current: <b>{esc(short(shown(spec), 80))}</b>\n"
        f"<i>{INPUT_TIMEOUT // 60} minute tak intezaar. Cancel: /cancel_env</i>\n\n"
        "<i>Bheja hua message main delete kar dunga.</i>"
    )
    keyboard = InlineKeyboardMarkup([
        [btn("🔙 Cancel", f"env_set:{name}:{page}")],
    ])
    target = reply_to or message
    try:
        await target.reply(prompt, reply_markup=keyboard,
                           parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.debug(f"[env] prompt failed: {e}")
        return

    chat_id = target.chat.id

    async def _stop_old():
        """Purana adhoorta input listener (agar pehle kabhi reh gaya ho)."""
        fn = getattr(bot, "stop_listening", None)
        if not fn:
            return
        try:
            await fn(chat_id=chat_id)      # sirf isi chat ke listeners
        except Exception:
            pass

    await _stop_old()
    try:
        answer = await bot.listen(
            filters=filters.text, timeout=INPUT_TIMEOUT,
            chat_id=chat_id, user_id=target.chat.id,
        )
    except ListenerTimeout:
        try:
            await target.reply("⌛️ Timeout — value nahi mili.")
        except Exception:
            pass
        return
    except Exception as e:
        logger.warning(f"[env] listen failed: {e}")
        return

    raw = (answer.text or "").strip()
    try:
        await answer.delete()      # input chat me na padi rahe
    except Exception:
        pass

    text, markup = confirm_page(name, raw, page)
    try:
        await target.reply(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass


# ======================================================
# 📟 /env COMMAND (PM only)
# ======================================================

def _usage() -> str:
    return (
        "⚙️ <b>/env — Environment manager</b>\n\n"
        "<code>/env</code> — panel (buttons)\n"
        "<code>/env all</code> — saare variables (value + source)\n"
        "<code>/env list</code> — sirf settable switches\n"
        "<code>/env get NAME</code> — ek variable\n"
        "<code>/env set NAME VALUE</code> — badlo (live)\n"
        "<code>/env reset NAME</code> — default par wapas\n"
        "<code>/env clear NAME</code> — text value khaali karo\n"
        "<code>/env search TEXT</code> — variable dhoondo\n\n"
        "<b>Examples</b>\n"
        "<code>/env set IS_PREMIUM false</code>\n"
        "<code>/env set MAX_WEB_RESULTS 30</code>\n"
        "<code>/env set PROTECT_CONTENT true</code>\n"
        "<code>/env get UPI_ID</code>\n"
        "<code>/env reset IS_PREMIUM</code>\n\n"
        "<i>Boolean ke liye true/false (on/off, 1/0 bhi chalega).\n"
        "Secrets mask hote hain; deployment vars (ADMINS, BIN_CHANNEL …) read-only hain.</i>"
    )


@Client.on_message(filters.private & filters.command(["env", "config", "setenv"]))
async def env_cmd(bot, message):
    if not _is_admin(message.from_user.id):
        return await message.reply("❌ Admins only")

    args = message.text.split()[1:]
    sub = args[0].lower() if args else ""

    # ─── no args → buttons panel ───
    if not sub:
        return await message.reply(
            index_text(), reply_markup=index_buttons(),
            parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True,
        )

    # ─── /env all ───
    if sub == "all":
        for chunk in full_env_chunks():
            await message.reply(
                chunk, parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
            )
        return await message.reply(
            "<i>Tip: <code>/env set NAME VALUE</code> se koi bhi value badliye.</i>",
            reply_markup=env_text_buttons(), parse_mode=enums.ParseMode.HTML,
        )

    # ─── /env list ───
    if sub == "list":
        lines = ["⚙️ <b>SETTABLE VARIABLES</b>", ""]
        for key in CATEGORY_ORDER:
            items = [s for s in specs_in(key) if s.settable]
            if not items:
                continue
            lines.append(f"<b>{group_title(key)}</b>")
            for s in items:
                lines.append(
                    f"{dot(s)} <code>{s.name}</code> = "
                    f"<b>{esc(short(shown(s), 30))}</b>"
                )
            lines.append("")
        lines.append("<i>Detail: /env get NAME · Badlo: /env set NAME VALUE</i>")
        return await message.reply(
            "\n".join(lines), parse_mode=enums.ParseMode.HTML,
            reply_markup=env_text_buttons(),
        )

    # ─── /env get NAME ───
    if sub == "get":
        if len(args) < 2:
            return await message.reply("❌ <code>/env get NAME</code>")
        name = args[1].upper().strip()
        if name not in SPEC_MAP:
            return await message.reply(f"❌ Unknown variable: <code>{esc(name)}</code>")
        text, markup = var_page(name, 0)
        return await message.reply(text, reply_markup=markup,
                                   parse_mode=enums.ParseMode.HTML)

    # ─── /env set NAME VALUE ───
    if sub in ("set", "change", "update"):
        if len(args) < 2:
            return await message.reply("❌ <code>/env set NAME VALUE</code>")
        name = args[1].upper().strip()
        if name not in SPEC_MAP:
            return await message.reply(f"❌ Unknown variable: <code>{esc(name)}</code>")
        spec = SPEC_MAP[name]

        if not spec.settable:
            return await message.reply(
                f"🔒 <code>{name}</code> deployment ka variable hai — panel se nahi badalta."
            )

        # value na di ho → prompt (input se)
        if len(args) < 3:
            return await ask_value(bot, message, name, 0)

        # `/env set NAME <value jo bhi ho>` → NAME ke baad ka poora text (spaces allowed)
        parts_txt = message.text.split(None, 3)
        raw = parts_txt[3] if len(parts_txt) > 3 else ""

        old_raw = env_text(spec, env_manager.get(name))
        ok, result = await env_manager.set(
            name, raw, by=message.from_user.id, old_text=old_raw,
        )
        if not ok:
            return await message.reply(result, parse_mode=enums.ParseMode.HTML)

        text, markup = var_page(name, 0, note=result)
        await message.reply(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        await log_change(bot, message.from_user, name, raw, old=old_raw)
        return

    # ─── /env reset NAME (ya `clear` = khaali text) ───
    if sub == "clear":
        if len(args) < 2:
            return await message.reply("❌ <code>/env clear NAME</code>")
        name = args[1].upper().strip()
        spec = SPEC_MAP.get(name)
        if spec is None:
            return await message.reply(f"❌ Unknown variable: <code>{esc(name)}</code>")
        if not spec.settable or spec.secret:
            return await message.reply("🔒 Ye variable panel se khaali nahi ho sakta.")
        old_raw = env_text(spec, env_manager.get(name))
        ok, result = await env_manager.set(
            name, "", by=message.from_user.id, old_text=old_raw,
        )
        text, markup = var_page(name, 0, note=result)
        await message.reply(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        if ok:
            await log_change(bot, message.from_user, name, "", old=old_raw)
        return

    if sub in ("reset", "default"):
        if len(args) < 2:
            return await message.reply("❌ <code>/env reset NAME</code>")
        name = args[1].upper().strip()
        if name not in SPEC_MAP:
            return await message.reply(f"❌ Unknown variable: <code>{esc(name)}</code>")
        if not env_manager.has_override(name):
            text, markup = var_page(name, 0, note="ℹ️ Koi panel override nahi tha.")
            return await message.reply(text, reply_markup=markup,
                                       parse_mode=enums.ParseMode.HTML)
        old_raw = env_text(SPEC_MAP[name], env_manager.get(name))
        ok, result = await env_manager.reset(name)
        text, markup = var_page(name, 0, note=result)
        await message.reply(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        if ok:
            await log_change(bot, message.from_user, name, "RESET", old=old_raw)
        return

    # ─── /env search TEXT ───
    if sub in ("search", "find", "grep"):
        needle = " ".join(args[1:]).lower().strip()
        if not needle:
            return await message.reply("❌ <code>/env search text</code>")
        hits = [
            s for s in SPECS
            if needle in s.name.lower() or needle in s.label.lower()
            or needle in s.hint.lower() or needle in s.category.lower()
        ]
        if not hits:
            return await message.reply(f"🔍 <code>{esc(needle)}</code> — kuch nahi mila.")
        lines = [f"🔍 <b>{len(hits)} match</b> — <code>{esc(needle)}</code>", ""]
        for s in hits[:40]:
            lines.append(f"{dot(s)} <code>{s.name}</code> = "
                         f"<b>{esc(short(shown(s), 30))}</b>")
        return await message.reply("\n".join(lines), parse_mode=enums.ParseMode.HTML)

    # ─── /env help | anything unknown ───
    return await message.reply(_usage(), parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.private & filters.command("cancel_env"))
async def cancel_env_cmd(bot, message):
    if not _is_admin(message.from_user.id):
        return
    _state("ENV_PENDING", {}).clear()
    try:
        await bot.stop_listening(chat_id=message.chat.id)
    except Exception:
        pass
    await message.reply("✅ Env input cancel kar diya.")
