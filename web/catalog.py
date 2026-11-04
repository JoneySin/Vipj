"""🧩 Unified Catalog UI — Posts + Directory (Actors / Apps / Websites).

`JoneySin/v5` में `post_routes.py` (≈790 lines) और `actor_routes.py` (≈590 lines)
अलग-अलग थे, दोनों में directory CSS/JS/search/pagination की हुबहू copy थी,
create/edit के लिए अलग full-page wizards थे (हर save पर page reload), और API
server से raw HTML strings भेजती थी।

यहाँ वही **features** हैं, पर fsv1 के लिए एकदम अलग / छोटा ढाँचा:

* **एक** `CATALOGS` config + **एक** CSS/JS engine → दोनों pages, कोई duplication नहीं।
* **JSON API + client-side render** (`textContent`-safe escaping) — server से HTML
  strings नहीं, इसलिए markup एक ही जगह और XSS का रास्ता बंद।
* **Inline edit modal** listing पर ही: create + edit + delete बिना page reload,
  live poster preview, image upload, dirty-state guard, `Ctrl/Cmd+S` save,
  `Esc` close, **Undo** वाला delete toast (v5 में नहीं था)।
* **🎬 Multi-video editor** — `videos[]` दोनों kinds पर, 50 तक; Library picker एक
  search में कई files जोड़ता है (बंद नहीं होता), ▲▼ reorder, per-row delete,
  duplicate guard. पुराने posts के `links`-में-रखे episodes auto-migrate होते हैं।
  **🖼️ Visual gallery** — multiple image upload (Telegram पर एक-एक करके),
  thumbnails/remove, कोई plain textarea नहीं।
* **🗂️ Detail tabs** — `ℹ️ Overview | 🎬 Videos | 🖼️ Gallery` (Actor) /
  `📸 Screenshots` (Post). v5 में tabs सिर्फ़ actor detail पर थे। Count badges,
  `?tab=` deep-link (Post `?tab=screenshots`), arrow-key nav, staggered panels,
  lightbox, **बिना reload** image delete/upload.
* **🏷️ Tag-driven Videos — सिर्फ़ Actor पर** (`tagMedia` config flag) — v5 का
  `get_actor_search_results(name|tags)`: Actor के Videos tab का दूसरा हिस्सा
  **Search Tags** से Library में खोजकर आता है, ऊपर search box में custom `q`
  टाइप करते ही tags ignore (बिल्कुल v5 जैसा)। fsv1 की अपनी `$text` +
  regex-fallback pipeline को हर term पर चलाकर results merge/dedupe/paginate
  करते हैं। **Post पर यह block बिल्कुल नहीं है** — वहाँ Videos tab में सिर्फ़
  attached `videos[]` दिखते हैं (API भी `disabled` लौटाता है)।
* **📐 Fixed grid** — `.cat-grid` (listing) + `.cat-vgrid` (Videos tab): 📱 mobile
  **1 card/row**, tablet 2, 🖥️ desktop (≥1024px) **बिल्कुल 3 cards/row** —
  `#catVideos` और `#catMediaResults` दोनों पर, Actor + Post दोनों kinds पर।
  Search page के 1/2/3 pattern के साथ consistent; पुरानी 4-column rule हटाई।
* **▶ Shared Click-to-Play** — Videos tab की हर card (attached `#catVideos` और
  Actor के tag-results `#catMediaResults`) अब **main `/search` वाला ही छोटा
  player modal** खोलती है: `web.web_assets` का `PLAYER_MODAL_HTML` + `PLAYER_JS`
  दोनों detail pages में include है, cards `data-fid`/`data-name` + delegated
  click/keyboard handler से `window.play(fid, name)` चलाती हैं → वही
  `POST /api/stream` → signed `<video>` + Player page / Download / Copy link.
  कोई नई tab, कोई अलग player UI, कोई duplicate JS नहीं।
* **🖼️ Direct gallery upload** — v5 का `<input multiple>` form अब detail tab पर
  ही; JSON response + in-place render (v5 reload करता था), uploads Telegram पर
  एक-एक करके anti-flood.
* **Animations**: staggered card entrance (IntersectionObserver), 3D hover +
  poster zoom + press feedback, shimmer skeleton, modal spring-pop, button
  ripple, toast slide-in, save-flash, lightbox zoom, hero fade-up — और
  `prefers-reduced-motion` respect (v5 में नहीं था)।
* कोई CDN dependency नहीं (v5 Cropper.js CDN से लाता था)।
"""

import html
import json
import re
from urllib.parse import quote

from web.web_assets import app_page, PLAYER_MODAL_HTML, PLAYER_JS

# ─────────────────────────────────────────────────────────────
# ⚙️ DATA-DRIVEN CONFIG — नया catalog जोड़ना हो तो सिर्फ़ यहाँ entry
# ─────────────────────────────────────────────────────────────
CATALOGS = {
    "posts": {
        "kind": "posts",
        "label": "Posts",
        "icon": "📝",
        "page": "Content Posts",
        "singular": "Post",
        "base": "/posts",
        "detail": "/post/",
        "nameLabel": "Post Title",
        "bodyLabel": "Short Description",
        "imageLabel": "Cover Image",
        "galleryLabel": "Screenshots",
        "galleryTab": "📸 Screenshots",
        "galleryIcon": "📸",
        "uploadLabel": "📂 Upload screenshots",
        "galleryHint": "Movie / episode के stills — एक साथ कई upload करें",
        "galleryEmpty": "📸 अभी कोई screenshot नहीं है।",
        "tabAlias": "screenshots",
        "linkKind": "media",
        "linkLabel": "🔗 External / Social Links",
        "linkLabelField": "Label (Trailer / IMDb / Instagram)",
        "linkValueField": "https://…",
        "videoLabel": "🎬 Videos / Episodes",
        "videoHint": "जितने चाहें उतने episodes जोड़ें — Library picker से एक-एक करके चुनें",
        "tagMedia": False,             # Post पर सिर्फ़ attached videos, कोई search-text results नहीं
        "videosHeading": "🎬 Videos",
        "videoEmptyHint": "Admin: ऊपर Add Videos से कितने भी videos जोड़ें।",
        "legacyLinksAsVideos": True,   # पुराने posts में `links` ही episodes थे
        "placeholder": "Movies, series, posts खोजें…",
        "empty": "🗂️ अभी कोई Post नहीं है।",
        "categories": [
            {"value": "Movies", "label": "🎬 Movies"},
            {"value": "Web Series", "label": "📺 Web Series"},
            {"value": "App Video", "label": "📱 App Video"},
            {"value": "Other", "label": "🗂️ Other"},
        ],
    },
    "actors": {
        "kind": "actors",
        "label": "Directory",
        "icon": "🎭",
        "page": "Directory Profiles",
        "singular": "Profile",
        "base": "/actors",
        "detail": "/actor/",
        "nameLabel": "Profile Name",
        "bodyLabel": "Biography / Details",
        "imageLabel": "Profile Photo / Icon",
        "galleryLabel": "Gallery",
        "galleryTab": "🖼️ Gallery",
        "galleryIcon": "🖼️",
        "uploadLabel": "📂 Add photos to gallery",
        "galleryHint": "एक साथ कई photos चुनें — Telegram पर एक-एक करके save होंगी",
        "galleryEmpty": "🖼️ Gallery खाली है।",
        "tabAlias": "gallery",
        "linkKind": "url",
        "linkLabel": "🔗 Social / Website Links",
        "linkLabelField": "Label (Instagram / YouTube / X)",
        "linkValueField": "https://…",
        "videoLabel": "🎬 Videos (Filmography)",
        "videoHint": "इस नाम की Library files जोड़ें — कितनी भी videos attach कर सकते हैं",
        "tagMedia": True,              # Actor: Search Tags से Library videos (v5 जैसा)
        "videosHeading": "📌 Attached Videos",
        "videoEmptyHint": "नीचे Search Tags से Library की videos अपने आप दिखेंगी।",
        "legacyLinksAsVideos": False,  # actors के `links` URLs हैं, videos नहीं
        "placeholder": "Actor, app, website खोजें…",
        "empty": "📇 अभी कोई Profile नहीं है।",
        "categories": [
            {"value": "actor", "label": "🎭 Actor"},
            {"value": "app", "label": "📱 App"},
            {"value": "website", "label": "🌐 Website"},
        ],
    },
}

_URL_RE = re.compile(r"^https?://", re.I)
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.I)


def clean_url(value, allow_tg=True) -> str:
    """सिर्फ़ http/https (या TG_ID:) — `javascript:` जैसी scheme तुरंत reject।"""
    v = str(value or "").strip()
    if not v:
        return ""
    if allow_tg and v.startswith("TG_ID:"):
        return v[:300]
    if not _URL_RE.match(v):
        if _SCHEME_RE.match(v):
            return ""
        v = "https://" + v
    return v[:500]


_MEDIA_ID_RE = re.compile(r"^[A-Za-z0-9_\-=]{2,256}$")


def clean_media_id(value) -> str:
    """Linked media हमेशा Telegram `file_id` हो — URL/`javascript:`/control chars reject।

    v5 में post wizard का "Videos / Episodes" field खाली-खाली raw string ले लेता था;
    यहाँ value सीधे `/setup_stream?file_id=…` में जाती है, इसलिए pattern-validate ज़रूरी है।
    """
    v = str(value or "").strip()
    return v if _MEDIA_ID_RE.match(v) else ""


def image_src(value: str) -> str:
    """TG_ID → अपना /api/catalog/photo (bytes Telegram से), वरना direct URL।"""
    v = str(value or "")
    if not v:
        return ""
    if v.startswith("TG_ID:"):
        return "/api/catalog/photo?id=" + quote(v[6:], safe="")
    return v


def normalize(kind: str, raw: dict) -> dict:
    """UI/API से आया raw payload → साफ़, bounded, validated item dict."""
    cfg = CATALOGS[kind]
    allowed = [c["value"] for c in cfg["categories"]]
    cat = str(raw.get("category") or "").strip()
    if cat not in allowed:
        cat = allowed[0]

    tags_raw = raw.get("tags") or []
    if isinstance(tags_raw, str):
        tags_raw = tags_raw.split(",")
    tags = [str(t).strip()[:40] for t in tags_raw if str(t).strip()][:12]

    gal_raw = raw.get("gallery") or []
    if isinstance(gal_raw, str):
        gal_raw = gal_raw.splitlines()
    gallery = [u for u in (clean_url(g) for g in gal_raw) if u][:12]

    # 🎬 Videos — दोनों kinds के लिए, *कितने भी* (50 तक)।
    # `file_id` सिर्फ़ Telegram का base64url token होना चाहिए; URLs/जंक reject।
    def _video_rows(rows):
        out = []
        for row in (rows or [])[:50]:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()[:80]
            fid = clean_media_id(row.get("file_id") or row.get("value"))
            if not fid:
                continue
            out.append({"label": label or "Video", "file_id": fid})
        return out

    raw_links = raw.get("links") or []
    if raw.get("videos") is not None:
        videos = _video_rows(raw.get("videos"))
        url_rows = raw_links
    elif cfg.get("legacyLinksAsVideos"):
        # 🔄 पुराने posts जिन्होंने episodes `links` में save किए थे — auto-migrate
        videos = _video_rows(raw_links)
        url_rows = []
    else:
        videos = []
        url_rows = raw_links

    links = []
    for row in url_rows[:20]:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()[:60]
        value = clean_url(row.get("value"), allow_tg=False)
        if not label or not value:
            continue
        links.append({"label": label, "value": value})

    return {
        "title": str(raw.get("title") or "").strip()[:120],
        "category": cat,
        "body": str(raw.get("body") or "").strip()[:3000],
        "tags": tags,
        "image": clean_url(raw.get("image")),
        "gallery": gallery,
        "links": links,
        "videos": videos,
    }


# ─────────────────────────────────────────────────────────────
# 🎨 SHARED CSS — दोनों pages + detail + modal + animations
# ─────────────────────────────────────────────────────────────
CATALOG_CSS = """
.cat-wrap{max-width:1200px;margin:0 auto}
.cat-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.cat-title{font-size:24px;font-weight:900;flex:1;min-width:170px;letter-spacing:-.5px}
.cat-count{font-size:11px;font-weight:800;color:var(--mut);background:var(--bg3);
border:1px solid var(--line);border-radius:20px;padding:5px 11px;white-space:nowrap}
.cat-count.bump{animation:catPop .5s cubic-bezier(.34,1.56,.64,1)}
.cat-btn{background:var(--red);color:#fff;border:0;border-radius:9px;padding:10px 18px;
font-weight:800;font-size:13px;cursor:pointer;font-family:inherit;transition:transform .16s,background .16s,box-shadow .16s}
.cat-btn:hover{background:var(--red2);transform:translateY(-2px);box-shadow:0 8px 22px rgba(229,9,20,.35)}
.cat-btn:active{transform:scale(.96)}
.cat-btn.ghost{background:var(--bg3);border:1px solid var(--line);color:var(--txt)}
.cat-btn.ghost:hover{background:var(--bg2);border-color:var(--red);box-shadow:none}
.cat-toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:var(--card);
border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:20px}
.cat-search{position:relative;flex:1 1 240px;min-width:0}
.cat-search input{width:100%;box-sizing:border-box;background:var(--bg3);border:1.5px solid var(--line);
border-radius:9px;padding:11px 38px 11px 14px;color:var(--txt);font-size:14px;font-weight:600;
font-family:inherit;outline:none;transition:border-color .18s,box-shadow .18s}
.cat-search input:focus{border-color:var(--red);box-shadow:0 0 0 3px rgba(229,9,20,.14)}
.cat-spin{display:none;position:absolute;right:14px;top:50%;transform:translateY(-50%);
width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--red);
border-radius:50%;animation:catSpin .65s linear infinite}
.cat-search.loading .cat-spin{display:block}
.cat-select{background:var(--bg3);border:1px solid var(--line);border-radius:9px;color:var(--txt);
padding:11px 12px;font:700 12px inherit;font-family:inherit;cursor:pointer;outline:none}
.cat-select:focus{border-color:var(--red)}
/* ── grid + cards ── */
.cat-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:620px){.cat-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
@media(min-width:1024px){.cat-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
.cat-grid.mode-text{display:flex;flex-direction:column;gap:8px}
.cat-card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
cursor:pointer;position:relative;transition:transform .28s cubic-bezier(.25,.8,.25,1),border-color .22s,box-shadow .28s}
.cat-card:hover{transform:translateY(-6px) scale(1.015);border-color:rgba(229,9,20,.65);
box-shadow:0 16px 38px rgba(0,0,0,.5),0 0 18px rgba(229,9,20,.22);z-index:2}
.cat-card:active{transform:scale(.97);transition:transform .1s}
.cat-card.enter{opacity:0}
.cat-card.enter.in{animation:catIn .55s cubic-bezier(.34,1.2,.64,1) forwards}
.cat-card.flash{animation:catFlash .8s ease-out}
@keyframes catIn{0%{opacity:0;transform:translateY(32px) scale(.93)}
60%{opacity:1;transform:translateY(-5px) scale(1.015)}100%{opacity:1;transform:translateY(0) scale(1)}}
@keyframes catFlash{0%{box-shadow:0 0 0 0 rgba(229,9,20,.6)}100%{box-shadow:0 0 0 20px rgba(229,9,20,0)}}
.cat-poster-wrap{position:relative;aspect-ratio:2/3;overflow:hidden;
background:linear-gradient(90deg,var(--bg3) 0,#2b2b3a 50%,var(--bg3) 100%);
background-size:200% 100%;animation:catShimmer 1.5s infinite linear}
@keyframes catShimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.cat-poster{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;
transition:opacity .35s ease,transform .5s cubic-bezier(.25,1,.5,1)}
.cat-poster.on{opacity:1}
.cat-card:hover .cat-poster{transform:scale(1.08)}
.cat-ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
font-size:34px;color:var(--mut);opacity:.55}
.cat-badge{position:absolute;top:8px;left:8px;z-index:2;background:rgba(229,9,20,.92);
color:#fff;font-size:10px;font-weight:800;padding:4px 9px;border-radius:6px;
letter-spacing:.4px;backdrop-filter:blur(6px);box-shadow:0 2px 10px rgba(0,0,0,.45)}
.cat-grad{position:absolute;bottom:0;left:0;right:0;z-index:2;padding:32px 12px 12px;
background:linear-gradient(to top,rgba(0,0,0,.95),rgba(0,0,0,.6) 45%,transparent)}
.cat-name{color:#fff;font-size:14px;font-weight:900;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;text-shadow:0 2px 8px rgba(0,0,0,.9)}
.cat-meta{padding:10px 12px 12px;display:flex;flex-direction:column;gap:5px}
.cat-meta-main{font-size:13px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cat-meta-sub{font-size:11px;color:var(--mut);font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cat-actions{position:absolute;bottom:0;left:0;right:0;z-index:3;display:flex;gap:6px;padding:8px;
opacity:0;transform:translateY(10px);transition:opacity .22s,transform .22s;pointer-events:none}
.cat-card:hover .cat-actions,.cat-card:focus-within .cat-actions{opacity:1;transform:translateY(0);pointer-events:all}
.cat-edit,.cat-del{flex:1;border:1px solid rgba(255,255,255,.2);border-radius:7px;padding:7px 4px;
font:800 11px inherit;font-family:inherit;cursor:pointer;backdrop-filter:blur(10px);transition:background .14s,transform .1s}
.cat-edit{background:rgba(30,30,40,.9);color:#fff}.cat-edit:hover{background:rgba(70,70,85,.95)}
.cat-del{background:rgba(160,8,8,.85);color:#fff}.cat-del:hover{background:rgba(229,9,20,.95)}
.cat-edit:active,.cat-del:active{transform:scale(.94)}
.cat-grid.mode-text .cat-card{display:flex;align-items:center;gap:10px;padding:10px 14px}
.cat-grid.mode-text .cat-poster-wrap{display:none}
.cat-grid.mode-text .cat-meta{flex:1;padding:0;flex-direction:row;justify-content:space-between;gap:10px}
.cat-grid.mode-text .cat-actions{position:static;opacity:1;transform:none;pointer-events:all;padding:0;flex:0 0 150px}
.cat-grid.mode-text .cat-card:hover{transform:translateX(3px)}
.cat-skel{aspect-ratio:2/3;border-radius:12px;border:1px solid var(--line);
background:linear-gradient(90deg,var(--bg3) 0,#2b2b3a 50%,var(--bg3) 100%);
background-size:200% 100%;animation:catShimmer 1.5s infinite linear}
.cat-empty{grid-column:1/-1;text-align:center;padding:64px 20px;color:var(--mut);font-weight:700;line-height:1.7}
.cat-pg{display:none;justify-content:center;align-items:center;gap:12px;margin:26px 0 10px}
.cat-pg.show{display:flex}
.cat-pg button{background:var(--bg3);border:1px solid var(--line);color:var(--txt);border-radius:8px;
padding:8px 18px;font:800 12px inherit;font-family:inherit;cursor:pointer;transition:background .15s,transform .12s}
.cat-pg button:not(:disabled):hover{background:var(--red);color:#fff;border-color:var(--red)}
.cat-pg button:disabled{opacity:.4;cursor:not-allowed}
.cat-pg span{font-size:12px;font-weight:800;color:var(--mut)}
/* ── edit modal ── */
.cat-modal{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.82);display:none;
align-items:center;justify-content:center;padding:16px;opacity:0;transition:opacity .22s}
.cat-modal.open{display:flex}.cat-modal.show{opacity:1}
.cat-mcard{background:var(--bg2);border:1px solid var(--line);border-radius:14px;width:100%;
max-width:640px;max-height:92vh;overflow-y:auto;padding:24px;position:relative;
transform:scale(.93) translateY(18px);transition:transform .3s cubic-bezier(.34,1.32,.64,1);
box-shadow:0 24px 70px rgba(0,0,0,.65)}
.cat-modal.show .cat-mcard{transform:scale(1) translateY(0)}
.cat-mhead{display:flex;align-items:center;gap:10px;margin-bottom:18px}
.cat-mtitle{font-size:18px;font-weight:900;flex:1}
.cat-x{background:none;border:0;color:var(--mut);font-size:22px;cursor:pointer;line-height:1}
.cat-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:560px){.cat-grid2{grid-template-columns:1fr}}
.cat-field{margin-bottom:14px}
.cat-label{display:block;font-size:10px;font-weight:900;letter-spacing:.8px;text-transform:uppercase;
color:var(--mut);margin-bottom:6px}
.cat-input,.cat-textarea,.cat-fselect{width:100%;box-sizing:border-box;background:var(--bg3);
border:1.5px solid var(--line);border-radius:8px;padding:10px 12px;color:var(--txt);
font:600 13px inherit;font-family:inherit;outline:none;transition:border-color .16s,box-shadow .16s}
.cat-input:focus,.cat-textarea:focus,.cat-fselect:focus{border-color:var(--red);box-shadow:0 0 0 3px rgba(229,9,20,.13)}
.cat-textarea{min-height:88px;resize:vertical;line-height:1.55}
.cat-preview{width:100%;aspect-ratio:16/9;background:var(--bg3);border:1px dashed var(--line);
border-radius:9px;overflow:hidden;display:flex;align-items:center;justify-content:center;margin-bottom:10px}
.cat-preview img{width:100%;height:100%;object-fit:cover}
.cat-preview span{color:var(--mut);font-size:12px;font-weight:700}
.cat-upload{display:inline-flex;align-items:center;gap:6px;background:var(--bg3);border:1px dashed var(--line);
border-radius:8px;padding:8px 12px;font:800 11px inherit;font-family:inherit;cursor:pointer;color:var(--txt)}
.cat-upload:hover{border-color:var(--red)}
.cat-upload input{display:none}
.cat-linkrow{display:flex;gap:8px;margin-bottom:8px;align-items:center}
.cat-linkrow input{flex:1}
.cat-linkrow .cat-mini{background:var(--bg3);border:1px solid var(--line);color:var(--mut);
border-radius:7px;padding:8px 11px;cursor:pointer;font-weight:900}
.cat-mini:hover{border-color:var(--red);color:var(--red)}
.cat-picker{max-height:170px;overflow-y:auto;background:var(--bg3);border:1px solid var(--line);
border-radius:8px;margin:8px 0 12px;display:none}
.cat-picker.show{display:block}
.cat-pick{padding:9px 12px;border-bottom:1px solid var(--line);font-size:12px;font-weight:700;cursor:pointer}
.cat-pick:last-child{border-bottom:0}.cat-pick:hover{background:var(--bg2);color:var(--red)}
.cat-mfoot{display:flex;gap:10px;align-items:center;margin-top:20px;flex-wrap:wrap}
.cat-mfoot .cat-btn{flex:1;min-width:130px}
.cat-dirty{font-size:11px;font-weight:800;color:var(--gold)}
/* ── toast ── */
.cat-toast{position:fixed;left:50%;bottom:24px;z-index:400;transform:translate(-50%,160%);
opacity:0;background:var(--bg2);border:1px solid var(--line);color:var(--txt);
border-radius:11px;padding:12px 18px;font:800 13px inherit;font-family:inherit;
box-shadow:0 14px 40px rgba(0,0,0,.5);display:flex;align-items:center;gap:14px;
transition:transform .34s cubic-bezier(.34,1.3,.64,1),opacity .28s;max-width:92vw}
.cat-toast.show{transform:translate(-50%,0);opacity:1}
.cat-toast.ok{border-color:rgba(40,167,69,.6)}.cat-toast.err{border-color:var(--red)}
.cat-toast button{background:var(--red);color:#fff;border:0;border-radius:7px;padding:7px 12px;
font:800 11px inherit;font-family:inherit;cursor:pointer}
/* ── ripple ── */
.cat-ripple{position:relative;overflow:hidden}
.cat-ripple i{position:absolute;border-radius:50%;background:rgba(255,255,255,.42);
transform:scale(0);animation:catRipple .5s ease-out forwards;pointer-events:none}
@keyframes catRipple{to{transform:scale(2.8);opacity:0}}
/* ── detail page ── */
.cat-hero{display:flex;gap:26px;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);
border-radius:16px;padding:24px;margin-bottom:24px;animation:catFade .5s ease both}
@keyframes catFade{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
.cat-hero-img{width:220px;max-width:100%;aspect-ratio:2/3;border-radius:12px;object-fit:cover;
background:var(--bg3);border:1px solid var(--line)}
.cat-hero-info{flex:1;min-width:240px}
.cat-hero-title{font-size:28px;font-weight:900;letter-spacing:-1px;margin-bottom:10px}
.cat-chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.cat-chip{background:var(--bg3);border:1px solid var(--line);border-radius:20px;padding:4px 10px;
font-size:11px;font-weight:800;color:var(--mut)}
.cat-chip.red{background:var(--red);border-color:var(--red);color:#fff}
.cat-body-txt{font-size:14px;line-height:1.7;color:var(--txt);white-space:pre-wrap;margin-bottom:18px}
.cat-links{display:flex;gap:9px;flex-wrap:wrap}
.cat-links a{background:var(--bg3);border:1px solid var(--line);border-radius:8px;padding:9px 14px;
font-size:12px;font-weight:800;color:var(--txt);transition:transform .16s,border-color .16s,color .16s}
.cat-links a:hover{transform:translateY(-2px);border-color:var(--red);color:var(--red)}
.cat-sec-title{font-size:15px;font-weight:900;margin:26px 0 14px;letter-spacing:.3px}
.cat-gal img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;border:1px solid var(--line);
cursor:zoom-in;opacity:0;transition:opacity .35s,transform .25s}
.cat-gal img.on{opacity:1}.cat-gal img:hover{transform:scale(1.03)}
.cat-lightbox{position:fixed;inset:0;z-index:350;background:rgba(0,0,0,.92);display:none;
align-items:center;justify-content:center;padding:20px;opacity:0;transition:opacity .25s}
.cat-lightbox.open{display:flex}.cat-lightbox.show{opacity:1}
.cat-lightbox img{max-width:94%;max-height:88vh;border-radius:10px;transform:scale(.94);
transition:transform .3s cubic-bezier(.34,1.3,.64,1)}
.cat-lightbox.show img{transform:scale(1)}
.cat-related{display:flex;flex-direction:column;gap:8px}
.cat-related a{display:flex;justify-content:space-between;gap:10px;background:var(--bg3);
border:1px solid var(--line);border-radius:8px;padding:10px 13px;font-size:12px;font-weight:700}
.cat-related a:hover{border-color:var(--red)}
@keyframes catSpin{to{transform:translateY(-50%) rotate(360deg)}}
@keyframes catPop{0%{transform:scale(1)}45%{transform:scale(1.16)}100%{transform:scale(1)}}

/* ─────────────── 🗂️ DETAIL TABS: Overview / Videos / Gallery ─────────────── */
.cat-tabs{display:flex;align-items:stretch;gap:2px;flex-wrap:wrap;border-bottom:2px solid var(--line);
margin:22px 0 20px;position:relative}
.cat-tab{background:none;border:0;color:var(--mut);font-family:inherit;font-weight:800;font-size:13px;
padding:12px 16px;cursor:pointer;position:relative;white-space:nowrap;transition:color .18s,transform .18s}
.cat-tab:hover{color:var(--txt);transform:translateY(-2px)}
.cat-tab.active{color:var(--red)}
.cat-tab::after{content:'';position:absolute;left:12px;right:12px;bottom:-2px;height:2px;
background:var(--red);transform:scaleX(0);transition:transform .28s cubic-bezier(.34,1.4,.64,1)}
.cat-tab.active::after{transform:scaleX(1)}
.cat-tab-n{display:inline-block;min-width:19px;margin-left:6px;padding:1px 6px;border-radius:20px;
background:var(--bg3);border:1px solid var(--line);font-size:10px;font-weight:800;color:var(--mut);
vertical-align:middle;transition:background .2s,color .2s}
.cat-tab.active .cat-tab-n{background:var(--red);border-color:var(--red);color:#fff}
.cat-tabspace{flex:1;min-width:8px}
.cat-tabedit{align-self:center;margin-bottom:6px;padding:7px 13px;font-size:11px}
.cat-panel{display:none;animation:catPanelIn .42s cubic-bezier(.25,.8,.25,1) both}
.cat-panel.active{display:block}
@keyframes catPanelIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
.cat-panel .cat-card.enter{opacity:1!important}

/* 🎬 Video tab */
.cat-vgrid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
@media(min-width:620px){.cat-vgrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
@media(min-width:1024px){.cat-vgrid{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
.cat-vgrid>.cat-vempty{grid-column:1/-1}
.cat-vcard{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
overflow:hidden;text-decoration:none;color:var(--txt);position:relative;opacity:0;cursor:pointer;
transform:translateY(18px) scale(.97);transition:transform .28s,border-color .22s,box-shadow .28s}
.cat-vcard:focus-visible{outline:2px solid var(--red);outline-offset:2px}
.cat-vcard.in{animation:catIn .5s cubic-bezier(.34,1.2,.64,1) forwards}
.cat-vcard:hover{transform:translateY(-5px) scale(1.015);border-color:var(--red);
box-shadow:0 14px 34px rgba(0,0,0,.45)}
.cat-vposter{position:relative;aspect-ratio:16/9;background:var(--bg3);overflow:hidden}
.cat-vposter img{width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .35s,transform .35s}
.cat-vposter img.on{opacity:1}.cat-vcard:hover .cat-vposter img{transform:scale(1.06)}
.cat-vph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
font-size:32px;color:var(--mut)}
.cat-vplay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
font-size:30px;background:linear-gradient(transparent,rgba(0,0,0,.5));opacity:0;transition:opacity .2s}
.cat-vcard:hover .cat-vplay{opacity:1}
.cat-vnum{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.7);color:#fff;
border-radius:6px;padding:3px 8px;font-size:10px;font-weight:800}
.cat-vinfo{padding:11px 12px}
.cat-vtitle{font-size:12.5px;font-weight:800;line-height:1.35;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cat-vsub{font-size:10px;color:var(--mut);margin-top:5px;font-weight:700}
.cat-vempty,.cat-gempty{background:var(--card);border:1px dashed var(--line);border-radius:12px;
padding:34px 18px;text-align:center;color:var(--mut);font-size:13px;font-weight:700}

/* 🖼️ Gallery tab */
.cat-galgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
@media(min-width:700px){.cat-galgrid{grid-template-columns:repeat(auto-fill,minmax(190px,1fr))}}
.cat-galitem{position:relative;aspect-ratio:1;border-radius:11px;overflow:hidden;border:1px solid var(--line);
background:var(--bg3);cursor:zoom-in;opacity:0;transform:scale(.94)}
.cat-galitem.in{animation:catIn .48s cubic-bezier(.34,1.2,.64,1) forwards}
.cat-galitem img{width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .35s,transform .3s}
.cat-galitem img.on{opacity:1}.cat-galitem:hover img{transform:scale(1.06)}
.cat-galdel{position:absolute;top:7px;right:7px;background:rgba(160,8,8,.9);border:0;color:#fff;
border-radius:6px;padding:4px 8px;font-size:10px;font-weight:800;cursor:pointer;opacity:0;
transition:opacity .2s}.cat-galitem:hover .cat-galdel{opacity:1}
.cat-lib{margin-top:26px}
.cat-lib-title{font-size:14px;font-weight:900;margin-bottom:12px;letter-spacing:-.2px}

/* ✏️ Editor: multi-video rows + visual gallery + sticky picker */
.cat-hint{display:block;font-size:10.5px;font-weight:600;color:var(--mut);margin-top:4px}
.cat-vrow{display:flex;gap:6px;align-items:center;margin-bottom:7px;animation:catRowIn .3s ease both}
@keyframes catRowIn{from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:none}}
.cat-vrow .cat-input{flex:1;min-width:0;margin:0}
.cat-vrow .v-fid{flex:1.3}
.cat-vbtn{background:var(--bg3);border:1px solid var(--line);color:var(--txt);border-radius:7px;
width:29px;height:34px;flex:0 0 29px;font-size:11px;cursor:pointer;font-family:inherit;
transition:background .15s,border-color .15s}
.cat-vbtn:hover{background:var(--bg2);border-color:var(--red)}
.cat-pickbar{display:flex;gap:8px;align-items:center;margin-top:9px;flex-wrap:wrap}
.cat-pickbar .cat-input{flex:1 1 220px;margin:0}
.cat-picker.max{position:static;max-height:230px;overflow:auto;margin-top:8px;
border:1px solid var(--line);border-radius:9px;background:var(--bg2)}
.cat-picker.max .cat-pick{display:flex;justify-content:space-between;align-items:center;gap:10px}
.cat-pick .pick-add{font-size:10px;font-weight:800;color:var(--red);white-space:nowrap}
.cat-pick.added{background:var(--bg3);color:var(--mut)}
.cat-pick.added .pick-add{color:#2ecc71}
.cat-galedit{display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:8px;margin-bottom:9px}
.cat-galedit:empty{display:none}
.cat-gthumb{position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;border:1px solid var(--line);
background:var(--bg3);animation:catRowIn .3s ease both}
.cat-gthumb img{width:100%;height:100%;object-fit:cover}
.cat-gthumb button{position:absolute;top:3px;right:3px;background:rgba(160,8,8,.92);border:0;color:#fff;
border-radius:5px;width:20px;height:20px;font-size:10px;cursor:pointer;line-height:1}
.cat-galadd{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.cat-galadd .cat-input{flex:1 1 190px;margin:0}
.cat-sec-h{font-size:11px;font-weight:900;color:var(--mut);letter-spacing:.6px;text-transform:uppercase;
margin:16px 0 8px;border-top:1px solid var(--line);padding-top:14px}


/* ───────── 🏷️ Tag-driven video search (v5 का actor Linked Media) ───────── */
.cat-subhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0 12px}
.cat-subhead h3{font-size:14px;font-weight:900;margin:0;letter-spacing:-.2px}
.cat-subhead .cat-hint{margin:0}
.cat-tagline{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.cat-tagpill{background:var(--bg3);border:1px solid var(--line);border-radius:20px;
padding:4px 10px;font-size:10.5px;font-weight:800;color:var(--mut)}
.cat-tagpill b{color:var(--red)}
.cat-mediabar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
.cat-mediabar .cat-search{flex:1 1 230px}
.cat-mediabar .cat-search input{width:100%;box-sizing:border-box;background:var(--bg3);
border:1.5px solid var(--line);border-radius:9px;padding:11px 14px;color:var(--txt);
font:600 13px inherit;font-family:inherit;outline:none;transition:border-color .18s,box-shadow .18s}
.cat-mediabar .cat-search input:focus{border-color:var(--red);box-shadow:0 0 0 3px rgba(229,9,20,.14)}
.cat-mediainfo{font-size:11px;font-weight:700;color:var(--mut);margin:0 0 12px;min-height:14px}
.cat-mediainfo b{color:var(--txt)}
.cat-mediapg{display:flex;gap:9px;align-items:center;justify-content:center;margin-top:16px}
.cat-mediapg button{background:var(--bg3);border:1px solid var(--line);color:var(--txt);
border-radius:8px;padding:8px 14px;font:800 11px inherit;font-family:inherit;cursor:pointer}
.cat-mediapg button:disabled{opacity:.4;cursor:default}
.cat-mediapg span{font-size:11px;font-weight:800;color:var(--mut)}
.cat-vgrid + .cat-subhead{margin-top:28px;border-top:1px solid var(--line);padding-top:22px}
.cat-toast{position:fixed;bottom:24px;left:50%;transform:translate(-50%,24px);z-index:400;
background:var(--card);border:1px solid var(--line);border-left:3px solid var(--red);
border-radius:10px;padding:11px 16px;font-size:12px;font-weight:800;color:var(--txt);
box-shadow:0 12px 34px rgba(0,0,0,.5);opacity:0;pointer-events:none;
transition:opacity .25s,transform .3s cubic-bezier(.34,1.3,.64,1);white-space:nowrap}
.cat-toast.show{opacity:1;transform:translate(-50%,0);pointer-events:auto}
.cat-toast.err{border-left-color:#e74c3c}
/* 🖼️ direct upload bar in Gallery/Screenshots tab */
.cat-uploadbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:var(--card);
border:1px dashed var(--line);border-radius:12px;padding:14px;margin-bottom:16px}
.cat-uploadbar .cat-hint{margin:0;flex:1 1 180px}
.cat-uploadbar .cat-upload{margin:0}
.cat-upnote{font-size:11px;font-weight:700;color:var(--mut);min-height:14px;margin-bottom:12px}

/* ♿ v5 में नहीं था: reduced-motion वालों के लिए सारे animations बंद */
@media(prefers-reduced-motion:reduce){
.cat-card,.cat-card.enter,.cat-card.enter.in,.cat-hero,.cat-modal,.cat-mcard,.cat-toast,
.cat-lightbox,.cat-lightbox img,.cat-gal img,.cat-poster,.cat-skel,.cat-poster-wrap,
.cat-panel,.cat-vcard,.cat-galitem,.cat-vrow,.cat-gthumb,.cat-tab,.cat-tab::after,
.cat-toast,.cat-tagpill{
animation:none!important;transition:none!important;opacity:1!important;transform:none!important}
.cat-card.enter{opacity:1!important}
}
"""


# ─────────────────────────────────────────────────────────────
# 🧠 SHARED JS — listing + inline editor (एक ही code दोनों kinds के लिए)
# ─────────────────────────────────────────────────────────────
CATALOG_JS = r"""
<script>
const CFG = __CFG__;
const ADMIN = __ADMIN__;
const LIMIT = 20;
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = {q:'', cat:'all', mode:localStorage.getItem('ff_cat_mode_'+CFG.kind)||'poster',
             offset:0, page:1, hasNext:false, req:0, items:{}, editing:null, dirty:false,
             flash:null, gallery:[]};

function imgSrc(v){
  if(!v) return '';
  if(v.indexOf('TG_ID:') === 0) return '/api/catalog/photo?id='+encodeURIComponent(v.slice(6));
  return v;
}
function catLabel(v){
  const c = CFG.categories.find(x => x.value === v);
  return c ? c.label : (v || '—');
}
function cardHTML(it){
  const id = esc(it.id), src = imgSrc(it.image);
  const tags = (it.tags||[]).slice(0,2).map(t=>'#'+t).join(' ');
  /* ⚠️ user data कभी inline JS string में नहीं — सिर्फ़ data-id */
  const admin = ADMIN ? `<div class="cat-actions">
      <button class="cat-edit" onclick="event.stopPropagation();openEditor(this.closest('.cat-card').dataset.id)">✏️ Edit</button>
      <button class="cat-del" onclick="event.stopPropagation();removeItem(this.closest('.cat-card').dataset.id)">🗑 Delete</button>
    </div>` : '';
  if(state.mode === 'text'){
    return `<div class="cat-card enter" data-id="${id}" onclick="openDetail(this.dataset.id)">
      <div class="cat-meta"><span class="cat-meta-main">${esc(it.title)}</span>
      <span class="cat-meta-sub">${esc(catLabel(it.category))} · ${esc(tags)}</span></div>${admin}</div>`;
  }
  return `<div class="cat-card enter" data-id="${id}" onclick="openDetail(this.dataset.id)">
    <div class="cat-poster-wrap">
      ${src ? `<img class="cat-poster" src="${esc(src)}" alt="" loading="lazy"
          onload="this.classList.add('on')" onerror="this.remove()">` : '<div class="cat-ph">🖼️</div>'}
      <div class="cat-badge">${esc(catLabel(it.category))}</div>
      <div class="cat-grad"><div class="cat-name">${esc(it.title)}</div></div>${admin}
    </div>
    <div class="cat-meta"><span class="cat-meta-main">${esc(it.title)}</span>
      <span class="cat-meta-sub">${esc(tags || 'No tags')}</span></div>
  </div>`;
}
function skeletons(){
  return Array.from({length:8},()=>'<div class="cat-skel"></div>').join('');
}
function emptyHTML(){ return `<div class="cat-empty">${esc(CFG.empty)}<br><span style="font-size:12px">दूसरा keyword या category चुनें।</span></div>`; }

/* ✨ staggered entrance — v5 की staggerCards, पर reduced-motion aware */
function reveal(grid){
  const cards = Array.from(grid.querySelectorAll('.cat-card.enter'));
  if(!cards.length) return;
  if(!('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches){
    cards.forEach(c=>c.classList.remove('enter')); return;
  }
  let seen = 0;
  const obs = new IntersectionObserver(entries => entries.forEach(e => {
    if(!e.isIntersecting) return;
    const c = e.target, delay = Math.min(seen++, 10) * 0.07;
    c.style.animationDelay = delay+'s';
    c.classList.add('in');
    setTimeout(()=>{ c.classList.remove('enter','in'); c.style.animationDelay=''; }, (0.55+delay)*1000);
    obs.unobserve(c);
  }), {threshold:.08});
  cards.forEach(c=>obs.observe(c));
  if(state.flash){
    const el = grid.querySelector(`[data-id="${state.flash}"]`);
    if(el) el.classList.add('flash');
    state.flash = null;
  }
}
function bump(){
  const el = $('#catCount'); el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump');
}
function updatePg(){
  const box = $('#catPg');
  box.classList.toggle('show', state.offset > 0 || state.hasNext);
  $('#catPrev').disabled = state.offset === 0;
  $('#catNext').disabled = !state.hasNext;
  $('#catPage').textContent = 'Page ' + state.page;
}
async function load(reset){
  if(reset){ state.offset = 0; state.page = 1; }
  const my = ++state.req, grid = $('#catGrid'), search = $('#catSearch');
  search.classList.add('loading');
  if(reset) grid.innerHTML = skeletons();
  try{
    const r = await fetch(`/api/catalog/${CFG.kind}?q=${encodeURIComponent(state.q)}&category=${encodeURIComponent(state.cat)}&offset=${state.offset}&limit=${LIMIT}`);
    if(r.status === 401){ location.href='/login'; return; }
    const d = await r.json();
    if(my !== state.req) return;
    state.items = {};
    (d.items||[]).forEach(it => state.items[it.id] = it);
    grid.className = 'cat-grid' + (state.mode === 'text' ? ' mode-text' : '');
    grid.innerHTML = (d.items||[]).length ? (d.items||[]).map(cardHTML).join('') : emptyHTML();
    state.hasNext = !!d.has_next;
    $('#catCount').textContent = (d.total||0) + ' entries';
    bump(); updatePg(); reveal(grid);
  }catch(e){ grid.innerHTML = '<div class="cat-empty">⚠️ Load नहीं हुआ। '+esc(e.message||e)+'</div>'; }
  finally{ if(my === state.req) search.classList.remove('loading'); }
}
function openDetail(id){ location.href = CFG.detail + encodeURIComponent(id); }

/* ── toast (Undo सहित) ── */
let toastTimer = null;
function toast(msg, type, actionLabel, actionFn){
  const t = $('#catToast');
  t.className = 'cat-toast show ' + (type||'ok');
  t.innerHTML = `<span>${esc(msg)}</span>`;
  if(actionLabel){
    const b = document.createElement('button');
    b.textContent = actionLabel;
    b.onclick = () => { actionFn(); hideToast(); };
    t.appendChild(b);
  }
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, actionLabel ? 7000 : 3200);
}
function hideToast(){ const t=$('#catToast'); t.classList.remove('show'); }

/* ── ripple (v5 का btnRipple, बिना CDN) ── */
document.addEventListener('pointerdown', e => {
  const b = e.target.closest('.cat-btn,.cat-edit,.cat-del,.cat-upload');
  if(!b) return;
  const r = b.getBoundingClientRect(), i = document.createElement('i');
  const d = Math.max(r.width, r.height);
  i.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX-r.left-d/2}px;top:${e.clientY-r.top-d/2}px`;
  b.classList.add('cat-ripple'); b.appendChild(i);
  setTimeout(()=>i.remove(), 520);
});

/* ── inline editor ── */
function editorHTML(){
  const opts = ['<option value="all">📂 All</option>']
    .concat(CFG.categories.map(c=>`<option value="${esc(c.value)}">${esc(c.label)}</option>`)).join('');
  return `<div class="cat-modal" id="catModal" onclick="if(event.target===this)closeEditor()">
  <div class="cat-mcard">
    <div class="cat-mhead"><div class="cat-mtitle" id="catMTitle">✏️ New ${esc(CFG.singular)}</div>
      <button class="cat-x" onclick="closeEditor()">✕</button></div>
    <div class="cat-grid2">
      <div class="cat-field"><label class="cat-label">${esc(CFG.nameLabel)} *</label>
        <input class="cat-input" id="fTitle" maxlength="120" required></div>
      <div class="cat-field"><label class="cat-label">Category</label>
        <select class="cat-fselect" id="fCat">${opts}</select></div>
    </div>
    <div class="cat-field"><label class="cat-label">${esc(CFG.bodyLabel)}</label>
      <textarea class="cat-textarea" id="fBody" maxlength="3000"></textarea></div>
    <div class="cat-field"><label class="cat-label">Search Tags (comma separated)</label>
      <input class="cat-input" id="fTags" placeholder="e.g. Action, Thriller, 2024"></div>
    <div class="cat-field"><label class="cat-label">${esc(CFG.imageLabel)}</label>
      <div class="cat-preview" id="fPreview"><span>कोई image नहीं</span></div>
      <input class="cat-input" id="fImage" placeholder="https://… या TG_ID:…" style="margin-bottom:8px">
      <label class="cat-upload">📂 Upload image
        <input type="file" id="fUpload" accept="image/*" onchange="uploadImage(this)"></label>
      <span id="fUploadNote" style="font-size:11px;color:var(--mut);margin-left:8px"></span></div>
    <div class="cat-sec-h">${esc(CFG.videoLabel)}</div>
    <div class="cat-field"><label class="cat-label">Videos / Episodes
      <span class="cat-hint">${esc(CFG.videoHint)}</span></label>
      <div id="fVideos"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:7px;align-items:center">
        <button class="cat-btn ghost" type="button" onclick="addVideo('','')" style="padding:7px 13px;font-size:11px">➕ Add Video</button>
        <span class="cat-hint" id="fVideoCount" style="margin:0"></span></div>
      <div class="cat-pickbar">
        <input class="cat-input" id="fPickerQ" placeholder="🔍 Library में file खोजें — कई videos एक साथ चुन सकते हैं…"
          oninput="clearTimeout(window.__pk);window.__pk=setTimeout(pickMedia,320)">
        <button class="cat-btn ghost" type="button" onclick="donePicking()" style="padding:7px 13px;font-size:11px">✓ Done</button>
      </div>
      <div class="cat-picker max" id="fPicker"></div></div>
    <div class="cat-sec-h">${esc(CFG.galleryIcon)} ${esc(CFG.galleryLabel)}</div>
    <div class="cat-field"><span class="cat-hint">${esc(CFG.galleryHint)}</span>
      <div class="cat-galedit" id="fGalList"></div>
      <div class="cat-galadd">
        <label class="cat-upload">${esc(CFG.uploadLabel)} (multiple)
          <input type="file" id="fGalUpload" accept="image/*" multiple onchange="uploadGallery(this)"></label>
        <input class="cat-input" id="fGalUrl" placeholder="https://… या TG_ID:…">
        <button class="cat-btn ghost" type="button" onclick="addGalleryUrl()" style="padding:7px 13px;font-size:11px">➕ Add URL</button>
      </div>
      <span class="cat-hint" id="fGalNote"></span></div>
    <div class="cat-sec-h">${esc(CFG.linkLabel)}</div>
    <div class="cat-field">
      <div id="fLinks"></div>
      <button class="cat-btn ghost" type="button" onclick="addLink('','')" style="padding:7px 13px;font-size:11px">➕ Add row</button>
    </div>
    <div class="cat-mfoot">
      <span class="cat-dirty" id="fDirty" style="display:none">● Unsaved changes</span>
      <button class="cat-btn ghost" type="button" id="fDelete" onclick="deleteFromEditor()" style="display:none">🗑 Delete</button>
      <button class="cat-btn" type="button" onclick="saveEditor()">💾 Save</button>
    </div>
  </div></div>`;
}
function linkRow(label, value){
  const wrap = document.createElement('div');
  wrap.className = 'cat-linkrow';
  const a = document.createElement('input'); a.className='cat-input'; a.placeholder=CFG.linkLabelField; a.value=label||'';
  const b = document.createElement('input'); b.className='cat-input'; b.placeholder=CFG.linkValueField; b.value=value||'';
  const x = document.createElement('button'); x.className='cat-mini'; x.type='button'; x.textContent='✕';
  x.onclick = ()=>{ wrap.remove(); markDirty(); };
  a.oninput = b.oninput = markDirty;
  wrap.append(a,b,x);
  $('#fLinks').appendChild(wrap);
}
function addLink(l,v){ linkRow(l,v); markDirty(); }

/* 🎬 MULTI-VIDEO: हर row = {label, file_id}. कोई hardcoded limit नहीं (UI 50 तक)।
   ▲▼ से order बदलें, ✕ से हटाएँ, Library picker से एक के बाद एक कई चुनें। */
function videoRow(label, fid){
  const wrap = document.createElement('div'); wrap.className = 'cat-vrow';
  const a = document.createElement('input'); a.className='cat-input v-label';
  a.placeholder='Label (Ep 1 · 1080p)'; a.value=label||'';
  const b = document.createElement('input'); b.className='cat-input v-fid';
  b.placeholder='Telegram File ID'; b.value=fid||'';
  const up=document.createElement('button'), dn=document.createElement('button'), x=document.createElement('button');
  for(const btn of [up,dn,x]){ btn.className='cat-vbtn'; btn.type='button'; }
  up.textContent='▲'; up.title='ऊपर ले जाएँ'; dn.textContent='▼'; dn.title='नीचे ले जाएँ';
  x.textContent='✕'; x.title='ये video हटाएँ';
  up.onclick=()=>{ if(wrap.previousElementSibling){ $('#fVideos').insertBefore(wrap,wrap.previousElementSibling); markDirty(); } };
  dn.onclick=()=>{ if(wrap.nextElementSibling){ $('#fVideos').insertBefore(wrap.nextElementSibling,wrap); markDirty(); } };
  x.onclick=()=>{ wrap.remove(); updateVideoCount(); markDirty(); };
  a.oninput=b.oninput=markDirty;
  wrap.append(a,b,up,dn,x);
  $('#fVideos').appendChild(wrap);
  updateVideoCount();
  return wrap;
}
function addVideo(l,v){ const w=videoRow(l,v); w.querySelector('input').focus(); }
function updateVideoCount(){
  const n=$('#fVideos').children.length;
  $('#fVideoCount').textContent = n
    ? `${n} video${n>1?'s':''} attached — और जोड़ सकते हैं` : 'कोई video नहीं — ऊपर से जोड़ें';
}
function attachedIds(){
  return Array.from(document.querySelectorAll('#fVideos .v-fid')).map(i=>i.value.trim()).filter(Boolean);
}
/* 🖼️ Gallery — visual thumbnails + remove, textarea की जगह */
function renderGallery(){
  const box=$('#fGalList'); box.innerHTML='';
  state.gallery.forEach((val,i)=>{
    const d=document.createElement('div'); d.className='cat-gthumb';
    const im=document.createElement('img'); im.src=imgSrc(val); im.onerror=()=>im.remove();
    const x=document.createElement('button'); x.type='button'; x.textContent='✕'; x.title='हटाएँ';
    x.onclick=()=>{ state.gallery.splice(i,1); renderGallery(); markDirty(); };
    d.append(im,x); box.appendChild(d);
  });
}
function addGalleryUrl(){
  const el=$('#fGalUrl'), v=el.value.trim();
  if(!v) return;
  if(state.gallery.length>=12) return toast('Maximum 12 images','err');
  state.gallery.push(v); el.value=''; renderGallery(); markDirty(); toast('🖼️ Image जोड़ी गई');
}
async function uploadGallery(input){
  const files=Array.from(input.files||[]); if(!files.length) return;
  const note=$('#fGalNote');
  /* Telegram rate-limit से बचने के लिए uploads भी एक-एक करके (जैसे thumbnails) */
  for(let i=0;i<files.length && state.gallery.length<12;i++){
    note.textContent=`⏳ Uploading ${i+1}/${files.length} — एक-एक करके…`;
    const fd=new FormData(); fd.append('image',files[i]);
    try{
      const r=await fetch('/api/catalog/upload',{method:'POST',body:fd});
      const d=await r.json();
      if(!d.ok) throw new Error(d.error||'Upload failed');
      state.gallery.push(d.value); renderGallery(); markDirty();
    }catch(e){ note.textContent='⚠️ '+e.message+' (URL paste करें)'; break; }
  }
  note.textContent=`✅ ${state.gallery.length} images ready — Save दबाएँ`;
  input.value='';
}
function donePicking(){
  const b=$('#fPicker'); b.classList.remove('show'); b.innerHTML='';
  toast('✓ Videos जोड़े गए — अब Save दबाएँ');
}
function markDirty(){ state.dirty = true; $('#fDirty').style.display='inline'; }
function setPreview(v){
  const p = $('#fPreview'), src = imgSrc(v);
  p.innerHTML = src ? `<img src="${esc(src)}" onerror="this.remove()">` : '<span>कोई image नहीं</span>';
}
async function openEditor(id, focus){
  state.editing = id || null; state.dirty = false;
  let it = id ? state.items[id] : null;
  if(id && !it){
    try{
      const r = await fetch(`/api/catalog/${CFG.kind}?id=${encodeURIComponent(id)}`);
      const d = await r.json();
      it = (d.items||[])[0] || null;
    }catch(e){ it = null; }
  }
  $('#catMTitle').textContent = id ? '✏️ Edit '+CFG.singular : '✨ New '+CFG.singular;
  $('#fTitle').value = it ? (it.title||'') : '';
  $('#fCat').value = it ? (it.category||CFG.categories[0].value) : CFG.categories[0].value;
  $('#fBody').value = it ? (it.body||'') : '';
  $('#fTags').value = it ? (it.tags||[]).join(', ') : '';
  $('#fImage').value = it ? (it.image||'') : '';
  /* 🎬 videos — पुराने posts के `links` को API पहले ही migrate कर देती है */
  $('#fVideos').innerHTML = '';
  const vids = (it && it.videos) || [];
  if(vids.length) vids.forEach(v=>videoRow(v.label, v.file_id));
  else if(!id) videoRow('','');   /* नया entry → एक खाली row से शुरू, multiple साफ़ दिखे */
  updateVideoCount();
  state.gallery = it ? [...(it.gallery||[])] : [];
  renderGallery();
  $('#fGalNote').textContent = '';
  $('#fGalUrl').value = '';
  $('#fPickerQ').value = ''; $('#fPicker').innerHTML = ''; $('#fPicker').classList.remove('show');
  $('#fLinks').innerHTML = '';
  (it && it.links || []).forEach(l=>linkRow(l.label,l.value));
  $('#fDelete').style.display = id ? 'inline-block' : 'none';
  $('#fDirty').style.display = 'none';
  setPreview($('#fImage').value);
  const m = $('#catModal'); m.classList.add('open');
  requestAnimationFrame(()=>m.classList.add('show'));
  setTimeout(()=>{
    const el = focus==='videos' ? $('#fPickerQ') : focus==='gallery' ? $('#fGalUrl') : $('#fTitle');
    if(el){ el.focus(); if(focus) el.scrollIntoView({block:'center',behavior:'smooth'}); }
  }, 150);
}
function closeEditor(force){
  if(!force && state.dirty && !confirm('बदलाव save नहीं हुए हैं। फिर भी बंद करें?')) return;
  const m = $('#catModal'); m.classList.remove('show');
  setTimeout(()=>m.classList.remove('open'), 220);
  state.editing = null; state.dirty = false;
}
function collect(){
  const links = Array.from(document.querySelectorAll('#fLinks .cat-linkrow')).map(r=>{
    const inp = r.querySelectorAll('input');
    return {label:inp[0].value.trim(), value:inp[1].value.trim()};
  }).filter(l=>l.label && l.value);
  return {
    id: state.editing || '',
    title: $('#fTitle').value.trim(),
    category: $('#fCat').value,
    body: $('#fBody').value.trim(),
    tags: $('#fTags').value,
    image: $('#fImage').value.trim(),
    gallery: state.gallery.slice(),
    links,
    videos: Array.from(document.querySelectorAll('#fVideos .cat-vrow')).map(r=>({
      label: r.querySelector('.v-label').value.trim(),
      file_id: r.querySelector('.v-fid').value.trim()
    })).filter(v=>v.file_id)
  };
}
async function saveEditor(){
  const payload = collect();
  if(!payload.title){ toast('Title ज़रूरी है', 'err'); $('#fTitle').focus(); return; }
  const btn = document.querySelector('#catModal .cat-mfoot .cat-btn:last-child');
  btn.disabled = true; btn.textContent = '⏳ Saving…';
  try{
    const r = await fetch(`/api/catalog/${CFG.kind}/save`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const d = await r.json();
    if(!r.ok || !d.ok) throw new Error(d.error || 'Save failed');
    state.flash = d.item.id;
    state.dirty = false;
    closeEditor(true);
    toast('✅ Saved');
    await load(true);
  }catch(e){ toast('⚠️ '+e.message, 'err'); }
  finally{ btn.disabled = false; btn.textContent = '💾 Save'; }
}
async function removeItem(id){
  const it = state.items[id];
  if(!it || !confirm(`"${it.title}" delete करें?`)) return;
  const r = await fetch(`/api/catalog/${CFG.kind}/delete`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({id})});
  const d = await r.json();
  if(!d.ok) return toast('⚠️ Delete failed', 'err');
  await load(true);
  toast('🗑 Deleted', 'err', '↩︎ Undo', async () => {
    const back = {...it}; delete back.id; delete back.created_at; delete back.updated_at;
    await fetch(`/api/catalog/${CFG.kind}/save`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({...back, id, restore:true})});
    load(true); toast('↩︎ Restored');
  });
}
async function deleteFromEditor(){
  const id = state.editing; if(!id) return;
  closeEditor(true); removeItem(id);
}
async function uploadImage(input){
  if(!input.files || !input.files[0]) return;
  const note = $('#fUploadNote'); note.textContent = '⏳ Uploading…';
  const fd = new FormData(); fd.append('image', input.files[0]);
  try{
    const r = await fetch('/api/catalog/upload', {method:'POST', body:fd});
    const d = await r.json();
    if(!d.ok) throw new Error(d.error || 'Upload failed');
    $('#fImage').value = d.value; setPreview(d.value); markDirty();
    note.textContent = '✅ Telegram पर save';
  }catch(e){ note.textContent = '⚠️ '+e.message+' (URL paste करें)'; }
  input.value = '';
}
async function pickMedia(){
  const q = $('#fPickerQ').value.trim();
  const box = $('#fPicker');
  if(q.length < 2){ box.classList.remove('show'); return; }
  box.classList.add('show'); box.innerHTML = '<div class="cat-pick">🔍 Searching…</div>';
  try{
    const r = await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=12');
    const d = await r.json();
    const have = new Set(attachedIds());
    box.innerHTML = (d.results||[]).length
      ? d.results.map(f=>{
          const fid=esc(f.file_id), name=esc(f.name), added=have.has(f.file_id);
          return `<div class="cat-pick${added?' added':''}" data-fid="${fid}" data-name="${name}">`
               + `<span>${name}</span><span class="pick-add">${added?'✓ Added':'+ Add'}</span></div>`;
        }).join('')
      : '<div class="cat-pick">कोई file नहीं मिली</div>';
  }catch(e){ box.innerHTML = '<div class="cat-pick">⚠️ Error</div>'; }
}
/* ⚠️ picker खुला रहता है — एक search से कई videos जोड़े जा सकते हैं */
document.addEventListener('click', e => {
  const p = e.target.closest('#fPicker .cat-pick');
  if(!p || !p.dataset.fid) return;
  const fid = p.dataset.fid;
  if(attachedIds().includes(fid)) return toast('ये video पहले से जोड़ा है');
  if($('#fVideos').children.length >= 50) return toast('Maximum 50 videos','err');
  videoRow((p.dataset.name||'Video').slice(0,70), fid);
  p.classList.add('added');
  const tag=p.querySelector('.pick-add'); if(tag) tag.textContent='✓ Added';
  markDirty(); toast(`📎 ${$('#fVideos').children.length} videos — और चुन सकते हैं`);
});
document.addEventListener('keydown', e => {
  if(!$('#catModal') || !$('#catModal').classList.contains('open')) return;
  if(e.key === 'Escape') closeEditor();
  if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's'){ e.preventDefault(); saveEditor(); }
});
document.addEventListener('input', e => {
  if(e.target.closest('#catModal')) markDirty();
  if(e.target.id === 'fImage') setPreview(e.target.value);
});

/* ── wiring ── */
$('#catQ').addEventListener('input', e => {
  clearTimeout(window.__catTimer);
  window.__catTimer = setTimeout(()=>{ state.q = e.target.value.trim(); load(true); }, 320);
});
$('#catQ').addEventListener('keydown', e => {
  if(e.key === 'Enter'){ clearTimeout(window.__catTimer); state.q = e.target.value.trim(); load(true); }
});
$('#catCategory').addEventListener('change', e => { state.cat = e.target.value; load(true); });
$('#catMode').addEventListener('change', e => {
  state.mode = e.target.value; localStorage.setItem('ff_cat_mode_'+CFG.kind, state.mode);
  $('#catGrid').className = 'cat-grid' + (state.mode==='text'?' mode-text':'');
  load(false);
});
$('#catPrev').onclick = () => { if(state.offset>0){ state.offset=Math.max(0,state.offset-LIMIT); state.page--; load(false); window.scrollTo(0,0); } };
$('#catNext').onclick = () => { if(state.hasNext){ state.offset+=LIMIT; state.page++; load(false); window.scrollTo(0,0); } };
$('#catMode').value = state.mode;
$('#catGrid').className = 'cat-grid' + (state.mode==='text'?' mode-text':'');
load(true).then(()=>{
  const p = new URLSearchParams(location.search);
  if(p.get('new') && ADMIN) openEditor('');
  else if(p.get('edit') && ADMIN) openEditor(p.get('edit'), p.get('focus'));
});
</script>
"""

DETAIL_JS = r"""
<script>
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const D = __DETAIL_CFG__;
let GALLERY = D.gallery.slice();
let mediaLoaded=false, mediaOffset=0, mediaNext='';
let toastTimer=null;

function imageSrc(v){
  if(!v) return '';
  if(v.indexOf('TG_ID:')===0) return '/api/catalog/photo?id='+encodeURIComponent(v.slice(6));
  return v;
}
function toast(msg,type){
  const t=document.getElementById('catToast'); if(!t) return;
  t.className='cat-toast show '+(type||''); t.textContent=msg;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.classList.remove('show'),3000);
}
/* 🗂️ tabs: Post का तीसरा tab "Screenshots", Actor का "Gallery" — एक ही engine */
function switchTab(name, init){
  if(name===D.tabAlias) name='gallery';
  if(!['overview','videos','gallery'].includes(name)) name='overview';
  document.querySelectorAll('.cat-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.cat-panel').forEach(p=>p.classList.toggle('active',p.id==='cp-'+name));
  if(name==='videos'){ stagger('#catVideos .cat-vcard'); if(D.tagMedia && !mediaLoaded) loadMedia(0); }
  if(name==='gallery') stagger('#catGallery .cat-galitem');
  if(!init){
    const u=new URL(location.href); u.searchParams.set('tab',name);
    history.replaceState(null,'',u.pathname+u.search);
  }
}
function stagger(sel){
  const els=Array.from(document.querySelectorAll(sel)).filter(e=>!e.classList.contains('in'));
  const reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
  els.forEach((e,i)=>{
    if(!reduce) e.style.animationDelay=(Math.min(i,12)*0.06)+'s';
    e.classList.add('in');
  });
}

/* ── 🏷️ v5 का tag-driven Linked Media, पर fsv1 की JSON API से ── */
function mediaCard(f){
  const meta=[f.size,f.duration,f.res].filter(Boolean).join(' · ');
  return '<div class="cat-vcard" role="button" tabindex="0" data-fid="'+esc(f.file_id)+'" '
    + 'data-name="'+esc(f.name)+'" aria-label="Play '+esc(f.name)+'">'
    + '<div class="cat-vposter"><div class="cat-vph">🎬</div>'
    + '<img src="'+esc(f.thumb)+'" alt="" loading="lazy" onerror="this.remove()">'
    + '<span class="cat-vnum">'+esc(f.quality||'VIDEO')+'</span><span class="cat-vplay">▶</span></div>'
    + '<div class="cat-vinfo"><div class="cat-vtitle">'+esc(f.name)+'</div>'
    + '<div class="cat-vsub">'+esc(meta ? meta+' · ▶ Click to play' : '▶ Click to play')+'</div></div></div>';
}
/* ▶ main page जैसा ही shared player — नाम/card पर click → छोटा modal */
function playCard(c){
  if(!c || !c.dataset.fid) return;
  if(typeof window.play==='function') window.play(c.dataset.fid, c.dataset.name||'Video');
}
document.addEventListener('click',e=>{
  const c=e.target.closest('.cat-vcard[data-fid]');
  if(c) playCard(c);
});
async function loadMedia(offset){
  if(!D.tagMedia) return;                 /* Post पर search-text results नहीं चाहिए */
  const box=document.getElementById('catMediaResults'); if(!box) return;
  mediaLoaded=true; mediaOffset=Math.max(0,offset||0);
  const q=(document.getElementById('catMediaQ')||{}).value||'';
  const info=document.getElementById('catMediaInfo');
  if(info) info.textContent='⏳ Library में खोजा जा रहा है…';
  try{
    const r=await fetch('/api/catalog/'+D.kind+'/media?id='+encodeURIComponent(D.id)
      +'&q='+encodeURIComponent(q.trim())+'&offset='+mediaOffset+'&limit='+D.limit);
    const d=await r.json();
    mediaNext=d.next_offset||'';
    const cards=(d.results||[]).map(mediaCard);
    box.innerHTML=cards.length?cards.join('')
      : '<div class="cat-vempty">🔍 इन tags से कोई Library file नहीं मिली।<br>'
        + '<span style="font-size:11px;font-weight:600">ऊपर search box में नाम लिखकर भी ढूँढ सकते हैं।</span></div>';
    box.querySelectorAll('img').forEach(im=>{
      im.addEventListener('load',()=>im.classList.add('on'));
      if(im.complete&&im.naturalWidth) im.classList.add('on');
    });
    if(info){
      if(d.source==='tags') info.innerHTML='🏷️ <b>'+d.terms.length+'</b> Search Tags से <b>'+d.total+'</b> videos मिलीं';
      else if(d.source==='custom') info.innerHTML='🔍 &quot;'+esc(q.trim())+'&quot; के लिए <b>'+d.total+'</b> results';
      else info.innerHTML='📝 Title से <b>'+d.total+'</b> results (इस entry पर Tags नहीं हैं)';
    }
    const pg=document.getElementById('catMediaPg');
    if(pg){
      pg.style.display=(mediaOffset>0||mediaNext)?'flex':'none';
      const pr=document.getElementById('catMediaPrev'), nx=document.getElementById('catMediaNext');
      if(pr) pr.disabled=mediaOffset===0;
      if(nx) nx.disabled=!mediaNext;
      const lbl=document.getElementById('catMediaPage');
      if(lbl) lbl.textContent='Page '+(Math.floor(mediaOffset/D.limit)+1);
    }
    stagger('#catMediaResults .cat-vcard');
  }catch(e){ if(info) info.textContent='⚠️ Load नहीं हुआ'; }
}
function mediaPage(step){
  if(!D.tagMedia) return;
  const next=mediaOffset+step*D.limit;
  if(next<0 || (step>0&&!mediaNext)) return;
  loadMedia(next);
}

/* ── 🖼️ Gallery / Screenshots — direct upload + in-place delete ── */
function renderGallery(){
  const box=document.getElementById('catGallery'); if(!box) return;
  box.innerHTML=GALLERY.length ? GALLERY.map((src,i)=>
      '<div class="cat-galitem in" data-idx="'+i+'" data-src="'+esc(src)+'" '
      +'onclick="openLight(this.dataset.src)">'
      +'<img src="'+esc(src)+'" alt="" loading="lazy" '
      +'onload="this.classList.add(\'on\')" onerror="this.remove()">'
      +(D.admin ? '<button class="cat-galdel" title="हटाएँ" '
        +'onclick="event.stopPropagation();deleteGallery('+i+')">✕</button>' : '')
      +'</div>').join('')
    : '<div class="cat-gempty">'+esc(D.galleryEmpty)+'</div>';
  const n=document.querySelector('.cat-tab[data-tab="gallery"] .cat-tab-n');
  if(n) n.textContent=GALLERY.length;
}
async function uploadGalleryFiles(input){
  const files=Array.from(input.files||[]); if(!files.length) return;
  const note=document.getElementById('catUpNote');
  const fd=new FormData();
  files.slice(0,12).forEach(f=>fd.append('image',f));
  fd.append('id',D.id);
  if(note) note.textContent='⏳ '+files.length+' photos Telegram पर एक-एक करके…';
  try{
    const r=await fetch('/api/catalog/'+D.kind+'/gallery_upload',{method:'POST',body:fd});
    const d=await r.json();
    if(!d.ok) throw new Error(d.error||'Upload failed');
    (d.added||[]).forEach(v=>GALLERY.push(imageSrc(v)));
    renderGallery();
    if(note) note.textContent='✅ '+(d.added||[]).length+' photos जोड़ी गईं';
    toast('🖼️ '+(d.added||[]).length+' photos added');
  }catch(e){
    if(note) note.textContent='⚠️ '+e.message;
    toast('⚠️ '+e.message,'err');
  }
  input.value='';
}
async function deleteGallery(idx){
  if(!confirm('ये image हटाएँ?')) return;
  try{
    const r=await fetch('/api/catalog/'+D.kind+'/gallery_delete',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({id:D.id,index:Number(idx)})});
    const d=await r.json();
    if(!d.ok) return toast(d.error||'Delete failed','err');
    GALLERY.splice(idx,1); renderGallery(); toast('🗑 Image हटाई गई');
  }catch(e){ toast('Delete failed','err'); }
}
function openLight(src){
  const l=document.getElementById('catLight');
  l.querySelector('img').src=src; l.classList.add('open');
  requestAnimationFrame(()=>l.classList.add('show'));
}
function closeLight(){
  const l=document.getElementById('catLight'); l.classList.remove('show');
  setTimeout(()=>l.classList.remove('open'),250);
}
async function deleteDetail(id){
  if(!confirm('Delete करें?')) return;
  const r=await fetch('/api/catalog/'+D.kind+'/delete',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  const d=await r.json();
  if(d.ok) location.href=D.base; else toast('Delete failed','err');
}
document.querySelectorAll('.cat-vposter img,.cat-galitem img').forEach(img=>{
  img.addEventListener('load',()=>img.classList.add('on'));
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){ closeLight(); if(window.closePlayer) window.closePlayer(); }
  const focused=document.activeElement||{};
  if((e.key==='Enter'||e.key===' ') && focused.classList && focused.classList.contains('cat-vcard')){
    e.preventDefault(); playCard(focused); return;
  }
  const tag=focused.tagName;
  if(tag==='INPUT'||tag==='TEXTAREA') return;
  if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
    const names=['overview','videos','gallery'];
    const cur=document.querySelector('.cat-tab.active');
    let i=names.indexOf(cur?cur.dataset.tab:'overview');
    i=(i+(e.key==='ArrowRight'?1:names.length-1))%names.length;
    switchTab(names[i]);
  }
});
document.addEventListener('pointerdown',e=>{
  const b=e.target.closest('.cat-btn'); if(!b)return;
  const r=b.getBoundingClientRect(),i=document.createElement('i'),d=Math.max(r.width,r.height);
  i.style.cssText=`width:${d}px;height:${d}px;left:${e.clientX-r.left-d/2}px;top:${e.clientY-r.top-d/2}px`;
  b.classList.add('cat-ripple'); b.appendChild(i); setTimeout(()=>i.remove(),520);
});
const mq=document.getElementById('catMediaQ');
if(mq){
  let t;
  mq.addEventListener('input',()=>{ clearTimeout(t); t=setTimeout(()=>loadMedia(0),320); });
  mq.addEventListener('keydown',e=>{ if(e.key==='Enter'){ clearTimeout(t); loadMedia(0); } });
}
const _initTab=new URLSearchParams(location.search).get('tab');
switchTab(_initTab||'overview',true);
</script>
"""

def _category_options(kind: str, include_all: bool = True) -> str:
    cfg = CATALOGS[kind]
    out = ['<option value="all">📂 All Categories</option>'] if include_all else []
    out += [
        f'<option value="{html.escape(c["value"])}">{html.escape(c["label"])}</option>'
        for c in cfg["categories"]
    ]
    return "".join(out)


def _listing_body(kind: str, role: str) -> str:
    cfg = CATALOGS[kind]
    admin = role == "admin"
    create_btn = (
        '<button class="cat-btn" onclick="openEditor(\'\')">✨ New ' + html.escape(cfg["singular"]) + "</button>"
        if admin else ""
    )
    return f"""<div class="main"><div class="cat-wrap">
  <div class="cat-head">
    <div class="cat-title">{html.escape(cfg['icon'])} {html.escape(cfg['page'])}</div>
    <span class="cat-count" id="catCount">…</span>
    {create_btn}
  </div>
  <div class="cat-toolbar">
    <div class="cat-search" id="catSearch">
      <input type="search" id="catQ" placeholder="{html.escape(cfg['placeholder'])}" autocomplete="off">
      <div class="cat-spin"></div>
    </div>
    <select class="cat-select" id="catCategory">{_category_options(kind)}</select>
    <select class="cat-select" id="catMode">
      <option value="poster">🖼️ Poster</option><option value="text">📄 Text</option>
    </select>
  </div>
  <div class="cat-grid" id="catGrid"></div>
  <div class="cat-pg" id="catPg">
    <button id="catPrev">◀ Prev</button><span id="catPage">Page 1</span><button id="catNext">Next ▶</button>
  </div>
</div></div>
<div class="cat-toast" id="catToast"></div>
<div class="cat-lightbox" id="catLight" onclick="if(event.target===this)closeLight()">
  <img src="" alt=""></div>
<div id="catModalHost"></div>
"""


def build_listing_page(kind: str, role: str, tg_id: int):
    """📝 /posts · 🎭 /actors — एक ही shell, सिर्फ़ config बदलता है।"""
    cfg = CATALOGS[kind]
    js = (
        CATALOG_JS
        .replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
        .replace("__ADMIN__", "true" if role == "admin" else "false")
        # editor modal को JS से inject करें ताकि markup एक ही जगह रहे
        .replace("/* ── wiring ── */", "/* ── wiring ── */\n$('#catModalHost').innerHTML = editorHTML();")
    )
    return app_page(
        f"{cfg['label']} - Fast Finder",
        f"<style>{CATALOG_CSS}</style>" + _listing_body(kind, role) + js,
        tg_id=tg_id, role=role, active_tab=kind,
    )


def _detail_body(kind: str, role: str, item: dict) -> str:
    """🗂️ Overview / 🎬 Videos (tags-driven) / 🖼️ Gallery या 📸 Screenshots।"""
    cfg = CATALOGS[kind]
    esc = html.escape
    admin = role == "admin"
    src = image_src(item.get("image"))
    title = esc(str(item.get("title") or "Untitled"))
    cat_label = next(
        (c["label"] for c in cfg["categories"] if c["value"] == item.get("category")),
        esc(str(item.get("category") or "—")),
    )
    chips = "".join(
        f'<span class="cat-chip">#{esc(str(t))}</span>' for t in (item.get("tags") or [])[:12]
    )
    body = esc(str(item.get("body") or ""))
    item_id = esc(str(item.get("id") or ""))
    gallery_tab = esc(cfg["galleryTab"])
    videos_heading = esc(cfg["videosHeading"])
    video_empty_hint = esc(cfg["videoEmptyHint"])

    links_html = "".join(
        f'<a href="{esc(str(l.get("value") or ""))}" target="_blank" rel="noopener noreferrer">'
        f'🔗 {esc(str(l.get("label") or "Link"))}</a>'
        for l in (item.get("links") or [])[:20] if l.get("value")
    )

    # 📌 manually attached videos (पिछला multi-video feature बरकरार)
    videos = [v for v in (item.get("videos") or [])[:50] if v.get("file_id")]
    if videos:
        vids_html = ""
        for i, v in enumerate(videos):
            fid = str(v.get("file_id") or "")
            poster = "/api/thumb?file_id=" + quote(fid, safe="") + "&v=1"
            label = str(v.get("label") or f"Video {i+1}")
            vids_html += (
                f'<div class="cat-vcard" role="button" tabindex="0" '
                f'data-fid="{esc(fid)}" data-name="{esc(label)}" '
                f'aria-label="Play {esc(label)}">'
                f'<div class="cat-vposter"><div class="cat-vph">🎬</div>'
                f'<img src="{esc(poster)}" alt="" loading="lazy" onerror="this.remove()">'
                f'<span class="cat-vnum">#{i+1}</span><span class="cat-vplay">▶</span></div>'
                f'<div class="cat-vinfo"><div class="cat-vtitle">{esc(label)}</div>'
                f'<div class="cat-vsub">📌 Attached · ▶ Click to play</div></div></div>'
            )
    else:
        vids_html = (
            '<div class="cat-vempty">🎬 अभी कोई video attach नहीं है।'
            f'<br><span style="font-size:11px;font-weight:600">{video_empty_hint}</span></div>'
        )

    # 🏷️ v5 जैसा: Videos tab का मुख्य हिस्सा "Search Tags" से आता है
    tags = [str(t).strip() for t in (item.get("tags") or []) if str(t).strip()][:12]
    tag_section = ""
    if cfg["tagMedia"]:
        tag_pills = "".join(f'<span class="cat-tagpill">🏷️ <b>#{esc(t)}</b></span>' for t in tags)
        if not tag_pills:
            tag_pills = '<span class="cat-tagpill">🏷️ कोई Search Tag नहीं — <b>Title</b> से खोजेंगे</span>'
        tag_section = f"""
    <div class="cat-subhead"><h3>🏷️ Library से — Search Tags के आधार पर</h3>
      <span class="cat-hint">जैसे v5 का actor Linked Media tab</span></div>
    <div class="cat-tagline" id="catTagPills">{tag_pills}</div>
    <div class="cat-mediabar">
      <div class="cat-search"><input type="search" id="catMediaQ" autocomplete="off"
        placeholder="Search inside this profile… (खाली = Tags से auto)"></div>
      <button class="cat-btn ghost" style="padding:9px 14px;font-size:11px" onclick="loadMedia(0)">🔍 Search</button>
    </div>
    <div class="cat-mediainfo" id="catMediaInfo">Videos tab खोलते ही Tags से search…</div>
    <div class="cat-vgrid" id="catMediaResults"></div>
    <div class="cat-mediapg" id="catMediaPg" style="display:none">
      <button id="catMediaPrev" onclick="mediaPage(-1)">◀ Prev</button>
      <span id="catMediaPage">Page 1</span>
      <button id="catMediaNext" onclick="mediaPage(1)">Next ▶</button>
    </div>"""

    # 🖼️ / 📸 tab
    gallery = [image_src(g) for g in (item.get("gallery") or [])[:12]]
    gallery = [u for u in gallery if u]
    if gallery:
        gal_html = ""
        for i, u in enumerate(gallery):
            del_btn = (
                f'<button class="cat-galdel" title="हटाएँ" '
                f'onclick="event.stopPropagation();deleteGallery(this.closest(\'.cat-galitem\').dataset.idx)">✕</button>'
                if admin else ""
            )
            gal_html += (
                f'<div class="cat-galitem" data-idx="{i}" data-src="{esc(u)}" '
                f'onclick="openLight(this.dataset.src)">'
                f'<img src="{esc(u)}" alt="" loading="lazy" onerror="this.remove()">{del_btn}</div>'
            )
    else:
        gal_html = f'<div class="cat-gempty">{esc(cfg["galleryEmpty"])}</div>'

    upload_bar = ""
    if admin:
        upload_bar = (
            '<div class="cat-uploadbar">'
            f'<label class="cat-upload">{esc(cfg["uploadLabel"])}'
            '<input type="file" id="catGalUpload" accept="image/*" multiple '
            'onchange="uploadGalleryFiles(this)"></label>'
            f'<span class="cat-hint">{esc(cfg["galleryHint"])}</span></div>'
            '<div class="cat-upnote" id="catUpNote"></div>'
        )

    admin_bar = ""
    if admin:
        admin_bar = (
            '<div style="display:flex;gap:10px;margin-top:18px;flex-wrap:wrap">'
            f'<a class="cat-btn" href="{cfg["base"]}?edit={item_id}">✏️ Edit</a>'
            f'<button class="cat-btn ghost" data-id="{item_id}" '
            'onclick="deleteDetail(this.dataset.id)">🗑 Delete</button></div>'
        )
    add_videos_btn = (
        f'<a class="cat-btn ghost cat-tabedit" href="{cfg["base"]}?edit={item_id}&focus=videos">'
        '🎬 Add Videos</a>' if admin else ""
    )
    hero_img = (
        f'<img class="cat-hero-img" src="{esc(src)}" alt="" onerror="this.style.visibility=\'hidden\'">'
        if src else '<div class="cat-hero-img" style="display:flex;align-items:center;'
                    'justify-content:center;font-size:44px">🖼️</div>'
    )

    return f"""<div class="main"><div class="cat-wrap">
  <div style="margin-bottom:16px"><a class="cat-btn ghost" href="{cfg['base']}">← Back to {esc(cfg['label'])}</a></div>
  <div class="cat-tabs" role="tablist">
    <button class="cat-tab active" data-tab="overview" onclick="switchTab('overview')">ℹ️ Overview</button>
    <button class="cat-tab" data-tab="videos" onclick="switchTab('videos')">🎬 Videos <span class="cat-tab-n">{len(videos)}</span></button>
    <button class="cat-tab" data-tab="gallery" onclick="switchTab('gallery')">{gallery_tab} <span class="cat-tab-n">{len(gallery)}</span></button>
    <span class="cat-tabspace"></span>{add_videos_btn}
  </div>

  <section class="cat-panel active" id="cp-overview">
    <div class="cat-hero">
      {hero_img}
      <div class="cat-hero-info">
        <div class="cat-hero-title">{title}</div>
        <div class="cat-chips"><span class="cat-chip red">{esc(cat_label)}</span>{chips}</div>
        <div class="cat-body-txt">{body or '<span style="color:var(--mut)">कोई description नहीं।</span>'}</div>
        <div class="cat-links">{links_html or '<span style="color:var(--mut);font-size:12px">🔗 कोई external link नहीं।</span>'}</div>
        {admin_bar}
      </div>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
      <button class="cat-btn ghost" onclick="switchTab('videos')">🎬 Videos देखें →</button>
      <button class="cat-btn ghost" onclick="switchTab('gallery')">{gallery_tab} ({len(gallery)}) →</button>
    </div>
  </section>

  <section class="cat-panel" id="cp-videos">
    <div class="cat-subhead"><h3>{videos_heading}</h3><span class="cat-hint">Editor से जोड़े गए · {len(videos)}</span></div>
    <div class="cat-vgrid" id="catVideos">{vids_html}</div>
    {tag_section}
  </section>

  <section class="cat-panel" id="cp-gallery">
    {upload_bar}
    <div class="cat-galgrid" id="catGallery">{gal_html}</div>
  </section>
</div></div>
<div class="cat-lightbox" id="catLight" onclick="if(event.target===this)closeLight()"><img src="" alt=""></div>
<div class="cat-toast" id="catToast"></div>"""

def build_detail_page(kind: str, role: str, tg_id: int, item: dict):
    cfg = CATALOGS[kind]
    resolved_gallery = [
        u for u in (image_src(g) for g in (item.get("gallery") or [])[:12]) if u
    ]
    detail_cfg = {
        "kind": kind,
        "id": str(item.get("id") or ""),
        "q": str(item.get("title") or ""),
        "base": cfg["base"],
        "admin": role == "admin",
        "tags": [str(t).strip() for t in (item.get("tags") or []) if str(t).strip()][:12],
        "gallery": resolved_gallery,
        "galleryTab": cfg["galleryTab"],
        "galleryEmpty": cfg["galleryEmpty"],
        "tabAlias": cfg["tabAlias"],
        "tagMedia": cfg["tagMedia"],
        "limit": 12,
    }
    js = DETAIL_JS.replace("__DETAIL_CFG__", json.dumps(detail_cfg, ensure_ascii=False))
    return app_page(
        f"{item.get('title') or cfg['singular']} - Fast Finder",
        (f"<style>{CATALOG_CSS}</style>" + _detail_body(kind, role, item)
         + js + PLAYER_MODAL_HTML + PLAYER_JS),
        tg_id=tg_id, role=role, active_tab=kind,
    )
