import json
import configparser
from pathlib import Path
from typing import Any

from openai import OpenAI

from agent.prompt import HEADER_PROMPT, EXTRACT_PROMPT
from logger import get_logger


class Agent:
    """LLM agent that only returns structured JSON."""

    logger = get_logger("agent.core")

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
        self.logger.info("[LLM] analyze_headers request: %s", headers)
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": HEADER_PROMPT},
                {"role": "user", "content": json.dumps(headers, ensure_ascii=False)},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        self.logger.info("[LLM] analyze_headers response: %s", raw)
        data = self._parse_json(raw)
        return {"address_field": str(data.get("address_field", ""))}

    def extract_info(self, text: str) -> dict[str, str]:
        self.logger.info("[LLM] extract_info request: %s", text)
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        self.logger.info("[LLM] extract_info response: %s", raw)
        data = self._parse_json(raw)
        return {
            "name": str(data.get("name", "")),
            "phone": str(data.get("phone", "")),
            "email": str(data.get("email", "")),
            "company_name": str(data.get("company_name") or data.get("company name", "")),
            "address": str(data.get("address") or data.get("full_address") or data.get("full address", "")),
            "province": str(data.get("province", "")),
            "city": str(data.get("city", "")),
            "country": str(data.get("country", "")),
            "postcode": str(data.get("postcode", "")),
            "remark": str(data.get("remark", "")),
        }
