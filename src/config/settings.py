import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')

# API Keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
BSCSCAN_API_KEY = os.getenv('BSCSCAN_API_KEY')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

# Proxy Configuration
PROXIES = {
    'http': os.getenv('HTTP_PROXY'),
    'https': os.getenv('HTTPS_PROXY')
}

# API Endpoints
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Cache Configuration
CACHE_FILE = "token_cache.db"

# Request Configuration
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 5