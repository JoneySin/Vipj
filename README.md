# 🚀 FAST FINDER — Web File Search + Real Thumbnails + Streaming

Telegram Auto-Filter Bot (`fsv1`) अब **web पर लॉगिन करके** फाइलें खोजने, हर फाइल के साथ
**असली Telegram thumbnail** देखने और **फाइल नाम पर क्लिक करते ही signed streaming लिंक से
वीडियो चलाने** की सुविधा देता है। यही flow `JoneySin/v5` में है — यहाँ उसे `fsv1` के
मौजूदा PyMongo + aiohttp architecture के अनुकूल port किया गया है।

---

## ✨ क्या-क्या नया है

| Feature | Detail |
|---|---|
| 🔐 Login / Register | Email + Password, registration Telegram bot PM में **OTP** से, forgot-password OTP reset, HttpOnly cookie session (RAM + MongoDB यानी restart पर भी login बना रहे) |
| 🔍 Web Search | `/search` → `/api/search` → MongoDB text search + regex fallback, **टाइप करते ही auto-search** (Search बटन नहीं), **21 results प्रति पेज** (3 columns × 7 rows desktop), "और दिखाओ" pagination, खाली query पर **Recently Added** (फाइलों की गिनती अब **Database Stats** में दिखती है) |
| 🧭 v5 Sidebar | हर logged-in पेज पर hamburger sidebar — **Home · Database Stats (admin-only) · Profile Settings**, header में `#ID · ADMIN`, footer में **Sign Out** (बिल्कुल `JoneySin/v5` जैसा) |
| 📊 Database Stats | `/stats` — v5 जैसे animated stat cards; **"🆕 Recently Added Files"** की गिनती यहीं, search पेज की meta लाइन में नहीं |
| ⚙️ Profile Settings | `/profile` — v5 जैसा Account Settings: `#ID · ADMIN` identity, Account Status (👑 Admin / 💎 Premium / 🆓 Free), Telegram ID, Email + Password बदलना (tabs, show/hide, strength meter) |
| 📐 Responsive Grid | 🖥️ Desktop ≥1024px: **3 वीडियो / row** · 📟 Tablet: 2 · 📱 Mobile: **1 वीडियो / row** |
| 🎛️ View / Filter | Search bar के नीचे 2 dropdowns — **Poster / Text** mode (Text में सिर्फ़ नाम + meta की कॉम्पैक्ट लिस्ट, कोई thumbnail request नहीं) और **All / Group / UnGroup** (एक ही टाइटल की 2+ फाइलें = Group, अकेली फाइल = UnGroup)। दोनों चुनाव browser में याद रहते हैं |
| 📏 Size Chip | **File size thumbnail के अंदर** (नीचे-दाएँ badge) — फाइल नाम के नीचे की size/Stream लाइन हटा दी गई |
| 📸 Real Thumbnails | **DB में सिर्फ़ Telegram का thumbnail file_id** — v5 की तरह `thumb_url: "TG_ID:<file_id>"` string. **Image bytes न DB में, न server RAM में** (Koyeb free पर RAM भर जाता है)। `/api/thumb` उन्हें Telegram से लाकर तुरंत response देता है और `ETag` + `Cache-Control` से **ब्राउज़र की अपनी memory/disk cache** में रखवाता है (`If-None-Match` → 304, दोबारा कोई server/Telegram call नहीं) |
| ▶ Click-to-Stream | फाइल नाम पर क्लिक → `/api/stream` → BIN_CHANNEL में cached media → **HMAC-signed** `/watch/<id>` + `/download/<id>` → modal `<video>` player (Range/seek supported), Download, Player page, Copy link |
| 🔗 Signed Links | `e` (expiry) + `s` (signature) — बिना सही signature के message-id guess करके file नहीं निकाली जा सकती। Telegram bot के Watch/Download buttons भी अब signed links बनाते हैं |
| ⚡ Seek Performance | `media_info` cache (5 मिनट) से हर Range request पर `get_messages()` नहीं लगती; Range parser + `StreamResponse` hardened, आख़िरी chunk सही कटता है |

---

## 🧭 Routes

| Method | Path | काम |
|---|---|---|
| GET | `/` | Logged-in → `/search`, वरना landing page (uptime-safe 200) |
| GET | `/login`, `/register`, `/verify_registration`, `/forgot_password` | Auth pages |
| POST | `/api/login`, `/api/register_step1`, `/api/register_step2`, `/api/forgot_password`, `/api/reset_password` | Auth APIs |
| GET | `/logout` | Session खत्म (RAM + DB) |
| GET | `/search` | Login-walled search UI (v5 sidebar के साथ) |
| GET | `/stats` | **Database Stats** (admin-only) — v5 जैसे counters, "Recently Added Files" की गिनती यहीं |
| GET | `/api/db_stats` | उन्हीं counters का JSON (admin-only) |
| GET | `/profile` | **Profile Settings** — v5 जैसा Account Settings (`#ID · ADMIN`, status, email, password) |
| POST | `/api/update_profile` | Email / password update (password बदलने पर सभी sessions बंद) |
| GET | `/api/search?q=&offset=&limit=&group=` | JSON results (`file_id`, `name`, `size`, `quality`, `duration`, `res`, `thumb`); `group=all\|group\|ungroup` |
| GET | `/api/thumb?file_id=&v=` | असली thumbnail image (login required) |
| POST | `/api/stream` `{file_id}` | `{watch, download, stream, poster, expires_in}` |
| GET | `/setup_stream?file_id=&mode=` | GET shortcut, signed watch/download पर redirect |
| GET | `/watch/<id>?e=&s=&poster=` | Signed player page |
| GET | `/download/<id>?e=&s=` | Signed Range streaming (206/416/HEAD) |

> **Stream links shareable हैं:** एक बार जारी किया गया signed link logout के बाद भी
> `WEB_STREAM_TTL` तक चलता है (जैसे v5 में)। नया link बनाने के लिए login ज़रूरी है।

---

## ⚙️ Environment Variables

जो vars कोड में सच में use होते हैं (`API_ID`, `API_HASH`, `BOT_TOKEN`, `ADMINS`,
`DATA_DATABASE_URL`, `DATABASE_NAME`, `COLLECTION_NAME`, `BIN_CHANNEL`, `URL`, `MAX_BTN`,
`PM_FILE_DELETE_TIME`, `IS_STREAM`, `USE_CAPTION_FILTER`, `PROTECT_CONTENT`, …) वैसे ही
रहेंगे। `info.py` से **unused legacy vars** (`SUPPORT_GROUP`, `SUPPORT_LINK`, `TUTORIAL`,
`QUALITY`, `LANGUAGES`, `CACHE_TIME`, `DELETE_TIME`, `TIME_ZONE`, `IS_VERIFY`, `AUTO_DELETE`,
`LINK_MODE`, `VERIFY_EXPIRE`, hot/cold collection names, …) हटा दिए गए हैं — इन्हें अब set
करने की कोई ज़रूरत नहीं, और `SUPPORT_GROUP` अब mandatory भी नहीं है। नए optional vars:

| Var | Default | मतलब |
|---|---|---|
| `MAX_WEB_RESULTS` | `21` | एक page में results (3×7 desktop); env से बदल सकते हैं |
| `WEB_SESSION_TTL` | `604800` | Login cookie validity (seconds, 7 दिन) |
| `WEB_STREAM_TTL` | `21600` | Web stream link validity (6 घंटे) |
| `THUMB_BROWSER_CACHE` | `604800` | ब्राउज़र poster कितने सेकंड अपने cache में रखे (7 दिन) |
| `THUMB_FETCH_CONCURRENCY` | `6` | एक साथ कितने Telegram thumbnail download चलें (FloodWait बचाव) |
| `STREAM_SECRET` | `BOT_TOKEN` से derive | HMAC secret — production में **ज़रूर सेट करें**, बदलने पर पुराने links expire हो जाएँगे |
| `ALLOW_UNSIGNED_LINKS` | `False` | Deploy से पहले बंटे पुराने unsigned `/watch/<id>` links को चालू रखने के लिए `True` करें |

---

## 🧑‍💻 पहली बार use कैसे करें

1. Telegram में bot को `/start` भेजें (OTP वहीं आएगा)।
2. `https://<your-domain>/register` खोलें → **Telegram ID + Email + Password** भरें →
   "Send OTP via Telegram" → bot PM में मिला 6-digit OTP डालें → Account बन गया।
3. `/login` पर Email + Password से sign in → `/search`।
4. Search box में नाम लिखें (या चिप्स दबाएँ) → cards में **असली thumbnail**, size,
   quality, resolution, duration दिखेंगे।
5. **फाइल नाम पर क्लिक** → streaming link तैयार → वीडियो modal में चलता है।
   चाहें तो "Player page" / "Download" / "Copy stream link" use करें।

> Thumbnail न मिलने पर card पर graceful placeholder दिखता है (कोई fake poster नहीं)।

> **🗂️ Group / UnGroup:** fsv1 के DB में `group_id` field नहीं है, इसलिए फ़िल्टर file
> name से चलता है — quality / भाषा / codec / extension tokens हटाने के बाद **एक ही
> टाइटल की 2+ फाइलें = Group**, अकेली फाइल = **UnGroup**, **All** = सब। इसके लिए DB में
> कोई नया field या bytes नहीं जोड़े गए; 21 प्रति पेज और "और दिखाओ" pagination वैसे ही हैं।

> **📸 Thumbnail storage:** `files` doc में `thumb_url: "TG_ID:<telegram_thumb_file_id>"`
> — बस एक छोटी सी string (DB)। असली JPEG/PNG/WEBP bytes **न MongoDB में, न server RAM
> cache में** — वे `/api/thumb` के `ETag` + `Cache-Control: private, max-age=...` से
> **उसी ब्राउज़र/साइट की memory-disk cache** में रहती हैं। Server पर सिर्फ़ चल रही request
> के दौरान ~10–60 KB transient buffer आता है और response के साथ free हो जाता है।
> `v` (= thumb_url का hash) बदलने पर ETag/URL बदलता है, तो नया poster अपने आप आ जाता है।

---

## 🗂️ कहाँ-क्या बदला

```
stream_security.py               → HMAC sign/verify (नया)
database/users_chats_db.py       → WebAuthDB: web_users + web_sessions + PBKDF2 + OTP (नया)
database/ia_filterdb.py          → save_file में `thumb_url` (सिर्फ ID) + meta fields,
                                   search projection, get_recent_files(),
                                   update_file_meta() (सिर्फ ID backfill)
utils.py                         → temp.USER_SESSIONS / REG_PENDING
web/web_assets.py                → get_auth(), CSS, login shell, search UI; auto-search,
                                   Poster/Text + All/Group/UnGroup dropdowns, size-in-poster
web/auth_routes.py               → login/register/OTP/logout routes (नया)
web/thumb_engine.py              → Telegram fetch (बिना किसी cache के), DB में सिर्फ ID backfill
web/search_routes.py             → /search, /api/search (group filter), /api/thumb, /api/stream (नया)
web/utils/media_info.py          → media metadata cache (नया)
web/utils/render_template.py     → signed player page + poster
web/utils/custom_dl.py           → FileId support + आख़िरी Range chunk fix
web/stream_routes.py             → landing, signed watch/download, hardened Range
web/__init__.py                  → तीनों route tables register
plugins/callbacks.py             → bot के Watch/Download links अब signed
```

### 🧹 Dead-code cleanup

`info.py` अब सिर्फ़ वही config रखता है जो कोड में सच में पढ़ा जाता है (unused env vars,
`import os`, purane link/collection/template constants हटाए)। इसके साथ `Script.py` के unused
message templates, कभी न बुलाए गए DB helpers/methods (`run_sync`, `update_file_quality`,
`database_health_check`, `delete_file_by_id`, ban/add-user API, `update_profile`,
`download_as_bytesio`, `drop_media_info`, `last_online`), unused imports/locals और बेकार `f`-strings/`global`
भी हटा दिए गए। `pyflakes` अब पूरे repo पर clean है; web/auth/stream/thumbnail behaviour
जस का तस है।

---

## 🚢 Deploy

`Procfile` / `Dockerfile` / `render.yaml` पहले जैसे ही `python bot.py` चलाते हैं; web app
bot के start होते ही `0.0.0.0:PORT` पर up हो जाता है। कोई extra service या dependency
नहीं जोड़नी पड़ी (सब stdlib + मौजूदा `aiohttp`/`pymongo`/`hydrogram`)।

> ⚠️ Purane unsigned watch/download links default में बंद हो जाएँगे (सुरक्षा के लिए)।
> अगर ऐसे links अभी circulate हो रहे हैं तो temporarily `ALLOW_UNSIGNED_LINKS=True` रखें।
