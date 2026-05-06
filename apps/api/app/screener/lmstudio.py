from __future__ import annotations

import httpx
from typing import Optional

from ..config import settings


class LMStudioClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or settings.lm_studio_base_url).rstrip("/")
        self.model = model or settings.lm_studio_model

    async def health(self) -> dict:
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                model_name = self.model or (models[0] if models else None)
                return {
                    "available": True,
                    "base_url": self.base_url,
                    "model": model_name,
                    "models": models,
                    "error": None,
                }
        except Exception as e:
            return {
                "available": False,
                "base_url": self.base_url,
                "model": None,
                "models": [],
                "error": str(e),
            }

    async def chat_json(self, system: str, user: str, max_tokens: int = 1024,
                        temperature: float = 0.2) -> Optional[dict]:
        """Call chat completions and return parsed JSON, or None on failure."""
        import json
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model or "local-model",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Attempt to extract a JSON object
                    start = content.find("{")
                    end = content.rfind("}")
                    if start >= 0 and end > start:
                        return json.loads(content[start:end + 1])
                    return None
        except Exception:
            return None


lmstudio = LMStudioClient()
