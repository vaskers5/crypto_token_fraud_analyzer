import asyncio
import random
from typing import Dict, List, Tuple
from ..api.coingecko import CoinGeckoAPI
from ..utils.gemini_wrapper import GeminiWrapper

class TokenAnalyzer:
    def __init__(self):
        self.coingecko = CoinGeckoAPI()
        self.gemini = GeminiWrapper()

    async def get_token_info(self, symbol: str) -> Dict:
        platforms = self.coingecko.get_token_contract_address(symbol)
        return {
            "platforms": platforms,
            "symbol": symbol,
        }

    async def analyze_token(self, token_info: Dict) -> Tuple[List[str], str]:
        symbol = token_info["symbol"]
        
        # Заглушка для бустинга
        boosting_result = random.choice(["Скам", "Не скам"])
        
        # Запросы для анализа
        queries = [
            self._get_analysis_prompt(symbol)
        ]
        
        # Параллельный анализ
        gemini_results = await asyncio.gather(
            *[self._analyze_with_search(query) for query in queries]
        )
        
        # Финальный анализ
        final_analysis = await self._get_final_analysis(
            symbol, boosting_result, gemini_results
        )
        
        return gemini_results, final_analysis

    async def _analyze_with_search(self, query: str) -> str:
        return self.gemini.generate(query)

    def _get_analysis_prompt(self, symbol: str) -> str:
        return (
            f"Ты - эксперт по криптобезопасности. "
            f"Проанализируй токен {symbol} и дай заключение "
            f"на основе последних новостей и информации. "
            f"Анализируй: подозрительную активность, красные флаги, "
            f"легитимность проекта. Дай структурированный анализ:"
            f"\n1) Основные факты"
            f"\n2) Риски"
            f"\n3) Преимущества"
            f"\n4) Заключение"
        )

    async def _get_final_analysis(
        self, 
        symbol: str, 
        boosting_result: str, 
        analysis_results: List[str]
    ) -> str:
        prompt = (
            f"На основе данных составь анализ токена {symbol}:\n\n"
            f"1. Алгоритмический анализ: {boosting_result}\n"
            f"2. Анализ данных: {analysis_results}\n\n"
            f"Структура ответа (не используй символы *, _, `, #, -, [, ], (, ) для форматирования):\n\n"
            f"💡 ОСНОВНЫЕ ВЫВОДЫ:\n"
            f"• Вывод 1\n"
            f"• Вывод 2\n\n"
            f"⚠️ УРОВЕНЬ РИСКА:\n"
            f"Укажи уровень риска и обоснование\n\n"
            f"🎯 ВЕРДИКТ:\n"
            f"Четкое заключение\n\n"
            f"👉 РЕКОМЕНДАЦИИ:\n"
            f"1️⃣ Рекомендация 1\n"
            f"2️⃣ Рекомендация 2\n\n"
            f"Используй эмодзи вместо символов форматирования. "
            f"Для списков используй символы • или эмодзи с цифрами (1️⃣, 2️⃣, 3️⃣). "
            f"Ответ на русском языке."
        )
        return self.gemini.generate(prompt)