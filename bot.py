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
import asyncio
from gemini_wrapper import GeminiWrapper
from typing import Dict, List, Tuple

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TG_BOT_TOKEN')

# Настройка прокси для запросов
proxies = {}
if os.getenv('HTTP_PROXY'):
    proxies['http'] = os.getenv('HTTP_PROXY')
if os.getenv('HTTPS_PROXY'):
    proxies['https'] = os.getenv('HTTPS_PROXY')

# Загрузка поддерживаемых цепочек
SUPPORTED_CHAINS = json.loads(open('data/supported_chains.json', encoding='utf-8').read())
NATIVE_SYMBOL_TO_CHAIN = {
    entry['native_symbol'].lower(): entry['id']
    for entry in SUPPORTED_CHAINS
    if entry.get('native_symbol')
}
CHAIN_IDS = [entry['id'] for entry in SUPPORTED_CHAINS]

WAIT_TICKER, WAIT_CHAIN = range(2)

# Инициализация Gemini
gemini = GeminiWrapper(model="gemini-2.0-flash-lite")

async def analyze_with_gemini_search(query: str) -> str:
    """Анализ информации через Gemini с использованием Google Search"""
    try:
        return gemini.generate(query)
    except Exception as e:
        logging.error(f"Ошибка при запросе к Gemini с поиском: {e}")
        return "Не удалось получить анализ"

async def analyze_with_gemini(query: str) -> str:
    """Стандартный анализ через Gemini без поиска"""
    try:
        return gemini.generate(query)
    except Exception as e:
        logging.error(f"Ошибка при запросе к Gemini: {e}")
        return "Не удалось получить анализ"

async def get_token_info(symbol: str) -> Dict:
    """Получение информации о токене из CoinGecko"""
    try:
        platforms = get_token_contract_address_via_search(symbol)
        return {
            "platforms": platforms,
            "symbol": symbol,
        }
    except Exception as e:
        logging.error(f"Ошибка при получении информации о токене: {e}")
        raise

async def analyze_token(token_info: Dict) -> Tuple[List[str], str]:
    """Комплексный анализ токена"""
    symbol = token_info["symbol"]
    
    # Заглушка для бустинга (пока просто рандом)
    boosting_result = random.choice(["Скам", "Не скам"])
    
    # Параллельный анализ через Gemini с поиском
    queries = [
        f"""Ты - эксперт по криптобезопасности. Проанализируй токен {symbol} cryptocurrency на scam. Analyze recent news and information. What are the red flags or suspicious activities related to {symbol} token? Analyze the legitimacy and trustworthiness of {symbol} cryptocurrency project. Выдай ответ в качестве анализа с указанием источников. Не пиши что ты AI и не можешь дать идеальный ответ, просто дай аналитику по новостям с источниками.""",
    ]
    
    gemini_results = await asyncio.gather(
        *[analyze_with_gemini_search(query) for query in queries]
    )
    print(gemini_results)
    # Финальный анализ всех результатов (без поиска)
    summary_prompt = (
        f"На основе представленных данных составь ответ для пользователя о том является ли токен {symbol} "
        f"скамом или нет:\n\n"
        f"1. Результат алгоритмического анализа: {boosting_result}\n"
        f"2. Результат анализа новостных данных: {gemini_results}"
        f"Дай ответ в следующем формате:\n\n"
        f"💡 ОСНОВНЫЕ ВЫВОДЫ:\n"
        f"Пункт m\n"
        f"⚠️ УРОВЕНЬ РИСКА:\n"
        f"(Укажи уровень риска и обоснуй опираясь на источники)\n\n"
        f"🎯 ВЕРДИКТ:\n"
        f"(Четкое заключение)\n\n"
        f"👉 РЕКОМЕНДАЦИИ:\n"
        f"k) Рекомендация k\n"
        f"Используй эмодзи для лучшей читаемости. Ответ должен быть на русском языке, "
        f"четким и структурированным. Не используй специальные символы, "
        f"такие как: _ * [ ] ( ) ~ ` > # + = | . !"
    )
    
    final_analysis = await analyze_with_gemini(summary_prompt)
    #print(final_analysis)
    return gemini_results, final_analysis

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите тикер токена для проверки (например, BTC, ETH, BNB):"
    )
    return WAIT_TICKER

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    symbol = update.message.text.strip().upper()
    context.user_data['symbol'] = symbol

    await update.message.reply_text("Анализирую токен, это может занять некоторое время...")

    try:
        # Получение информации о токене
        token_info = await get_token_info(symbol)
        
        # Комплексный анализ
        gemini_results, final_analysis = await analyze_token(token_info)
        
        # Экранируем все специальные символы для MarkdownV2
        def escape_markdown(text: str) -> str:
            """Экранирование специальных символов для MarkdownV2"""
            chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        # Форматируем сообщение
        message = (
            f"🔍 *Анализ токена {escape_markdown(symbol)}*\n\n"
            f"{escape_markdown(final_analysis)}"
        )
        
        # Разбиваем длинное сообщение
        if len(message) > 4096:
            parts = [message[i:i+4096] for i in range(0, len(message), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(message, parse_mode='MarkdownV2')
        
        return ConversationHandler.END

    except TokenNotFoundError as e:
        await update.message.reply_text(escape_markdown(str(e)), parse_mode='MarkdownV2')
        return ConversationHandler.END
    except Exception as e:
        logging.exception("Unexpected error during analysis")
        await update.message.reply_text(
            escape_markdown("Произошла ошибка при анализе. Пожалуйста, попробуйте позже."),
            parse_mode='MarkdownV2'
        )
        return ConversationHandler.END

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
