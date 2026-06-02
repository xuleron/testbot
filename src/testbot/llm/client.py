"""OpenAI 兼容 LLM 客户端。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from testbot.config import Settings
from testbot.llm.providers import ResolvedLLMConfig, resolve_llm_config
from testbot.llm.json_utils import parse_json_lenient

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用异常。"""


class LLMClient:
    """支持 OpenAI 兼容 API（OpenAI / DeepSeek / Ollama 等）。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.config: ResolvedLLMConfig = resolve_llm_config(settings)

    @property
    def chat_url(self) -> str:
        base = self.config.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if self.config.requires_api_key and not self.config.api_key:
            raise LLMError(
                f"未配置 LLM_API_KEY（当前服务商: {self.config.provider}）"
            )

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.llm_temperature,
        }
        payload["max_tokens"] = max_tokens if max_tokens is not None else self.settings.llm_max_tokens

        use_json_mode = json_mode and self.config.supports_json_mode
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        logger.debug(
            "LLM 请求 [%s]: model=%s messages=%d json_mode=%s",
            self.config.provider,
            self.config.model,
            len(messages),
            use_json_mode,
        )

        with httpx.Client(timeout=self.settings.llm_timeout) as client:
            response = client.post(self.chat_url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise LLMError(
                    f"LLM API 错误 [{self.config.provider} {response.status_code}]: {response.text}"
                )
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"LLM 响应格式异常: {data}") from exc

        if not content:
            raise LLMError("LLM 返回空内容")
        return content

    @staticmethod
    def parse_json(content: str, *, array_key: str | None = None) -> Any:
        try:
            return parse_json_lenient(content, array_key=array_key)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"无法解析 LLM JSON 响应: {exc}; 片段: {content[:500]}") from exc

    def ping(self) -> str:
        content = self.chat(
            [{"role": "user", "content": '回复 JSON: {"status":"ok"}'}],
            json_mode=True,
            max_tokens=64,
        )
        data = self.parse_json(content)
        return str(data.get("status", "ok"))
