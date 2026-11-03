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
| 🔍 Web Search | `/search` → `/api/search` → MongoDB text search + regex fallback, pagination / "और दिखाओ", खाली query पर **Recently Added** |
| 📸 Real Thumbnails | Index के समय Telegram के `media.thumbs[0].file_id` DB में save; पुरानी फाइलों के लिए `send_cached_media()` से lazy backfill. RAM-bounded LRU + per-file lock + FloodWait retry |
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
| GET | `/search` | Login-walled search UI |
| GET | `/api/search?q=&offset=&limit=` | JSON results (`file_id`, `name`, `size`, `quality`, `duration`, `res`, `thumb`) |
| GET | `/api/thumb?file_id=&v=` | असली thumbnail image (login required) |
| POST | `/api/stream` `{file_id}` | `{watch, download, stream, poster, expires_in}` |
| GET | `/setup_stream?file_id=&mode=` | GET shortcut, signed watch/download पर redirect |
| GET | `/watch/<id>?e=&s=&poster=` | Signed player page |
| GET | `/download/<id>?e=&s=` | Signed Range streaming (206/416/HEAD) |

> **Stream links shareable हैं:** एक बार जारी किया गया signed link logout के बाद भी
> `WEB_STREAM_TTL` तक चलता है (जैसे v5 में)। नया link बनाने के लिए login ज़रूरी है।

---

## ⚙️ Environment Variables

पुराने सभी vars (`API_ID`, `API_HASH`, `BOT_TOKEN`, `ADMINS`, `DATA_DATABASE_URL`,
`DATABASE_NAME`, `COLLECTION_NAME`, `BIN_CHANNEL`, `URL`, …) वैसे ही रहेंगे। नए optional vars:

| Var | Default | मतलब |
|---|---|---|
| `MAX_WEB_RESULTS` | `30` | एक page में maximum results (max 100) |
| `WEB_SESSION_TTL` | `604800` | Login cookie validity (seconds, 7 दिन) |
| `WEB_STREAM_TTL` | `21600` | Web stream link validity (6 घंटे) |
| `THUMB_CACHE_ITEMS` | `256` | RAM में कितने posters cache हों (24 MB byte-cap भी है) |
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

---

## 🗂️ कहाँ-क्या बदला

```
stream_security.py               → HMAC sign/verify (नया)
database/users_chats_db.py       → WebAuthDB: web_users + web_sessions + PBKDF2 + OTP (नया)
database/ia_filterdb.py          → save_file में thumb/meta fields, search projection,
                                   get_recent_files(), update_file_meta()
utils.py                         → temp.USER_SESSIONS / REG_PENDING
web/web_assets.py                → get_auth(), CSS, login shell, search UI (नया)
web/auth_routes.py               → login/register/OTP/logout routes (नया)
web/thumb_engine.py              → real Telegram thumbnail fetch + LRU + backfill (नया)
web/search_routes.py             → /search, /api/search, /api/thumb, /api/stream (नया)
web/utils/media_info.py          → media metadata cache (नया)
web/utils/render_template.py     → signed player page + poster
web/utils/custom_dl.py           → FileId support + आख़िरी Range chunk fix
web/stream_routes.py             → landing, signed watch/download, hardened Range
web/__init__.py                  → तीनों route tables register
plugins/callbacks.py             → bot के Watch/Download links अब signed
```

---

## 🚢 Deploy

`Procfile` / `Dockerfile` / `render.yaml` पहले जैसे ही `python bot.py` चलाते हैं; web app
bot के start होते ही `0.0.0.0:PORT` पर up हो जाता है। कोई extra service या dependency
नहीं जोड़नी पड़ी (सब stdlib + मौजूदा `aiohttp`/`pymongo`/`hydrogram`)।

> ⚠️ Purane unsigned watch/download links default में बंद हो जाएँगे (सुरक्षा के लिए)।
> अगर ऐसे links अभी circulate हो रहे हैं तो temporarily `ALLOW_UNSIGNED_LINKS=True` रखें।
