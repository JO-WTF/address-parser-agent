import json
import configparser
from pathlib import Path
from typing import Any

from openai import OpenAI

from agent.prompt import HEADER_PROMPT, EXTRACT_PROMPT


class Agent:
    """LLM agent that only returns structured JSON."""

    def __init__(self) -> None:
        config = configparser.ConfigParser()
        config_path = Path(__file__).resolve().parent.parent / "config.ini"
        config.read(config_path, encoding="utf-8")

        base_url = config.get("llm", "base_url", fallback="http://localhost:11434/v1")
        api_key = config.get("llm", "api_key", fallback="ollama")
        self.model = config.get("llm", "model", fallback="qwen2.5:7b")

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )

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
        return {"address_field": str(data.get("address_field", ""))}

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
