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
from .config.settings import TG_BOT_TOKEN
from .services.token_analyzer import TokenAnalyzer
from .api.coingecko import TokenNotFoundError, NativeTokenError  # добавляем импорт

WAIT_TICKER = 0

class ScamAnalyzerBot:
    def __init__(self):
        self.token_analyzer = TokenAnalyzer()
        self.logger = logging.getLogger(__name__)

    def run(self):
        """Запуск бота."""
        app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
        
        conv = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                WAIT_TICKER: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, 
                        self.handle_ticker
                    )
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        
        app.add_handler(conv)
        app.run_polling()

    @staticmethod
    def escape_markdown(text: str) -> str:
        """Экранирование специальных символов для MarkdownV2."""
        # Сохраняем форматирование для жирного текста
        import re
        
        def escape_special_chars(text: str) -> str:
            chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', 
                    '-', '=', '|', '{', '}', '.', '!']
            for char in chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        # Находим все части текста между звездочками
        parts = []
        last_end = 0
        
        for match in re.finditer(r'\*(.*?)\*', text):
            start, end = match.span()
            
            # Добавляем текст до звездочек
            if start > last_end:
                parts.append(escape_special_chars(text[last_end:start]))
            
            # Добавляем жирный текст
            bold_content = escape_special_chars(match.group(1))
            parts.append(f'*{bold_content}*')
            
            last_end = end
        
        # Добавляем оставшийся текст
        if last_end < len(text):
            parts.append(escape_special_chars(text[last_end:]))
        
        return ''.join(parts)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            "Введите тикер токена для проверки (например, BTC, ETH, BNB):"
        )
        return WAIT_TICKER

    async def handle_ticker(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        symbol = update.message.text.strip().upper()
        await update.message.reply_text(
            "Анализирую токен, это может занять некоторое время..."
        )

        try:
            token_info = await self.token_analyzer.get_token_info(symbol)
            gemini_results, final_analysis = await self.token_analyzer.analyze_token(
                token_info
            )
            
            message = (
                f"🔍 *Анализ токена {self.escape_markdown(symbol)}*\n\n"
                f"{self.escape_markdown(final_analysis)}"
            )
            
            if len(message) > 4096:
                parts = [message[i:i+4096] for i in range(0, len(message), 4096)]
                for part in parts:
                    await update.message.reply_text(
                        part, 
                        parse_mode='MarkdownV2'
                    )
            else:
                await update.message.reply_text(
                    message, 
                    parse_mode='MarkdownV2'
                )
            
            return ConversationHandler.END

        except NativeTokenError as e:  # добавляем обработку новой ошибки
            await update.message.reply_text(
                self.escape_markdown(str(e)),
                parse_mode='MarkdownV2'
            )
            return ConversationHandler.END
        except TokenNotFoundError as e:
            await update.message.reply_text(
                self.escape_markdown(str(e)), 
                parse_mode='MarkdownV2'
            )
            return ConversationHandler.END
        except Exception as e:
            self.logger.exception("Unexpected error during analysis")
            await update.message.reply_text(
                self.escape_markdown(
                    "Произошла ошибка при анализе. Пожалуйста, попробуйте позже."
                ),
                parse_mode='MarkdownV2'
            )
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Проверка отменена.")
        return ConversationHandler.END