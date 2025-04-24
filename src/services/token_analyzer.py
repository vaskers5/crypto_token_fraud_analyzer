import asyncio
import random
import json
import os
from typing import Dict, List, Tuple
from ..api.coingecko import CoinGeckoAPI
from ..utils.gemini_wrapper import GeminiWrapper

class TokenAnalyzer:
    def __init__(self):
        self.coingecko = CoinGeckoAPI()
        self.gemini = GeminiWrapper()
        
        # Загружаем поддерживаемые цепочки
        chains_path = os.path.join('data', 'supported_chains.json')
        with open(chains_path, encoding='utf-8') as f:
            supported_chains = json.load(f)
            
        self.native_tokens = {
            entry['native_symbol'].lower(): entry['id']
            for entry in supported_chains
            if entry.get('native_symbol')
        }

    async def get_token_info(self, symbol: str) -> Dict:
        """Get token information."""
        symbol_lower = symbol.lower()
        token_info = {"symbol": symbol}
        
        # Проверяем, является ли токен нативным
        if symbol_lower in self.native_tokens:
            token_info.update({
                "is_native": True,
                "chain_id": self.native_tokens[symbol_lower],
                "type": "native"
            })
            return token_info

        # Если не нативный, получаем информацию через CoinGecko
        try:
            platforms = self.coingecko.get_token_contract_address(symbol)
            token_info.update({
                "is_native": False,
                "platforms": platforms,
                "type": "token"
            })
        except Exception as e:
            token_info.update({
                "is_native": False,
                "error": str(e),
                "type": "unknown"
            })
        
        return token_info

    async def analyze_token(self, token_info: Dict) -> Tuple[List[str], str]:
        """Analyze token."""
        symbol = token_info["symbol"]
        token_type = token_info.get("type", "unknown")
        
        # Базовый промпт в зависимости от типа токена
        base_context = self._get_base_context(token_info)
        
        # Анализ через Gemini с учетом контекста
        queries = [
            f"{base_context}\n{self._get_analysis_prompt(symbol)}"
        ]
        
        # Параллельный анализ
        gemini_results = await asyncio.gather(
            *[self._analyze_with_search(query) for query in queries]
        )
        
        # Финальный анализ
        final_analysis = await self._get_final_analysis(
            symbol, token_type, gemini_results
        )
        
        return gemini_results, final_analysis

    def _get_base_context(self, token_info: Dict) -> str:
        """Формируем базовый контекст о токене."""
        symbol = token_info["symbol"]
        context = []

        if token_info.get("is_native"):
            context.append(
                f"Токен {symbol} является нативным токеном для блокчейна "
                f"{token_info['chain_id']}. Нативные токены обычно более "
                f"надежны, так как являются основой блокчейна."
            )
        elif "platforms" in token_info:
            chains = ", ".join(token_info["platforms"].keys())
            context.append(
                f"Токен {symbol} представлен в следующих сетях: {chains}"
            )
        
        return "\n".join(context)

    def _get_analysis_prompt(self, symbol: str) -> str:
        return (
            f"Проанализируй токен {symbol} и предоставь следующую информацию:\n"
            f"1. Общий анализ токена и его использования\n"
            f"2. История проекта и команды\n"
            f"3. Технические особенности и безопасность\n"
            f"4. Потенциальные риски скама и red flags\n"
            f"5. Рыночные показатели и ликвидность"
        )

    async def _get_final_analysis(
        self, 
        symbol: str, 
        token_type: str,
        analysis_results: List[str]
    ) -> str:
        # Добавляем базовую оценку риска для нативных токенов
        risk_context = ""
        if token_type == "native":
            risk_context = (
                f"ВАЖНО: {symbol} является нативным токеном блокчейна. "
                f"Нативные токены несут минимальные риски скама, так как:\n"
                f"1. Являются основой блокчейна\n"
                f"2. Имеют проверенную историю\n"
                f"3. Обладают высокой ликвидностью\n"
                f"4. Поддерживаются основными биржами\n"
                f"Этот факт следует учитывать при итоговой оценке рисков.\n\n"
            )

        prompt = (
            f"На основе анализа токена {symbol} и следующих данных:\n\n"
            f"{risk_context}"
            f"Анализ:\n{analysis_results}\n\n"
            f"Составь структурированный отчет, именно по токену {symbol}, не затрагивая другие, используя следующее форматирование:\n"
            f"• Для обычных пунктов используй символ •\n"
            f"• Для жирного текста используй *текст*\n\n"
            f"💡 *ОСНОВНЫЕ ВЫВОДЫ:*\n\n"
            f"*Ключевые факты о токене:*\n"
            f"• Информация о токене\n"
            f"• Назначение токена\n"
            f"• Особенности реализации\n\n"
            f"*Важные особенности:*\n"
            f"• Особенность 1\n"
            f"• Особенность m\n\n"
            f"⚠️ *УРОВЕНЬ РИСКА:*\n"
            f"Подробная оценка рисков скама\n\n"
            f"🎯 *ВЕРДИКТ:*\n"
            f"Четкое заключение скам/не скам\n\n"
            f"👉 *РЕКОМЕНДАЦИИ:*\n"
            f"• Рекомендация 1\n"
            f"• Рекомендация n\n\n"
            f"Рекомендации должны быть инвестировать или нет исходя из скам/не скам.\n"
            f"Используй эмодзи для лучшей читаемости. "
            f"Ответ должен быть на русском языке. "
            f"Не используй другие символы форматирования кроме • и *."
        )
        return self.gemini.generate(prompt)

    async def _analyze_with_search(self, query: str) -> str:
        """Analyze with Gemini using search."""
        return self.gemini.generate(query)