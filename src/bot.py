# src/bot.py

import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from src.services.combined_inspector import CombinedTokenInspector
from src.config.settings             import TG_BOT_TOKEN

WAIT_TICKER = 0


class ScamAnalyzerBot:
    def __init__(self):
        self.inspector = CombinedTokenInspector()
        self.logger    = logging.getLogger(__name__)

    def run(self):
        app = (ApplicationBuilder()
               .token(TG_BOT_TOKEN)
               .build())
        conv = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={ WAIT_TICKER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle)
            ]},
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        app.add_handler(conv)
        app.run_polling()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Введите тикер токена (BTC, ETH, BNB и т.д.):")
        return WAIT_TICKER

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        symbol = update.message.text.strip()
        await update.message.reply_text("Собираю данные и анализ…")

        try:
            result = await self.inspector.inspect(symbol)

            # Краткий бустинг-отчёт
            verdict_emoji = "🚩 СКАМ" if result["prediction"] else "✅ НЕ СКАМ"
            summary = (
                f"*{result['symbol']}* ({result['address']})\n"
                f"{verdict_emoji}, вероятность: *{result['scam_probability']:.1f}%*\n\n"
            )
            # Полный LLM-отчёт
            full_report = result["llm_report"]

            # Разбиваем на части по 4096 символов
            message = summary + full_report
            for part in [message[i:i+4096] for i in range(0, len(message), 4096)]:
                await update.message.reply_text(part, parse_mode="Markdown")
        except Exception as e:
            self.logger.exception("Error in handle")
            await update.message.reply_text("❌ Ошибка при анализе, попробуйте позже.")

        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Отменено.")
        return ConversationHandler.END


if __name__ == "__main__":
    ScamAnalyzerBot().run()
