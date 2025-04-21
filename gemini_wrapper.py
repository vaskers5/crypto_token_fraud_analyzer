import os
import requests
from typing import Any, Optional
from dotenv import load_dotenv

class GeminiWrapper:
    def __init__(self, model: str = "gemini-2.0-flash-lite", api_key: Optional[str] = None):
        """
        Инициализация обертки для Gemini API.
        
        Args:
            model (str): Идентификатор модели Gemini
            api_key (str, optional): API ключ (если не указан, берется из GEMINI_API_KEY)
        """
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        
        # Настройка прокси
        self.proxies = {}
        if os.getenv('HTTP_PROXY'):
            self.proxies['http'] = os.getenv('HTTP_PROXY')
        if os.getenv('HTTPS_PROXY'):
            self.proxies['https'] = os.getenv('HTTPS_PROXY')

    def generate(self, prompt: str) -> str:
        """
        Отправка запроса к Gemini API.
        
        Args:
            prompt (str): Текст запроса
            
        Returns:
            str: Ответ модели
        """
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
            
            response_json = resp.json()
            
            if self.model == 'gemini-2.0-flash-lite':
                return response_json['candidates'][0]['content']['parts'][0]['text']
                
            contents = response_json.get("contents", [])
            if not contents:
                return ""
                
            parts = contents[0].get("parts", [])
            if not parts:
                return ""
                
            return parts[0].get("text", "")

        except Exception as e:
            print(f"Ошибка при вызове Gemini API: {e}")
            return ""