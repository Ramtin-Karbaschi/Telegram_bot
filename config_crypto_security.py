"""
Configuration template for enhanced crypto payment security.
Add these settings to your main config.py file.
"""

# TronGrid API Configuration
TRONGRID_API_KEY = "your_trongrid_api_key_here"  # Get from https://www.trongrid.io/
USDT_TRC20_CONTRACT_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT TRC20 contract
CRYPTO_WALLET_ADDRESS = "your_wallet_address_here"  # Your receiving wallet

# Security Settings
TRON_MIN_CONFIRMATIONS = 1  # Minimum block confirmations required (0 to disable)
MAX_TX_AGE_HOURS = 24  # Maximum age of transaction to accept (prevents old hash reuse)

# Payment Timeout
CRYPTO_PAYMENT_TIMEOUT_MINUTES = 180  # How long payment requests stay valid (3 hours)

# Audit and Logging
ENABLE_PAYMENT_AUDIT_LOG = True  # Enable detailed audit logging
AUDIT_LOG_FILE = "logs/payment_audit.log"  # Audit log file path

# Admin Notifications (optional)
ADMIN_TELEGRAM_CHAT_ID = None  # Telegram chat ID for admin notifications
ADMIN_NOTIFICATION_WEBHOOK = None  # Webhook URL for admin notifications

# Rate Limiting
MAX_VERIFICATION_ATTEMPTS_PER_HOUR = 10  # Max verification attempts per user per hour
VERIFICATION_COOLDOWN_SECONDS = 30  # Cooldown between verification attempts

# Development/Testing
ENABLE_TESTNET = False  # Use Shasta testnet instead of mainnet
TESTNET_ENDPOINT = "https://api.shasta.trongrid.io"  # Testnet endpoint
