"""LLM 执行器测试。"""

import json
from unittest.mock import MagicMock

from testbot.config import Settings
from testbot.executor.llm_executor import LLMCaseExecutor, LLMExecutionItem
from testbot.llm.client import LLMClient
from testbot.models.testcase import CaseType, StepResult, TestCaseDraft, TestCaseStep


def test_normalize_execution_status():
    item = LLMExecutionItem.model_validate(
        {"title": "t", "status": "passed", "real": "ok", "steps": []}
    )
    assert item.status == StepResult.PASS


def test_llm_executor_run(sample_analysis):
    settings = Settings(
        TARGET_PROJECT_PATH=sample_analysis.project_path,
        LLM_EXEC_BATCH_SIZE=5,
    )
    mock_client = MagicMock()
    mock_client.parse_json.side_effect = LLMClient.parse_json
    mock_client.chat.return_value = json.dumps(
        {
            "results": [
                {
                    "title": "验证 hello",
                    "status": "pass",
                    "real": "main.py 中 hello 返回 world",
                    "steps": [{"result": "pass", "real": "符合预期"}],
                }
            ]
        },
        ensure_ascii=False,
    )

    cases = [
        TestCaseDraft(
            title="验证 hello",
            zentao_id=101,
            steps=[TestCaseStep(action="调用 hello()", expect="返回 world")],
            type=CaseType.UNIT,
        )
    ]

    executor = LLMCaseExecutor(settings, client=mock_client)
    results = executor.execute(sample_analysis, cases)

    assert len(results) == 1
    assert results[0].status == StepResult.PASS
    assert results[0].case_id == 101
    assert results[0].automated is True
