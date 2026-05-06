import json
import os
from typing import Any

from openai import OpenAI

from agent.prompt import HEADER_PROMPT, EXTRACT_PROMPT


class Agent:
    """LLM agent that only returns structured JSON."""

    def __init__(self) -> None:
        self.client = OpenAI(
            base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("LLM_API_KEY", "ollama"),
        )
        self.model = os.getenv("LLM_MODEL", "qwen2.5:7b")

    def _parse_json(self, text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError(f"Invalid JSON from model: {text}")

    def analyze_headers(self, headers: list[str]) -> dict[str, str]:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": HEADER_PROMPT},
                {"role": "user", "content": json.dumps(headers, ensure_ascii=False)},
            ],
        )
        data = self._parse_json(resp.choices[0].message.content or "{}")
        return {
            "name_field": str(data.get("name_field", "")),
            "address_field": str(data.get("address_field", "")),
            "phone_field": str(data.get("phone_field", "")),
        }

    def extract_info(self, text: str) -> dict[str, str]:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = self._parse_json(resp.choices[0].message.content or "{}")
        keys = ["name", "phone", "address", "province", "city"]
        return {k: str(data.get(k, "")) for k in keys}
