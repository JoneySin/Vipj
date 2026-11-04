"""🗂️ PERMANENT QUALITY GROUPS — fsv1 का अपना group store.

GitHub reference (`JoneySin/v5`) से **समझा**: `QualityGroups` collection में हर
group का अपना `_id`/`num`, `members` (file_ids), `auto_keys`, `excluded`, master
thumbnail; `QualityGroupSeq` से sequential number; हर file doc पर `group_id` mark;
नई quality (same title) `auto_keys` से अपने-आप उसी group में जुड़ती है; files और
groups merge / ungroup / remove / scan_all होते हैं।

fsv1 का अपना रूप (verbatim copy नहीं):
  * **एक ही** `collection` (fsv1 में primary/cloud/archive जैसा कोई section नहीं) —
    इसलिए `thumb_col`/`COLLECTIONS`/`source_col` जैसी चीज़ें यहाँ नहीं हैं।
  * fsv1 का **synchronous PyMongo** + `asyncio.to_thread`; MongoDB न हो तो
    transparent **in-memory fallback** (जैसे `catalog_db.py`) — preview/unit tests
    बिना DB चलते हैं।
  * store सिर्फ़ high-level methods देता है (`get`, `by_members`, `add_members`,
    `merge`, …), कोई raw `$addToSet`/`$pull` query routes में नहीं लिखी जाती।
  * Group doc:
    `{_id:"12", num:12, name, members:[fid], files:[{id,name}], auto_keys:[key],
      excluded:[fid], thumb_fid:"", thumb_url:"", auto_created, scan_created,
      created_at, updated_at, scanned_at}`
"""

import asyncio
import logging
import re
import time

try:
    from database.users_chats_db import dbase
except Exception:                                      # pragma: no cover
    dbase = None

logger = logging.getLogger(__name__)

# ── Title normalization (एक ही जगह — search, scan, auto-join सब यही) ──────
NOISE = frozenset("""
144p 240p 360p 480p 576p 720p 1080p 1440p 2160p 4k 8k uhd hd sd
hdr hdr10 hdr10plus dv sdr 10bit 8bit hevc x264 x265 h264 h265 avc xvid divx
bluray blueray brrip bdrip bdremux remux webdl webrip web hdtv dvdrip dvd
cam hdcam predvd ts tc hdrip dvdscr r5
hindi english eng tamil telugu kannada malayalam bengali marathi punjabi
dual multi audio org original esub esubs sub subs subtitle subtitles
dd dd5 dd51 ddp ac3 aac mp3 flac truehd atmos 2ch 5ch 6ch
imax extended proper repack unrated theatrical directors cut
amzn nf netflix dsnp hmax hotstar prime zee sony
mkv mp4 avi mov webm m4v wmv flv mpeg mpg m2ts vob 3gp iso
www http https com net org
""".split())
_EPISODE_RE = re.compile(r"^[se]\d{1,3}$", re.IGNORECASE)
_RES_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:240|360|480|540|576|720|1080|1440|2160|4320)\s*[pP]|4[kK]|8[kK]|[uU][hH][dD])(?![A-Za-z0-9])"
)
_EXT_TAIL_RE = re.compile(
    r"[\s._\-]*(?<![A-Za-z0-9])(?:mp4|mkv|avi|mov|webm|m4v|ts|wmv|flv|mpg|mpeg)\s*$", re.I
)


def title_key(name) -> str:
    """File name → normalized group key (quality/भाषा/codec/extension हटाकर)।

    v5 के `_group_key` से प्रेरणा, पर fsv1 का अपना token-based rule — पहले से
    मौजूद Group/UnGroup फ़िल्टर की ही key है, इसलिए पुराना behaviour बरकरार।
    """
    text = re.sub(r"[\[(][^\])]*[\])]", " ", str(name or "").lower())
    clean = []
    for token in re.findall(r"[^\W_]+", text, re.UNICODE):
        if token in NOISE or _EPISODE_RE.match(token):
            continue
        if len(token) <= 2 and token.isdigit():
            continue
        clean.append(token)
        if len(clean) == 4:
            break
    return " ".join(clean)


def group_title(name) -> str:
    """दिखाने लायक साफ़ टाइटल (original case, quality + extension हटाकर)।"""
    s = _EXT_TAIL_RE.sub("", str(name or ""))
    s = _RES_TOKEN_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"^[\s|\-–_.]+|[\s|\-–_.]+$", "", s)


def quality_height(res, name=""):
    """`1920×1080` / `1080p` → sortable height (chips के लिए)।"""
    m = re.search(r"(\d{3,5})\D+(\d{3,5})", str(res or ""))
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        return max(h, int(w * 9 / 16))
    m = re.search(r"(?<!\d)(2160|1440|1080|720|576|480|360|240)[pP]?(?!\d)", str(name or ""))
    return int(m.group(1)) if m else 0


def quality_label(res, name="", quality=None):
    """`('1080p', 1080)` जैसा chip label — group card की quality chips।

    पहले वही `quality` value जो shared `.vcard` chip दिखाता है (`vcard_meta()`),
    ताकि group के अंदर और बाहर label एक जैसा रहे; न हो तो `res`/नाम से अनुमान।
    """
    q = str(quality or "").strip()
    m = re.fullmatch(r"(\d{3,4})[pP]", q)
    if m:
        return q.lower(), int(m.group(1))
    if re.fullmatch(r"4[kK]", q):
        return "2160p", 2160
    if re.fullmatch(r"8[kK]", q):
        return "8K", 4320
    h = quality_height(res, name)
    for floor, label in ((4000, "8K"), (2000, "2160p"), (1300, "1440p"),
                         (1000, "1080p"), (650, "720p"), (450, "480p"),
                         (330, "360p"), (220, "240p")):
        if h >= floor:
            return label, h
    return (f"{h}p", h) if h else ("?", 0)


def file_collection():
    """fsv1 की एकमात्र file collection — lazy import (Mongo न हो तो None)।"""
    try:
        from database.ia_filterdb import collection
        return collection
    except Exception:
        return None


# ── In-memory fallback ────────────────────────────────────────────────────
class _MemoryGroups:
    """PyMongo-जैसा छोटा store (बिना DB वाले preview/tests के लिए)।"""

    def __init__(self):
        self.data = {}
        self.seq = 0

    def get(self, gid):
        d = self.data.get(str(gid))
        return dict(d) if d else None

    def all(self):
        return [dict(d) for d in self.data.values()]

    def insert(self, doc):
        self.data[str(doc["_id"])] = dict(doc)
        return dict(doc)

    def save(self, doc):
        self.data[str(doc["_id"])] = dict(doc)
        return dict(doc)

    def delete(self, gid):
        return self.data.pop(str(gid), None)

    def next_num(self):
        self.seq += 1
        return self.seq


class GroupStore:
    """Permanent groups का एकमात्र store — MongoDB या in-memory, API एक ही।"""

    def __init__(self, database):
        self.col = database["quality_groups"] if database is not None else None
        self.seq = database["quality_group_seq"] if database is not None else None
        self.mem = _MemoryGroups() if self.col is None else None

    # ── low-level sync helpers ───────────────────────────────────────────
    def _get(self, gid):
        if self.mem:
            return self.mem.get(gid)
        return self.col.find_one({"_id": str(gid)})

    def _all(self):
        if self.mem:
            return self.mem.all()
        return list(self.col.find({}))

    def _save(self, doc):
        if self.mem:
            return self.mem.save(doc)
        # ⚠️ MongoDB में `_id` immutable है — उसे $set में भेजना error देता है
        fields = {k: v for k, v in doc.items() if k != "_id"}
        self.col.update_one({"_id": doc["_id"]}, {"$set": fields}, upsert=True)
        return doc

    def _insert(self, doc):
        if self.mem:
            return self.mem.insert(doc)
        self.col.insert_one(doc)
        return doc

    def _delete(self, gid):
        if self.mem:
            return self.mem.delete(gid)
        old = self.col.find_one({"_id": str(gid)})
        self.col.delete_one({"_id": str(gid)})
        return old

    def _next_num(self):
        if self.mem:
            return self.mem.next_num()
        # default = document BEFORE update; upsert पर None → 1
        d = self.seq.find_one_and_update(
            {"_id": "seq"}, {"$inc": {"n": 1}}, upsert=True
        )
        return int((d or {}).get("n", 0)) + 1

    # ── async public API ─────────────────────────────────────────────────
    async def get(self, gid):
        return await asyncio.to_thread(self._get, gid)

    async def all_groups(self):
        return await asyncio.to_thread(self._all)

    async def list(self, q="", limit=25):
        """Group search — नाम या number (`#12`) से, नये पहले।"""
        def _run():
            needle = str(q or "").strip().lstrip("#")
            docs = self._all()
            if needle:
                ql = needle.lower()
                docs = [d for d in docs
                        if needle == str(d.get("_id") or "") or needle == str(d.get("num") or "")
                        or ql in str(d.get("name") or "").lower()]
            docs.sort(key=lambda d: int(d.get("updated_at") or 0), reverse=True)
            return [{"id": str(d["_id"]), "num": d.get("num", ""),
                     "name": d.get("name", ""), "count": len(d.get("members") or []),
                     "thumb_fid": d.get("thumb_fid", ""),
                     "thumb_url": d.get("thumb_url", "")}
                    for d in docs[:max(1, min(int(limit or 25), 200))]]
        return await asyncio.to_thread(_run)

    async def by_members(self, ids):
        """दिये file_ids जिन-जिन saved groups के members हैं, वो groups।"""
        def _run():
            s = {str(i) for i in ids if i}
            if not s:
                return []
            if self.mem:
                return [dict(d) for d in self.mem.all()
                        if s.intersection(str(m) for m in (d.get("members") or []))]
            return list(self.col.find({"members": {"$in": list(s)}}))
        return await asyncio.to_thread(_run)

    async def by_keys(self, keys):
        """`auto_keys` से groups — नई quality का auto-join यहीं से।"""
        def _run():
            s = {str(k) for k in keys if k}
            if not s:
                return []
            if self.mem:
                return [dict(d) for d in self.mem.all()
                        if s.intersection(str(k) for k in (d.get("auto_keys") or []))]
            return list(self.col.find({"auto_keys": {"$in": list(s)}}))
        return await asyncio.to_thread(_run)

    async def next_num(self):
        return await asyncio.to_thread(self._next_num)

    async def create(self, *, name, items, auto_keys=(), auto_created=False,
                     scan_created=False):
        """नया PERMANENT group — अपना number, members, files, auto_keys।"""
        now = int(time.time())
        num = await self.next_num()
        gid = str(num)
        doc = {
            "_id": gid, "num": num,
            "name": str(name or "").strip()[:200],
            "members": [str(i) for i, _ in items],
            "files": [{"id": str(i), "name": str(n or "")[:300]} for i, n in items],
            "auto_keys": sorted({str(k) for k in auto_keys if k}),
            "excluded": [], "thumb_fid": "", "thumb_url": "",
            "auto_created": bool(auto_created), "scan_created": bool(scan_created),
            "created_at": now, "updated_at": now, "scanned_at": 0,
        }
        await asyncio.to_thread(self._insert, doc)
        return doc

    async def update(self, gid, fields):
        """Naam / master thumbnail / timestamps — सिर्फ़ whitelisted keys।"""
        allowed = {"name", "thumb_fid", "thumb_url", "auto_keys", "excluded",
                   "updated_at", "scanned_at", "scan_created"}

        def _run():
            g = self._get(gid)
            if not g:
                return None
            clean = {k: v for k, v in (fields or {}).items() if k in allowed}
            clean["updated_at"] = int(time.time())
            g.update(clean)
            self._save(g)
            return g
        return await asyncio.to_thread(_run)

    async def add_members(self, gid, items, auto_keys=(), unexclude=True,
                          scanned_at=0):
        """Group में files जोड़ो (idempotent) — `$addToSet` जैसा, पर Python में।"""
        def _run():
            g = self._get(gid)
            if not g:
                return None
            members = list(g.get("members") or [])
            files = list(g.get("files") or [])
            by_id = {str(f.get("id")): f for f in files}
            for fid, name in items:
                fid = str(fid)
                if fid not in members:
                    members.append(fid)
                by_id[fid] = {"id": fid, "name": str(name or "")[:300]}
            g["members"] = members
            g["files"] = [by_id[i] for i in members]
            g["auto_keys"] = sorted(set(map(str, g.get("auto_keys") or []))
                                    | {str(k) for k in auto_keys if k})
            if unexclude:
                added = {str(i) for i, _ in items}
                g["excluded"] = [x for x in (g.get("excluded") or []) if str(x) not in added]
            if scanned_at:
                g["scanned_at"] = int(scanned_at)
            g["updated_at"] = int(time.time())
            self._save(g)
            return g
        return await asyncio.to_thread(_run)

    async def rename_member(self, gid, fid, name):
        """File editor में नाम बदले तो group की `files[].name` भी ताज़ा रहे।"""
        def _run():
            g = self._get(gid)
            if not g:
                return None
            target = str(fid)
            for f in (g.get("files") or []):
                if str(f.get("id")) == target:
                    f["name"] = str(name or "")[:300]
            g["updated_at"] = int(time.time())
            self._save(g)
            return g
        return await asyncio.to_thread(_run)

    async def remove_member(self, gid, fid, exclude=True):
        """Group से file निकालो + blacklist ताकि auto-key उसे वापस न जोड़े।"""
        def _run():
            g = self._get(gid)
            if not g:
                return None
            target = str(fid)
            g["members"] = [m for m in (g.get("members") or []) if str(m) != target]
            g["files"] = [f for f in (g.get("files") or []) if str(f.get("id")) != target]
            if exclude:
                ex = list(map(str, g.get("excluded") or []))
                if target not in ex:
                    ex.append(target)
                g["excluded"] = ex
            if str(g.get("thumb_fid") or "") == target:
                g["thumb_fid"] = ""
            g["updated_at"] = int(time.time())
            self._save(g)
            return g
        return await asyncio.to_thread(_run)

    async def delete(self, gid):
        """Group हटाओ — files नहीं हटतीं, बस ungroup हो जाती हैं।"""
        def _run():
            old = self._delete(gid)
            return list((old or {}).get("members") or [])
        return await asyncio.to_thread(_run)

    async def pull_files(self, ids, exclude=False):
        """Deleted files को सब groups से हटाओ (file editor delete पर)।"""
        def _run():
            s = {str(i) for i in ids if i}
            changed = []
            for g in self._all():
                hit = s.intersection(str(m) for m in (g.get("members") or []))
                if not hit:
                    continue
                g["members"] = [m for m in g["members"] if str(m) not in s]
                g["files"] = [f for f in (g.get("files") or []) if str(f.get("id")) not in s]
                if exclude:
                    g["excluded"] = sorted(set(map(str, g.get("excluded") or [])) | s)
                g["updated_at"] = int(time.time())
                self._save(g)
                changed.append(str(g["_id"]))
            return changed
        return await asyncio.to_thread(_run)

    async def cleanup_empty(self):
        """2 से कम members वाले groups मिटाओ (ek file ka group बेकार है)।"""
        def _run():
            gone = []
            for g in self._all():
                if len(g.get("members") or []) < 2:
                    self._delete(g["_id"])
                    gone.append(str(g["_id"]))
            return gone
        return await asyncio.to_thread(_run)

    async def merge(self, source, target):
        """Source group की सारी files/auto_keys target में; source हट जाता है।"""
        src = await self.get(source)
        tgt = await self.get(target)
        if not src or not tgt:
            return None
        items = [(i, next((f.get("name", "") for f in (src.get("files") or [])
                           if str(f.get("id")) == str(i)), "")) for i in src.get("members") or []]
        keys = list(src.get("auto_keys") or []) + list(tgt.get("auto_keys") or [])
        await self.add_members(str(tgt["_id"]), items, auto_keys=keys)
        await self.delete(str(src["_id"]))
        return await self.get(target)

    # ── file collection helpers (fsv1 में सिर्फ़ एक collection) ────────────
    async def mark_files(self, ids, gid):
        """हर file doc पर `group_id` mark / unset — v5 का `_mark_files`।"""
        ids = [str(i) for i in ids if i]
        if not ids:
            return 0
        def _run():
            col = file_collection()
            if col is None:
                return 0
            try:
                upd = {"$set": {"group_id": str(gid)}} if gid else {"$unset": {"group_id": ""}}
                res = col.update_many({"_id": {"$in": ids}}, upd)
                return int(getattr(res, "modified_count", 0) or 0)
            except Exception as e:
                logger.warning(f"group mark_files skipped: {e}")
                return 0
        return await asyncio.to_thread(_run)

    async def files_by_ids(self, ids):
        """Group के सारे members के पूरे docs — चाहे search page पर हों या न हों।"""
        ids = [str(i) for i in ids if i]
        if not ids:
            return []
        def _run():
            col = file_collection()
            if col is None:
                return []
            try:
                return list(col.find({"_id": {"$in": ids}}))
            except Exception as e:
                logger.warning(f"group files_by_ids skipped: {e}")
                return []
        return await asyncio.to_thread(_run)

    async def scan_files(self, limit=20000):
        """Scan-all के लिए हल्का `{_id, file_name, group_id}` list।"""
        def _run():
            col = file_collection()
            if col is None:
                return []
            try:
                return list(col.find({}, {"_id": 1, "file_name": 1, "group_id": 1}).limit(limit))
            except Exception as e:
                logger.warning(f"group scan_files skipped: {e}")
                return []
        return await asyncio.to_thread(_run)

    async def count(self):
        def _run():
            return len(self._all())
        return await asyncio.to_thread(_run)


store = GroupStore(dbase)
