"""🎨 Shared web assets: session/auth helper, page shell, CSS and the search UI.

`v5` के dashboard/miniapp जैसा look — sidebar (Home / Database Stats /
Profile Settings / Sign Out), stats cards और profile settings, पर fsv1 के
लिए एक ही self-contained page (कोई extra template engine नहीं)।

▶ `PLAYER_MODAL_HTML` + `PLAYER_JS` एक **shared player component** है: `/search`
के अलावा `/post/<id>` और `/actor/<id>` के Videos tabs भी यही modal, यही
`/api/stream` flow और यही signed watch/download actions इस्तेमाल करते हैं।
JS एक IIFE में `window.play/closePlayer/copyLink` expose करता है, इसलिए हर
page के अपने `$` / `esc` / `const` से कोई नाम-टकराव नहीं होता।

✏️ `FILE_EDIT_HTML` + `FILE_EDIT_JS` admin-only **file editor** है — v5 के
`Edit Title Metadata` (name / caption / poster / delete) का fsv1
रूप: JSON API, बिना CDN का 16:9 canvas crop, बिना reload card update।

🎛️ `FILTER_CSS` + `FILTER_JS` एक **shared filter dropdown component** है —
सिर्फ़ `<select class="filter-dd">` लिखो, `SITE_JS` का `FilterDD` engine उसे
styled button + custom options menu में upgrade कर देता है (MutationObserver से
बाद में आने वाले selects भी)। Native select hidden रहकर `value`/`change` बनाए
रखता है, इसलिए पुराना JS बिल्कुल नहीं बदलना पड़ता। **Dropdown का पूरा UI इसी एक
जगह है** — बदलाव एक file में करो, `/search`, `/posts`, `/actors`, editor modals
सब में दिखेगा। **Filter buttons की options/specs भी यहीं** `FILTER_OPTIONS` +
`SEARCH_FILTERS`/`CATALOG_FILTERS` + `filter_buttons()` में — कोई page अपना
`<option>` नहीं लिखता, `sel.value=` लिखते ही label अपने आप sync हो जाता है
(किसी page पर अलग `ddSet()` code नहीं)। Mobile पर दोनों toolbar एक ही
`.filters` row + एक ही `@media` नियम: search bar ऊपर, दो बराबर buttons नीचे।

🎴 `VCARD_TEMPLATE` + `VCARD_CHIP_SPEC` + `vcard_meta()` — **video card का
एकमात्र source**: markup, chips (size/duration/quality/res/type) और data
normalization सब यहीं। Python `render_vcard()` और JS `vcardHTML()` उसी एक
template/spec को भरते हैं; `/search`, Post attached videos, Actor tag-results
तीनों बिल्कुल एक जैसे cards दिखाते हैं। बदलाव = सिर्फ़ यहाँ।

🎴 `VIDEO_CARD_CSS` एक **shared video card** है — `/search` की grid और
Post/Actor Videos tabs बिल्कुल वही `.vcard`/`.vgrid` markup वाली cards,
वही 1/2/3 responsive grid और नाम के नीचे वही compact padding दिखाती हैं।
"""

import html
import json
import time

from web.group_assets import (
    GROUP_CSS, GROUP_JS, GROUP_ADMIN_HTML, GROUP_ADMIN_JS,
)
from web.mode_assets import VIEW_MODE_OPTIONS, MODE_CSS, MODE_JS

from aiohttp import web

from info import ADMINS
from utils import temp, get_size
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
VIDEO_CARD_CSS = r"""
/* ─────────────────────────────────────────────────────────────
   ▶ SHARED VIDEO CARD — /search + /post/<id> + /actor/<id> Videos tabs
   सब एक ही `.vcard` markup, एक ही `.vgrid` (📱 1 / 📟 2 / 🖥️ 3) और
   नाम के नीचे minimum padding इस्तेमाल करते हैं।
   ───────────────────────────────────────────────────────────── */
.vgrid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:620px){.vgrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
@media(min-width:1024px){.vgrid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
.vgrid>.vempty,.vgrid>.state,.vgrid>.cat-vempty{grid-column:1/-1}
.vcard{display:block;position:relative;overflow:hidden;background:var(--card);
border:1px solid var(--line);border-radius:10px;color:var(--txt);cursor:pointer;
text-decoration:none;transition:transform .22s,border-color .22s,box-shadow .28s}
.vcard:focus-visible{outline:2px solid var(--red);outline-offset:2px}
@media(hover:hover){.vcard:hover{transform:translateY(-4px);border-color:rgba(229,9,20,.65);
box-shadow:0 14px 34px rgba(0,0,0,.45)}}
.vcard.enter{opacity:0}
.vcard.enter.in{animation:vIn .48s cubic-bezier(.34,1.2,.64,1) forwards}
@keyframes vIn{0%{opacity:0;transform:translateY(18px) scale(.97)}100%{opacity:1;transform:none}}
@keyframes sh{0%{background-position:200% 0}100%{background-position:-200% 0}}
.vposter{position:relative;aspect-ratio:16/9;overflow:hidden;
background:linear-gradient(90deg,var(--bg3) 0,#2b2b3a 50%,var(--bg3) 100%);
background-size:200% 100%;animation:sh 1.5s infinite linear}
.vposter.no-thumb{animation:none;background:none}
.vimg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;
transition:opacity .3s,transform .35s}
.vimg.on{opacity:1}.vimg.hidden{display:none}
.vcard:hover .vimg.on{transform:scale(1.05)}
.vph{position:absolute;inset:0;display:none;align-items:center;justify-content:center;
flex-direction:column;gap:4px;color:var(--mut);font-size:11px;font-weight:800;
letter-spacing:1px;background:linear-gradient(135deg,#1b1b28,#101018)}
.vposter.no-thumb .vph{display:flex}
.vph b{font-size:30px;color:var(--red)}
.vchips{position:absolute;top:0;left:0;right:0;z-index:2;display:flex;gap:5px;
padding:7px;flex-wrap:wrap;pointer-events:none}
.vtag{background:rgba(0,0,0,.78);backdrop-filter:blur(6px);color:#fff;border-radius:5px;
padding:3px 7px;font-size:10px;font-weight:800;border:1px solid rgba(255,255,255,.14)}
.vtag.gold{color:var(--gold);border-color:rgba(255,209,102,.4)}
.vtag.blue{color:#93c5fd;border-color:rgba(147,197,253,.35)}
.vsize{position:absolute;right:7px;bottom:7px;z-index:2;pointer-events:none;
background:rgba(0,0,0,.78);backdrop-filter:blur(6px);color:#fff;border-radius:5px;
padding:3px 7px;font-size:10px;font-weight:800;border:1px solid rgba(255,255,255,.14)}
.vplay{position:absolute;inset:0;z-index:2;display:flex;align-items:center;justify-content:center;
font-size:30px;background:linear-gradient(transparent,rgba(0,0,0,.5));
opacity:0;transition:opacity .2s;pointer-events:none}
.vcard:hover .vplay{opacity:1}
.vposter{cursor:pointer}
/* 📸 v5 जैसा: thumbnail पर click → उसी poster के अंदर Edit/Delete बार slide-up */
.vadmin{position:absolute;left:0;right:0;bottom:0;z-index:5;display:flex;gap:6px;
padding:9px 8px;background:linear-gradient(transparent,rgba(0,0,0,.9) 45%);
opacity:0;visibility:hidden;transform:translateY(10px);pointer-events:none;
transition:opacity .2s ease,transform .22s ease,visibility .2s}
.vcard.admin-active .vposter::after{content:'';position:absolute;inset:0;z-index:4;
background:rgba(0,0,0,.42);pointer-events:none}
.vcard.admin-active .vadmin{opacity:1;visibility:visible;transform:translateY(0);pointer-events:all}
.vadmin button{flex:1;padding:8px 4px;border-radius:6px;font-size:11px;font-weight:800;
font-family:inherit;cursor:pointer;color:#fff;border:1px solid rgba(255,255,255,.2);
backdrop-filter:blur(8px);transition:background .12s,transform .1s}
.vadmin .va-edit{background:rgba(42,42,48,.9)}
.vadmin .va-edit:hover{background:rgba(80,80,88,.96)}
.vadmin .va-del{background:rgba(160,8,8,.82);border-color:rgba(229,9,20,.5)}
.vadmin .va-del:hover{background:rgba(229,9,20,.95)}
.vadmin button:active{transform:scale(.94)}
/* ✅ नाम के नीचे का extra space हटाया — सिर्फ़ उतनी ही padding जितनी ज़रूरी */
.vbody{padding:8px 11px 9px}
.vtitle{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
font-size:13px;font-weight:700;line-height:1.35;cursor:pointer;transition:color .18s}
.vcard:hover .vtitle{color:var(--red)}
.state{grid-column:1/-1;text-align:center;padding:70px 20px;color:var(--mut);
font-weight:600;line-height:1.7}
@media(prefers-reduced-motion:reduce){
.vcard,.vcard.enter,.vcard.enter.in,.vposter{animation:none!important;
transition:none!important;opacity:1!important;transform:none!important}
}
"""


# 🎨 SHARED CSS
# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# 🎴 SHARED VIDEO CARD — markup + chips + data का **एकमात्र source**
#   `/search`, Post attached videos, Actor tag-results तीनों यहीं से बनते हैं:
#     Python  → render_vcard() / vcard_chips() / vcard_size()
#     JS      → vcardHTML()    / vcardChips() / vcardSize()  (SITE_JS में नीचे)
#   Template और chip spec दोनों एक बार लिखे हैं — JS को यही Python values
#   json.dumps करके दी जाती हैं। chip जोड़ना/हटाना/क्रम बदलना/रंग बदलना
#   हो → सिर्फ़ VCARD_CHIP_SPEC बदलो, तीनों जगह एक साथ बदलेगा।
# ─────────────────────────────────────────────────────────────
# ⚠️ "VIDEO"/"FILE" टाइप chip हटा दी गई — thumbnail पर अब सिर्फ़
#    quality → res → duration chips हैं। `type` payload में रह सकता है
#    (API/editor इस्तेमाल करते हैं), पर card पर chip नहीं बनती।
VCARD_CHIP_SPEC = (
    ("quality",  "vtag blue", ("unknown",)),
    ("res",      "vtag",      ()),
    ("duration", "vtag gold", ()),
)

VCARD_TEMPLATE = (
    '<div class="vcard vm-card{CARD_CLASS}" role="button" tabindex="0"{EXTRA_ATTRS} '
    'data-fid="{FID}" data-name="{NAME}" aria-label="Play {NAME}">'
    '<div class="vposter vm-poster"{POSTER_ID}>'
    '<img class="vimg vm-img" {IMG_ATTRS} alt="" loading="lazy" '
    'onload="this.classList.add(\'on\')" onerror="{IMG_ERROR}">'
    '<div class="vph vm-ph vm-overlay"><b>▶</b><span>NO THUMBNAIL</span></div>'
    '<div class="vchips vm-details">{CHIPS}</div>{SIZE}'
    '<span class="vplay vm-overlay">▶</span>'
    '<div class="vadmin vm-actions"><button class="va-edit" data-fid="{RAW_FID}">✏️ Edit</button>'
    '<button class="va-del" data-fid="{RAW_FID}">🗑️ Delete</button></div>'
    '</div><div class="vbody vm-body"><div class="vtitle vm-title">{NAME}</div></div></div>'
)

_VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts",
              ".wmv", ".flv", ".mpeg", ".mpg")


def vcard_is_video(doc) -> bool:
    """Library doc video है या नहीं — सभी card payloads यहीं से `type` लेते हैं।"""
    doc = doc or {}
    name = str(doc.get("file_name") or "").lower()
    mime = str(doc.get("mime_type") or "").lower()
    return (doc.get("file_type") == "video" or mime.startswith("video/")
            or name.endswith(_VIDEO_EXT))


def _vcard_duration(value) -> str:
    try:
        sec = int(value or 0)
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def vcard_meta(doc) -> dict:
    """🎴 एकमात्र card-data normalizer — `/api/search`, `/api/catalog/{kind}/media`
    और attached-video enrichment सब यही size/duration/res/quality/type लेते हैं,
    इसलिए तीनों जगह chips का text भी बिल्कुल एक जैसा होता है।"""
    doc = doc or {}
    fid = str(doc.get("_id") or "")
    try:
        w = int(doc.get("width") or 0)
    except (TypeError, ValueError):
        w = 0
    try:
        h = int(doc.get("height") or 0)
    except (TypeError, ValueError):
        h = 0
    return {
        "file_id": fid,
        "name": str(doc.get("file_name") or "Untitled"),
        "size": get_size(doc.get("file_size") or 0),
        "quality": str(doc.get("quality") or ""),
        "type": "VIDEO" if vcard_is_video(doc) else "FILE",
        "duration": _vcard_duration(doc.get("duration")),
        "res": f"{w}×{h}" if w and h else "",
    }


def vcard_chips(data) -> str:
    """सभी `.vchips` — order/class/skip rules सिर्फ़ VCARD_CHIP_SPEC में।"""
    data = data or {}
    out = []
    for field, cls, skip in VCARD_CHIP_SPEC:
        val = str(data.get(field) or "").strip()
        if not val or val.lower() in skip:
            continue
        out.append(f'<span class="{cls}">{html.escape(val)}</span>')
    return "".join(out)


def vcard_size(data) -> str:
    val = str((data or {}).get("size") or "").strip()
    return f'<span class="vsize vm-size">{html.escape(val)}</span>' if val else ""


def render_vcard(**kw) -> str:
    """Python-side card render — उसी VCARD_TEMPLATE से जो JS इस्तेमाल करता है।"""
    tokens = {k: "" for k in (
        "CARD_CLASS", "EXTRA_ATTRS", "POSTER_ID", "IMG_ATTRS", "IMG_ERROR",
        "CHIPS", "SIZE", "FID", "NAME", "RAW_FID")}
    tokens.update({k: str(v) for k, v in kw.items()})
    return VCARD_TEMPLATE.format(**tokens)


_VCARD_JS_TPL = r"""/* 🎴 SHARED VIDEO CARD — template + chip spec web_assets.py से (Python → JS) */
(function(){
  var TPL=__VCARD_TEMPLATE__, SPEC=__VCARD_CHIP_SPEC__;
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function chips(f){
    f=f||{};
    return SPEC.map(function(c){
      var v=String(f[c[0]]==null?'':f[c[0]]).trim();
      if(!v||c[2].indexOf(v.toLowerCase())>=0)return '';
      return '<span class="'+c[1]+'">'+esc(v)+'</span>';
    }).join('');
  }
  function vsize(f){
    var s=String((f||{}).size==null?'':f.size).trim();
    return s?'<span class="vsize vm-size">'+esc(s)+'</span>':'';
  }
  function html(t){
    t=t||{};
    return TPL.replace(/\{([A-Z_]+)\}/g,function(m,k){
      return Object.prototype.hasOwnProperty.call(t,k)?String(t[k]):'';
    });
  }
  window.vcardChips=chips;window.vcardSize=vsize;window.vcardHTML=html;
})();
"""
VCARD_JS = (_VCARD_JS_TPL
            .replace("__VCARD_TEMPLATE__", json.dumps(VCARD_TEMPLATE))
            .replace("__VCARD_CHIP_SPEC__",
                     json.dumps([list(x) for x in VCARD_CHIP_SPEC])))

FILE_EDIT_HTML = r"""<style>
/* ✏️ Shared FILE EDITOR — v5 "Edit Title Metadata" का fsv1 रूप (कोई CDN नहीं) */
.femodal{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.88);display:none;
align-items:center;justify-content:center;padding:14px}
.femodal.open{display:flex}
.fecard{background:var(--bg2);border:1px solid var(--line);border-radius:14px;width:100%;
max-width:640px;max-height:92vh;display:flex;flex-direction:column;overflow:hidden;
box-shadow:0 24px 70px rgba(0,0,0,.7)}
.fehead{display:flex;align-items:center;gap:10px;padding:13px 16px;border-bottom:1px solid var(--line)}
.fetitle{flex:1;font-weight:900;font-size:15px}
.fex{background:transparent;border:0;color:var(--mut);font-size:22px;cursor:pointer;line-height:1}
.febody{padding:14px 16px;overflow-y:auto}
.feposter{position:relative;width:100%;aspect-ratio:16/9;background:#000;border:1px solid var(--line);
border-radius:9px;overflow:hidden;margin-bottom:10px}
.feposter img,.feposter canvas{width:100%;height:100%;object-fit:contain;display:block}
.feposter canvas{object-fit:cover;cursor:grab;touch-action:none;display:none}
.feposter canvas:active{cursor:grabbing}
.fethumbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.fezoom{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:800;color:var(--mut);flex:1;min-width:130px}
.fezoom input{flex:1;min-width:70px;accent-color:var(--red)}
.febtn{border:1px solid var(--line);border-radius:8px;padding:9px 13px;font-size:12px;font-weight:800;
cursor:pointer;font-family:inherit;background:var(--bg3);color:var(--txt);transition:border-color .15s,transform .1s}
.febtn:hover{border-color:var(--red)}.febtn:active{transform:scale(.96)}
.febtn:disabled{opacity:.5;cursor:not-allowed}
.febtn.save{background:var(--red);border-color:var(--red);color:#fff}
.febtn.danger{background:rgba(160,8,8,.35);border-color:rgba(229,9,20,.5)}
.festate,.festatus{font-size:11px;color:var(--mut);font-weight:700;margin:6px 0 12px;min-height:15px}
.fegrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:560px){.fegrid{grid-template-columns:1fr}}
.fegrid label{display:flex;flex-direction:column;gap:5px;font-size:11px;font-weight:800;color:var(--mut)}
.fegrid label.wide{grid-column:1/-1}
.fegrid input,.fegrid select,.fegrid textarea{width:100%;box-sizing:border-box;background:var(--bg3);
border:1px solid var(--line);border-radius:8px;padding:9px 11px;color:var(--txt);font:700 13px inherit;
font-family:inherit;outline:none}
.fegrid textarea{resize:vertical;min-height:58px}
.fegrid input:focus,.fegrid select:focus,.fegrid textarea:focus{border-color:var(--red)}
.fefoot{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--line);flex-wrap:wrap}
.fefoot .save{margin-left:auto}
.fetoast{position:fixed;left:50%;bottom:22px;z-index:420;transform:translate(-50%,160%);
opacity:0;background:var(--bg2);border:1px solid var(--line);border-left:4px solid #2ecc71;
color:var(--txt);border-radius:10px;padding:11px 17px;font-size:12px;font-weight:800;
box-shadow:0 12px 34px rgba(0,0,0,.55);transition:transform .3s,opacity .3s;max-width:92vw}
.fetoast.show{transform:translate(-50%,0);opacity:1}
.fetoast.err{border-left-color:var(--red)}
</style>
<div class="femodal" id="feModal" onclick="if(event.target===this)closeFileEdit()">
  <div class="fecard">
    <div class="fehead"><div class="fetitle">✏️ Edit File Metadata</div>
      <button class="fex" onclick="closeFileEdit()" aria-label="Close">✕</button></div>
    <div class="febody">
      <div class="feposter"><img id="fePoster" src="" alt="Current poster">
        <canvas id="feCanvas" width="1280" height="720"></canvas></div>
      <div class="fethumbar">
        <label class="febtn">📂 New poster<input type="file" id="feFile" accept="image/*" hidden></label>
        <label class="fezoom">Zoom <input type="range" id="feZoom" min="1" max="3" step="0.05" value="1"></label>
        <button class="febtn" id="feReset">🔄 Original</button>
      </div>
      <div class="festate" id="feThumbState">🖼️ Telegram original</div>
      <div class="fegrid">
        <label class="wide">📝 File name<input id="feName" type="text" maxlength="300"></label>
        <label class="wide">🏷️ Caption / Search tags<textarea id="feCaption" maxlength="1000"
          placeholder="e.g. Ajay Devgan, 1080p, Comedy…"></textarea></label>
        <label>🎞️ Quality<select class="filter-dd" id="feQuality" data-fdd-full="1" data-fdd-cap="Quality">
          <option value="">Unknown</option><option value="144p">144p</option>
          <option value="240p">240p</option><option value="360p">360p</option>
          <option value="480p">480p</option><option value="720p">720p</option>
          <option value="1080p">1080p</option><option value="1440p">1440p</option>
          <option value="2160p">2160p</option><option value="4K">4K</option>
          <option value="8K">8K</option><option value="HD">HD</option>
          <option value="HDR">HDR</option></select></label>
        <label>⏱️ Duration<input id="feDuration" type="text" placeholder="1:36:22"></label>
        <label>📐 Resolution<input id="feRes" type="text" placeholder="1920×1080"></label>
      </div>
      <div class="festatus" id="feStatus">…</div>
    </div>
    <div class="fefoot">
      <button class="febtn danger" id="feDelete">🗑️ Delete file</button>
      <button class="febtn" onclick="closeFileEdit()">Cancel</button>
      <button class="febtn save" id="feSave">💾 Save Changes</button>
    </div>
  </div>
</div>
<div class="fetoast" id="feToast"></div>"""

FILE_EDIT_JS = r"""<script>
(function(){
  const q = s => document.querySelector(s);
  const esc = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current=null, crop=null, busy=false, toastTimer=null;
  function toast(msg, err){
    const t=q('#feToast'); if(!t) return;
    t.textContent=msg; t.classList.toggle('err',!!err); t.classList.add('show');
    clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.classList.remove('show'),3200);
  }
  function isOpen(){ const m=q('#feModal'); return !!m && m.classList.contains('open'); }
  function cards(fid){
    return Array.prototype.filter.call(document.querySelectorAll('.vcard[data-fid]'),c=>{
      try{ return decodeURIComponent(c.dataset.fid)===fid; }catch(e){ return c.dataset.fid===fid; }
    });
  }
  function syncCard(f){
    const list=cards(f.file_id);
    list.forEach(c=>{
      if(c.dataset.label!=='1'){
        const t=c.querySelector('.vtitle'); if(t) t.textContent=f.name;
        c.dataset.name=f.name; c.setAttribute('aria-label','Play '+f.name);
      }
      // chips + size भी उसी shared spec से — edit के बाद card अलग न दिखे
      const chips=c.querySelector('.vchips');
      if(chips) chips.innerHTML=vcardChips(f);
      const sz=c.querySelector('.vsize');
      if(sz) sz.outerHTML=vcardSize(f);
      const im=c.querySelector('.vimg');
      if(im && f.thumb){ im.src=f.thumb; im.classList.remove('hidden'); }
    });
  }
  function setPoster(f){
    const im=q('#fePoster'); if(!im) return;
    im.src=f.thumb+'&t='+Date.now(); im.style.display='block';
    const cv=q('#feCanvas'); if(cv) cv.style.display='none';
    const st=q('#feThumbState');
    if(st) st.textContent=f.custom_thumb?'📸 Custom poster (web upload)':'🖼️ Telegram original';
  }
  function drawCrop(){
    const cv=q('#feCanvas'); if(!cv) return;
    const ctx=cv.getContext && cv.getContext('2d'); if(!ctx) return;
    ctx.fillStyle='#000'; ctx.fillRect(0,0,1280,720);
    if(!crop||!crop.img) return;
    const im=crop.img, scale=Math.max(1280/im.width,720/im.height)*crop.zoom;
    const w=im.width*scale, h=im.height*scale;
    let x=(1280-w)/2+crop.x, y=(720-h)/2+crop.y;
    x=Math.min(0,Math.max(1280-w,x)); y=Math.min(0,Math.max(720-h,y));
    crop.x=x-(1280-w)/2; crop.y=y-(720-h)/2;
    ctx.drawImage(im,x,y,w,h);
  }
  function loadLocal(input){
    const file=input.files&&input.files[0]; if(!file) return;
    const rd=new FileReader();
    rd.onload=e=>{
      const im=new Image();
      im.onload=()=>{
        crop={img:im,zoom:1,x:0,y:0,dragging:false};
        q('#feZoom').value=1;
        const po=q('#fePoster'); if(po) po.style.display='none';
        const cv=q('#feCanvas'); if(cv) cv.style.display='block';
        drawCrop();
        q('#feStatus').textContent='✂️ 16:9 crop — drag से position, slider से zoom';
      };
      im.src=e.target.result;
    };
    rd.readAsDataURL(file);
  }
  function open(fid){
    if(!fid||!q('#feModal')) return;
    current=String(fid); crop=null; busy=false;
    q('#feModal').classList.add('open');
    q('#feStatus').textContent='लोड हो रहा है…';
    q('#feFile').value=''; q('#feZoom').value=1;
    fetch('/api/file/meta?id='+encodeURIComponent(current),{credentials:'same-origin'})
      .then(r=>r.json()).then(d=>{
        if(!d.ok){ q('#feStatus').textContent=d.error||'Load failed'; return; }
        const f=d.file;
        q('#feName').value=f.name; q('#feCaption').value=f.caption;
        q('#feDuration').value=f.duration; q('#feRes').value=f.res;
        const sel=q('#feQuality');
        if(f.quality && !Array.prototype.some.call(sel.options,o=>o.value===f.quality))
          sel.add(new Option(f.quality,f.quality));
        sel.value=f.quality||'';
        q('#feStatus').textContent='✏️ ID: '+esc(f.file_id)+' · '+esc(f.size)+' · '+esc(f.quality||'—');
        setPoster(f);
      }).catch(e=>{ q('#feStatus').textContent='Load error: '+String(e.message||e); });
  }
  function close(){
    const m=q('#feModal'); if(m) m.classList.remove('open');
    current=null; crop=null; busy=false;
  }
  function setBusy(v){
    busy=v;
    const b=q('#feSave'); if(b){ b.disabled=v; b.textContent=v?'Processing…':'💾 Save Changes'; }
  }
  async function save(){
    if(!current||busy) return;
    const payload={file_id:current,name:q('#feName').value,caption:q('#feCaption').value,
      quality:q('#feQuality').value,duration:q('#feDuration').value,
      res:q('#feRes').value};
    setBusy(true);
    try{
      const r=await fetch('/api/file/edit',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const d=await r.json();
      if(!d.ok){ toast(d.error||'Save failed',true); return; }
      let f=d.file;
      if(crop && crop.img){
        const cv=q('#feCanvas');
        const blob=await new Promise(res=>{
          if(!cv.toBlob){ res(null); return; }
          cv.toBlob(res,'image/jpeg',0.9);
        });
        if(blob){
          const fd=new FormData(); fd.append('file_id',current);
          fd.append('image',blob,'poster.jpg');
          const ur=await fetch('/api/file/thumb',{method:'POST',credentials:'same-origin',body:fd});
          const ud=await ur.json();
          if(ud.ok) f=ud.file; else toast('Poster: '+(ud.error||'upload failed'),true);
        }
      }
      syncCard(f); setPoster(f); toast('✨ File updated — बिना reload'); close();
    }catch(e){ toast('Network error: '+String(e.message||e),true); }
    finally{ setBusy(false); }
  }
  async function resetThumb(){
    if(!current||busy) return;
    if(!confirm('Custom poster हटाकर Telegram की original thumbnail लाएँ?')) return;
    setBusy(true);
    try{
      const r=await fetch('/api/file/thumb_reset',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:current})});
      const d=await r.json();
      if(!d.ok){ toast(d.error||'Reset failed',true); return; }
      syncCard(d.file); setPoster(d.file);
      toast('🔄 Original thumbnail serial queue में डाली गई');
    }catch(e){ toast('Network error: '+String(e.message||e),true); }
    finally{ setBusy(false); }
  }
  async function deleteById(fid){
    if(!fid||busy) return;
    if(!confirm('इस file को database से permanently हटाएँ?')) return;
    setBusy(true);
    try{
      const r=await fetch('/api/file/delete',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:fid})});
      const d=await r.json();
      if(!d.ok){ toast(d.error||'Delete failed',true); return; }
      cards(fid).forEach(c=>c.remove());
      toast('🗑️ File deleted');
      if(current===fid) close();
    }catch(e){ toast('Network error: '+String(e.message||e),true); }
    finally{ setBusy(false); }
  }
  function remove(){ if(current) return deleteById(current); }

  /* ── 📸 v5-style: thumbnail के अंदर Edit/Delete overlay ─────── */
  function closeAdmin(){
    Array.prototype.forEach.call(document.querySelectorAll('.vcard.admin-active'),
      c=>c.classList.remove('admin-active'));
  }
  function toggleAdmin(card){
    const was=card.classList.contains('admin-active');
    closeAdmin();                         /* एक समय पर सिर्फ़ एक card खुला */
    if(!was) card.classList.add('admin-active');
  }
  function fidOf(node){
    let fid=node&&node.dataset?node.dataset.fid:'';
    if(!fid){
      const c=node&&node.closest?node.closest('.vcard[data-fid]'):null;
      fid=c?c.dataset.fid:'';
    }
    try{ return decodeURIComponent(fid||''); }catch(err){ return fid||''; }
  }
  window.openFileEdit=open; window.closeFileEdit=close;
  window.closeFileActions=closeAdmin; window.deleteFileById=deleteById;
  document.addEventListener('click',e=>{
    const t=e.target, near=(sel)=>t&&t.closest?t.closest(sel):null;
    const act=near('.vadmin button');
    if(act){                              /* ✏️ Edit / 🗑️ Delete */
      e.preventDefault(); e.stopPropagation();
      const fid=fidOf(act); closeAdmin();
      if(act.classList.contains('va-del')){ if(fid) deleteById(fid); }
      else if(fid) open(fid);
      return;
    }
    const poster=near('.vcard .vposter');
    if(poster){
      const card=poster.closest('.vcard[data-fid]');
      if(card){
        e.preventDefault(); e.stopPropagation();   /* player न खुले — overlay खुले */
        toggleAdmin(card);
        return;
      }
    }
    closeAdmin();                         /* बाहर click → सब overlay बंद */
  },true);
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){
      if(document.querySelector('.vcard.admin-active')){ closeAdmin(); return; }
      if(isOpen()){ close(); return; }
      return;
    }
    if(!isOpen()) return;
    if((e.ctrlKey||e.metaKey)&&String(e.key).toLowerCase()==='s'){ e.preventDefault(); save(); }
  });
  q('#feSave').addEventListener('click',save);
  q('#feReset').addEventListener('click',resetThumb);
  q('#feDelete').addEventListener('click',remove);
  q('#feFile').addEventListener('change',e=>loadLocal(e.target));
  q('#feZoom').addEventListener('input',e=>{
    if(crop){ crop.zoom=Number(e.target.value); drawCrop(); }
  });
  const cv=q('#feCanvas');
  if(cv){
    cv.addEventListener('pointerdown',e=>{
      if(!crop) return;
      crop.dragging=true; crop.sx=e.clientX; crop.sy=e.clientY;
    });
    cv.addEventListener('pointermove',e=>{
      if(!crop||!crop.dragging) return;
      const r=cv.getBoundingClientRect();
      crop.x+=(e.clientX-crop.sx)*(1280/(r.width||1280));
      crop.y+=(e.clientY-crop.sy)*(720/(r.height||720));
      crop.sx=e.clientX; crop.sy=e.clientY; drawCrop();
    });
    cv.addEventListener('pointerup',()=>{ if(crop) crop.dragging=false; });
  }
})();
</script>"""


FILTER_CSS = r"""
/* ═══════════════════════════════════════════════════════════════════
   🎛️ SHARED FILTER DROPDOWN — हर filter control का UI सिर्फ़ यहीं
   कोई भी <select class="filter-dd"> अपने आप इसी component में बदल जाता है
   (SITE_JS का FilterDD engine)। बदलाव = सिर्फ़ यह CSS + नीचे वाला JS।
   ═══════════════════════════════════════════════════════════════════ */
.fdd{position:relative;display:inline-flex;min-width:132px;flex:0 0 auto;vertical-align:middle}
.fdd.full{display:flex;width:100%;min-width:0}
.fdd-btn{display:flex;align-items:center;gap:8px;width:100%;min-height:42px;
box-sizing:border-box;padding:10px 12px;background:var(--bg3);border:1.5px solid var(--line);
border-radius:10px;color:var(--txt);font:800 12px 'DM Sans',sans-serif;
font-family:'DM Sans',sans-serif;cursor:pointer;text-align:left;
transition:border-color .18s,background .18s,box-shadow .18s,transform .1s}
.fdd-btn:hover{border-color:var(--red);background:var(--bg2)}
.fdd.open .fdd-btn{border-color:var(--red);background:var(--bg2);
box-shadow:0 0 0 3px rgba(229,9,20,.13)}
.fdd-btn:active{transform:scale(.98)}
.fdd-ico{font-size:15px;line-height:1;flex:0 0 auto}
.fdd-label{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.fdd-arrow{flex:0 0 auto;font-size:10px;color:var(--mut);transition:transform .2s}
.fdd.open .fdd-arrow{transform:rotate(180deg)}
.fdd-menu{position:absolute;top:calc(100% + 8px);left:0;z-index:150;
min-width:100%;max-width:min(320px,90vw);max-height:300px;overflow-y:auto;
box-sizing:border-box;padding:6px;background:var(--bg2);border:1.5px solid var(--line);
border-radius:12px;box-shadow:0 18px 48px rgba(0,0,0,.62);display:none;
animation:fddIn .16s ease-out}
.fdd.open .fdd-menu{display:block}
.fdd.up .fdd-menu{top:auto;bottom:calc(100% + 8px)}
@keyframes fddIn{from{opacity:0;transform:translateY(-6px) scale(.98)}to{opacity:1;transform:none}}
.fdd-cap{padding:6px 10px 9px;font-size:10px;font-weight:900;letter-spacing:1px;
text-transform:uppercase;color:var(--mut);border-bottom:1px solid var(--line);margin-bottom:4px}
.fdd-item{display:flex;align-items:center;gap:10px;width:100%;box-sizing:border-box;
padding:10px 11px;border:0;border-radius:8px;background:transparent;color:var(--txt);
font:700 12px 'DM Sans',sans-serif;font-family:'DM Sans',sans-serif;
cursor:pointer;text-align:left;transition:background .12s,color .12s}
.fdd-item:hover,.fdd-item:focus-visible{background:var(--bg3);outline:none}
.fdd-item[aria-selected=true]{background:rgba(229,9,20,.14);color:var(--red)}
.fdd-opt-ico{font-size:15px;width:18px;flex:0 0 18px;text-align:center}
.fdd-opt-text{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.fdd-tick{flex:0 0 auto;color:var(--red);font-weight:900;opacity:0}
.fdd-item[aria-selected=true] .fdd-tick{opacity:1}
.fdd > select.fdd-native{position:absolute!important;left:0!important;top:0!important;
width:1px!important;height:1px!important;padding:0!important;border:0!important;
opacity:0!important;pointer-events:none!important;clip:rect(0,0,0,0)!important;
overflow:hidden!important}
/* container layout भी यहीं — filter row की base + mobile CSS एक ही ब्लॉक में */
.filters{display:flex;gap:10px;align-items:center;flex:0 0 auto}
.filters .fdd{min-width:132px}
/* 📱 mobile: /search और /posts–/actors **एक ही नियम** — search bar अपनी लाइन,
   filter buttons उसी `.filters` row में ठीक नीचे, बराबर चौड़ाई के। */
@media(max-width:760px){
.qwrap,.cat-toolbar .cat-search{flex:1 1 100%}
.filters{flex:1 1 100%}
.filters .fdd{flex:1 1 0;min-width:0}
/* ⚠️ CATALOG_CSS का <style> head के बाद आता है → specificity (0,2,0) ज़रूरी */
.cat-toolbar.cat-toolbar{background:transparent;border:0;border-radius:0;padding:0;gap:10px}
}
@media(prefers-reduced-motion:reduce){.fdd-menu{animation:none}.fdd-btn,.fdd-arrow{transition:none}}
"""

FILTER_JS = r"""
/* 🎛️ SHARED FILTER DROPDOWN ENGINE — सभी <select class="filter-dd"> यहीं से upgrade.
   Native <select> DOM में hidden रहता है (value + change events = पुराना code वैसा ही),
   दिखता है styled button + custom options menu. नया select कभी भी जोड़ो —
   MutationObserver उसे अपने आप upgrade कर देगा, किसी दूसरी file में बदलाव नहीं। */
(function(){
  var ALL=[];
  function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;
    if(txt!=null)e.textContent=txt;return e;}
  function split(t){
    var v=String(t==null?'':t).trim(), m=v.match(/^(\S+)\s+(.+)$/);
    if(m&&/[^\x00-\x7F]/.test(m[1])) return {ico:m[1],text:m[2].trim()};
    return {ico:'',text:v};
  }
  function capOf(sel){return sel.getAttribute('data-fdd-cap')||
    sel.getAttribute('aria-label')||sel.title||'Options';}
  function render(d){
    var o=d.sel.options[d.sel.selectedIndex], p=o?split(o.text):{ico:'',text:'—'};
    d.btn.querySelector('.fdd-ico').textContent=p.ico;
    d.btn.querySelector('.fdd-label').textContent=p.text||'—';
    Array.prototype.forEach.call(d.menu.querySelectorAll('.fdd-item'),function(it){
      it.setAttribute('aria-selected',
        it.getAttribute('data-value')===String(d.sel.value)?'true':'false');
    });
  }
  function buildMenu(d){
    d.menu.innerHTML='';
    d.menu.appendChild(el('div','fdd-cap',capOf(d.sel)));
    Array.prototype.forEach.call(d.sel.options,function(o){
      var p=split(o.text), it=el('button','fdd-item');
      it.type='button';it.setAttribute('role','option');
      it.setAttribute('data-value',o.value);it.setAttribute('aria-selected','false');
      it.appendChild(el('span','fdd-opt-ico',p.ico));
      it.appendChild(el('span','fdd-opt-text',p.text||o.value));
      it.appendChild(el('span','fdd-tick','✓'));
      it.addEventListener('click',function(ev){ev.stopPropagation();choose(d,o.value);});
      it.addEventListener('keydown',function(ev){
        if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();choose(d,o.value);return;}
        var all=Array.prototype.slice.call(d.menu.querySelectorAll('.fdd-item')),
            i=all.indexOf(ev.currentTarget);
        if(ev.key==='ArrowDown'){ev.preventDefault();(all[i+1]||all[0]).focus();}
        else if(ev.key==='ArrowUp'){ev.preventDefault();(all[i-1]||all[all.length-1]).focus();}
        else if(ev.key==='Escape'){ev.preventDefault();close(d);d.btn.focus();}
      });
      d.menu.appendChild(it);
    });
    render(d);
  }
  function close(d){d.wrap.classList.remove('open','up');
    d.btn.setAttribute('aria-expanded','false');}
  function closeAll(){ALL.forEach(close);}
  function open(d){
    closeAll();render(d);
    d.wrap.classList.add('open');d.btn.setAttribute('aria-expanded','true');
    var r=d.wrap.getBoundingClientRect(), h=d.menu.offsetHeight||220;
    if(r.bottom+h+10>window.innerHeight&&r.top>h) d.wrap.classList.add('up');
  }
  function choose(d,v){
    d.sel.value=v;
    d.sel.dispatchEvent(new Event('change',{bubbles:true}));
    render(d);close(d);d.btn.focus();
  }
  /* कोई भी page `sel.value = x` लिखे → button label अपने आप sync.
     इसलिए किसी page पर ddSet()/refresh() बुलाने वाला अलग code नहीं चाहिए। */
  function watchValue(sel,d){
    var desc=null,pObj=Object.getPrototypeOf(sel);
    while(pObj&&!desc){
      var x=Object.getOwnPropertyDescriptor(pObj,'value');
      if(x&&x.get&&x.set){desc=x;break;}
      pObj=Object.getPrototypeOf(pObj);
    }
    if(!desc)return;
    try{
      Object.defineProperty(sel,'value',{configurable:true,enumerable:true,
        get:function(){return desc.get.call(this);},
        set:function(v){desc.set.call(this,v);if(d.menu)buildMenu(d);}});
    }catch(err){}
  }
  function build(sel){
    if(sel.getAttribute('data-fdd')) return null;
    sel.setAttribute('data-fdd','1');
    var wrap=el('div','fdd'),btn=el('button','fdd-btn'),menu=el('div','fdd-menu');
    if(sel.getAttribute('data-fdd-full'))wrap.classList.add('full');
    btn.type='button';btn.setAttribute('aria-haspopup','listbox');
    btn.setAttribute('aria-expanded','false');
    btn.appendChild(el('span','fdd-ico',''));
    btn.appendChild(el('span','fdd-label','—'));
    btn.appendChild(el('span','fdd-arrow','▾'));
    menu.setAttribute('role','listbox');
    sel.parentNode.insertBefore(wrap,sel);
    wrap.appendChild(btn);wrap.appendChild(menu);wrap.appendChild(sel);
    sel.classList.add('fdd-native');
    var d={sel:sel,wrap:wrap,btn:btn,menu:menu};
    ALL.push(d);
    watchValue(sel,d);
    btn.addEventListener('click',function(ev){ev.stopPropagation();
      if(wrap.classList.contains('open'))close(d);else open(d);});
    btn.addEventListener('keydown',function(ev){
      if(ev.key==='ArrowDown'||ev.key==='Enter'||ev.key===' '){
        ev.preventDefault();if(!wrap.classList.contains('open'))open(d);
        var f=d.menu.querySelector('.fdd-item[aria-selected=true]')||
              d.menu.querySelector('.fdd-item');if(f)f.focus();
      }else if(ev.key==='Escape'){close(d);}
    });
    buildMenu(d);
    return d;
  }
  function find(id){
    var s=typeof id==='string'?document.getElementById(id):id;
    if(!s)return null;
    for(var i=0;i<ALL.length;i++)if(ALL[i].sel===s)return ALL[i];
    return build(s);
  }
  function init(root){
    var scope=root&&root.querySelectorAll?root:document;
    Array.prototype.forEach.call(
      scope.querySelectorAll('select.filter-dd:not([data-fdd])'),build);
  }
  function set(id,value,fire){
    var d=find(id);if(!d)return;
    d.sel.value=value;buildMenu(d);
    if(fire)d.sel.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function ensure(id,value,label){
    var d=find(id);if(!d)return;
    var has=Array.prototype.some.call(d.sel.options,function(o){return o.value===value;});
    if(value&&!has)d.sel.add(new Option(label||value,value));
    buildMenu(d);set(id,value||'');
  }
  function refresh(id){var d=find(id);if(d)buildMenu(d);}
  window.FilterDD={init:init,set:set,ensure:ensure,refresh:refresh,
                   closeAll:closeAll,find:find};
  window.ddSet=set;
  document.addEventListener('click',function(ev){
    if(!ev.target||!ev.target.closest||!ev.target.closest('.fdd'))closeAll();
  },true);
  document.addEventListener('keydown',function(ev){
    if(ev.key==='Escape')closeAll();
  });
  document.addEventListener('change',function(ev){
    if(ev.target&&ev.target.matches&&ev.target.matches('select.filter-dd')){
      var d=find(ev.target);if(d)render(d);
    }
  },true);
  var pending=false;
  function schedule(){if(pending)return;pending=true;
    setTimeout(function(){pending=false;init(document);},0);}
  function start(){
    init(document);
    if(window.MutationObserver&&document.body)
      new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')
    document.addEventListener('DOMContentLoaded',start);
  else start();
})();
"""


# ─────────────────────────────────────────────────────────────
# 🎛️ FILTER BUTTONS — एकमात्र definition (options, labels, markup)
#   "Poster/Text" जैसे options अब दोनों pages पर अलग-अलग नहीं लिखे जाते।
#   नया button जोड़ना हो / label बदलना हो → सिर्फ़ यहाँ बदलो।
# ─────────────────────────────────────────────────────────────
FILTER_OPTIONS = {
    "view":  VIEW_MODE_OPTIONS,
    "group": (("all", "All"), ("group", "Group"), ("ungroup", "UnGroup")),
}

# (id, options, caption, aria/title label, onchange)
SEARCH_FILTERS = (
    {"id": "modeSel",  "options": "view",  "cap": "View mode",     "label": "Mode",   "vm": True},
    {"id": "groupSel", "options": "group", "cap": "Result filter", "label": "Filter", "onchange": "setGroup(this.value)"},
)
CATALOG_FILTERS = (
    {"id": "catCategory", "options": None,   "cap": "Category",  "label": "Category"},  # options = dynamic per kind
    {"id": "catMode",     "options": "view", "cap": "View mode", "label": "Mode", "vm": True},
)


def filter_select(sel_id, *, options, cap, label, onchange="", full=False, vm=False):
    """एक filter button का markup। `options` = FILTER_OPTIONS key | (value,label)
    pairs | पहले से बना `<option>` HTML (जैसे catalog की dynamic categories)।"""
    if options is None:
        options = ()
    if isinstance(options, str) and options in FILTER_OPTIONS:
        options = FILTER_OPTIONS[options]
    if isinstance(options, str):
        opts = options
    else:
        opts = "".join(
            '<option value="%s">%s</option>'
            % (html.escape(str(v), quote=True), html.escape(str(l)))
            for v, l in options)
    e = lambda x: html.escape(str(x), quote=True)
    extra = (' data-fdd-full="1"' if full else "") + \
            (' data-vm-select="1"' if vm else "")
    cb = ' onchange="%s"' % e(onchange) if onchange else ""
    return (f'<select class="filter-dd" id="{e(sel_id)}" data-fdd-cap="{e(cap)}"'
            f' aria-label="{e(label)}" title="{e(label)}"{extra}{cb}>{opts}</select>')


def filter_buttons(specs, dynamic=None):
    """पूरी `.filters` row — `/search` और `/posts`–`/actors` दोनों यहीं से।
    `dynamic` = {select_id: `<option>` HTML} (catalog categories)।"""
    dynamic = dynamic or {}
    out = ["      " + filter_select(
        sp["id"], options=dynamic.get(sp["id"], sp.get("options")),
        cap=sp.get("cap", sp["id"]), label=sp.get("label", sp["id"]),
        onchange=sp.get("onchange", ""), full=sp.get("full", False),
        vm=sp.get("vm", False))
        for sp in specs]
    return '<div class="filters">\n' + "\n".join(out) + "\n    </div>"


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
.main{padding:18px 4% 60px;max-width:1700px;margin:0 auto}
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
/* 📱 mobile filter row (search + दोनों buttons) → FILTER_CSS में एक ही नियम */
@media(max-width:520px){.spin{display:none!important}
.auth-card{padding:24px}.vgrid{gap:8px}}

"""

SITE_CSS += VIDEO_CARD_CSS
SITE_CSS += FILTER_CSS
SITE_CSS += GROUP_CSS
# ⚠️ MODE_CSS आख़िर में — Poster/Text का इकलौता नियम-सेट, बाकी सब ऊपर base only
SITE_CSS += MODE_CSS




# ─────────────────────────────────────────────────────────────
# 🧭 APP SHELL — JoneySin/v5 (web/web_assets.py) जैसा sidebar
#    Home · Database Stats · Profile Settings + footer में Sign Out.
#    Identity badge अब सिर्फ़ Profile Settings में — desktop topbar/
#    sidebar में "#<tg_id> · ADMIN" नहीं दिखता।
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
.scard{padding:20px}}
"""

# Theme + sidebar — सभी logged-in pages पर एक ही script (v5 की तरह shared head)
SITE_JS = """
(function(){if(localStorage.getItem('ff_theme')==='light')document.documentElement.classList.add('light')})();
function toggleTheme(){var l=document.documentElement.classList.toggle('light');localStorage.setItem('ff_theme',l?'light':'dark')}
function openSidebar(){var s=document.getElementById('sidebar'),o=document.getElementById('sbOverlay');if(s)s.classList.add('open');if(o)o.classList.add('open')}
function closeSidebar(){var s=document.getElementById('sidebar'),o=document.getElementById('sbOverlay');if(s)s.classList.remove('open');if(o)o.classList.remove('open')}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeSidebar()});
"""
SITE_JS += FILTER_JS
SITE_JS += VCARD_JS
SITE_JS += GROUP_JS
SITE_JS += MODE_JS

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
    # ℹ️ desktop topbar से "#<tg_id> · ADMIN" badge हटा दिया गया — identity
    #    अब सिर्फ़ Profile Settings पर दिखती है (sidebar में भी ID नहीं)।
    role_txt = "ADMIN" if role == "admin" else "USER"
    return (
        '<div class="sidebar-overlay" id="sbOverlay" onclick="closeSidebar()"></div>'
        '<div class="sidebar" id="sidebar">'
          '<div class="sb-header"><div class="sb-logo"><span class="nfi">F</span> FAST FINDER</div>'
          '<button class="sb-close" onclick="closeSidebar()" aria-label="Close menu">&#10005;</button></div>'
          f'<div class="sb-user"><span class="sb-uid">Account</span>'
          f'<span class="sb-role">{role_txt}</span></div>'
          f'<nav class="sb-nav"><div class="sb-section">Menu</div>{links}</nav>'
          '<div class="sb-footer"><a href="/logout" class="sb-logout">Sign Out</a></div>'
        '</div>'
        '<div class="top">'
          '<button class="ham-btn" id="hamBtn" onclick="openSidebar()" aria-label="Open menu">'
            '<span class="ham-line"></span><span class="ham-line"></span><span class="ham-line"></span>'
          '</button>'
          '<a class="logo" href="/search"><span class="nfi">F</span> FAST FINDER</a>'
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
# ▶ SHARED PLAYER MODAL — /search + /post/<id> + /actor/<id> सब एक ही
#   modal, एक ही `/api/stream` flow इस्तेमाल करते हैं (कोई duplicate JS नहीं)।
#   PLAYER_JS एक IIFE में `window.play/closePlayer/copyLink` expose करता है,
#   इसलिए page के अपने `$` / `esc` / `const` से कोई नाम-टकराव नहीं होता।
# ─────────────────────────────────────────────────────────────
PLAYER_MODAL_HTML = """<div class="modal" id="modal" onclick="if(event.target===this)closePlayer()">
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
</div>"""

PLAYER_JS = r"""<script>
(function(){
  const q = s => document.querySelector(s);
  let currentWatch = '';
  window.play = async function(fid, name){
    const modal=q('#modal'), v=q('#player');
    if(!modal || !v) return;
    q('#pTitle').textContent='⏳ '+name;
    q('#pNote').textContent='Streaming link तैयार हो रही है…';
    modal.classList.add('open');
    v.pause(); v.removeAttribute('src');
    try{
      const r=await fetch('/api/stream',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:fid})});
      if(r.status===401){location.href='/login?err='+encodeURIComponent('Session expired. Please sign in again.');return}
      const d=await r.json();
      if(!d.stream){q('#pTitle').textContent='❌ '+(d.error||'Stream unavailable');
        q('#pNote').textContent='यह फाइल अभी stream नहीं हो सकी।';return}
      currentWatch=location.origin+d.watch;
      q('#pTitle').textContent='▶ '+name;
      q('#pNote').textContent='Signed link · '+(d.expires_in||0)+' seconds valid · Range/seek supported';
      q('#pWatch').href=d.watch;
      q('#pDl').href=d.download;
      v.poster=d.poster||'';
      v.src=d.stream;
      v.load();
      const pr=v.play(); if(pr && typeof pr.catch==='function') pr.catch(()=>{});
    }catch(e){q('#pTitle').textContent='❌ Stream error';
      q('#pNote').textContent=String(e.message||e)}
  };
  window.closePlayer = function(){
    const v=q('#player'); if(!v) return;
    v.pause(); v.removeAttribute('src'); v.load();
    const m=q('#modal'); if(m) m.classList.remove('open');
  };
  window.copyLink = function(){
    if(!currentWatch) return;
    const note=q('#pNote'), clip=navigator.clipboard;
    if(!clip || !clip.writeText){ if(note) note.textContent=currentWatch; return; }
    clip.writeText(currentWatch).then(()=>{
      if(note) note.textContent='🔗 Link copied: '+currentWatch;
    }).catch(()=>{ if(note) note.textContent=currentWatch; });
  };
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') window.closePlayer(); });
})();
</script>"""


# ─────────────────────────────────────────────────────────────
# 🔍 SEARCH PAGE (login ke baad)
# ─────────────────────────────────────────────────────────────
SEARCH_BODY = """<div class="search-zone">
  <div class="srow" id="srow">
    <div class="qwrap">
      <input class="sinput" id="q" type="search" placeholder="Movie / series / file name खोजें..." autocomplete="off">
      <div class="spin"></div>
    </div>
    __FILTER_BUTTONS__
  </div>
</div>

<div class="main">
  <div class="vgrid vm-grid" id="grid"></div>
  <button class="more" id="more" onclick="load(false)">और दिखाओ ⬇</button>
</div>

__PLAYER_MODAL__
__FILE_EDIT_HTML__
__GROUP_ADMIN_HTML__

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let curQ='',offset=0,loading=false,hasMore=false,seenGroups={};
let debounce=null;
/* 🖼️📄 Poster/Text पूरा `web/mode_assets.py` (SITE_JS → window.ViewMode) से —
   यहाँ कोई mode logic नहीं; सिर्फ़ एक init call। Group filter अलग feature है। */
let groupMode=localStorage.getItem('ff_group_mode')||'all';
if(!['all','group','ungroup'].includes(groupMode))groupMode='all';
ViewMode.init({storage:ViewMode.storageFor()});
$('#groupSel').value=groupMode;
function setGroup(v){groupMode=['all','group','ungroup'].includes(v)?v:'all';
  localStorage.setItem('ff_group_mode',groupMode);
  $('#groupSel').value=groupMode;doSearch()}
function doSearch(){curQ=$('#q').value.trim();load(true)}
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(debounce);doSearch()}});
$('#q').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{
  const v=$('#q').value.trim();if(v.length>=2||v==='')doSearch()},420)});

/* 🎴 card का markup/chips/size सब web_assets.VCARD_TEMPLATE + VCARD_CHIP_SPEC से —
   Post/Actor Videos tabs भी बिल्कुल यही vcardHTML()/vcardChips()/vcardSize() चलाते हैं। */
function imgAttrs(f){
  // src ⇄ data-src का फैसला सिर्फ़ ViewMode (web/mode_assets.py) करता है
  return ViewMode.imgAttrs(f.thumb?encodeURI(f.thumb):'');
}
function cardTokens(f){
  const fid=encodeURIComponent(f.file_id);
  return {
    FID:fid, RAW_FID:esc(f.file_id), NAME:esc(f.name), POSTER_ID:` id="pb-${fid}"`,
    IMG_ATTRS:imgAttrs(f), IMG_ERROR:'thumbFail(this)',
    CHIPS:vcardChips(f), SIZE:vcardSize(f)
  };
}
/* 🎴 एक ही entry point: group card (`web/group_assets.py`) या shared vcard.
   Group के अंदर की हर variant भी इसी cardHTML() → vcardHTML() से बनती है,
   इसलिए /search, Post, Actor तीनों पर card बिल्कुल एक जैसा रहता है। */
function cardHTML(f){
  if(f.group)return groupHTML(f,imgAttrs(f),'thumbFail(this)');
  return vcardHTML(cardTokens(f));
}
window.cardHTML=cardHTML;
function card(f){return cardHTML(f)}
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
  const p=img.closest('.vposter,.gposter');if(p)p.classList.add('no-thumb');
}

async function load(reset){
  if(loading)return;
  if(reset){offset=0;hasMore=false;seenGroups={};$('#grid').innerHTML='';}
  loading=true;$('#srow').classList.add('loading');
  try{
    const r=await fetch(`/api/search?q=${encodeURIComponent(curQ)}&offset=${offset}&group=${groupMode}`,{credentials:'same-origin'});
    if(r.status===401){location.href='/login?err='+encodeURIComponent('Session expired. Please sign in again.');return}
    const d=await r.json();
    // 🗂️ Saved group के सारे members हर page पर आते हैं — एक ही group card
    //    दोबारा न दिखे, इसलिए key याद रखो (raw-file offset बरकरार)।
    const list=(d.results||[]).filter(f=>{
      if(!f.group)return true;
      const k=String(f.key||f.gid||'');
      if(seenGroups[k])return false;
      seenGroups[k]=1;return true;
    });
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
  const el=e.target.closest('.vcard[data-fid]');if(!el)return;
  play(decodeURIComponent(el.dataset.fid),el.dataset.name);
});
document.addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' ')return;
  const a=document.activeElement;
  const el=a&&a.closest?a.closest('.vcard[data-fid]'):null;
  if(!el)return;
  e.preventDefault();play(decodeURIComponent(el.dataset.fid),el.dataset.name);
});

ViewMode.apply();
load(true);
</script>
__PLAYER_JS__
__FILE_EDIT_JS__
__GROUP_ADMIN_JS__"""


def search_page(tg_id: int, role: str):
    """v5 जैसा sidebar वाला app shell + search body.

    * Sign Out सिर्फ़ sidebar footer में (topbar पर नहीं)।
    * Mode/Filter dropdowns desktop पर search bar के साथ एक लाइन में,
      mobile पर उसके ठीक नीचे एक ही लाइन में।
    * "Recently Added / Database Stats" वाली meta लाइन हटा दी गई —
      गिनती सिर्फ़ `/stats` (Database Stats) पेज पर।
    """
    admin = role == "admin"
    body = (SEARCH_BODY
            .replace("__FILTER_BUTTONS__", filter_buttons(SEARCH_FILTERS))
            .replace("__PLAYER_MODAL__", PLAYER_MODAL_HTML)
            .replace("__PLAYER_JS__", PLAYER_JS)
            .replace("__FILE_EDIT_HTML__", FILE_EDIT_HTML if admin else "")
            .replace("__FILE_EDIT_JS__", FILE_EDIT_JS if admin else "")
            .replace("__GROUP_ADMIN_HTML__", GROUP_ADMIN_HTML if admin else "")
            .replace("__GROUP_ADMIN_JS__", GROUP_ADMIN_JS if admin else ""))
    # GROUP_JS (head) को admin flag body के पहले script में मिलता है —
    # ताकि load(true) से बनने वाले group cards में admin overlay आ जाए।
    if admin:
        body = '<script>window.IS_GROUP_ADMIN=true;</script>' + body
    return app_page(
        "FAST FINDER — Search Files", body,
        tg_id=tg_id, role=role, active_tab="dash",
    )
