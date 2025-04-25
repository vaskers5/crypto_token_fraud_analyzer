import os
import requests
from typing import Optional
from ..config.settings import GEMINI_API_KEY, PROXIES, GEMINI_API_BASE

class GeminiWrapper:
    def __init__(self, model: str = "gemini-2.0-flash-lite"):
        self.model = model
        self.api_key = GEMINI_API_KEY
        self.api_url = f"{GEMINI_API_BASE}/models/{self.model}:generateContent"
        if PROXIES["ENABLED"]:
            self.proxies = PROXIES
        else:
            self.proxies = None

    def generate(self, prompt: str) -> str:
        try:
            data = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            }

            headers = {"Content-Type": "application/json"}
            api_endpoint = f"{self.api_url}?key={self.api_key}"
            
            resp = requests.post(
                api_endpoint,
                headers=headers,
                json=data,
                proxies=self.proxies
            )
            resp.raise_for_status()
            
            return resp.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f"Error in Gemini API call: {e}")
            return "Не удалось получить анализ"