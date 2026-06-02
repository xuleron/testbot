"""Bug 自动登记测试。"""

from testbot.config import Settings
from testbot.models.report import CaseExecutionResult
from testbot.models.testcase import StepResult, TestStepResult
from testbot.reporter.bug_reporter import build_bug_draft
from testbot.reporter.zentao_reporter import ResultReporter


def test_build_bug_draft():
    settings = Settings(
        ZENTAO_PRODUCT_ID=20,
        ZENTAO_PROJECT_ID=20,
        ZENTAO_BUG_TYPE="codeerror",
    )
    result = CaseExecutionResult(
        case_id=563,
        title="登录失败用例",
        status=StepResult.FAIL,
        steps=[TestStepResult(result=StepResult.FAIL, real="RSA 加密异常")],
        error="assertion failed",
        automated=True,
    )
    draft = build_bug_draft(result, settings, case_id=563)
    assert draft.title.startswith("[TestBot]")
    assert "563" in draft.steps
    assert "RSA" in draft.steps
    assert draft.product_id == 20


def test_file_bugs_skips_pass():
    settings = Settings(ZENTAO_AUTO_CREATE_BUGS=True)
    report = __import__("testbot.models.report", fromlist=["ExecutionReport"]).ExecutionReport(
        project_path=".",
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        results=[
            CaseExecutionResult(title="ok", status=StepResult.PASS, automated=True),
            CaseExecutionResult(title="bad", status=StepResult.FAIL, case_id=1, automated=True),
        ],
    )
    from unittest.mock import MagicMock

    zentao = MagicMock()
    zentao.create_bug.return_value = 1001
    reporter = ResultReporter(zentao, settings)
    count = reporter.file_bugs_to_zentao(report)
    assert count == 1
    zentao.create_bug.assert_called_once()
    assert report.results[1].bug_id == 1001
