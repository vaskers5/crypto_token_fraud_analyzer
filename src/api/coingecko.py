import time
import shelve
import requests
from typing import Dict
from ..config.settings import (
    COINGECKO_API_BASE, REQUEST_TIMEOUT, 
    MAX_RETRIES, RETRY_DELAY, CACHE_FILE, PROXIES
)

class TokenNotFoundError(Exception):
    """Raised when no coin matches the given symbol."""
    pass

class ContractAddressError(Exception):
    """Raised when no contract address is available."""
    pass

class NativeTokenError(Exception):
    """Raised when token is native for blockchain."""
    pass

class CoinGeckoAPI:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = COINGECKO_API_BASE
        self.proxies = PROXIES

    def get_token_contract_address(self, symbol: str) -> Dict[str, str]:
        symbol_lower = symbol.lower()

        with shelve.open(CACHE_FILE) as cache:
            if symbol_lower in cache:
                return cache[symbol_lower]

        coin_id = self._search_token(symbol_lower)
        platforms = self._get_token_details(coin_id)

        with shelve.open(CACHE_FILE) as cache:
            cache[symbol_lower] = platforms

        return platforms

    def _search_token(self, symbol: str) -> str:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}/search",
                    params={"query": symbol},
                    timeout=REQUEST_TIMEOUT,
                    proxies=self.proxies
                )
                response.raise_for_status()
                coins = response.json().get("coins", [])
                matches = [c for c in coins if c.get("symbol", "").lower() == symbol]
                if not matches:
                    raise TokenNotFoundError(f"Токен не найден: {symbol}")
                return matches[0]["id"]
            except requests.RequestException:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)

    def _get_token_details(self, coin_id: str) -> Dict[str, str]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}/coins/{coin_id}",
                    params={
                        "localization": "false",
                        "tickers": "false",
                        "market_data": "false",
                        "community_data": "false",
                        "developer_data": "false",
                        "sparkline": "false",
                    },
                    timeout=REQUEST_TIMEOUT,
                    proxies=self.proxies
                )
                response.raise_for_status()
                data = response.json()
                
                # Проверка на нативный токен
                if 'asset_platform_id' in data and data['asset_platform_id'] is None:
                    chain_name = data.get('platforms', {}).get('', '')
                    if chain_name:
                        raise NativeTokenError(
                            f"Токен '{data.get('symbol', '').upper()}' является нативным для цепочки '{chain_name}'. "
                            f"Вероятность скама низкая."
                        )
                
                platforms = {
                    chain: addr 
                    for chain, addr in data.get("platforms", {}).items() 
                    if addr
                }
                if not platforms:
                    raise ContractAddressError(
                        f"Контрактные адреса не найдены для {coin_id}"
                    )
                return platforms
            except requests.RequestException:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)