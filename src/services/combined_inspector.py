# src/services/combined_inspector.py

import asyncio
import pandas as pd
from typing import Dict, Any

from src.services.token_data_fetcher import TokenDataFetcher
from src.services.boosting_classifier import BoostingFraudClassifier
from src.models.gemini_wrapper import GeminiWrapper
from src.config.settings import FRAUD_MODEL_PATH


class CombinedTokenInspector:
    """
    Сначала собирает данные и гонит их через бустинг,
    затем параллельно запрашивает у LLM (Gemini) развернутый анализ.
    """

    def __init__(self):
        self.fetcher    = TokenDataFetcher()
        self.classifier = BoostingFraudClassifier(FRAUD_MODEL_PATH)
        self.gemini     = GeminiWrapper()

    async def inspect(self, symbol: str) -> Dict[str, Any]:
        symbol_u = symbol.upper()

        # 1) Получаем адрес контракта
        platforms = self.fetcher.get_token_platforms(symbol_u)
        address = platforms.get("ethereum") or next(iter(platforms.values()))

        # 2) Собираем фичи и делаем prediction
        features = self.fetcher.get_token_features(address)
        df = pd.DataFrame([features])
        pred_series = self.classifier.predict(df)
        proba_df    = self.classifier.predict_proba(df)

        is_scam = bool(pred_series.iloc[0])
        scam_prob = float(proba_df[f"prob_class_{int(is_scam)}"].iloc[0]) * 100

        # 3) Формируем prompt для LLM, включив туда и результат бустинга
        prompt = (
            f"У токена *{symbol_u}* ({address}) получены следующие признаки:\n"
            + "".join(f"• `{k}` = {v}\n" for k, v in features.items())
            + f"\nРезультат бустинг-классификации: *{'СКАМ' if is_scam else 'НЕ СКАМ'}*, "
            f"вероятность = *{scam_prob:.1f}%*.\n\n"
            "На основе этих данных сделай структурированный отчёт в формате:\n"
            "• **Ключевые факты**\n"
            "• **Риски и red flags**\n"
            "• **Итоговый вердикт и рекомендации**\n\n"
            "Ответ дай на русском, используй эмодзи и Markdown-форматирование."
        )

        # 4) Запрашиваем у Gemini, не блокируя asyncio-loop
        loop = asyncio.get_running_loop()
        llm_report = await loop.run_in_executor(
            None,
            lambda: self.gemini.generate(prompt)
        )

        return {
            "symbol": symbol_u,
            "address": address,
            "features": features,
            "prediction": is_scam,
            "scam_probability": scam_prob,
            "llm_report": llm_report
        }
