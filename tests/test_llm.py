"""LLM 模块测试。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testbot.analyzer.llm_analyzer import LLMProjectAnalyzer
from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.planner.llm_generator import LLMCaseItem, LLMTestCaseGenerator
from testbot.models.testcase import CaseType


@pytest.fixture
def llm_settings(sample_analysis) -> Settings:
    return Settings(
        TARGET_PROJECT_PATH=sample_analysis.project_path,
        LLM_API_BASE="https://api.test/v1",
        LLM_API_KEY="test-key",
        LLM_MODEL="test-model",
    )


def test_llm_client_parse_json_direct():
    data = LLMClient.parse_json('{"cases": []}')
    assert data == {"cases": []}


def test_llm_client_parse_json_fenced():
    text = '说明\n```json\n{"status": "ok"}\n```'
    data = LLMClient.parse_json(text)
    assert data["status"] == "ok"


def test_llm_analyzer_enrich(sample_analysis, llm_settings):
    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {
            "summary": "示例 API 项目",
            "core_features": ["加法运算"],
            "test_focus": ["边界值"],
            "risk_areas": ["溢出"],
            "recommended_case_types": ["unit"],
        },
        ensure_ascii=False,
    )
    mock_client.parse_json.side_effect = LLMClient.parse_json

    analyzer = LLMProjectAnalyzer(llm_settings, client=mock_client)
    enriched = analyzer.enrich(sample_analysis, Path(sample_analysis.project_path))

    assert enriched.llm_summary == "示例 API 项目"
    assert "边界值" in enriched.test_focus
    mock_client.chat.assert_called_once()


def test_llm_case_item_normalizes_component_type():
    item = LLMCaseItem(
        title="组件渲染",
        type="component",
        steps=[{"action": "打开页面", "expect": "组件显示"}],
    )
    assert item.type == CaseType.FEATURE


def test_llm_generator(sample_analysis, llm_settings):
    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {
            "cases": [
                {
                    "title": "验证 hello 返回值",
                    "type": "unit",
                    "pri": 2,
                    "precondition": "无",
                    "source": "main.py",
                    "steps": [
                        {"action": "调用 hello()", "expect": "返回 world"},
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    mock_client.parse_json.side_effect = LLMClient.parse_json

    generator = LLMTestCaseGenerator(llm_settings, client=mock_client)
    cases = generator.generate(sample_analysis, Path(sample_analysis.project_path))

    assert len(cases) == 1
    assert cases[0].title == "验证 hello 返回值"
    assert cases[0].steps[0].expect == "返回 world"
