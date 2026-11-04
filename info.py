import re
from os import environ
import logging

logger = logging.getLogger(__name__)

# ================= BASIC UTILS =================

def is_enabled(type, value):
    data = environ.get(type, str(value))
    if data.lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif data.lower() in ["false", "no", "0", "disable", "n"]:
        return False
    else:
        logger.error(f'{type} is invalid, exiting now')
        exit()

def is_valid_ip(ip):
    ip_pattern = r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                 r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                 r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                 r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    return re.match(ip_pattern, ip) is not None

# ================= BOT INFO =================

API_ID = environ.get('API_ID', '')
if not API_ID:
    logger.error('API_ID is missing')
    exit()
API_ID = int(API_ID)

API_HASH = environ.get('API_HASH', '')
if not API_HASH:
    logger.error('API_HASH is missing')
    exit()

BOT_TOKEN = environ.get('BOT_TOKEN', '')
if not BOT_TOKEN:
    logger.error('BOT_TOKEN is missing')
    exit()

PORT = int(environ.get('PORT', '80'))

# ================= IMAGES =================

PICS = environ.get(
    'PICS',
    'https://i.postimg.cc/8C15CQ5y/1.png'
).split()

# ================= ADMINS / CHANNELS =================

ADMINS = environ.get('ADMINS', '')
if not ADMINS:
    logger.error('ADMINS is missing')
    exit()
ADMINS = [int(x) for x in ADMINS.split()]

INDEX_CHANNELS = [
    int(x) if x.startswith("-") else x
    for x in environ.get('INDEX_CHANNELS', '').split()
]

LOG_CHANNEL = environ.get('LOG_CHANNEL', '')
if not LOG_CHANNEL:
    logger.error('LOG_CHANNEL is missing')
    exit()
LOG_CHANNEL = int(LOG_CHANNEL)

# 🔥 INDEX LOG CHANNEL
INDEX_LOG_CHANNEL = environ.get('INDEX_LOG_CHANNEL', '')
if not INDEX_LOG_CHANNEL:
    logger.info('INDEX_LOG_CHANNEL not set, using LOG_CHANNEL')
    INDEX_LOG_CHANNEL = LOG_CHANNEL
else:
    INDEX_LOG_CHANNEL = int(INDEX_LOG_CHANNEL)

BIN_CHANNEL = environ.get("BIN_CHANNEL", "")
if not BIN_CHANNEL:
    logger.error('BIN_CHANNEL is missing')
    exit()
BIN_CHANNEL = int(BIN_CHANNEL)

# ================= DATABASE =================

DATA_DATABASE_URL = environ.get('DATA_DATABASE_URL', "")
if not DATA_DATABASE_URL:
    logger.error('DATA_DATABASE_URL is missing')
    exit()

DATABASE_NAME = environ.get('DATABASE_NAME', "bot_db")
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'files')
MAX_BTN = int(environ.get('MAX_BTN', 8))

# ================= FILE / STREAM SETTINGS =================

PM_FILE_DELETE_TIME = int(environ.get('PM_FILE_DELETE_TIME', 3600))

USE_CAPTION_FILTER = is_enabled('USE_CAPTION_FILTER', True)
PROTECT_CONTENT = is_enabled('PROTECT_CONTENT', False)
IS_STREAM = is_enabled('IS_STREAM', True)

# ================= WEB SEARCH / LOGIN =================
# Web par ek page me kitne results dikhane hain (pagination / load-more)
# 21 = 3 columns × 7 rows (desktop), mobile पर 21 rows
MAX_WEB_RESULTS = max(1, min(int(environ.get('MAX_WEB_RESULTS', '21')), 100))

# Web login cookie ki validity (seconds) — default 7 din
WEB_SESSION_TTL = int(environ.get('WEB_SESSION_TTL', 7 * 24 * 3600))

# Web stream link ki validity (seconds) — default 6 ghante
WEB_STREAM_TTL = int(environ.get('WEB_STREAM_TTL', 6 * 3600))

# 📸 DB में सिर्फ Telegram thumbnail का file_id ("TG_ID:..." string) जाता है।
# Image bytes न DB में, न server RAM cache में — browser के HTTP cache में रहती हैं।
# Server पर कोई RAM cache नहीं (Koyeb free 512MB); browser अपने HTTP cache में
# poster रखेगा — ETag + max-age नीचे।
THUMB_BROWSER_CACHE = int(environ.get('THUMB_BROWSER_CACHE', 7 * 24 * 3600))
# एक साथ कितने Telegram thumbnail downloads चलें (सिर्फ़ known TG_ID वाली फाइलें)
THUMB_FETCH_CONCURRENCY = max(1, min(int(environ.get('THUMB_FETCH_CONCURRENCY', '6')), 20))

# ── 🖼️ FIRST-TIME THUMBNAIL EXTRACTION (JoneySin/v5 के warmup engine जैसा) ──
# पहली बार 21 नई फाइलें एक साथ खुलने पर Telegram FLOOD_WAIT न लगे, इसलिए
# probes एक-एक करके चलते हैं और हर file के बीच random gap रहता है।
THUMB_PROBE_GAP_MIN = float(environ.get('THUMB_PROBE_GAP_MIN', '1.2'))
THUMB_PROBE_GAP_MAX = max(THUMB_PROBE_GAP_MIN, float(environ.get('THUMB_PROBE_GAP_MAX', '3.0')))
THUMB_PROBE_ATTEMPTS = max(1, min(int(environ.get('THUMB_PROBE_ATTEMPTS', '5')), 10))
# FLOOD_WAIT में Telegram के बताए seconds + यह extra buffer
THUMB_FLOOD_EXTRA = max(0, int(environ.get('THUMB_FLOOD_EXTRA', '10')))

# Purane (unsigned) /watch/<id> links deploy se pehle bheje gaye ho sakte hain.
# Default False = sirf signed links chalengi. True karke backward compatibility on karo.
ALLOW_UNSIGNED_LINKS = is_enabled('ALLOW_UNSIGNED_LINKS', False)

# ================= PUBLIC URL =================

URL = environ.get("URL", "")
if not URL:
    logger.error('URL is missing')
    exit()

if URL.startswith(('https://', 'http://')):
    if not URL.endswith("/"):
        URL += '/'
elif is_valid_ip(URL):
    URL = f'http://{URL}/'
else:
    logger.error('URL is invalid')
    exit()

# ================= PREMIUM =================

IS_PREMIUM = is_enabled('IS_PREMIUM', True)
PRE_DAY_AMOUNT = int(environ.get('PRE_DAY_AMOUNT', '10'))

UPI_ID = environ.get("UPI_ID", "")
UPI_NAME = environ.get("UPI_NAME", "")
RECEIPT_SEND_USERNAME = environ.get("RECEIPT_SEND_USERNAME", "")

if not UPI_ID or not UPI_NAME:
    logger.info('Premium disabled due to missing UPI details')
    IS_PREMIUM = False
