"""
Configuration file for Daraei Academy Telegram bots
"""

import os
import logging # Moved import logging earlier
import json
from dotenv import load_dotenv

# Load environment variables from .env file at the very beginning
load_dotenv()

# --- Logger Setup ---
# Get a logger instance. This should be configured early if used throughout the config.
logger = logging.getLogger(__name__)
# Basic configuration for logging to console, can be expanded.
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')



# Database settings
# DATABASE_NAME = "database/data/daraei_academy.db"  # This was an initial hardcoded value, replaced by dynamic loading later

# Bot tokens (Load from environment variables for security)
MAIN_BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN")
MANAGER_BOT_TOKEN = os.getenv("MANAGER_BOT_TOKEN")

# Ensure tokens are set
if not MAIN_BOT_TOKEN:
    raise ValueError("MAIN_BOT_TOKEN environment variable not set.")
if not MANAGER_BOT_TOKEN:
    raise ValueError("MANAGER_BOT_TOKEN environment variable not set.")

# --- Telegram Channels Information ---
TELEGRAM_CHANNELS_INFO_JSON = os.getenv("TELEGRAM_CHANNELS_INFO")
TELEGRAM_CHANNELS_INFO = [] # Default to an empty list

if TELEGRAM_CHANNELS_INFO_JSON:
    try:
        parsed_channels = json.loads(TELEGRAM_CHANNELS_INFO_JSON)
        if isinstance(parsed_channels, list):
            valid_channels = []
            for channel_info in parsed_channels:
                if isinstance(channel_info, dict) and \
                   'id' in channel_info and isinstance(channel_info['id'], int) and \
                   'link' in channel_info and isinstance(channel_info['link'], str) and \
                   'title' in channel_info and isinstance(channel_info['title'], str):
                    valid_channels.append({
                        "id": channel_info['id'],
                        "link": channel_info['link'],
                        "title": channel_info['title']
                    })
                else:
                    logger.warning(
                        f"Invalid channel entry in TELEGRAM_CHANNELS_INFO: {channel_info}. "
                        "Each entry must be a dict with 'id' (int), 'link' (str), and 'title' (str)."
                    )
            TELEGRAM_CHANNELS_INFO = valid_channels
            if not TELEGRAM_CHANNELS_INFO and parsed_channels: # If all entries were invalid but there was data
                 logger.error(
                    "TELEGRAM_CHANNELS_INFO was set in .env but contained no valid channel entries after parsing. "
                    "Please check the format."
                )
            elif TELEGRAM_CHANNELS_INFO:
                 logger.info(f"Successfully loaded {len(TELEGRAM_CHANNELS_INFO)} channel(s)/group(s) from TELEGRAM_CHANNELS_INFO.")

        else:
            logger.error(
                "TELEGRAM_CHANNELS_INFO in .env is not a valid JSON list. "
                "Please ensure it is a list of channel/group objects."
            )
    except json.JSONDecodeError:
        logger.error(
            "Failed to parse TELEGRAM_CHANNELS_INFO from .env. Ensure it is valid JSON. "
            "Example: '[{\"id\": -100123, \"link\": \"https://t.me/joinchat/...\", \"title\": \"My Channel\"}]'"
        )
else:
    logger.warning(
        "TELEGRAM_CHANNELS_INFO not set in .env. No channels/groups will be managed or displayed. "
        "To define channels, set TELEGRAM_CHANNELS_INFO as a JSON string in your .env file."
    )

# Optional: Check if TELEGRAM_CHANNELS_INFO is empty and raise an error if critical
# if not TELEGRAM_CHANNELS_INFO:
#     raise ValueError("Configuration error: TELEGRAM_CHANNELS_INFO is empty or invalid. At least one channel/group must be defined.")



# --- Payment Gateway Settings ---
_URL_NOT_SET_PLACEHOLDER = "URL_NOT_SET_IN_ENV"
_KEY_NOT_SET_PLACEHOLDER = "KEY_NOT_SET_IN_ENV"
_WALLET_NOT_SET_PLACEHOLDER = "WALLET_NOT_SET_IN_ENV"

# Generic Payment Gateway URL (e.g., for Rial, if RIAL_GATEWAY_URL is not specifically used elsewhere)
PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL")
if not PAYMENT_GATEWAY_URL:
    PAYMENT_GATEWAY_URL = _URL_NOT_SET_PLACEHOLDER
    logger.warning("PAYMENT_GATEWAY_URL not set in .env. Using placeholder: '%s'. Payment functionality might be affected.", PAYMENT_GATEWAY_URL)

PAYMENT_CALLBACK_URL = os.getenv("PAYMENT_CALLBACK_URL")
if not PAYMENT_CALLBACK_URL:
    PAYMENT_CALLBACK_URL = _URL_NOT_SET_PLACEHOLDER
    logger.warning("PAYMENT_CALLBACK_URL not set in .env. Using placeholder: '%s'. Payment verification might fail.", PAYMENT_CALLBACK_URL)

PAYMENT_API_KEY = os.getenv("PAYMENT_API_KEY")
if not PAYMENT_API_KEY:
    PAYMENT_API_KEY = _KEY_NOT_SET_PLACEHOLDER
    logger.warning("PAYMENT_API_KEY not set in .env. Using placeholder. Payment gateway communication might fail.")

# Crypto payment settings
TETHER_WALLET_ADDRESS = os.getenv("TETHER_WALLET_ADDRESS")
if not TETHER_WALLET_ADDRESS:
    TETHER_WALLET_ADDRESS = _WALLET_NOT_SET_PLACEHOLDER
    logger.warning("TETHER_WALLET_ADDRESS not set in .env. Using placeholder: '%s'. Crypto payments may not be possible.", TETHER_WALLET_ADDRESS)
# Crypto Payment Gateway Settings from .env
CRYPTO_WALLET_ADDRESS = os.getenv("CRYPTO_WALLET_ADDRESS")
if not CRYPTO_WALLET_ADDRESS:
    CRYPTO_WALLET_ADDRESS = _WALLET_NOT_SET_PLACEHOLDER
    logger.warning("CRYPTO_WALLET_ADDRESS not set in .env. Using placeholder: '%s'. USDT payments will fail.", CRYPTO_WALLET_ADDRESS)

TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY")
if not TRONGRID_API_KEY:
    TRONGRID_API_KEY = _KEY_NOT_SET_PLACEHOLDER
    logger.warning("TRONGRID_API_KEY not set in .env. Using placeholder. TronGrid communication will fail.")

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "") # Default to empty string if not set
if not COINGECKO_API_KEY:
    logger.info("COINGECKO_API_KEY not set or empty in .env. Real-time exchange rates via CoinGecko will not be used if it is required by the implementation.")

USDT_TRC20_CONTRACT_ADDRESS = os.getenv("USDT_TRC20_CONTRACT_ADDRESS")
if not USDT_TRC20_CONTRACT_ADDRESS:
    USDT_TRC20_CONTRACT_ADDRESS = "USDT_CONTRACT_NOT_SET_IN_ENV" 
    logger.error("CRITICAL: USDT_TRC20_CONTRACT_ADDRESS not set in .env. USDT payment processing will fail. Using placeholder: '%s'", USDT_TRC20_CONTRACT_ADDRESS)

CRYPTO_PAYMENT_CONFIRMATIONS_STR = os.getenv("CRYPTO_PAYMENT_CONFIRMATIONS", "20") 
try:
    CRYPTO_PAYMENT_CONFIRMATIONS = int(CRYPTO_PAYMENT_CONFIRMATIONS_STR)
except ValueError:
    logger.warning(
        f"Invalid value for CRYPTO_PAYMENT_CONFIRMATIONS in .env: '{CRYPTO_PAYMENT_CONFIRMATIONS_STR}'. "
        f"Using default value: 20."
    )
    CRYPTO_PAYMENT_CONFIRMATIONS = 20

CRYPTO_PAYMENT_TIMEOUT_MINUTES_STR = os.getenv("CRYPTO_PAYMENT_TIMEOUT_MINUTES", "30")
try:
    CRYPTO_PAYMENT_TIMEOUT_MINUTES = int(CRYPTO_PAYMENT_TIMEOUT_MINUTES_STR)
except ValueError:
    logger.warning(
        f"Invalid value for CRYPTO_PAYMENT_TIMEOUT_MINUTES in .env: '{CRYPTO_PAYMENT_TIMEOUT_MINUTES_STR}'. "
        f"Using default value: 30."
    )
    CRYPTO_PAYMENT_TIMEOUT_MINUTES = 30


# Specific Payment Gateway URLs
RIAL_GATEWAY_URL = os.getenv("RIAL_GATEWAY_URL")
if not RIAL_GATEWAY_URL:
    RIAL_GATEWAY_URL = _URL_NOT_SET_PLACEHOLDER
    logger.warning("RIAL_GATEWAY_URL not set in .env. Using placeholder: '%s'. Rial payments might be affected if this specific URL is required.", RIAL_GATEWAY_URL)

CRYPTO_GATEWAY_URL = os.getenv("CRYPTO_GATEWAY_URL")
if CRYPTO_GATEWAY_URL is None:  # Explicitly check for None, as empty string is a valid 'not configured' state
    CRYPTO_GATEWAY_URL = ""  # Default to empty string if not set, meaning no specific crypto gateway URL
    logger.info("CRYPTO_GATEWAY_URL not set in .env. Defaulting to empty string (no specific crypto gateway configured).")
elif not CRYPTO_GATEWAY_URL:
    logger.info("CRYPTO_GATEWAY_URL is set to an empty string in .env (no specific crypto gateway configured).")

# Time settings
TEHRAN_TIMEZONE = "Asia/Tehran"
EXPIRATION_REMINDER_DAYS = 5  # Number of days before subscription expires to send a reminder
REMINDER_HOUR = 13  # Hour to send daily reminders (in 24-hour format)

# --- Database Settings ---
# Get the directory where this config.py file is located
_CONFIG_FILE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the subdirectories for the database file relative to config.py's location
_DATABASE_SUBDIR = "database"
_DATA_SUBDIR = "data"

# Read the database filename from .env. If not set, use a default and log a warning.
DB_FILENAME_FROM_ENV = os.getenv("DB_FILENAME")
if not DB_FILENAME_FROM_ENV:
    DB_FILENAME_FROM_ENV = "daraei_academy_default.db"  # Default filename if not in .env
    logger.warning(
        "DB_FILENAME not set in .env. Using default filename: '%s'. "
        "The database will be created/looked for in the '%s/%s/' subdirectory relative to config.py.",
        DB_FILENAME_FROM_ENV, _DATABASE_SUBDIR, _DATA_SUBDIR
    )

# Construct the full path to the database directory and file
_DATABASE_FULL_DIR = os.path.join(_CONFIG_FILE_DIR, _DATABASE_SUBDIR, _DATA_SUBDIR)
DATABASE_PATH = os.path.join(_DATABASE_FULL_DIR, DB_FILENAME_FROM_ENV)

# Ensure the database directory exists
try:
    os.makedirs(_DATABASE_FULL_DIR, exist_ok=True)
    logger.info(f"Database path configured to: {DATABASE_PATH}")
    logger.info(f"Database directory {_DATABASE_FULL_DIR} ensured to exist.")
except OSError as e:
    logger.error(f"Could not create database directory {_DATABASE_FULL_DIR}: {e}")
    raise  # Re-raise the exception as this is critical

# For SQLAlchemy or other ORMs, you might need a URL (adjust if not using SQLite)
# Ensure forward slashes for the SQLite URL, especially on Windows.
DATABASE_URL = f"sqlite:///{DATABASE_PATH.replace(os.sep, '/')}"

# For compatibility, DATABASE_NAME should be the full path to the database file.
DATABASE_NAME = DATABASE_PATH

# Education levels for registration
EDUCATION_LEVELS = [
    "دیپلم",
    "کاردانی",
    "کارشناسی",
    "کارشناسی ارشد",
    "دکتری"
]

# Channel member validation frequency (in seconds)
VALIDATION_INTERVAL = 60  # Check every minute

# Membership reminder settings
REMINDER_DAYS = 5  # Send reminders when 5 days are left

import json
# logging import and logger definition moved earlier

# --- Admin Role Constants ---
ROLE_MAIN_BOT_ERROR_CONTACT = "main_bot_error_contact"
ROLE_MAIN_BOT_SUPPORT_STAFF = "main_bot_support_staff"
ROLE_MANAGER_BOT_ADMIN = "manager_bot_admin"
ROLE_MANAGER_BOT_ERROR_CONTACT = "manager_bot_error_contact"
# Add other roles here if any, e.g.:
# ROLE_SUPER_ADMIN = "super_admin"

# --- Consolidated Admin Configuration Processing ---
ALL_ADMINS_CONFIG_JSON = os.getenv("ALL_ADMINS_CONFIG", "[]")
ALL_ADMINS_LIST = []
try:
    ALL_ADMINS_LIST = json.loads(ALL_ADMINS_CONFIG_JSON)
    if not isinstance(ALL_ADMINS_LIST, list):
        logger.warning("ALL_ADMINS_CONFIG in .env is not a valid JSON list. Using empty list. Admin functionalities may be affected.")
        ALL_ADMINS_LIST = []
except json.JSONDecodeError:
    logger.error(f"ALL_ADMINS_CONFIG in .env ('{ALL_ADMINS_CONFIG_JSON}') is not valid JSON. Using empty list. Admin functionalities may be affected.")

MAIN_BOT_ERROR_CONTACT_IDS = []
MAIN_BOT_SUPPORT_STAFF_LIST = [] # List of {"chat_id": int, "alias": str}
MANAGER_BOT_ADMINS_DICT = {} # Dict of {chat_id: alias}
MANAGER_BOT_ERROR_CONTACT_IDS = []

for admin_info in ALL_ADMINS_LIST:
    chat_id = admin_info.get("chat_id")
    alias = admin_info.get("alias")
    roles = admin_info.get("roles", [])

    if not isinstance(chat_id, int) or not isinstance(alias, str) or not isinstance(roles, list):
        logger.warning(f"Invalid admin entry in ALL_ADMINS_CONFIG: {admin_info}. Skipping.")
        continue

    if ROLE_MAIN_BOT_ERROR_CONTACT in roles:
        MAIN_BOT_ERROR_CONTACT_IDS.append(chat_id)
    if ROLE_MAIN_BOT_SUPPORT_STAFF in roles:
        MAIN_BOT_SUPPORT_STAFF_LIST.append({"chat_id": chat_id, "alias": alias})
    if ROLE_MANAGER_BOT_ADMIN in roles:
        MANAGER_BOT_ADMINS_DICT[chat_id] = alias
    if ROLE_MANAGER_BOT_ERROR_CONTACT in roles:
        MANAGER_BOT_ERROR_CONTACT_IDS.append(chat_id)

# Extract all unique admin chat_ids into ADMIN_USER_IDS for general use
ADMIN_USER_IDS = list(set(admin.get("chat_id") for admin in ALL_ADMINS_LIST if isinstance(admin.get("chat_id"), int)))
if not ADMIN_USER_IDS:
    logger.warning("ADMIN_USER_IDS is empty. This might be expected if ALL_ADMINS_LIST is empty or contains no valid chat_ids.")

# Warnings for critical missing roles
if not MAIN_BOT_ERROR_CONTACT_IDS:
    logger.warning(f"No admin configured with '{ROLE_MAIN_BOT_ERROR_CONTACT}' role. Main bot error reporting via Telegram might be disabled.")
if not MAIN_BOT_SUPPORT_STAFF_LIST:
    logger.info(f"No admin configured with '{ROLE_MAIN_BOT_SUPPORT_STAFF}' role. Main bot might not display support staff info if this list is used directly for that.")
if not MANAGER_BOT_ADMINS_DICT:
    logger.warning(f"No admin configured with '{ROLE_MANAGER_BOT_ADMIN}' role. Manager bot may not be accessible by any admin.")
if not MANAGER_BOT_ERROR_CONTACT_IDS:
    logger.warning(f"No admin configured with '{ROLE_MANAGER_BOT_ERROR_CONTACT}' role. Manager bot error reporting via Telegram might be disabled.")

# For compatibility, define ADMIN_CHAT_ID (for main bot errors)
ADMIN_CHAT_ID = MAIN_BOT_ERROR_CONTACT_IDS[0] if MAIN_BOT_ERROR_CONTACT_IDS else None
if ADMIN_CHAT_ID is None and not MAIN_BOT_ERROR_CONTACT_IDS:
     logger.warning(f"ADMIN_CHAT_ID (legacy, for main bot errors) is not set as no admin has '{ROLE_MAIN_BOT_ERROR_CONTACT}' role.")
# The case 'ADMIN_CHAT_ID is None and MAIN_BOT_ERROR_CONTACT_IDS' should not happen with the current logic.
# If MAIN_BOT_ERROR_CONTACT_IDS is populated, ADMIN_CHAT_ID will be its first element.

# For compatibility, define MANAGER_BOT_ADMIN_USERS (for manager bot admins)
MANAGER_BOT_ADMIN_USERS = MANAGER_BOT_ADMINS_DICT

# For compatibility, define ADMIN_USERS (for main bot support staff list)
ADMIN_USERS = MAIN_BOT_SUPPORT_STAFF_LIST
# --- End of Consolidated Admin Configuration Processing ---
