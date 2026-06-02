"""LLM 服务商预设与配置解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testbot.config import Settings


@dataclass(frozen=True)
class LLMProviderPreset:
    name: str
    api_base: str
    default_model: str
    requires_api_key: bool = True
    supports_json_mode: bool = True
    description: str = ""


PROVIDERS: dict[str, LLMProviderPreset] = {
    "openai": LLMProviderPreset(
        name="openai",
        api_base="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        description="OpenAI API",
    ),
    "deepseek": LLMProviderPreset(
        name="deepseek",
        api_base="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        description="DeepSeek API（OpenAI 兼容）",
    ),
    "ollama": LLMProviderPreset(
        name="ollama",
        api_base="http://localhost:11434/v1",
        default_model="qwen2.5:7b",
        requires_api_key=False,
        supports_json_mode=False,
        description="本地 Ollama",
    ),
}

OPENAI_DEFAULT_BASE = PROVIDERS["openai"].api_base
OPENAI_DEFAULT_MODEL = PROVIDERS["openai"].default_model


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider: str
    api_base: str
    model: str
    api_key: str
    requires_api_key: bool
    supports_json_mode: bool
    description: str


def get_provider(name: str) -> LLMProviderPreset:
    key = name.lower().strip()
    if key not in PROVIDERS:
        supported = ", ".join(PROVIDERS)
        raise ValueError(f"不支持的 LLM 服务商: {name}，可选: {supported}")
    return PROVIDERS[key]


def resolve_llm_config(settings: Settings) -> ResolvedLLMConfig:
    """根据 LLM_PROVIDER 解析最终 API 配置，未显式覆盖时使用各服务商默认值。"""
    provider_name = settings.llm_provider.lower().strip()
    preset = get_provider(provider_name)

    api_base = settings.llm_api_base.rstrip("/")
    model = settings.llm_model

    # 当 api_base / model 仍为 OpenAI 默认值时，按 provider 自动切换
    if provider_name != "openai":
        if api_base == OPENAI_DEFAULT_BASE or not api_base:
            api_base = preset.api_base.rstrip("/")
        if model == OPENAI_DEFAULT_MODEL or not model:
            model = preset.default_model

    return ResolvedLLMConfig(
        provider=provider_name,
        api_base=api_base,
        model=model,
        api_key=settings.llm_api_key,
        requires_api_key=preset.requires_api_key,
        supports_json_mode=preset.supports_json_mode,
        description=preset.description,
    )
