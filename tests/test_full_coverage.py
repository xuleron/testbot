"""全量覆盖生成器测试。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.models.project import ProjectAnalysis, ProjectModule
from testbot.models.testcase import TestCaseDraft, TestCaseStep
from testbot.planner.full_coverage import FeaturePoint, FullCoverageGenerator


def test_dedupe_cases():
    cases = [
        TestCaseDraft(title="登录-成功", steps=[TestCaseStep(action="a", expect="b")]),
        TestCaseDraft(title="登录-成功", steps=[TestCaseStep(action="c", expect="d")]),
        TestCaseDraft(title="登录-失败", steps=[TestCaseStep(action="e", expect="f")]),
    ]
    result = FullCoverageGenerator._dedupe_cases(cases)
    assert len(result) == 2
    assert result[0].title == "登录-成功"
    assert result[1].title == "登录-失败"


def test_merge_with_analysis_modules(sample_analysis):
    settings = Settings(TARGET_PROJECT_PATH=sample_analysis.project_path)
    generator = FullCoverageGenerator(settings, client=MagicMock())
    features = [FeaturePoint(name="已有功能", source="src/demo/main.py")]
    merged = generator._merge_with_analysis_modules(features, sample_analysis)
    names = {f.name for f in merged}
    assert "已有功能" in names
    assert any(m.name in names for m in sample_analysis.modules)


def test_full_coverage_generate(sample_analysis):
    settings = Settings(
        TARGET_PROJECT_PATH=sample_analysis.project_path,
        LLM_FEATURE_BATCH_SIZE=2,
        LLM_CASES_PER_FEATURE=2,
    )
    mock_client = MagicMock()
    mock_client.parse_json.side_effect = LLMClient.parse_json
    mock_client.chat.side_effect = [
        json.dumps(
            {
                "features": [
                    {"name": "hello 接口", "module": "demo", "source": "main.py"},
                    {"name": "健康检查", "module": "demo", "source": "main.py"},
                ]
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "cases": [
                    {
                        "title": "hello-正常返回",
                        "type": "unit",
                        "pri": 2,
                        "precondition": "无",
                        "source": "main.py",
                        "module_name": "demo",
                        "steps": [{"action": "调用 hello()", "expect": "返回 world"}],
                    },
                    {
                        "title": "hello-空参数",
                        "type": "unit",
                        "pri": 3,
                        "precondition": "无",
                        "source": "main.py",
                        "module_name": "demo",
                        "steps": [{"action": "调用 hello()", "expect": "正常"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
    ]

    generator = FullCoverageGenerator(settings, client=mock_client)
    analysis = sample_analysis.model_copy(update={"modules": [], "core_features": []})
    cases = generator.generate(analysis, Path(sample_analysis.project_path))

    assert len(cases) == 2
    assert mock_client.chat.call_count == 2
    assert cases[0].title == "hello-正常返回"
