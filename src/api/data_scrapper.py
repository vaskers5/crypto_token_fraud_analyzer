import os
import requests
from dotenv import load_dotenv

class DataScrapper:
    def __init__(self):
        load_dotenv()  # reads .env into environment
        self.etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
        self.coingecko_base = os.getenv('COINGECKO_BASE').rstrip('/')

    def fetch_etherscan_abi(self, address: str) -> dict:
        url = (
            f"https://api.etherscan.io/api"
            f"?module=contract&action=getabi"
            f"&address={address}"
            f"&apikey={self.etherscan_api_key}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_etherscan_source(self, address: str) -> dict:
        url = (
            f"https://api.etherscan.io/api"
            f"?module=contract&action=getsourcecode"
            f"&address={address}"
            f"&apikey={self.etherscan_api_key}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def check_etherscan_contract(self, address: str) -> dict:
        abi_data = self.fetch_etherscan_abi(address)
        src_data = self.fetch_etherscan_source(address)

        res = {
            'is_verified': False,
            'has_mint': False,
            'has_blacklist': False,
            'has_setfee': False,
            'has_withdraw': False,
            'has_unlock': False,
            'has_pause': False,
            'has_changefee': False,
            'has_owner': False,
            'OptimizationUsed': ''
        }

        if abi_data.get('status') == '1' and abi_data.get('result') != 'Contract source code not verified':
            res['is_verified'] = True
            abi_text = abi_data['result'].lower()
            for flag in ['mint', 'blacklist', 'setfee', 'withdraw', 'unlock', 'pause', 'changefee', 'owner']:
                res[f'has_{flag}'] = (flag in abi_text)

        if src_data.get('status') == '1' and src_data.get('result'):
            info = src_data['result'][0]
            res['OptimizationUsed'] = info.get('OptimizationUsed', '')

        return res

    def get_dex_cex_data(self, token_address: str) -> dict:
        result = {
            'cex_listings': False,
            'trading_volume_24h': 0.0,
            'price_change_24h': 0.0,
            'price_change_7d': 0.0,
            'large_dumps_detected': False
        }

        # 1) fetch main token data
        try:
            token_data = requests.get(
                f"{self.coingecko_base}/coins/ethereum/contract/{token_address}",
                timeout=10
            ).json()
        except requests.RequestException:
            return result

        cid = token_data.get('id')
        if not cid:
            return result

        # 2) check centralized exchange listings
        try:
            tickers = requests.get(
                f"{self.coingecko_base}/coins/{cid}/tickers",
                timeout=10
            ).json().get('tickers', [])
            result['cex_listings'] = any(
                t.get('market', {}).get('identifier') in
                {'binance','kraken','coinbase','huobi','okex'}
                for t in tickers
            )
        except requests.RequestException:
            pass

        # 3) market data
        md = token_data.get('market_data', {}) or {}
        result['trading_volume_24h'] = float(md.get('total_volume', {}).get('usd', 0.0)) or 0.0
        result['price_change_24h'] = float(md.get('price_change_percentage_24h', 0.0)) or 0.0
        result['price_change_7d'] = float(md.get('price_change_percentage_7d', 0.0)) or 0.0

        # 4) detect large dumps (>25% drop in any 24h window over past 7 days)
        try:
            chart = requests.get(
                f"{self.coingecko_base}/coins/{cid}/market_chart",
                params={'vs_currency': 'usd', 'days': '7'},
                timeout=10
            ).json()
            prices = chart.get('prices', [])
            for prev_pt, curr_pt in zip(prices, prices[1:]):
                prev, curr = prev_pt[1], curr_pt[1]
                if prev and ((curr - prev) / prev * 100) < -25:
                    result['large_dumps_detected'] = True
                    break
        except requests.RequestException:
            pass

        return result

    def get_token_info(self, contract_address: str) -> dict:
        contract_info = self.check_etherscan_contract(contract_address)
        market_data   = self.get_dex_cex_data(contract_address)

        # merge preserving desired order
        return {
            **{k: contract_info[k] for k in [
                'is_verified','has_mint','has_blacklist','has_setfee','has_withdraw',
                'has_unlock','has_pause','has_changefee','has_owner','OptimizationUsed'
            ]},
            **market_data
        }


if __name__ == '__main__':
    scraper = DataScrapper()
    info = scraper.get_token_info('0x0a07525aa264a3e14cdbdd839b1eda02a34e2778')
    print(info)
