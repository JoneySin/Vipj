"""🔐 Web login / registration / password reset routes.

Flow (v5 जैसा):
  * Email + password से login → HttpOnly cookie session (RAM + MongoDB).
  * नया अकाउंट: Telegram ID + Email + Password → bot PM में OTP → verify.
  * Password भूल गए: Telegram ID → bot PM में OTP → नया password.
  * Logout / password reset पर सारे पुराने sessions बंद.
"""

import logging
import re
import secrets
import time
from urllib.parse import quote

from aiohttp import web

from info import WEB_SESSION_TTL
from utils import temp
from database.users_chats_db import (
    web_db,
    MIN_PASSWORD_LEN,
    OTPRateLimited,
)
from web.web_assets import (
    form_page,
    get_auth,
    is_secure_request,
    prune_sessions,
)

logger = logging.getLogger(__name__)
auth_routes = web.RouteTableDef()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REG_OTP_TTL = 300        # registration OTP 5 मिनट
REG_MAX_TRIES = 5


def _redirect(path, **params):
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v not in (None, ""))
    return web.HTTPFound(path + (f"?{qs}" if qs else ""))


async def _send_otp(tg_id: int, message: str) -> bool:
    """Bot PM में OTP भेजो (user ने bot को /start किया होना चाहिए)।"""
    bot = getattr(temp, "BOT", None)
    if bot is None:
        return False
    try:
        await bot.send_message(tg_id, message)
        return True
    except Exception as e:
        logger.warning(f"OTP send failed for {tg_id}: {e}")
        return False


# ───────────────────────── SIGN IN ─────────────────────────
@auth_routes.get("/login")
async def login_page(req):
    role, _ = await get_auth(req)
    if role:
        return web.HTTPFound("/search")
    inner = (
        "<div class='lead'>अपने अकाउंट से लॉगिन करें और सीधे web पर फाइलें खोजें, "
        "असली thumbnail देखें और नाम पर क्लिक करके stream करें।</div>"
        "<form action='/api/login' method='post'>"
        "<input type='email' name='email' placeholder='Email Address' required autocomplete='username'>"
        "<input type='password' name='password' placeholder='Password' required autocomplete='current-password'>"
        "<button class='submit' type='submit'>Sign In</button></form>"
        "<div class='links'><a href='/forgot_password'>Forgot Password?</a>"
        "<a href='/register'>New? Create Account →</a></div>"
    )
    return form_page(
        "Sign In", inner,
        err=req.query.get("err", ""), msg=req.query.get("msg", ""),
    )


@auth_routes.post("/api/login")
async def api_login(req):
    data = await req.post()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    user = await web_db.verify_login(email, password)
    if not user:
        return _redirect("/login", err="Invalid Email or Password")

    tg_id = int(user["tg_id"])
    await web_db.update_last_login(tg_id)

    sid = secrets.token_urlsafe(32)
    expiry = time.time() + WEB_SESSION_TTL
    temp.USER_SESSIONS[sid] = {"tg_id": tg_id, "expiry": expiry}
    prune_sessions()
    await web_db.create_session(sid, tg_id, expiry)   # restart पर भी login बना रहे

    res = web.HTTPFound("/search")
    res.set_cookie(
        "user_session", sid,
        max_age=WEB_SESSION_TTL, path="/",
        httponly=True, secure=is_secure_request(req), samesite="Lax",
    )
    return res


@auth_routes.get("/logout")
async def logout(req):
    sid = req.cookies.get("user_session")
    if sid:
        temp.USER_SESSIONS.pop(sid, None)
        try:
            await web_db.delete_session(sid)
        except Exception:
            pass
    res = web.HTTPFound("/login?msg=Signed%20out%20successfully")
    res.del_cookie("user_session", path="/")
    return res


# ─────────────────────── REGISTRATION ───────────────────────
@auth_routes.get("/register")
async def register_page(req):
    inner = (
        "<div class='lead'>OTP आपके Telegram bot PM में जाएगा — पहले bot को "
        "<b>/start</b> भेजें। Telegram ID और Email आपके अकाउंट से लिंक होंगे।</div>"
        "<form action='/api/register_step1' method='post'>"
        "<input type='number' name='tg_id' placeholder='Telegram ID (e.g. 123456789)' required>"
        "<input type='email' name='email' placeholder='Email Address' required>"
        "<input type='password' name='password' placeholder='Create Password (min 6 chars)' required minlength='6'>"
        "<button class='submit' type='submit'>Send OTP via Telegram</button></form>"
        "<div class='links'><span></span><a href='/login'>Already have an account? Sign In</a></div>"
    )
    return form_page("Create Account", inner, err=req.query.get("err", ""))


@auth_routes.post("/api/register_step1")
async def api_register_step1(req):
    d = await req.post()
    try:
        tg_id = int(d.get("tg_id"))
        if tg_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _redirect("/register", err="Invalid Telegram ID")

    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    if not EMAIL_RE.match(email):
        return _redirect("/register", err="Enter a valid Email Address")
    if len(password) < MIN_PASSWORD_LEN:
        return _redirect("/register", err=f"Password must be at least {MIN_PASSWORD_LEN} characters")

    if await web_db.identity_exists(tg_id, email):
        return _redirect("/register", err="Telegram ID or Email already registered!")

    otp = str(secrets.randbelow(900000) + 100000)
    temp.REG_PENDING[tg_id] = {
        "email": email, "password": password, "otp": otp,
        "expiry": time.time() + REG_OTP_TTL, "tries": 0,
    }
    sent = await _send_otp(
        tg_id,
        f"🔐 Fast Finder — Web Registration\n\n"
        f"OTP: {otp}\n\nValid for 5 minutes. Do not share it with anyone.",
    )
    if not sent:
        temp.REG_PENDING.pop(tg_id, None)
        return _redirect(
            "/register",
            err="OTP नहीं भेजा जा सका। पहले Telegram में bot को /start करें।",
        )
    return _redirect("/verify_registration", tg_id=tg_id)


@auth_routes.get("/verify_registration")
async def verify_registration_page(req):
    tg_id = req.query.get("tg_id", "")
    if not tg_id.isdigit():
        return web.HTTPFound("/register")
    inner = (
        "<div class='lead'>आपके Telegram bot PM में 6-digit OTP भेजा गया है।</div>"
        "<form action='/api/register_step2' method='post'>"
        f"<input type='hidden' name='tg_id' value='{tg_id}'>"
        "<input type='text' name='otp' placeholder='Enter 6-digit OTP' "
        "inputmode='numeric' pattern='[0-9]{6}' maxlength='6' required>"
        "<button class='submit' type='submit'>Verify & Create Account</button></form>"
    )
    return form_page("Verify OTP", inner, err=req.query.get("err", ""))


@auth_routes.post("/api/register_step2")
async def api_register_step2(req):
    d = await req.post()
    try:
        tg_id = int(d.get("tg_id"))
    except (TypeError, ValueError):
        return _redirect("/register", err="Invalid Request")

    pending = temp.REG_PENDING.get(tg_id)
    if not pending:
        return _redirect("/register", err="Session expired. Please register again.")
    if time.time() > pending["expiry"]:
        temp.REG_PENDING.pop(tg_id, None)
        return _redirect("/register", err="OTP Expired. Please restart registration.")

    pending["tries"] = pending.get("tries", 0) + 1
    if pending["tries"] > REG_MAX_TRIES:
        temp.REG_PENDING.pop(tg_id, None)
        return _redirect("/register", err="Too many wrong attempts. Start again.")

    otp = str(d.get("otp") or "").strip()
    if not secrets.compare_digest(str(pending["otp"]).encode(), otp.encode()):
        return _redirect("/verify_registration", tg_id=tg_id, err="Invalid OTP")

    ok, msg = await web_db.create_user(tg_id, pending["email"], pending["password"])
    temp.REG_PENDING.pop(tg_id, None)
    if not ok:
        return _redirect("/register", err=msg)
    return _redirect("/login", msg="Account created! Please sign in.")


# ─────────────────── FORGOT / RESET PASSWORD ───────────────────
@auth_routes.get("/forgot_password")
async def forgot_password_page(req):
    inner = (
        "<div class='lead'>अपना Telegram ID डालें, bot PM में OTP जाएगा। "
        "उसी OTP से नीचे नया password सेट करें।</div>"
        "<form action='/api/forgot_password' method='post'>"
        "<input type='number' name='tg_id' placeholder='Telegram ID' required>"
        "<button class='submit' type='submit'>Send OTP to Telegram</button></form>"
        "<hr class='hr'>"
        "<form action='/api/reset_password' method='post'>"
        "<input type='number' name='tg_id' placeholder='Confirm Telegram ID' required>"
        "<input type='text' name='otp' placeholder='Enter OTP' maxlength='6' required>"
        "<input type='password' name='new_password' placeholder='New Password (min 6 chars)' required minlength='6'>"
        "<button class='submit' type='submit'>Update Password</button></form>"
        "<div class='links'><span></span><a href='/login'>Back to Sign In</a></div>"
    )
    return form_page(
        "Reset Password", inner,
        err=req.query.get("err", ""), msg=req.query.get("msg", ""),
    )


@auth_routes.post("/api/forgot_password")
async def api_forgot_password(req):
    d = await req.post()
    try:
        tg_id = int(d.get("tg_id"))
    except (TypeError, ValueError):
        return _redirect("/forgot_password", err="Invalid Telegram ID")
    try:
        otp = await web_db.generate_otp(tg_id)
    except OTPRateLimited:
        return _redirect("/forgot_password", err="Too many OTP requests. Try again after 10 minutes.")
    if not otp:
        return _redirect("/forgot_password", err="Telegram ID is not registered!")
    sent = await _send_otp(
        tg_id,
        f"🔐 Fast Finder — Password Reset\n\n"
        f"OTP: {otp}\n\nValid for 10 minutes. Do not share it with anyone.",
    )
    if not sent:
        return _redirect("/forgot_password", err="OTP नहीं भेजा जा सका। Bot को /start करें।")
    return _redirect("/forgot_password", msg="OTP sent to your Telegram!")


@auth_routes.post("/api/reset_password")
async def api_reset_password(req):
    d = await req.post()
    try:
        tg_id = int(d.get("tg_id"))
    except (TypeError, ValueError):
        return _redirect("/forgot_password", err="Invalid Input")

    new_password = d.get("new_password") or ""
    if len(new_password) < MIN_PASSWORD_LEN:
        return _redirect(
            "/forgot_password",
            err=f"Password must be at least {MIN_PASSWORD_LEN} characters",
        )
    ok = await web_db.verify_otp_and_reset(tg_id, d.get("otp"), new_password)
    if not ok:
        return _redirect("/forgot_password", err="Invalid or expired OTP")

    # Password बदलते ही पुराने सारे sessions बंद (RAM + DB)
    for key in [k for k, v in temp.USER_SESSIONS.items() if v.get("tg_id") == tg_id]:
        temp.USER_SESSIONS.pop(key, None)
    try:
        await web_db.delete_user_sessions(tg_id)
    except Exception:
        pass
    return _redirect("/login", msg="Password updated! Please sign in again.")
