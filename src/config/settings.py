# config/settings.py

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
SUPPORTED_CHAINS_PATH = os.getenv("SUPPORTED_CHAINS_PATH", "data/supported_chains.json")
# API Keys
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
BSCSCAN_API_KEY    = os.getenv("BSCSCAN_API_KEY")
ETHERSCAN_API_KEY  = os.getenv("ETHERSCAN_API_KEY")
FRAUD_MODEL_PATH   = os.getenv("FRAUD_MODEL_PATH", "models/fraud_model.pkl")

# Proxies
PROXIES = {
    "ENABLED": os.getenv("PROXY_ENABLED", "false").lower() == "true",
    "http":  os.getenv("PROXY_HTTP"),
    "https": os.getenv("PROXY_HTTPS"),
}
# Endpoints
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
GEMINI_API_BASE    = "https://generativelanguage.googleapis.com/v1beta"

# Caching & retries
CACHE_FILE    = "token_cache.db"
REQUEST_TIMEOUT = 10
MAX_RETRIES     = 3
RETRY_DELAY     = 5
