# src/bot.py

import logging
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import BadRequest

from src.services.combined_inspector import CombinedTokenInspector
from src.config.settings import TG_BOT_TOKEN

# Состояния разговора
WAIT_TICKER, WAIT_CHAIN = range(2)

# Клавиатура
DEFAULT_KEYBOARD = ReplyKeyboardMarkup(
    [["Проверить токен", "/help"]], resize_keyboard=True
)

class ScamAnalyzerBot:
    def __init__(self):
        self.inspector = CombinedTokenInspector()
        self.logger = logging.getLogger(__name__)

    def run(self):
        app = ApplicationBuilder().token(TG_BOT_TOKEN).build()

        conv = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start),
                MessageHandler(filters.Regex(r"^Проверить токен$"), self.start)
            ],
            states={
                WAIT_TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_ticker)],
                WAIT_CHAIN: [CallbackQueryHandler(self.handle_chain_selection)],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel),
                MessageHandler(filters.Regex(r"^Отмена$"), self.cancel)
            ],
            allow_reentry=True,
        )

        app.add_handler(conv)
        app.add_handler(CommandHandler("help", self.help))

        app.run_polling()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        # При старте показываем инструкцию
        await update.message.reply_text(("""👋 Привет! Я — бот для проверки токенов на скам.\n Нажми "Проверить токен" или введи /start, чтобы начать.\n Для справки в любой момент введи /help."""),
            reply_markup=DEFAULT_KEYBOARD
        )
        # Запрашиваем тикер
        await update.message.reply_text(
            "Введи тикер (напр. BTC, ETH):", reply_markup=DEFAULT_KEYBOARD
        )
        return WAIT_TICKER

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "📝 Как пользоваться:\n"
            "1. Нажми 'Проверить токен' или /start.\n"
            "2. Введи тикер токена.\n"
            "3. Если нужно, выбери сеть из списка.\n"
            "4. Получи отчёт.\n"
            "Для отмены введи /cancel.",
            reply_markup=DEFAULT_KEYBOARD
        )

    async def handle_ticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        symbol = update.message.text.strip().upper()
        context.user_data['symbol'] = symbol

        await update.message.reply_text("🔍 Сбор данных и анализ...")
        # Сразу анализируем нативные токены
        if symbol.lower() in self.inspector.native_tokens:
            result = await self.inspector.inspect(symbol)
            await self._send_report(update, result)
            return ConversationHandler.END

        # Получаем платформы
        try:
            platforms = await asyncio.get_running_loop().run_in_executor(
                None,
                self.inspector.fetcher.get_token_platforms,
                symbol
            )
        except Exception as e:
            self.logger.error(f"Error fetching platforms: {e}")
            result = await self.inspector.inspect(symbol)
            await self._send_report(update, result)
            return ConversationHandler.END

        if not platforms:
            result = await self.inspector.inspect(symbol)
            await self._send_report(update, result)
            return ConversationHandler.END

        # Если одна платформа — анализ
        if len(platforms) == 1:
            chain = next(iter(platforms))
            result = await self.inspector.inspect(symbol, chain=chain)
            await self._send_report(update, result)
            return ConversationHandler.END

        # Несколько платформ — предлагаем выбрать
        buttons = [InlineKeyboardButton(chain, callback_data=chain) for chain in platforms]
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        await update.message.reply_text(
            "Выбери сеть для анализа:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['platforms'] = platforms
        return WAIT_CHAIN

    async def handle_chain_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        chain = query.data
        symbol = context.user_data.get('symbol')

        await query.edit_message_text(f"🔄 Анализ {symbol} в сети {chain}...")
        result = await self.inspector.inspect(symbol, chain=chain)
        await query.message.reply_text("✅ Отчёт готов:")
        await self._send_report(update, result)
        return ConversationHandler.END

    async def _send_report(self, update: Update, result: dict) -> None:
        # Заголовок отчёта
        if 'chain_id' in result:
            header = f"*{result['symbol']}* (chain: {result['chain_id']})\n\n"
        elif 'address' in result:
            header = f"*{result['symbol']}* (`{result['address']}`)\n\n"
        else:
            header = f"*{result['symbol']}*\n\n"

        text = header + result.get('llm_report', '')
        # Разбиваем на части по 4096 символов
        for chunk in [text[i:i+4096] for i in range(0, len(text), 4096)]:
            try:
                await update.effective_chat.send_message(chunk, parse_mode='Markdown')
            except BadRequest:
                await update.effective_chat.send_message(chunk)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("❌ Операция отменена.", reply_markup=DEFAULT_KEYBOARD)
        return ConversationHandler.END


if __name__ == '__main__':
    ScamAnalyzerBot().run()
