# src/services/combined_inspector.py

import json
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, Optional, List

import pandas as pd

from src.services.token_data_fetcher import TokenDataFetcher
from src.services.boosting_classifier import BoostingFraudClassifier
from src.models.gemini_wrapper import GeminiWrapper
from src.config.settings import FRAUD_MODEL_PATH, SUPPORTED_CHAINS_PATH


class CombinedTokenInspector:
    NEWS_RSS_URL = "https://news.google.com/rss/search?q={q}&hl=ru&gl=RU&ceid=RU:ru"

    def __init__(self):
        # Загрузка нативных токенов
        with open(SUPPORTED_CHAINS_PATH, encoding="utf-8") as f:
            chains = json.load(f)
        self.native_tokens = {
            entry["native_symbol"].lower(): entry["id"]
            for entry in chains if entry.get("native_symbol")
        }

        self.fetcher    = TokenDataFetcher()
        self.classifier = BoostingFraudClassifier(FRAUD_MODEL_PATH)
        self.gemini     = GeminiWrapper()

    def _fetch_news(self, query: str, max_items: int = 5) -> List[Dict[str, str]]:
        url = self.NEWS_RSS_URL.format(q=requests.utils.requote_uri(query))
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall('.//item')[:max_items]
            news = []
            for itm in items:
                title = itm.findtext('title', '').strip()
                pub   = itm.findtext('pubDate', '').strip()
                news.append({'date': pub, 'title': title})
            return news
        except Exception:
            return []

    def _format_bullets(self, items: List[str]) -> str:
        return "\n".join(f"• {line}" for line in items)

    def _build_final_prompt(
        self,
        symbol: str,
        date_str: str,
        news: List[Dict[str, str]],
        risk_context: Optional[str],
        analysis_items: List[str]
    ) -> str:
        # Собираем новости
        news_lines = [f"{n['date']} — {n['title']}" for n in news]

        # Стартовое описание
        parts = [
            f"На основе следующих данных по токену {symbol}:",
            f"Дата: {date_str}",
        ]
        if risk_context:
            parts.append(risk_context.strip())
        if news_lines:
            parts.append("Новости:")
            parts.extend(news_lines)
        if analysis_items:
            parts.append("Технический анализ и метрики:")
            parts.extend(analysis_items)

        # Инструкция по итоговому отчёту
        instruction = (
            "Составь структурированный отчёт только по токену {symbol}, используя строго следующее форматирование:\n"
            "• Для обычных пунктов используй символ •\n"
            "• Для жирного текста используй *текст*\n\n"
            "💡 *ОСНОВНЫЕ ВЫВОДЫ:*\n"
            "*Ключевые факты о токене:*\n"
            "• Символ и адрес контракта (если есть)\n"
            "• Число листингов и платформа (если применимо)\n"
            "*Важные особенности:*\n"
            "• Особенности контракта и рынка\n"
            "⚠️ *УРОВЕНЬ РИСКА:*\n"
            "• Оценка вероятности скама и red flags\n"
            "🎯 *ВЕРДИКТ:*\n"
            "• Скам/не скам\n"
            "👉 *РЕКОМЕНДАЦИИ:*\n"
            "• Инвестировать/не инвестировать на основе риска\n\n"
            "Ответ должен быть на русском языке. Не используй другие символы форматирования кроме • и *."
        ).format(symbol=symbol)

        # Объединяем
        prompt = "\n".join(parts + [instruction])
        return prompt

    async def inspect(
        self,
        symbol: str,
        chain: Optional[str] = None
    ) -> Dict[str, Any]:
        symbol_u = symbol.upper()
        symbol_l = symbol.lower()

        # Дата
        months = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }
        now = datetime.now()
        date_str = f"{now.day} {months[now.month]} {now.year}"

        # Новости
        news = self._fetch_news(symbol_u)

        # Контекст для нативных токенов
        is_native = symbol_l in self.native_tokens
        risk_context = None
        if is_native:
            network = self.native_tokens[symbol_l]
            risk_context = f"*Важная заметка:* {symbol_u} — нативный токен сети {network}, риски зависят от сети.\n"

        if is_native:
            analysis_items = []
            # основная рекомендация
            analysis_items.append("Нативный токен — риски зависят от сети.")
            prompt = self._build_final_prompt(symbol_u, date_str, news, risk_context, analysis_items)
            llm_report = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.gemini.generate(prompt)
            )
            return {
                'symbol': symbol_u,
                'prediction': False,
                'scam_probability': 0.01,
                'llm_report': llm_report
            }

        # Платформы и адрес
        try:
            platforms = self.fetcher.get_token_platforms(symbol_u)
        except Exception:
            platforms = {}
        address = None
        if platforms:
            address = platforms.get(chain) or next(iter(platforms.values()))

        # Фичи и прогноз
        features, is_scam, scam_prob = {}, None, None
        if address:
            try:
                features = self.fetcher.get_token_features(address)
                df = pd.DataFrame([features])
                is_scam = bool(self.classifier.predict(df).iloc[0])
                scam_prob = float(
                    self.classifier.predict_proba(df)[f"prob_class_{int(is_scam)}"].iloc[0]
                ) * 100
            except Exception:
                pass

        # Формируем анализ
        analysis_items = []
        if address:
            analysis_items.append(f"Адрес: {address}")
        for k, v in (features.items()):
            analysis_items.append(f"{k.replace('_', ' ')}: {v}")
        if scam_prob is not None:
            analysis_items.append(f"Вероятность скама: {scam_prob:.1f}%")

        # Финальный промпт
        prompt = self._build_final_prompt(symbol_u, date_str, news, risk_context, analysis_items)
        llm_report = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.gemini.generate(prompt)
        )

        result = {
            'symbol': symbol_u,
            'prediction': is_scam,
            'scam_probability': scam_prob,
            'llm_report': llm_report
        }
        if address:
            result['address'] = address
        return result
