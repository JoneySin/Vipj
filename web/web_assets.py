"""🎨 Shared web assets: session/auth helper, page shell, CSS and the search UI.

`v5` के dashboard/miniapp जैसा look — sidebar (Home / Database Stats /
Profile Settings / Sign Out), stats cards और profile settings, पर fsv1 के
लिए एक ही self-contained page (कोई extra template engine नहीं)।
"""

import html
import time

from aiohttp import web

from info import ADMINS
from utils import temp
from database.users_chats_db import web_db


# ─────────────────────────────────────────────────────────────
# 🔐 SESSION / AUTH
# ─────────────────────────────────────────────────────────────
def prune_sessions():
    """RAM की expired sessions साफ़ करो + uncontrolled growth रोको."""
    sessions = temp.USER_SESSIONS
    if len(sessions) <= 5000:
        return
    now = time.time()
    for key in [k for k, v in sessions.items() if v.get("expiry", 0) <= now]:
        sessions.pop(key, None)
    while len(sessions) > 5000:
        sessions.pop(next(iter(sessions)), None)


async def get_auth(req):
    """Returns (role, tg_id) — role 'admin' | 'user', ya (None, None)."""
    sid = req.cookies.get("user_session")
    if not sid:
        return None, None

    session = temp.USER_SESSIONS.get(sid)
    if not session:
        # Bot restart / dusra instance → DB se session wapas lao
        try:
            session = await web_db.get_session(sid)
            if session:
                temp.USER_SESSIONS[sid] = session
                prune_sessions()
        except Exception:
            session = None

    if session and session.get("expiry", 0) > time.time():
        tg_id = session.get("tg_id")
        if tg_id:
            return ("admin" if tg_id in ADMINS else "user"), tg_id

    temp.USER_SESSIONS.pop(sid, None)
    return None, None


def is_secure_request(req):
    """Proxy (Koyeb/Render) के पीछे असली scheme का पता लगाओ."""
    return (
        req.secure
        or req.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() == "https"
    )


# ─────────────────────────────────────────────────────────────
# 🎨 SHARED CSS
# ─────────────────────────────────────────────────────────────
SITE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b0b0f;--bg2:#14141c;--bg3:#1e1e2a;--card:#16161f;--line:#2a2a38;
--txt:#f5f5f7;--mut:#9a9aad;--red:#e50914;--red2:#b30710;--gold:#ffd166}
html.light{--bg:#f4f5f8;--bg2:#fff;--bg3:#eceef4;--card:#fff;--line:#d8dbe5;
--txt:#101018;--mut:#5c5c70}
body{font-family:'DM Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--txt);min-height:100vh;transition:background .2s,color .2s}
a{color:inherit;text-decoration:none}
.top{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:14px;
height:62px;padding:0 4%;background:var(--bg2);border-bottom:1px solid var(--line);
box-shadow:0 4px 20px rgba(0,0,0,.35)}
.logo{font-size:19px;font-weight:900;letter-spacing:1px;color:var(--red);display:flex;
align-items:center;gap:8px;flex:1}
.nfi{background:var(--red);color:#fff;border-radius:4px;padding:2px 8px;font-size:17px}
.tbadge{font-size:12px;color:var(--mut);background:var(--bg3);border:1px solid var(--line);
padding:5px 10px;border-radius:20px;white-space:nowrap}
.tbtn{background:transparent;border:1px solid var(--line);color:var(--txt);border-radius:6px;
padding:7px 13px;font-weight:700;font-size:12px;cursor:pointer;font-family:inherit}
.tbtn:hover{border-color:var(--red)}
.search-zone{padding:18px 4% 14px;background:var(--bg);border-bottom:1px solid var(--line)}
/* 🖥️ desktop: search input + दोनों filter dropdowns एक ही लाइन में */
.srow{display:flex;gap:10px;max-width:1100px;align-items:center;flex-wrap:wrap}
.qwrap{position:relative;flex:1 1 320px;min-width:0}
.sinput{display:block;width:100%;min-width:0;box-sizing:border-box;background:var(--bg2);
border:1.5px solid var(--line);border-radius:10px;padding:13px 16px;color:var(--txt);
font-size:15px;font-weight:600;font-family:inherit;outline:none;transition:border-color .18s}
.sinput:focus{border-color:var(--red)}
.spin{display:none;position:absolute;right:16px;top:50%;transform:translateY(-50%);
width:17px;height:17px;border:2px solid var(--line);border-top-color:var(--red);
border-radius:50%;animation:spin .6s linear infinite}
.srow.loading .spin{display:block}
@keyframes spin{to{transform:translateY(-50%) rotate(360deg)}}
/* ── filter dropdowns: desktop पर search bar के साथ, mobile पर ठीक नीचे एक लाइन ── */
.filters{display:flex;gap:10px;align-items:center;flex:0 0 auto}
.fwrap{position:relative;display:inline-flex;align-items:center;gap:7px;min-width:0}
.flabel{font-size:10px;color:var(--mut);font-weight:900;letter-spacing:.7px;text-transform:uppercase}
.fsel{-webkit-appearance:none;appearance:none;background:var(--bg3);border:1px solid var(--line);
color:var(--txt);border-radius:8px;padding:9px 30px 9px 12px;font-family:inherit;
font-size:12px;font-weight:800;cursor:pointer;min-width:120px;outline:none}
.fsel:hover,.fsel:focus{border-color:var(--red)}
.fwrap::after{content:'▾';position:absolute;right:11px;top:50%;transform:translateY(-50%);
pointer-events:none;color:var(--mut);font-size:11px;font-weight:900}
.main{padding:18px 4% 60px;max-width:1700px;margin:0 auto}
/* 📱 mobile: 1 video/row  ·  📟 tablet: 2  ·  🖥️ desktop: 3 (fix, बड़ी screen पर भी 3 ही) */
.grid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:600px){.grid{grid-template-columns:repeat(2,1fr);gap:14px}}
@media(min-width:1024px){.grid{grid-template-columns:repeat(3,1fr);gap:18px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
overflow:hidden;transition:transform .2s,border-color .2s}
@media(hover:hover){.card:hover{transform:translateY(-3px);border-color:rgba(229,9,20,.6)}}
.poster{position:relative;aspect-ratio:16/9;background:linear-gradient(90deg,var(--bg3) 0,#2b2b3a 50%,var(--bg3) 100%);
background-size:200% 100%;animation:sh 1.5s infinite linear;overflow:hidden}
@keyframes sh{0%{background-position:200% 0}100%{background-position:-200% 0}}
.poster img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
opacity:0;transition:opacity .3s}
.poster img.on{opacity:1}
.poster img.hidden{display:none}
.ph{display:none;position:absolute;inset:0;align-items:center;justify-content:center;
flex-direction:column;gap:4px;color:var(--mut);font-size:11px;font-weight:800;
letter-spacing:1px;background:linear-gradient(135deg,#1b1b28,#101018)}
.poster.no-thumb .ph{display:flex}
.poster.no-thumb{animation:none;background:none}
.ph b{font-size:30px;color:var(--red)}
.chips{position:absolute;top:0;left:0;right:0;display:flex;gap:5px;padding:7px;
flex-wrap:wrap;pointer-events:none}
.tg{background:rgba(0,0,0,.78);backdrop-filter:blur(6px);color:#fff;border-radius:5px;
padding:3px 7px;font-size:10px;font-weight:800;border:1px solid rgba(255,255,255,.14)}
.tg.gold{color:var(--gold);border-color:rgba(255,209,102,.4)}
.tg.blue{color:#93c5fd;border-color:rgba(147,197,253,.35)}
.body{padding:10px 11px 13px}
.fname{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
font-size:13px;font-weight:700;line-height:1.45;cursor:pointer;min-height:38px;
transition:color .18s}
.fname:hover{color:var(--red)}
.size-tag{position:absolute;right:7px;bottom:7px;z-index:2;pointer-events:none;
background:rgba(0,0,0,.78);backdrop-filter:blur(6px);color:#fff;border-radius:5px;
padding:3px 7px;font-size:10px;font-weight:800;border:1px solid rgba(255,255,255,.14)}
.tinfo{display:none;align-items:center;gap:5px;flex-shrink:0}
.tsize{background:rgba(229,9,20,.14);color:var(--red);border:1px solid rgba(229,9,20,.35);
border-radius:5px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap}
/* Text mode: सिर्फ़ नाम + meta वाली कॉम्पैक्ट लिस्ट, कोई thumbnail नहीं */
.grid.mode-text{display:block}
.grid.mode-text .card{display:flex;align-items:center;gap:6px;padding:9px 11px;
margin-bottom:8px;border-radius:8px}
.grid.mode-text .poster{display:none}
.grid.mode-text .body{display:flex;align-items:center;justify-content:space-between;
gap:10px;padding:0;flex:1;min-width:0}
.grid.mode-text .fname{display:block;flex:1;min-width:0;min-height:0;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;-webkit-line-clamp:1}
.grid.mode-text .tinfo{display:flex}
.grid.mode-text .tg{font-size:9px;padding:2px 5px}
@media(max-width:599px){.grid.mode-text .tinfo .tg{display:none}}
.state{grid-column:1/-1;text-align:center;padding:70px 20px;color:var(--mut);
font-weight:600;line-height:1.7}
.more{display:none;margin:28px auto 0;padding:11px 30px;border-radius:8px;
background:var(--bg3);border:1px solid var(--line);color:var(--txt);font-weight:800;
cursor:pointer;font-family:inherit}
.more.show{display:block}
/* ── player modal ── */
.modal{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.88);
display:none;align-items:center;justify-content:center;padding:16px}
.modal.open{display:flex}
.mcard{background:var(--bg2);border:1px solid var(--line);border-radius:14px;
width:100%;max-width:940px;overflow:hidden;box-shadow:0 20px 70px rgba(0,0,0,.7)}
.mhead{display:flex;align-items:center;gap:10px;padding:12px 16px;
border-bottom:1px solid var(--line)}
.mtitle{flex:1;font-weight:800;font-size:14px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.xbtn{background:transparent;border:0;color:var(--mut);font-size:22px;cursor:pointer;
line-height:1}
.video-wrap{background:#000;aspect-ratio:16/9}
video{width:100%;height:100%;display:block;background:#000}
.mactions{display:flex;gap:8px;flex-wrap:wrap;padding:13px 16px}
.mactions a,.mactions button{background:var(--bg3);border:1px solid var(--line);
color:var(--txt);border-radius:7px;padding:9px 14px;font-size:12px;font-weight:800;
cursor:pointer;font-family:inherit}
.mactions a.red{background:var(--red);border-color:var(--red);color:#fff}
.mnote{padding:0 16px 15px;font-size:11px;color:var(--mut)}
/* ── auth pages ── */
.auth-bg{background:radial-gradient(circle at 20% 10%,rgba(229,9,20,.18),transparent 45%),
radial-gradient(circle at 85% 80%,rgba(80,70,229,.15),transparent 45%),var(--bg)}
.auth-wrap{min-height:calc(100vh - 62px);display:flex;align-items:center;
justify-content:center;padding:24px}
.auth-card{width:100%;max-width:430px;background:var(--card);border:1px solid var(--line);
border-radius:16px;padding:34px;box-shadow:0 18px 60px rgba(0,0,0,.45)}
.auth-card h2{font-size:27px;margin-bottom:6px}
.auth-card .lead{font-size:13px;color:var(--mut);margin-bottom:24px;line-height:1.5}
.auth-card input{width:100%;background:var(--bg);border:1.5px solid var(--line);
border-radius:9px;padding:14px;color:var(--txt);font-size:14px;margin-bottom:13px;
font-family:inherit;outline:none}
.auth-card input:focus{border-color:var(--red)}
.submit{width:100%;background:var(--red);color:#fff;border:0;border-radius:9px;
padding:15px;font-weight:800;font-size:14px;cursor:pointer;font-family:inherit;margin-top:8px}
.submit:hover{background:var(--red2)}
.err,.ok{border-radius:8px;padding:11px 14px;font-size:13px;font-weight:700;margin-bottom:16px}
.err{background:rgba(229,9,20,.16);color:#ff8c92;border:1px solid rgba(229,9,20,.4)}
.ok{background:rgba(40,167,69,.15);color:#6ee7a0;border:1px solid rgba(40,167,69,.4)}
.links{display:flex;justify-content:space-between;margin-top:20px;font-size:13px;
font-weight:700;color:var(--mut);gap:10px;flex-wrap:wrap}
.links a:hover{color:var(--red)}
.hr{border:0;border-top:1px solid var(--line);margin:24px 0}
/* 📱 mobile/tablet: search bar अपनी लाइन पर, दोनों filter buttons नीचे एक ही लाइन में */
@media(max-width:760px){
.qwrap{flex:1 1 100%}
.filters{flex:1 1 100%}
.fwrap{flex:1 1 0}
.fsel{flex:1;width:100%;min-width:0}
}
@media(max-width:520px){.spin{display:none!important}
.auth-card{padding:24px}.grid{gap:8px}}
"""



# ─────────────────────────────────────────────────────────────
# 🧭 APP SHELL — JoneySin/v5 (web/web_assets.py) जैसा sidebar
#    Home · Database Stats · Profile Settings + footer में Sign Out.
#    "#<tg_id> · ADMIN" identity भी v5 की तरह sidebar header + Profile
#    Settings में दिखती है (topbar वाला badge "जैसा है वैसा" बना रहा)।
# ─────────────────────────────────────────────────────────────
APP_CSS = """
/* ── v5-style sidebar / app shell ── */
.ham-btn{background:transparent;border:0;cursor:pointer;color:var(--txt);display:flex;
flex-direction:column;gap:4px;padding:6px}
.ham-line{width:21px;height:2px;background:currentColor;border-radius:2px}
.topbar-right{display:flex;align-items:center;gap:8px}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,.68);z-index:150;
opacity:0;pointer-events:none;transition:opacity .2s}
.sidebar-overlay.open{opacity:1;pointer-events:all}
.sidebar{position:fixed;top:0;left:0;height:100%;width:260px;max-width:82vw;
background:var(--bg2);border-right:1px solid var(--line);z-index:160;display:flex;
flex-direction:column;transform:translateX(-100%);transition:transform .3s}
.sidebar.open{transform:translateX(0)}
.sb-header{padding:18px 18px 14px;border-bottom:1px solid var(--line);display:flex;
align-items:center;justify-content:space-between}
.sb-logo{font-size:14px;font-weight:900;color:var(--red);display:flex;align-items:center;
gap:8px;letter-spacing:.6px}
.sb-close{background:none;border:0;color:var(--mut);font-size:20px;cursor:pointer;line-height:1}
.sb-user{margin:14px 14px 0;padding:10px 12px;background:var(--bg3);border:1px solid var(--line);
border-radius:8px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.sb-uid{font-size:12px;font-weight:800;color:var(--txt);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}
.sb-role{font-size:9px;font-weight:900;letter-spacing:.8px;color:#fff;background:var(--red);
border-radius:20px;padding:3px 8px;flex-shrink:0}
.sb-nav{padding:14px 10px;flex:1;overflow-y:auto}
.sb-section{font-size:10px;font-weight:900;color:var(--mut);padding:8px 12px;
letter-spacing:1.4px;text-transform:uppercase}
.sb-link{display:block;padding:12px 15px;border-radius:8px;color:var(--mut);font-size:14px;
font-weight:700;margin-bottom:4px;transition:background .15s,color .15s}
.sb-link:hover{background:var(--bg3);color:var(--txt)}
.sb-link.active{background:var(--red);color:#fff}
.sb-footer{padding:14px 10px;border-top:1px solid var(--line)}
.sb-logout{display:block;padding:12px;border-radius:8px;text-align:center;color:var(--txt);
font-weight:800;font-size:13px;border:1px solid var(--line);background:var(--bg3)}
.sb-logout:hover{border-color:var(--red);color:var(--red)}
/* ── Database Stats (v5-style cards) ── */
@keyframes ffFade{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
.anim-card{animation:ffFade .45s ease both}
.stat-hero{background:linear-gradient(135deg,var(--card),var(--bg3));border:1px solid var(--line);
border-radius:16px;padding:26px 30px;margin-bottom:20px;position:relative;overflow:hidden}
.stat-hero::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
background:linear-gradient(90deg,#3399ff,#9933ff,var(--red))}
.stat-hero-label{font-size:11px;font-weight:800;color:var(--mut);text-transform:uppercase;
letter-spacing:1.4px;margin-bottom:8px}
.stat-hero-num{font-size:50px;font-weight:900;letter-spacing:-2px;line-height:1;color:var(--red)}
.stat-hero-sub{font-size:12px;color:var(--mut);margin-top:10px;line-height:1.6}
.stat-title{font-size:24px;font-weight:900;margin-bottom:6px}
.stat-lead{font-size:13px;color:var(--mut);margin-bottom:24px;line-height:1.6}
.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}
.st-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;
position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
.st-card:hover{transform:translateY(-2px);border-color:rgba(229,9,20,.55)}
.st-bar{position:absolute;top:0;left:0;right:0;height:3px}
.st-label{font-size:10px;font-weight:900;color:var(--mut);text-transform:uppercase;
letter-spacing:.8px;margin:6px 0 10px}
.st-val{font-size:32px;font-weight:900;letter-spacing:-1px;line-height:1;margin-bottom:10px}
.st-sub{font-size:12px;color:var(--mut);line-height:1.5}
.st-link{display:inline-block;margin-top:12px;font-size:12px;font-weight:800;color:var(--red)}
@media(max-width:800px){.stat-grid{grid-template-columns:1fr 1fr}}
/* ── Profile Settings (v5-style) ── */
.scard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px}
.scard-label{font-size:11px;font-weight:900;color:var(--mut);text-transform:uppercase;
letter-spacing:.9px;margin-bottom:9px}
.prof-status{background:var(--bg3);padding:18px;border-radius:10px;margin-bottom:22px}
.prof-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(229,9,20,.14);
border:1px solid rgba(229,9,20,.38);color:var(--red);font-size:12px;font-weight:900;
padding:6px 12px;border-radius:20px;margin-bottom:14px}
.prof-tab-bar{display:flex;gap:4px;background:var(--bg3);border:1px solid var(--line);
border-radius:9px;padding:4px;margin-bottom:20px}
.prof-tab{flex:1;padding:9px 0;border-radius:6px;border:0;cursor:pointer;font-size:13px;
font-weight:800;font-family:inherit;background:transparent;color:var(--mut)}
.prof-tab.active{background:var(--bg2);color:var(--txt);box-shadow:0 2px 8px rgba(0,0,0,.2)}
.prof-panel{display:none}.prof-panel.active{display:block}
.prof-field{margin-bottom:18px}
.prof-input{width:100%;background:var(--bg3);border:1.5px solid var(--line);border-radius:8px;
padding:11px 14px;font-size:14px;color:var(--txt);font-family:inherit;outline:none;
box-sizing:border-box;transition:border-color .15s}
.prof-input:focus{border-color:var(--red)}.prof-input:disabled{opacity:.6;cursor:default}
.prof-input.pass-input{padding-right:46px}.pass-wrap{position:relative}
.pass-toggle{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;
border:0;cursor:pointer;color:var(--mut);padding:0;display:flex;align-items:center}
.str-row{display:flex;gap:4px;margin-top:8px}
.str-bar{flex:1;height:3px;border-radius:2px;background:var(--bg3)}
.info-row{display:flex;align-items:center;gap:12px;background:var(--bg3);
border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.info-row-lbl{font-size:11px;color:var(--mut);margin-bottom:2px}
.info-row-val{font-size:13px;font-weight:800;color:var(--txt)}
.prof-divider{border:0;border-top:1px solid var(--line);margin:18px 0}
.prof-save-row{display:flex;justify-content:flex-end;margin-top:22px}
.prof-save{background:var(--red);color:#fff;border:0;border-radius:8px;padding:12px 24px;
font-weight:800;font-size:13px;cursor:pointer;font-family:inherit}
.prof-save:hover{background:var(--red2)}
@media(max-width:520px){.stat-grid{grid-template-columns:1fr}.stat-hero-num{font-size:38px}
.scard{padding:20px}.tbadge{display:none}}
"""

# Theme + sidebar — सभी logged-in pages पर एक ही script (v5 की तरह shared head)
SITE_JS = """
(function(){if(localStorage.getItem('ff_theme')==='light')document.documentElement.classList.add('light')})();
function toggleTheme(){var l=document.documentElement.classList.toggle('light');localStorage.setItem('ff_theme',l?'light':'dark')}
function openSidebar(){var s=document.getElementById('sidebar'),o=document.getElementById('sbOverlay');if(s)s.classList.add('open');if(o)o.classList.add('open')}
function closeSidebar(){var s=document.getElementById('sidebar'),o=document.getElementById('sbOverlay');if(s)s.classList.remove('open');if(o)o.classList.remove('open')}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeSidebar()});
"""

# v5 के NAV_MENU जैसा — Database Stats admin-only है
NAV_MENU = (
    ("dash",    "/search",  "🏠 Home"),
    ("posts",   "/posts",   "📝 Posts"),
    ("actors",  "/actors",  "🎭 Actors"),
    ("stats",   "/stats",   "📊 Database Stats"),
    ("profile", "/profile", "⚙️ Profile Settings"),
)


def identity_badge(tg_id: int, role: str) -> str:
    """'#5292444428 · ADMIN' — v5 में यही identity Profile Settings में दिखती है।"""
    return f"#{html.escape(str(tg_id))}" + (" · ADMIN" if role == "admin" else "")


def nav_shell(tg_id: int, role: str, active_tab: str = "") -> str:
    """v5 जैसा sidebar + topbar. Sign Out सिर्फ़ sidebar footer में है —
    main/topbar पर दोबारा नहीं दिखता।"""
    links = "".join(
        f'<a href="{href}" class="sb-link {"active" if active_tab == tab else ""}">{label}</a>'
        for tab, href, label in NAV_MENU
        if role == "admin" or tab != "stats"      # Database Stats admin-only (v5)
    )
    badge = identity_badge(tg_id, role)
    role_txt = "ADMIN" if role == "admin" else "USER"
    return (
        '<div class="sidebar-overlay" id="sbOverlay" onclick="closeSidebar()"></div>'
        '<div class="sidebar" id="sidebar">'
          '<div class="sb-header"><div class="sb-logo"><span class="nfi">F</span> FAST FINDER</div>'
          '<button class="sb-close" onclick="closeSidebar()" aria-label="Close menu">&#10005;</button></div>'
          f'<div class="sb-user"><span class="sb-uid">{badge}</span>'
          f'<span class="sb-role">{role_txt}</span></div>'
          f'<nav class="sb-nav"><div class="sb-section">Menu</div>{links}</nav>'
          '<div class="sb-footer"><a href="/logout" class="sb-logout">Sign Out</a></div>'
        '</div>'
        '<div class="top">'
          '<button class="ham-btn" id="hamBtn" onclick="openSidebar()" aria-label="Open menu">'
            '<span class="ham-line"></span><span class="ham-line"></span><span class="ham-line"></span>'
          '</button>'
          '<a class="logo" href="/search"><span class="nfi">F</span> FAST FINDER</a>'
          f'<span class="tbadge">{badge}</span>'
          '<div class="topbar-right">'
            '<button class="tbtn" onclick="toggleTheme()">Theme</button>'
          '</div>'
        '</div>'
    )


def app_page(title: str, body: str, tg_id: int, role: str,
             active_tab: str = "", body_class: str = ""):
    """Logged-in pages (Search / Database Stats / Profile Settings) का common shell."""
    return html_response(
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap' rel='stylesheet'>"
        f"<style>{SITE_CSS}{APP_CSS}</style>"
        f"<script>{SITE_JS}</script></head>"
        f"<body class='{body_class}'>{nav_shell(tg_id, role, active_tab)}{body}</body></html>"
    )


def html_response(body: str, status: int = 200):
    return web.Response(text=body, content_type="text/html", charset="utf-8", status=status)


def page(title: str, body: str, body_class: str = "", topbar: str = ""):
    """Common shell: CSS + topbar + body."""
    return html_response(
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap' rel='stylesheet'>"
        f"<style>{SITE_CSS}{APP_CSS}</style>"
        f"<script>{SITE_JS}</script></head>"
        f"<body class='{body_class}'>{topbar}{body}</body></html>"
    )


DEFAULT_TOPBAR = (
    "<div class='top'><a class='logo' href='/'><span class='nfi'>F</span> FAST FINDER</a>"
    "<button class='tbtn' onclick=\"toggleTheme()\">Theme</button></div>"
)


def form_page(title: str, inner: str, err: str = "", msg: str = "", heading: str = ""):
    e = f"<div class='err'>{html.escape(err)}</div>" if err else ""
    m = f"<div class='ok'>{html.escape(msg)}</div>" if msg else ""
    body = (
        "<div class='auth-wrap'><div class='auth-card'>"
        f"<h2>{html.escape(heading or title)}</h2>{e}{m}{inner}</div></div>"
    )
    return page(title, body, "auth-bg", DEFAULT_TOPBAR)


# ─────────────────────────────────────────────────────────────
# 🔍 SEARCH PAGE (login ke baad)
# ─────────────────────────────────────────────────────────────
SEARCH_BODY = """<div class="search-zone">
  <div class="srow" id="srow">
    <div class="qwrap">
      <input class="sinput" id="q" type="search" placeholder="Movie / series / file name खोजें..." autocomplete="off">
      <div class="spin"></div>
    </div>
    <div class="filters">
      <div class="fwrap">
        <span class="flabel">Mode</span>
        <select class="fsel" id="modeSel" onchange="setMode(this.value)">
          <option value="poster">🖼️ Poster</option>
          <option value="text">📄 Text</option>
        </select>
      </div>
      <div class="fwrap">
        <span class="flabel">Filter</span>
        <select class="fsel" id="groupSel" onchange="setGroup(this.value)">
          <option value="all">All</option>
          <option value="group">Group</option>
          <option value="ungroup">UnGroup</option>
        </select>
      </div>
    </div>
  </div>
</div>

<div class="main">
  <div class="grid" id="grid"></div>
  <button class="more" id="more" onclick="load(false)">और दिखाओ ⬇</button>
</div>

<div class="modal" id="modal" onclick="if(event.target===this)closePlayer()">
  <div class="mcard">
    <div class="mhead"><div class="mtitle" id="pTitle">Loading stream…</div>
      <button class="xbtn" onclick="closePlayer()">✕</button></div>
    <div class="video-wrap"><video id="player" controls playsinline></video></div>
    <div class="mactions">
      <a class="red" id="pWatch" href="#" target="_blank" rel="noopener">▶ Player page</a>
      <a id="pDl" href="#">⬇ Download</a>
      <button onclick="copyLink()">🔗 Copy stream link</button>
      <button onclick="closePlayer()">Close</button>
    </div>
    <div class="mnote" id="pNote">Signed streaming link — सीमित समय के लिए वैध।</div>
  </div>
</div>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let curQ='',offset=0,loading=false,hasMore=false,currentWatch='';
let debounce=null;
let viewMode=localStorage.getItem('ff_view_mode')||'poster';
let groupMode=localStorage.getItem('ff_group_mode')||'all';
if(viewMode!=='poster'&&viewMode!=='text')viewMode='poster';
if(!['all','group','ungroup'].includes(groupMode))groupMode='all';

function applyMode(){
  const text=viewMode==='text';
  $('#grid').classList.toggle('mode-text',text);
  $('#modeSel').value=viewMode;
  $('#groupSel').value=groupMode;
  if(!text){
    // Poster mode पर लौटने तब तक कोई thumbnail request न गई हो → अब लाओ
    document.querySelectorAll('#grid img[data-src]').forEach(img=>{
      if(!img.getAttribute('src'))img.src=img.dataset.src;
    });
  }
}
function setMode(v){viewMode=(v==='text')?'text':'poster';localStorage.setItem('ff_view_mode',viewMode);applyMode()}
function setGroup(v){groupMode=['all','group','ungroup'].includes(v)?v:'all';
  localStorage.setItem('ff_group_mode',groupMode);applyMode();doSearch()}
function doSearch(){curQ=$('#q').value.trim();load(true)}
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(debounce);doSearch()}});
$('#q').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{
  const v=$('#q').value.trim();if(v.length>=2||v==='')doSearch()},420)});

function card(f){
  const fid=encodeURIComponent(f.file_id);
  const dur=f.duration?`<span class="tg gold">${esc(f.duration)}</span>`:'';
  const q=f.quality&&f.quality!=='unknown'?`<span class="tg blue">${esc(f.quality)}</span>`:'';
  const res=f.res?`<span class="tg">${esc(f.res)}</span>`:'';
  // Text mode में thumbnail request ही न जाए — src तभी लगाओ जब Poster mode हो
  const thumbUrl=encodeURI(f.thumb);
  const imgAttr=viewMode==='poster'?`src="${thumbUrl}"`:`data-src="${thumbUrl}"`;
  return `<div class="card">
    <div class="poster" id="pb-${fid}">
      <img ${imgAttr} alt="" loading="lazy" data-thumb="${thumbUrl}" data-retry="0"
           onload="this.classList.add('on')" onerror="thumbFail(this)">
      <div class="ph"><b>▶</b><span>NO THUMBNAIL</span></div>
      <div class="chips"><span class="tg">${esc(f.type)}</span>${q}${res}${dur}</div>
      <span class="size-tag">${esc(f.size)}</span>
    </div>
    <div class="body">
      <div class="fname" data-fid="${fid}" data-name="${esc(f.name)}"
           title="Stream करने के लिए क्लिक करें">${esc(f.name)}</div>
      <div class="tinfo"><span class="tg">${esc(f.type)}</span>${q}${res}${dur}<span class="tsize">${esc(f.size)}</span></div>
    </div></div>`;
}
// v5 के reloadThumb(fileId) जैसा: पहली बार poster serial warmup queue में
// एक-एक करके निकलता है, इसलिए 404 पर `retry=true&t=...` से धीरे-धीरे दोबारा
// माँगो — जैसे-जैसे ID DB में lock होती है, posters अपने आप दिखते जाते हैं।
function thumbFail(img){
  const delays=[1500,2500,4000,6000,9000,12000,16000,20000];
  const n=Number(img.dataset.retry||0);
  if(n<delays.length&&!img.classList.contains('hidden')){
    img.dataset.retry=String(n+1);
    setTimeout(()=>{
      if(!img.isConnected||img.classList.contains('on'))return;
      const base=img.dataset.thumb||img.getAttribute('src')||'';
      if(!base)return;
      img.src=base+(base.includes('?')?'&':'?')+'retry=true&t='+Date.now();
    },delays[n]);
    return;
  }
  img.classList.add('hidden');
  const p=img.closest('.poster');if(p)p.classList.add('no-thumb');
}

async function load(reset){
  if(loading)return;
  if(reset){offset=0;hasMore=false;$('#grid').innerHTML='';}
  loading=true;$('#srow').classList.add('loading');
  try{
    const r=await fetch(`/api/search?q=${encodeURIComponent(curQ)}&offset=${offset}&group=${groupMode}`,{credentials:'same-origin'});
    if(r.status===401){location.href='/login?err='+encodeURIComponent('Session expired. Please sign in again.');return}
    const d=await r.json();
    const list=d.results||[];
    $('#grid').insertAdjacentHTML('beforeend',list.map(card).join(''));
    hasMore=!!d.next_offset;
    offset=hasMore?Number(d.next_offset):0;
    $('#more').classList.toggle('show',hasMore);
    // ℹ️ "Recently Added / Database Stats" वाली meta लाइन हटा दी गई —
    //    गिनती सिर्फ़ sidebar के "Database Stats" पेज पर दिखती है।
    if(!$('#grid').children.length){
      $('#grid').innerHTML=`<div class="state">🔍 कोई फाइल नहीं मिली।<br>दूसरा नाम / keyword ट्राय करें।</div>`;
    }
  }catch(e){
    $('#grid').innerHTML=`<div class="state">⚠️ Search load नहीं हुआ।<br>${esc(e.message||e)}</div>`;
  }finally{loading=false;$('#srow').classList.remove('loading')}
}

$('#grid').addEventListener('click',e=>{
  const el=e.target.closest('.fname');if(!el)return;
  play(decodeURIComponent(el.dataset.fid),el.dataset.name);
});

async function play(fid,name){
  const modal=$('#modal'),v=$('#player');
  $('#pTitle').textContent='⏳ '+name;
  $('#pNote').textContent='Streaming link तैयार हो रही है…';
  modal.classList.add('open');
  v.pause();v.removeAttribute('src');
  try{
    const r=await fetch('/api/stream',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:fid})});
    if(r.status===401){location.href='/login?err='+encodeURIComponent('Session expired. Please sign in again.');return}
    const d=await r.json();
    if(!d.stream){$('#pTitle').textContent='❌ '+(d.error||'Stream unavailable');
      $('#pNote').textContent='यह फाइल अभी stream नहीं हो सकी।';return}
    currentWatch=location.origin+d.watch;
    $('#pTitle').textContent='▶ '+name;
    $('#pNote').textContent='Signed link · '+(d.expires_in||0)+' seconds valid · Range/seek supported';
    $('#pWatch').href=d.watch;
    $('#pDl').href=d.download;
    v.poster=d.poster||'';
    v.src=d.stream;
    v.load();
    v.play().catch(()=>{});
  }catch(e){$('#pTitle').textContent='❌ Stream error';
    $('#pNote').textContent=String(e.message||e)}
}
function closePlayer(){
  const v=$('#player');v.pause();v.removeAttribute('src');v.load();
  $('#modal').classList.remove('open');
}
function copyLink(){
  if(!currentWatch)return;
  navigator.clipboard.writeText(currentWatch).then(()=>{
    $('#pNote').textContent='🔗 Link copied: '+currentWatch;
  }).catch(()=>{$('#pNote').textContent=currentWatch});
}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePlayer()});
applyMode();
load(true);
</script>"""


def search_page(tg_id: int, role: str):
    """v5 जैसा sidebar वाला app shell + search body.

    * Sign Out सिर्फ़ sidebar footer में (topbar पर नहीं)।
    * Mode/Filter dropdowns desktop पर search bar के साथ एक लाइन में,
      mobile पर उसके ठीक नीचे एक ही लाइन में।
    * "Recently Added / Database Stats" वाली meta लाइन हटा दी गई —
      गिनती सिर्फ़ `/stats` (Database Stats) पेज पर।
    """
    return app_page(
        "FAST FINDER — Search Files", SEARCH_BODY,
        tg_id=tg_id, role=role, active_tab="dash",
    )
