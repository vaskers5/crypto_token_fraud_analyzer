# services/token_data_fetcher.py

import time
import shelve
import requests
from typing import Dict, Any

from src.config.settings import (
    COINGECKO_API_BASE, ETHERSCAN_API_KEY, PROXIES,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, CACHE_FILE
)


class TokenDataFetcher:
    """
    Unified scraper: берёт адреса токена у CoinGecko,
    а затем запрашивает данные по контракту (ABI, верификация)
    и рыночные метрики (объём, изменение цены, CEX-листинги, дамп-флаги).
    """

    def __init__(self):
        self.session = requests.Session()
        # Прокси, если указаны
        if PROXIES["ENABLED"]:
            self.session.proxies.update({k: v for k, v in PROXIES.items() if v})
        self.gecko_base = COINGECKO_API_BASE
        self.eth_key    = ETHERSCAN_API_KEY
        self.cache_file = CACHE_FILE

    def get_token_platforms(self, symbol: str) -> Dict[str, str]:
        """
        По тикеру токена возвращает {chain: contract_address},
        с локальным кэшем через shelve.
        """
        key = symbol.lower()
        with shelve.open(self.cache_file) as cache:
            if key in cache:
                return cache[key]

        coin_id = self._search_coin_id(key)
        platforms = self._fetch_coin_platforms(coin_id)

        with shelve.open(self.cache_file) as cache:
            cache[key] = platforms

        return platforms

    def _search_coin_id(self, symbol_key: str) -> str:
        url = f"{self.gecko_base}/search"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    url,
                    params={"query": symbol_key},
                    timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                coins = resp.json().get("coins", [])
                matches = [c for c in coins if c.get("symbol", "").lower() == symbol_key]
                if not matches:
                    raise ValueError(f"Token not found: {symbol_key}")
                return matches[0]["id"]
            except requests.RequestException:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)

    def _fetch_coin_platforms(self, coin_id: str) -> Dict[str, str]:
        url = f"{self.gecko_base}/coins/{coin_id}"
        params = {
            "localization": False, "tickers": False, "market_data": False,
            "community_data": False, "developer_data": False, "sparkline": False
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                platforms = {
                    chain: addr
                    for chain, addr in data.get("platforms", {}).items()
                    if addr
                }
                if not platforms:
                    raise ValueError(f"No contract addresses for {coin_id}")
                return platforms
            except requests.RequestException:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(RETRY_DELAY)

    def _fetch_contract_info(self, address: str) -> Dict[str, Any]:
        """
        Анализ контракта через Etherscan: ABI, верификация, функции.
        """
        base = "https://api.etherscan.io/api"
        result = {
            "is_verified": False,
            "has_mint": False,
            "has_blacklist": False,
            "has_setfee": False,
            "has_withdraw": False,
            "has_unlock": False,
            "has_pause": False,
            "has_changefee": False,
            "has_owner": False,
            "optimization_used": ""
        }

        # 1) ABI
        abi_params = {
            "module": "contract",
            "action": "getabi",
            "apikey": self.eth_key,
            "address": address
        }
        resp = self.session.get(base, params=abi_params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        abi_data = resp.json()
        if abi_data.get("status") == "1" and "Contract source code not verified" not in abi_data.get("result", ""):
            result["is_verified"] = True
            text = abi_data["result"].lower()
            for flag in ["mint", "blacklist", "setfee", "withdraw", "unlock", "pause", "changefee", "owner"]:
                result[f"has_{flag}"] = flag in text

        # 2) Source
        src_params = {
            "module": "contract",
            "action": "getsourcecode",
            "apikey": self.eth_key,
            "address": address
        }
        resp = self.session.get(base, params=src_params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        src = resp.json().get("result", [])
        if src and isinstance(src, list):
            result["optimization_used"] = src[0].get("OptimizationUsed", "")

        return result

    def _fetch_market_info(self, address: str) -> Dict[str, Any]:
        """
        Данные с Coingecko: объём, изменение цены, CEX-листинги, детект дэмпов.
        """
        info = {
            "cex_listings": False,
            "trading_volume_24h": 0.0,
            "price_change_24h": 0.0,
            "price_change_7d": 0.0,
            "large_dumps_detected": False
        }
        # 1) Основные данные по контракту
        try:
            resp = self.session.get(
                f"{self.gecko_base}/coins/ethereum/contract/{address}",
                timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            token = resp.json()
        except requests.RequestException:
            return info

        cid = token.get("id")
        if not cid:
            return info

        # 2) CEX-listings
        try:
            tickers = self.session.get(
                f"{self.gecko_base}/coins/{cid}/tickers",
                timeout=REQUEST_TIMEOUT
            ).json().get("tickers", [])
            info["cex_listings"] = any(
                t.get("market", {}).get("identifier") in
                {"binance", "kraken", "coinbase", "huobi", "okex"}
                for t in tickers
            )
        except requests.RequestException:
            pass

        # 3) market_data
        md = token.get("market_data", {}) or {}
        info["trading_volume_24h"] = float(md.get("total_volume", {}).get("usd", 0.0) or 0.0)
        info["price_change_24h"]    = float(md.get("price_change_percentage_24h", 0.0) or 0.0)
        info["price_change_7d"]     = float(md.get("price_change_percentage_7d", 0.0) or 0.0)

        # 4) detect large dumps
        try:
            chart = self.session.get(
                f"{self.gecko_base}/coins/{cid}/market_chart",
                params={"vs_currency": "usd", "days": "7"},
                timeout=REQUEST_TIMEOUT
            ).json()
            prices = chart.get("prices", [])
            for prev, curr in zip(prices, prices[1:]):
                if prev[1] and ((curr[1] - prev[1]) / prev[1] * 100) < -25:
                    info["large_dumps_detected"] = True
                    break
        except requests.RequestException:
            pass

        return info

    def get_token_features(self, address: str) -> Dict[str, Any]:
        """
        Собирает все фичи для модели по одному адресу контракта.
        """
        contract = self._fetch_contract_info(address)
        market   = self._fetch_market_info(address)
        return {**contract, **market}
