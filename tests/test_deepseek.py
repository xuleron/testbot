"""DeepSeek / Provider 配置测试。"""

import pytest

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.llm.providers import get_provider, resolve_llm_config


def test_deepseek_provider_preset():
    preset = get_provider("deepseek")
    assert preset.api_base == "https://api.deepseek.com/v1"
    assert preset.default_model == "deepseek-chat"
    assert preset.supports_json_mode is True


def test_deepseek_auto_resolve_defaults():
    settings = Settings(
        LLM_PROVIDER="deepseek",
        LLM_API_KEY="test-key",
        LLM_MODEL="gpt-4o-mini",
    )
    config = resolve_llm_config(settings)
    assert config.provider == "deepseek"
    assert config.api_base == "https://api.deepseek.com/v1"
    assert config.model == "deepseek-chat"


def test_deepseek_custom_model_override():
    settings = Settings(
        LLM_PROVIDER="deepseek",
        LLM_API_KEY="test-key",
        LLM_MODEL="deepseek-reasoner",
    )
    config = resolve_llm_config(settings)
    assert config.model == "deepseek-reasoner"


def test_deepseek_custom_base_override():
    settings = Settings(
        LLM_PROVIDER="deepseek",
        LLM_API_KEY="test-key",
        LLM_API_BASE="https://custom.deepseek.proxy/v1",
        LLM_MODEL="deepseek-chat",
    )
    config = resolve_llm_config(settings)
    assert config.api_base == "https://custom.deepseek.proxy/v1"


def test_unknown_provider_raises():
    settings = Settings(LLM_PROVIDER="unknown")
    with pytest.raises(ValueError, match="不支持的 LLM 服务商"):
        resolve_llm_config(settings)


def test_deepseek_client_chat_url():
    settings = Settings(
        LLM_PROVIDER="deepseek",
        LLM_API_KEY="test-key",
    )
    client = LLMClient(settings)
    assert client.chat_url == "https://api.deepseek.com/v1/chat/completions"
    assert client.config.provider == "deepseek"
