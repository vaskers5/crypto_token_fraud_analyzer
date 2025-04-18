### search.py
import requests
from typing import Dict
import time
import shelve

# Константы
REQUEST_TIMEOUT = 10
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
MAX_RETRIES = 3
RETRY_DELAY = 5  # секунд
CACHE_FILE = "token_cache.db"

class TokenNotFoundError(Exception):
    """Raised when no coin matches the given symbol."""
    pass

class ContractAddressError(Exception):
    """Raised when no contract address is available for the given symbol and chain."""
    pass


def get_token_contract_address_via_search(symbol: str) -> Dict[str, str]:
    symbol_lower = symbol.lower()

    # Проверка локального кеша
    with shelve.open(CACHE_FILE) as cache:
        if symbol_lower in cache:
            return cache[symbol_lower]

    session = requests.Session()

    # Шаг 1: поиск ID токена с ретраями
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                f"{COINGECKO_API_BASE}/search",
                params={"query": symbol_lower},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)

    coins = response.json().get("coins", [])
    matches = [c for c in coins if c.get("symbol", "").lower() == symbol_lower]
    if not matches:
        raise TokenNotFoundError(f"No token found for symbol: {symbol}")

    coin_id = matches[0]["id"]

    # Шаг 2: получение деталей токена с ретраями
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            detail_resp = session.get(
                f"{COINGECKO_API_BASE}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
                timeout=REQUEST_TIMEOUT
            )
            detail_resp.raise_for_status()
            break
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)

    data = detail_resp.json()
    platforms = {chain: addr for chain, addr in data.get("platforms", {}).items() if addr}
    if not platforms:
        raise ContractAddressError(f"No contract addresses available for {symbol}")

    # Сохранение в локальный кеш
    with shelve.open(CACHE_FILE) as cache:
        cache[symbol_lower] = platforms

    return platforms


import os
import logging
import json
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from difflib import get_close_matches

# from search import (
#     get_token_contract_address_via_search,
#     TokenNotFoundError,
#     ContractAddressError,
#     RETRY_DELAY,
# )

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# Загрузка поддерживаемых цепочек
SUPPORTED_CHAINS = json.loads(open('supported_chains.json', encoding='utf-8').read())
NATIVE_SYMBOL_TO_CHAIN = {
    entry['native_symbol'].lower(): entry['id']
    for entry in SUPPORTED_CHAINS
    if entry.get('native_symbol')
}
CHAIN_IDS = [entry['id'] for entry in SUPPORTED_CHAINS]

WAIT_TICKER, WAIT_CHAIN = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите тикер токена для проверки (например, BTC, ETH, BNB):"
    )
    return WAIT_TICKER

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    symbol = update.message.text.strip().upper()
    context.user_data['symbol'] = symbol

    if symbol.lower() in NATIVE_SYMBOL_TO_CHAIN:
        chain_id = NATIVE_SYMBOL_TO_CHAIN[symbol.lower()]
        await update.message.reply_text(
            f"Токен '{symbol}' является нативным для цепочки '{chain_id}'. Вероятность скама низкая."
        )
        return ConversationHandler.END

    try:
        platforms = get_token_contract_address_via_search(symbol)
    except TokenNotFoundError as e:
        await update.message.reply_text(str(e))
        return ConversationHandler.END
    except ContractAddressError as e:
        await update.message.reply_text(str(e))
        return ConversationHandler.END
    except Exception:
        logging.exception("Unexpected error during token search")
        await update.message.reply_text(
            f"Произошла ошибка при запросе к CoinGecko. Пожалуйста, подождите {RETRY_DELAY} секунд и попробуйте снова."
        )
        return ConversationHandler.END

    context.user_data['platforms'] = platforms
    buttons = [[InlineKeyboardButton(cid, callback_data=cid)] for cid in platforms]
    await update.message.reply_text(
        f"Выберите сеть для {symbol}:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return WAIT_CHAIN

async def chain_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data
    platforms = context.user_data.get('platforms', {})
    if choice not in platforms:
        suggestions = get_close_matches(choice, CHAIN_IDS, n=3, cutoff=0.6)
        msg = (
            f"Сеть '{choice}' не найдена."
            + (f" Возможно, вы имели в виду: {', '.join(suggestions)}." if suggestions else "")
        )
        await query.edit_message_text(msg)
        return ConversationHandler.END

    address = platforms[choice]
    result = random.choice(["Скам", "Не скам"])
    await query.edit_message_text(
        f"{context.user_data['symbol']} на {choice}: {address}\nРезультат: {result}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Проверка отменена.")
    return ConversationHandler.END

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN not set in environment variables")

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAIT_TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker)],
            WAIT_CHAIN: [CallbackQueryHandler(chain_choice)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv)
    app.run_polling()
