# Pipeline using only Etherscan ABI/sourcecode + CoinGecko/CEX data from provided snippet
import os
import json
import requests
import pandas as pd
from itertools import zip_longest
from tqdm import tqdm
import warnings

# Suppress all warnings (including pandas FutureWarnings)
warnings.filterwarnings('ignore')
pd.options.mode.chained_assignment = None  # default='warn'

# === Configuration ===
RAW_DIR = 'raw_data'
OUT_CSV = 'dataset_with_features.csv'
BSCSCAN_API_KEY = os.getenv('BSCSCAN_API_KEY', '47SCZSUG7BZI3FRFY5Z9CQ521K4E5J1DTM')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', 'B9ZDBYU6VIQVDQRXIPD3KI5SCVZ9J61ZJD')
COINGECKO_BASE = 'https://api.coingecko.com/api/v3'

os.makedirs(RAW_DIR, exist_ok=True)

# === Caching wrapper ===
def cache_api_response(key: str, fetch_fn):
    """
    Cache JSON by key under RAW_DIR/{key}.json
    """
    cache_file = os.path.join(RAW_DIR, f"{key}.json")
    if os.path.isfile(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    data = fetch_fn()
    with open(cache_file, 'w') as f:
        json.dump(data, f)
    return data

# === Feature functions ===

def fetch_etherscan_abi(address: str):
    url = (f"https://api.etherscan.io/api?module=contract&action=getabi"
           f"&address={address}&apikey={ETHERSCAN_API_KEY}")
    return requests.get(url, timeout=10).json()

def fetch_etherscan_source(address: str):
    url = (f"https://api.etherscan.io/api?module=contract&action=getsourcecode"
           f"&address={address}&apikey={ETHERSCAN_API_KEY}")
    return requests.get(url, timeout=10).json()

def check_etherscan_contract(address: str) -> dict:
    """Returns verification status and ABI/sourceinfo"""
    abi_data = cache_api_response(f"abi_{address}", lambda: fetch_etherscan_abi(address))
    src_data = cache_api_response(f"source_{address}", lambda: fetch_etherscan_source(address))

    res = {k: False for k in ['is_verified','has_mint','has_blacklist',
                                'has_setfee','has_withdraw','has_unlock',
                                'has_pause','has_changefee','has_owner']}
    res.update({'ContractName': None, 'CompilerVersion': None, 'OptimizationUsed': None})

    if abi_data.get('status') == '1' and abi_data.get('result') != 'Contract source code not verified':
        res['is_verified'] = True
        abi = abi_data['result'].lower()
        for flag in ['mint','blacklist','setfee','withdraw','unlock','pause','changefee','owner']:
            res[f'has_{flag}'] = (flag in abi)
    if src_data.get('status') == '1' and src_data.get('result'):
        info = src_data['result'][0]
        res['ContractName'] = info.get('ContractName')
        res['CompilerVersion'] = info.get('CompilerVersion')
        res['OptimizationUsed'] = info.get('OptimizationUsed')
    return res

def get_dex_cex_data(token_address: str, blockchain: str = 'ethereum') -> dict:
    """Returns CEX listing, 24h volume, price changes, DEX liquidity, dumps, risk score"""
    base_url = COINGECKO_BASE
    blockchain_id = {'ethereum':'ethereum','bsc':'binance-smart-chain'}.get(blockchain.lower(),'ethereum')
    def fetch_token():
        return requests.get(
            f"{base_url}/coins/{blockchain_id}/contract/{token_address}", timeout=10
        ).json()
    token_data = cache_api_response(f"cg_{blockchain_id}_{token_address}", fetch_token)

    # default dict
    fields = ['cex_listings','trading_volume_24h','price_change_24h','price_change_7d',
              'liquidity_usd','large_dumps_detected','risk_score']
    default = dict.fromkeys(fields, None)

    cid = token_data.get('id')
    if not cid:
        return default

    # CEX listing
    cex = False
    try:
        tickers = requests.get(f"{base_url}/coins/{cid}/tickers", timeout=10).json().get('tickers', [])
        cex = any(t.get('market',{}).get('identifier') in ['binance','kraken','coinbase','huobi','okex']
                  for t in tickers)
    except:
        pass
    # Market data
    md = token_data.get('market_data') or {}
    vol24 = md.get('total_volume',{}).get('usd') or 0
    ch24 = md.get('price_change_percentage_24h') or 0
    ch7 = md.get('price_change_percentage_7d') or 0
    liq = md.get('total_liquidity',{}).get('usd') or 0
    # large dumps
    dumps = False
    try:
        chart = requests.get(f"{base_url}/coins/{cid}/market_chart?vs_currency=usd&days=7", timeout=10).json()
        prices = chart.get('prices', [])
        for i in range(1,len(prices)):
            prev, curr = prices[i-1][1], prices[i][1]
            if prev and ((curr - prev)/prev*100) < -25:
                dumps = True
                break
    except:
        pass

    # risk score safe
    def calc_risk(vol, c24, liq_u, dp):
        vol = vol or 0; c24 = c24 or 0; liq_u = liq_u or 0
        s=0
        s += 3 if vol<10000 else 1 if vol<50000 else 0
        s += 2 if abs(c24)>30 else 0
        s += 2 if liq_u<50000 else 0
        s += 3 if dp else 0
        return min(10,s)
    rs = calc_risk(vol24, ch24, liq, dumps)

    return {
        'cex_listings': cex,
        'trading_volume_24h': vol24,
        'price_change_24h': ch24,
        'price_change_7d': ch7,
        'liquidity_usd': liq,
        'large_dumps_detected': dumps,
        'risk_score': rs
    }

if __name__ == '__main__':
    df = pd.read_csv('data.csv')
    df_scam = df[df.label=='scam'].sample(frac=1,random_state=42)
    df_not = df[df.label=='not_scam'].sample(frac=1,random_state=42)
    n=min(len(df_scam),len(df_not)); df_scam,df_not=df_scam.iloc[:n],df_not.iloc[:n]
    inter=[]
    for (_,r1),(_,r2) in zip(df_not.iterrows(),df_scam.iterrows()): inter+=[r1,r2]
    df_sorted=pd.DataFrame(inter).reset_index(drop=True)
    flags=['is_verified','has_mint','has_blacklist','has_setfee','has_withdraw','has_unlock',
           'has_pause','has_changefee','has_owner','ContractName','CompilerVersion','OptimizationUsed']
    dex=['cex_listings','trading_volume_24h','price_change_24h','price_change_7d','liquidity_usd','large_dumps_detected','risk_score']
    for col in flags+dex: df_sorted[col]=pd.NA
    df_sorted.to_csv(OUT_CSV,index=False)
    df_sorted=pd.read_csv(OUT_CSV)
    start=next((i for i,v in df_sorted['risk_score'].items() if pd.isna(v)),len(df_sorted))
    print(f"Resuming at row {start}")
    for idx in tqdm(range(start,len(df_sorted))):
        addr=df_sorted.at[idx,'contract_address']
        ev=check_etherscan_contract(addr)
        for k,v in ev.items(): df_sorted.at[idx,k]=v
        df_sorted.to_csv(OUT_CSV,index=False)
        dv=get_dex_cex_data(addr,'ethereum')
        for k,v in dv.items(): df_sorted.at[idx,k]=v
        df_sorted.to_csv(OUT_CSV,index=False)
    print(f"Done. Saved to {OUT_CSV}")
