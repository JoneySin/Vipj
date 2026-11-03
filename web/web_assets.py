"""🎨 Shared web assets: session/auth helper, page shell, CSS and the search UI.

`v5` के dashboard/miniapp जैसा look, पर fsv1 के लिए एक ही self-contained
page (कोई extra template engine / CDN dependency नहीं — सिर्फ़ Plyr CSS/JS
stream page पर optional है)।
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
.tbtn.red{background:var(--red);border-color:var(--red);color:#fff}
.search-zone{padding:18px 4% 14px;background:var(--bg);border-bottom:1px solid var(--line)}
.srow{display:flex;gap:10px;max-width:760px;position:relative}
.sinput{flex:1;min-width:0;background:var(--bg2);border:1.5px solid var(--line);
border-radius:10px;padding:13px 16px;color:var(--txt);font-size:15px;font-weight:600;
font-family:inherit;outline:none;transition:border-color .18s}
.sinput:focus{border-color:var(--red)}
.sbtn{background:var(--red);color:#fff;border:0;border-radius:10px;padding:0 26px;
font-weight:800;font-size:14px;cursor:pointer;font-family:inherit;white-space:nowrap}
.sbtn:hover{background:var(--red2)}
.spin{display:none;position:absolute;right:118px;top:50%;transform:translateY(-50%);
width:17px;height:17px;border:2px solid var(--line);border-top-color:var(--red);
border-radius:50%;animation:spin .6s linear infinite}
.srow.loading .spin{display:block}
@keyframes spin{to{transform:translateY(-50%) rotate(360deg)}}
.hint{margin-top:10px;font-size:12px;color:var(--mut);display:flex;gap:8px;
flex-wrap:wrap;align-items:center}
.chip{background:var(--bg3);border:1px solid var(--line);border-radius:20px;
padding:5px 12px;cursor:pointer;font-weight:700;font-size:11px}
.chip:hover{border-color:var(--red);color:var(--red)}
.main{padding:18px 4% 60px;max-width:1700px;margin:0 auto}
.meta{font-size:13px;color:var(--mut);font-weight:700;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media(min-width:560px){.grid{grid-template-columns:repeat(3,1fr);gap:12px}}
@media(min-width:850px){.grid{grid-template-columns:repeat(4,1fr);gap:14px}}
@media(min-width:1200px){.grid{grid-template-columns:repeat(5,1fr);gap:16px}}
@media(min-width:1600px){.grid{grid-template-columns:repeat(6,1fr)}}
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
.sub{margin-top:8px;font-size:11px;color:var(--mut);font-weight:600;
display:flex;justify-content:space-between;gap:6px}
.play-ico{color:var(--red);font-weight:900}
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
@media(max-width:520px){.srow{flex-direction:column}.sbtn{padding:13px}.spin{display:none!important}
.auth-card{padding:24px}.grid{gap:8px}}
"""


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
        f"<style>{SITE_CSS}</style></head>"
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
SEARCH_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FAST FINDER — Search Files</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>__CSS__</style></head>
<body>
<div class="top">
  <a class="logo" href="/"><span class="nfi">F</span> FAST FINDER</a>
  <span class="tbadge">#__TG_ID____ROLE__</span>
  <button class="tbtn" onclick="toggleTheme()">Theme</button>
  <a class="tbtn red" href="/logout">Sign Out</a>
</div>

<div class="search-zone">
  <div class="srow" id="srow">
    <input class="sinput" id="q" type="search" placeholder="Movie / series / file name खोजें..." autocomplete="off">
    <div class="spin"></div>
    <button class="sbtn" onclick="doSearch()">🔎 Search</button>
  </div>
  <div class="hint"><span>टिप:</span>
    <span class="chip" onclick="quick('')">🆕 Recent</span>
    <span class="chip" onclick="quick('720p')">720p</span>
    <span class="chip" onclick="quick('1080p')">1080p</span>
    <span class="chip" onclick="quick('mkv')">MKV</span>
    <span class="chip" onclick="quick('hindi')">Hindi</span>
  </div>
</div>

<div class="main">
  <div class="meta" id="meta">नई फाइलें लोड हो रही हैं…</div>
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
(function(){if(localStorage.getItem('ff_theme')==='light')document.documentElement.classList.add('light')})();
function toggleTheme(){var l=document.documentElement.classList.toggle('light');localStorage.setItem('ff_theme',l?'light':'dark')}
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let curQ='',offset=0,loading=false,hasMore=false,currentWatch='';
let debounce=null;

function quick(q){$('#q').value=q;doSearch()}
function doSearch(){curQ=$('#q').value.trim();load(true)}
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter')doSearch()});
$('#q').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{
  const v=$('#q').value.trim();if(v.length>=2||v==='')doSearch()},420)});

function card(f){
  const fid=encodeURIComponent(f.file_id);
  const dur=f.duration?`<span class="tg gold">${esc(f.duration)}</span>`:'';
  const q=f.quality&&f.quality!=='unknown'?`<span class="tg blue">${esc(f.quality)}</span>`:'';
  const res=f.res?`<span class="tg">${esc(f.res)}</span>`:'';
  return `<div class="card">
    <div class="poster" id="pb-${fid}">
      <img src="${encodeURI(f.thumb)}" alt="" loading="lazy"
           onload="this.classList.add('on')" onerror="thumbFail(this)">
      <div class="ph"><b>▶</b><span>NO THUMBNAIL</span></div>
      <div class="chips"><span class="tg">${esc(f.type)}</span>${q}${res}${dur}</div>
    </div>
    <div class="body">
      <div class="fname" data-fid="${fid}" data-name="${esc(f.name)}"
           title="Stream करने के लिए क्लिक करें">${esc(f.name)}</div>
      <div class="sub"><span>${esc(f.size)}</span><span class="play-ico">▶ Stream</span></div>
    </div></div>`;
}
function thumbFail(img){
  img.classList.add('hidden');
  const p=img.closest('.poster');if(p)p.classList.add('no-thumb');
}

async function load(reset){
  if(loading)return;
  if(reset){offset=0;hasMore=false;$('#grid').innerHTML='';}
  loading=true;$('#srow').classList.add('loading');
  try{
    const r=await fetch(`/api/search?q=${encodeURIComponent(curQ)}&offset=${offset}`,{credentials:'same-origin'});
    if(r.status===401){location.href='/login?err='+encodeURIComponent('Session expired. Please sign in again.');return}
    const d=await r.json();
    const list=d.results||[];
    $('#grid').insertAdjacentHTML('beforeend',list.map(card).join(''));
    hasMore=!!d.next_offset;
    offset=hasMore?Number(d.next_offset):0;
    $('#more').classList.toggle('show',hasMore);
    $('#meta').innerHTML=curQ
      ? `<b>"${esc(curQ)}"</b> — ${esc(d.total||list.length)} results`
      : `🆕 Recently Added — ${esc(d.total||list.length)} files`;
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
load(true);
</script>
</body></html>"""


def search_page(tg_id: int, role: str):
    html_out = SEARCH_HTML.replace("__CSS__", SITE_CSS)
    html_out = html_out.replace("__TG_ID__", str(tg_id))
    html_out = html_out.replace(
        "__ROLE__", " · ADMIN" if role == "admin" else ""
    )
    return html_response(html_out)
