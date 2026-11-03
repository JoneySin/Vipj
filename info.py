import re
from os import environ
import os
from Script import script
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

BOT_ID = BOT_TOKEN.split(":")[0]
PORT = int(environ.get('PORT', '80'))

# ================= IMAGES =================

PICS = environ.get(
    'PICS',
    'https://i.postimg.cc/8C15CQ5y/1.png'
).split()

# ================= ADMINS =================

ADMINS = environ.get('ADMINS', '')
if not ADMINS:
    logger.error('ADMINS is missing')
    exit()
ADMINS = [int(x) for x in ADMINS.split()]

# ================= CHANNELS =================

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

SUPPORT_GROUP = environ.get('SUPPORT_GROUP', '')
if not SUPPORT_GROUP:
    logger.error('SUPPORT_GROUP is missing')
    exit()
SUPPORT_GROUP = int(SUPPORT_GROUP)

# ================= DATABASE =================

DATA_DATABASE_URL = environ.get('DATA_DATABASE_URL', "")
if not DATA_DATABASE_URL:
    logger.error('DATA_DATABASE_URL is missing')
    exit()

DATABASE_NAME = environ.get('DATABASE_NAME', "bot_db")

# 🔥 MAIN COLLECTION (Backward Compatible)
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'files')

# 🔥 FUTURE READY (Hot / Cold)
FILES_COLLECTION = environ.get('FILES_COLLECTION', 'files_hot')
FILES_BACKUP_COLLECTION = environ.get('FILES_BACKUP_COLLECTION', 'files_cold')

USERS_COLLECTION = environ.get('USERS_COLLECTION', 'users')
CHATS_COLLECTION = environ.get('CHATS_COLLECTION', 'chats')
BANS_COLLECTION = environ.get('BANS_COLLECTION', 'bans')

# ================= LINKS =================

SUPPORT_LINK = environ.get('SUPPORT_LINK', 'https://t.me/HA_Bots_Support')
UPDATES_LINK = environ.get('UPDATES_LINK', 'https://t.me/HA_Bots')
FILMS_LINK = environ.get('FILMS_LINK', 'https://t.me/HA_Films_World')
TUTORIAL = environ.get("TUTORIAL", "https://t.me/HA_Bots")

# ================= SETTINGS =================

TIME_ZONE = environ.get('TIME_ZONE', 'Asia/Kolkata')
DELETE_TIME = int(environ.get('DELETE_TIME', 3600))
CACHE_TIME = int(environ.get('CACHE_TIME', 300))
MAX_BTN = int(environ.get('MAX_BTN', 8))

LANGUAGES = environ.get(
    'LANGUAGES',
    'hindi english tamil telugu'
).lower().split()

QUALITY = environ.get(
    'QUALITY',
    '360p 480p 720p 1080p'
).lower().split()

FILE_CAPTION = environ.get("FILE_CAPTION", script.FILE_CAPTION)
VERIFY_EXPIRE = int(environ.get('VERIFY_EXPIRE', 86400))
WELCOME_TEXT = environ.get("WELCOME_TEXT", script.WELCOME_TEXT)

PM_FILE_DELETE_TIME = int(environ.get('PM_FILE_DELETE_TIME', 3600))

# ================= BOOLEAN FLAGS =================

USE_CAPTION_FILTER = is_enabled('USE_CAPTION_FILTER', True)
IS_VERIFY = is_enabled('IS_VERIFY', True)
AUTO_DELETE = is_enabled('AUTO_DELETE', False)
WELCOME = is_enabled('WELCOME', True)
PROTECT_CONTENT = is_enabled('PROTECT_CONTENT', False)
LINK_MODE = is_enabled("LINK_MODE", True)

# ================= STREAM =================

IS_STREAM = is_enabled('IS_STREAM', True)

BIN_CHANNEL = environ.get("BIN_CHANNEL", "")
if not BIN_CHANNEL:
    logger.error('BIN_CHANNEL is missing')
    exit()
BIN_CHANNEL = int(BIN_CHANNEL)

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
