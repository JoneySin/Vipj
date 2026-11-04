"""🗂️ PERMANENT GROUP APIs + group-first search cards.

v5 (`JoneySin/v5` → `web/search_api.py` + `web/dashboard_routes.py`) से **समझकर**
fsv1 के लिए दोबारा बनाया — verbatim copy नहीं, कोई `COLLECTIONS`/primary/cloud/
archive/section नहीं, fsv1 की एक ही collection + sync PyMongo + shared
`.vcard`/filter components बरकरार।

Endpoints (सब admin-only, सिवाय group poster पढ़ने के):
  GET  /api/group/list?q=                group search (नाम / #number)
  POST /api/group/save                   नया permanent group YA मौजूदा में files जोड़ो
  POST /api/group/update                 नाम / master thumbnail बदलो
  POST /api/group/remove_file            group से file निकालो (+ blacklist)
  POST /api/group/delete                 ungroup (files नहीं हटतीं)
  POST /api/group/merge                  source group → target group number
  POST /api/group/scan_all               पूरी library scan → permanent groups
  GET  /api/group/scan_status            scan progress
  POST /api/group/upload_thumb           custom group poster (multipart)
  GET  /api/group/thumb?gid=             custom group poster bytes
"""

import asyncio
import logging
import re
import time
from collections import defaultdict

from aiohttp import web

import info as _info
from info import BIN_CHANNEL, THUMB_BROWSER_CACHE
from utils import temp
from database.group_db import (
    store, title_key, group_title, quality_label, episode_chips,
    episode_label, detect_episodes, guess_kind, normal_kind,
    clean_episode_map, group_kind_meta, KIND_QUALITIES, KIND_EPISODES,
)
from web.web_assets import get_auth
from web.thumb_engine import get_image_bytes, image_content_type, thumb_version
from web.image_validate import is_image_magic

logger = logging.getLogger(__name__)
group_routes = web.RouteTableDef()

_STORAGE_CHANNEL = getattr(_info, "CATALOG_STORAGE_CHANNEL", BIN_CHANNEL)
_MAX_UPLOAD = 5 * 1024 * 1024
SCAN_MAX_GROUP = 30          # इससे बड़ा bucket = बहुत आम नाम, group मत बनाओ
SCAN_STATE = {"running": False}


def _json(data, status=200):
    return web.json_response(data, status=status)


async def _admin(req):
    role, _ = await get_auth(req)
    return role == "admin"


def _denied():
    return _json({"ok": False, "error": "Admins only"}, 403)


async def _body(req):
    try:
        data = await req.json()
        if not isinstance(data, dict):
            raise ValueError("expected object")
        return data, None
    except Exception:
        return None, _json({"ok": False, "error": "Bad JSON"}, 400)


def _fid(value) -> str:
    """User input → safe id. `file_edit_routes._file_id()` वाला ही whitelist —
    Telegram file_ids + fsv1 short ids; URL/control/markup chars reject."""
    fid = str(value or "").strip()
    return fid[:512] if re.fullmatch(r"[A-Za-z0-9_\-=]{1,512}", fid) else ""


def _items(data):
    """`items:[{id,name}]` → unique `(fid, name)` pairs. कभी raw dict DB में नहीं।"""
    out, seen = [], set()
    for x in data.get("items") or []:
        if not isinstance(x, dict):
            continue
        fid = _fid(x.get("id") or x.get("file_id"))
        if fid and fid not in seen:
            seen.add(fid)
            out.append((fid, str(x.get("name") or "")[:300]))
    return out


def _group_public(g):
    g = g or {}
    return {
        "group_id": str(g.get("_id") or ""),
        "num": g.get("num", ""),
        "name": str(g.get("name") or ""),
        "count": len(g.get("members") or []),
        "members": [str(i) for i in (g.get("members") or [])],
        "files": [{"id": str(f.get("id") or ""), "name": str(f.get("name") or "")}
                  for f in (g.get("files") or [])],
        "auto_keys": list(g.get("auto_keys") or []),
        "excluded": [str(i) for i in (g.get("excluded") or [])],
        "thumb_fid": str(g.get("thumb_fid") or ""),
        "thumb_url": str(g.get("thumb_url") or ""),
        "auto_created": bool(g.get("auto_created")),
        # 🧮 type/episode गिनती का एक ही source `database/group_db.py`
        **group_kind_meta(g),
        "updated_at": int(g.get("updated_at") or 0),
    }


def _group_thumb_url(g, variants):
    """Master thumbnail: custom upload > चुना हुआ member > सबसे बड़ी quality।"""
    gid = str(g.get("_id") or "")
    ts = int(g.get("updated_at") or 0)
    custom = str(g.get("thumb_url") or "")
    if custom.startswith("TG_ID:"):
        return f"/api/group/thumb?gid={gid}&v={thumb_version(gid, custom)}"
    chosen = str(g.get("thumb_fid") or "")
    if chosen:
        return f"/api/thumb?file_id={chosen}&v={thumb_version(chosen, str(ts))}"
    for v in reversed(variants or []):
        if v.get("thumb"):
            return v["thumb"]
    return ""


# ─────────────────────────────────────────────────────────────
# 🎴 GROUP-FIRST SEARCH — page के cards को groups में बदलो
# ─────────────────────────────────────────────────────────────
async def group_cards(cards, normalize=None, auto_join=True):
    """Normalized card dicts → वही list, पर 2+ वाले buckets एक group card बनते हैं।

    * Saved group (`members`/`auto_keys`) → **permanent** group card, `gid` + `num`,
      और group के **सारे** members variants में (चाहे वो इस page पर न हों)।
    * Same-title unsaved bucket → auto group card (`manual:false`), admin के लिए
      "Save as Group" action — click करते ही permanent हो जाता है।
    * `auto_join`: किसी saved group की `auto_keys` से मिलती नई file तुरंत DB में
      जुड़ जाती है (v5 का `_persist_joins`) — `excluded` file वापस नहीं आती।
    * Input dicts mutate नहीं होते; ranking बरकरार (group पहली file की जगह)।
    """
    cards = list(cards or [])
    if not cards:
        return cards
    ids = [str(c.get("file_id") or "") for c in cards]
    keys = {title_key(c.get("name")) for c in cards}
    keys.discard("")

    found = await store.by_members(ids)
    found += await store.by_keys(sorted(keys))
    by_gid = {}
    for g in found:
        by_gid[str(g.get("_id"))] = g
    groups = list(by_gid.values())

    owner, key2g = {}, {}
    for g in groups:
        for m in (g.get("members") or []):
            owner[str(m)] = g
        for k in (g.get("auto_keys") or []):
            key2g.setdefault(str(k), g)

    # 🆕 नई quality (same title) → saved group में auto-join
    joins = defaultdict(list)
    if auto_join:
        for c in cards:
            fid = str(c.get("file_id") or "")
            if not fid or fid in owner:
                continue
            g = key2g.get(title_key(c.get("name")))
            if not g or fid in {str(x) for x in (g.get("excluded") or [])}:
                continue
            gid = str(g["_id"])
            owner[fid] = g
            joins[gid].append((fid, str(c.get("name") or "")))
        for gid, items in joins.items():
            await store.add_members(gid, items)
            await store.mark_files([i for i, _ in items], gid)
        if joins:
            # ताज़ा group docs दोबारा लें ताकि variants नये members सहित दिखें
            fresh = await store.by_members(ids)
            fresh += await store.by_keys(sorted(keys))
            groups = list({str(g.get("_id")): g for g in fresh}.values())
            owner = {}
            for g in groups:
                for m in (g.get("members") or []):
                    owner[str(m)] = g

    # Saved group के बाकी members (जो इस page पर नहीं मिले) DB से लाओ
    needed = []
    have = set(ids)
    for g in groups:
        for m in (g.get("members") or []):
            if str(m) not in have and str(m) not in needed:
                needed.append(str(m))
    extra = []
    if needed and normalize:
        for doc in await store.files_by_ids(needed):
            extra.append(normalize(doc))
    pool = defaultdict(list)
    for c in cards:
        pool[str(c.get("file_id") or "")].append(c)
    for c in extra:
        fid = str(c.get("file_id") or "")
        if fid not in pool:
            pool[fid].append(c)

    order, buckets = [], {}
    for c in cards:
        fid = str(c.get("file_id") or "")
        g = owner.get(fid)
        if g:
            k = "m:" + str(g.get("_id"))
        else:
            t = title_key(c.get("name"))
            k = "a:" + t if t else "s:" + fid
        if k.startswith("s:"):
            order.append(("single", c))
            continue
        if k not in buckets:
            buckets[k] = {"g": g if g else None, "key": k, "fids": []}
            order.append(("group", k))
        if fid not in buckets[k]["fids"]:
            buckets[k]["fids"].append(fid)

    out = []
    for kind, value in order:
        if kind == "single":
            out.append(value)
            continue
        b = buckets[value]
        g = b["g"]
        if g:
            fids = [str(m) for m in (g.get("members") or [])]
        else:
            fids = list(b["fids"])
        variants = []
        for fid in fids:
            for c in pool.get(fid, []):
                variants.append(dict(c))
        if len(variants) < 2:
            out.extend(variants[:1])
            continue
        for v in variants:
            lab, h = quality_label(v.get("res"), v.get("name"), v.get("quality"))
            v["ql"] = lab
            v["qh"] = h
            v["gid"] = str(g["_id"]) if g else ""
            v["gnum"] = g.get("num", "") if g else ""
        # 🎞️ एक ही फाइल की qualities ⇄ 📺 सीरीज के अलग episodes
        # Saved group पर admin की चुनी `kind`; auto bucket पर नामों से अंदाज़ा।
        if g:
            gkind = normal_kind(g.get("kind"))
            emap = clean_episode_map(g.get("episode_map"))
        else:
            gkind = guess_kind([v.get("name") for v in variants])
            emap = {}
        if gkind == KIND_EPISODES:
            chips, episodes = episode_chips(variants, emap)
            variants.sort(key=lambda v: episode_label(v.get("el"), 0)[1])
            qualities = 0
        else:
            variants.sort(key=lambda v: v["qh"])
            chips, seen = [], {}
            for i, v in enumerate(variants):
                fid = str(v.get("file_id") or "")
                v["el"] = emap.get(fid) or episode_label(v.get("name"), i)[0]
            for v in variants:
                lab = v["ql"] or "?"
                if lab in seen:
                    seen[lab]["count"] += 1
                else:
                    seen[lab] = {"label": lab, "count": 1}
                    chips.append(seen[lab])
            episodes = 0
            qualities = len(variants)
        gid = str(g["_id"]) if g else ""
        rep = variants[-1]
        if g:
            title = str(g.get("name") or "") or str(rep.get("name") or "Group")
        else:
            first = next((c for c in cards if "a:" + title_key(c.get("name")) == value), None)
            title = (group_title(first.get("name")) if first else "") \
                or str((first or rep).get("name") or "Group")
        out.append({
            "group": True,
            "manual": bool(g),
            "gid": gid,
            "num": g.get("num", "") if g else "",
            "key": ("m" + gid) if g else f"{value[2:]}",
            "nkey": "" if g else value[2:],
            "name": title,
            "count": len(variants),
            "type": rep.get("type", "VIDEO"),
            # ⚠️ group card पर किसी एक फाइल का size/duration नहीं — अलग-अलग
            #    files/episodes का अलग size और अलग duration होता है। वे chips
            #    expand करने पर हर variant के अपने shared `.vcard` पर दिखते हैं।
            "kind": gkind,
            "qualities": qualities,
            "episodes": episodes,
            "episode_map": emap,
            "thumb": _group_thumb_url(g or {}, variants),
            "custom_thumb": bool(g and str(g.get("thumb_url") or "").startswith("TG_ID:")),
            "chips": chips,
            "variants": variants,
        })
    return out


def filter_group_cards(cards, mode):
    """`group` = सिर्फ़ group cards, `ungroup` = सिर्फ़ अकेली files, `all` = सब।"""
    if mode == "group":
        return [c for c in cards if c.get("group")]
    if mode == "ungroup":
        return [c for c in cards if not c.get("group")]
    return cards


# ─────────────────────────────────────────────────────────────
# 📋 LIST / SAVE / UPDATE / REMOVE / DELETE / MERGE
# ─────────────────────────────────────────────────────────────
@group_routes.get("/api/group/list")
async def api_group_list(req):
    if not await _admin(req):
        return _denied()
    try:
        limit = max(1, min(int(req.query.get("limit", "25")), 200))
    except ValueError:
        limit = 25
    groups = await store.list(req.query.get("q", ""), limit)
    return _json({"ok": True, "groups": groups})


@group_routes.post("/api/group/save")
async def api_group_save(req):
    """नया group (नया number) YA मौजूदा `group_id` में files जोड़ो।

    Jo file किसी और group में थी, वहाँ से निकलकर **blacklist** (`excluded`)
    हो जाती है ताकि auto-key उसे वापस न ले जाए — v5 का यही नियम है।
    """
    if not await _admin(req):
        return _denied()
    data, err = await _body(req)
    if err:
        return err
    items = _items(data)
    if not items:
        return _json({"ok": False, "error": "कोई file select नहीं हुई"}, 400)
    gid = _fid(data.get("group_id") or "")
    name = str(data.get("name") or "").strip()[:200]
    auto_keys = sorted({title_key(n) for _, n in items if title_key(n)})
    raw_kind = data.get("kind")
    kind = normal_kind(raw_kind) if raw_kind else guess_kind([n for _, n in items])
    raw_emap = data.get("episode_map")
    # ⚠️ Side-effect (बाकी groups से निकालना) से पहले target मौजूद है या नहीं देखो
    if gid and not await store.get(gid):
        return _json({"ok": False, "error": "Group नहीं मिला"}, 404)
    if not gid and not name:
        return _json({"ok": False, "error": "Group का नाम लिखिए"}, 400)

    # पहले इन files को बाकी सब groups से निकालो (excluded = वापस न जुड़ें)
    fids = [i for i, _ in items]
    await store.pull_files(fids, exclude=True)
    if gid:
        g = await store.add_members(gid, items, auto_keys=auto_keys)
        # ✏️ Edit modal से मौजूदा group में files जोड़ते वक्त नया नाम भी आता है।
        #    पहले इसे ignore कर दिया जाता था → rename कभी DB में नहीं पहुँचता था।
        #    खाली नाम = कोई rename नहीं (किसी दूसरे group में सिर्फ़ files जोड़ना)।
        upd = {}
        if name and name != str(g.get("name") or ""):
            upd["name"] = name
        # Type न भेजा हो तो group की मौजूदा पसंद बरकरार रखें।
        if raw_kind is None:
            kind = normal_kind(g.get("kind"))
        # Edit modal से group type भी बदल सकता है (qualities ⇄ episodes)
        if raw_kind is not None or "episode_map" in data:
            upd["kind"] = kind
            if "episode_map" in data:
                upd["episode_map"] = clean_episode_map(raw_emap)
        if upd:
            g = await store.update(gid, upd)
    else:
        g = await store.create(name=name, items=items, auto_keys=auto_keys,
                               kind=kind,
                               episode_map=clean_episode_map(raw_emap)
                               or detect_episodes(items))
    await store.mark_files(fids, str(g["_id"]))
    await store.cleanup_empty()
    return _json({"ok": True, "group": _group_public(g),
                  "group_id": str(g["_id"]), "num": g.get("num", ""),
                  "group_name": str(g.get("name") or "")})


@group_routes.post("/api/group/update")
async def api_group_update(req):
    """नाम / master thumbnail बदलो। `thumb_file_id:''` = AUTO (highest quality)।"""
    if not await _admin(req):
        return _denied()
    data, err = await _body(req)
    if err:
        return err
    gid = _fid(data.get("group_id"))
    g = await store.get(gid)
    if not g:
        return _json({"ok": False, "error": "Group नहीं मिला"}, 404)
    fields = {}
    if "name" in data:
        name = str(data.get("name") or "").strip()[:200]
        if not name:
            return _json({"ok": False, "error": "नाम खाली नहीं हो सकता"}, 400)
        fields["name"] = name
    if "thumb_file_id" in data:
        tf = _fid(data.get("thumb_file_id"))
        # सिर्फ़ उसी group का member master thumbnail बन सकता है
        if tf and tf not in {str(m) for m in (g.get("members") or [])}:
            return _json({"ok": False, "error": "ये file इस group में नहीं है"}, 400)
        fields["thumb_fid"] = tf
        if tf:
            fields["thumb_url"] = ""       # custom upload हटाकर member चुन लिया
    if data.get("auto_keys"):
        fields["auto_keys"] = sorted({title_key(k) for k in data["auto_keys"] if title_key(k)})
    if data.get("clear_custom"):
        fields["thumb_url"] = ""
    if "kind" in data:
        k = str(data.get("kind") or "").strip().lower()
        if k not in (KIND_QUALITIES, KIND_EPISODES):
            return _json({"ok": False, "error": "Group type गलत है"}, 400)
        fields["kind"] = k
    if "episode_map" in data:
        fields["episode_map"] = clean_episode_map(data.get("episode_map"))
    updated = await store.update(gid, fields)
    return _json({"ok": True, "group": _group_public(updated)})


@group_routes.post("/api/group/remove_file")
async def api_group_remove_file(req):
    if not await _admin(req):
        return _denied()
    data, err = await _body(req)
    if err:
        return err
    gid, fid = _fid(data.get("group_id")), _fid(data.get("file_id"))
    if not gid or not fid:
        return _json({"ok": False, "error": "Missing inputs"}, 400)
    g = await store.remove_member(gid, fid)
    if not g:
        return _json({"ok": False, "error": "Group नहीं मिला"}, 404)
    await store.mark_files([fid], "")
    await store.cleanup_empty()
    return _json({"ok": True, "group": _group_public(g)})


@group_routes.post("/api/group/delete")
async def api_group_delete(req):
    """Ungroup — सिर्फ़ group मिटता है, files नहीं (वो फिर auto-group में जा सकती हैं)।"""
    if not await _admin(req):
        return _denied()
    data, err = await _body(req)
    if err:
        return err
    gid = _fid(data.get("group_id"))
    if not await store.get(gid):
        return _json({"ok": False, "error": "Group नहीं मिला"}, 404)
    members = await store.delete(gid)
    await store.mark_files(members, "")
    return _json({"ok": True, "removed": len(members)})


@group_routes.post("/api/group/merge")
async def api_group_merge(req):
    """Source group की सारी files + auto_keys → target group number; source हटता है।"""
    if not await _admin(req):
        return _denied()
    data, err = await _body(req)
    if err:
        return err
    src = _fid(data.get("source"))
    tgt = _fid(str(data.get("target") or "").strip().lstrip("#"))
    if not src or not tgt:
        return _json({"ok": False, "error": "Group number लिखिए"}, 400)
    if src == tgt:
        return _json({"ok": False, "error": "उसी group में merge नहीं हो सकता"}, 400)
    if not await store.get(src) or not await store.get(tgt):
        return _json({"ok": False, "error": "Source/target group नहीं मिला"}, 404)
    merged = await store.merge(src, tgt)
    await store.mark_files([str(m) for m in (merged.get("members") or [])], tgt)
    await store.cleanup_empty()
    return _json({"ok": True, "group": _group_public(merged),
                  "group_id": tgt, "num": merged.get("num", ""),
                  "group_name": str(merged.get("name") or "")})


# ─────────────────────────────────────────────────────────────
# ⚙️ SCAN ALL — पूरी library से permanent groups बनाओ (idempotent)
# ─────────────────────────────────────────────────────────────
async def _scan_all_groups():
    st = SCAN_STATE
    st.update(running=True, phase="groups load ho rahe hain", scanned=0, total=0,
              created=0, added=0, skipped_big=0, skipped_keys=[], fixed_marks=0,
              existing_groups=0, multi_buckets=0, error="", started=time.time(),
              finished=0)
    try:
        existing = await store.all_groups()
        key2g, owner = {}, {}
        for g in existing:
            gd = {"id": str(g["_id"]), "excl": {str(x) for x in (g.get("excluded") or [])}}
            for m in (g.get("members") or []):
                owner[str(m)] = str(g["_id"])
            for k in (g.get("auto_keys") or []):
                key2g.setdefault(str(k), gd)
        st["existing_groups"] = len({g["id"] for g in key2g.values()})

        docs = await store.scan_files()
        st["total"] = len(docs)
        st["phase"] = "files scan ho rahe hain"
        buckets = defaultdict(list)
        fix_set, fix_unset = defaultdict(list), []
        for d in docs:
            st["scanned"] += 1
            fid = str(d.get("_id") or "")
            og, cg = owner.get(fid), str(d.get("group_id") or "")
            if og and cg != og:
                fix_set[og].append(fid)
            elif not og and cg:
                fix_unset.append(fid)
            k = title_key(d.get("file_name"))
            if len(k) >= 3:
                buckets[k].append((fid, str(d.get("file_name") or "")))
            if st["scanned"] % 2000 == 0:
                await asyncio.sleep(0)

        st["phase"] = "groups tay ho rahe hain"
        now = int(time.time())
        for k, items in buckets.items():
            g = key2g.get(k)
            if len(items) >= 2:
                st["multi_buckets"] += 1
            if g:
                fresh = [(i, n) for i, n in items
                         if i not in owner and i not in g["excl"]]
                if not fresh:
                    continue
                await store.add_members(g["id"], fresh, auto_keys=[k], scanned_at=now)
                fix_set[g["id"]].extend(i for i, _ in fresh)
                st["added"] += len(fresh)
                continue
            if len(items) < 2 or len(items) > SCAN_MAX_GROUP:
                if len(items) > SCAN_MAX_GROUP:
                    st["skipped_big"] += 1
                    if len(st["skipped_keys"]) < 20:
                        st["skipped_keys"].append(f"{k} ({len(items)} files)")
                continue
            cand = [(i, n) for i, n in items if i not in owner]
            if len(cand) < 2:
                continue
            g = await store.create(name=group_title(cand[0][1]) or cand[0][1],
                                   items=cand, auto_keys=[k], auto_created=True,
                                   scan_created=True,
                                   kind=guess_kind([n for _, n in cand]),
                                   episode_map=detect_episodes(cand))
            await store.update(str(g["_id"]), {"scanned_at": now})
            fix_set[str(g["_id"])].extend(i for i, _ in cand)
            st["created"] += 1

        st["phase"] = "files par group_id mark ho raha hai"
        for gid, ids in fix_set.items():
            if ids:
                await store.mark_files(ids, gid)
                st["fixed_marks"] += len(ids)
        if fix_unset:
            await store.mark_files(fix_unset, "")
            st["fixed_marks"] += len(fix_unset)
        await store.cleanup_empty()
        st["phase"] = "complete"
    except Exception as e:
        logger.error(f"group scan failed: {e}")
        st["error"] = str(e)
        st["phase"] = "error"
    finally:
        st["running"] = False
        st["finished"] = time.time()
        logger.info(f"🗂️ Group scan: scanned={st.get('scanned')}/{st.get('total')} "
                    f"created={st.get('created')} added={st.get('added')} "
                    f"fixed={st.get('fixed_marks')} err={st.get('error')}")


@group_routes.post("/api/group/scan_all")
async def api_group_scan_all(req):
    if not await _admin(req):
        return _denied()
    if SCAN_STATE.get("running"):
        return _json({"ok": True, "started": False, "running": True})
    asyncio.create_task(_scan_all_groups())
    return _json({"ok": True, "started": True})


@group_routes.get("/api/group/scan_status")
async def api_group_scan_status(req):
    if not await _admin(req):
        return _denied()
    return _json({"ok": True, **SCAN_STATE})


# ─────────────────────────────────────────────────────────────
# 🖼️ MASTER THUMBNAIL — custom upload / member चुनना / serve
# ─────────────────────────────────────────────────────────────
@group_routes.post("/api/group/upload_thumb")
async def api_group_upload_thumb(req):
    if not await _admin(req):
        return _denied()
    try:
        reader = await req.multipart()
        gid, raw = "", b""
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "group_id":
                gid = _fid((await part.read()).decode("utf-8", "replace"))
            elif part.name == "image":
                raw = await part.read()
    except Exception as e:
        return _json({"ok": False, "error": f"Bad upload: {e}"}, 400)
    if not gid or not await store.get(gid):
        return _json({"ok": False, "error": "Group नहीं मिला"}, 404)
    if not raw or len(raw) > _MAX_UPLOAD or not is_image_magic(raw):
        return _json({"ok": False, "error": "सिर्फ़ JPG/PNG/WEBP, अधिकतम 5 MB"}, 400)
    bot = getattr(temp, "BOT", None)
    if bot is None:
        return _json({"ok": False, "error": "Bot अभी ready नहीं"}, 503)
    try:
        import io
        buf = io.BytesIO(raw)
        buf.name = "group_poster.jpg"
        msg = await bot.send_photo(chat_id=_STORAGE_CHANNEL, photo=buf)
        photo = getattr(msg, "photo", None)
        sizes = getattr(photo, "sizes", None) if photo else None
        tid = sizes[-1].file_id if sizes else getattr(photo, "file_id", "")
    except Exception as e:
        logger.warning(f"group thumb upload failed: {e}")
        return _json({"ok": False, "error": "Telegram upload fail हुआ"}, 502)
    if not tid:
        return _json({"ok": False, "error": "Thumbnail file_id नहीं मिला"}, 502)
    g = await store.update(gid, {"thumb_url": "TG_ID:" + str(tid), "thumb_fid": ""})
    return _json({"ok": True, "group": _group_public(g),
                  "thumb": f"/api/group/thumb?gid={gid}&v={thumb_version(gid, 'TG_ID:' + str(tid))}"})


@group_routes.get("/api/group/thumb")
async def api_group_thumb(req):
    role, _ = await get_auth(req)
    if not role:
        return web.Response(status=401)
    gid = _fid(req.query.get("gid"))
    g = await store.get(gid) if gid else None
    ref = str((g or {}).get("thumb_url") or "")
    if not ref.startswith("TG_ID:"):
        return web.Response(status=404)
    etag = f'"{req.query.get("v") or thumb_version(gid, ref)}"'
    headers = {"Cache-Control": f"private, max-age={THUMB_BROWSER_CACHE}", "ETag": etag}
    if req.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    data = await get_image_bytes(ref[len("TG_ID:"):])
    if not data:
        return web.Response(status=404, headers={"Cache-Control": "no-store"})
    return web.Response(body=data, content_type=image_content_type(data), headers=headers)
