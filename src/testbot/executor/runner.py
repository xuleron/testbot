"""测试执行器。"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from testbot.config import Settings, get_settings
from testbot.executor.llm_executor import LLMCaseExecutor
from testbot.executor.playwright_executor import PlaywrightCaseExecutor, PlaywrightNotInstalledError
from testbot.models.project import ProjectAnalysis
from testbot.models.report import CaseExecutionResult, ExecutionReport
from testbot.models.testcase import StepResult, TestCaseDraft, TestStepResult

logger = logging.getLogger(__name__)


class TestExecutor:
    """执行自动化测试；支持 LLM 自动判定手工用例。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._llm_executor: LLMCaseExecutor | None = None
        self._playwright_executor: PlaywrightCaseExecutor | None = None

    @property
    def playwright_executor(self) -> PlaywrightCaseExecutor:
        if self._playwright_executor is None:
            self._playwright_executor = PlaywrightCaseExecutor(self.settings)
        return self._playwright_executor

    @property
    def llm_executor(self) -> LLMCaseExecutor:
        if self._llm_executor is None:
            self._llm_executor = LLMCaseExecutor(self.settings)
        return self._llm_executor

    def execute(
        self,
        analysis: ProjectAnalysis,
        cases: list[TestCaseDraft],
        *,
        run_automation: bool = True,
        executor_mode: str | None = None,
    ) -> ExecutionReport:
        started = datetime.now(timezone.utc)
        mode = (executor_mode or self.settings.executor_mode or "auto").lower()
        results: list[CaseExecutionResult] = []
        framework_output = ""

        if run_automation and analysis.existing_tests and analysis.test_framework:
            auto_results = self._run_automated_tests(analysis)
            results.extend(auto_results)
            framework_output = self._collect_framework_output(auto_results)

        covered_titles = {r.title for r in results}
        pending_cases = [c for c in cases if c.title not in covered_titles]

        if mode == "playwright" and pending_cases:
            if not self.settings.target_app_url.strip():
                logger.error("playwright 模式需要配置 TARGET_APP_URL")
                for case in pending_cases:
                    results.append(self._blocked_case(case, "未配置 TARGET_APP_URL"))
            else:
                logger.info("使用 Playwright 浏览器执行 %d 条用例", len(pending_cases))
                try:
                    pw_results = self.playwright_executor.execute(
                        analysis,
                        pending_cases,
                        Path(analysis.project_path),
                    )
                    results.extend(pw_results)
                except PlaywrightNotInstalledError as exc:
                    logger.error("%s", exc)
                    for case in pending_cases:
                        results.append(self._blocked_case(case, str(exc)))
        elif mode in ("llm", "auto") and pending_cases:
            logger.info("使用 LLM 执行 %d 条用例（模式: %s）", len(pending_cases), mode)
            llm_results = self.llm_executor.execute(
                analysis,
                pending_cases,
                Path(analysis.project_path),
                framework_output=framework_output,
            )
            results.extend(llm_results)
        elif pending_cases:
            for case in pending_cases:
                results.append(self._manual_placeholder(case))

        finished = datetime.now(timezone.utc)
        report = ExecutionReport(
            project_path=analysis.project_path,
            started_at=started,
            finished_at=finished,
            total=len(results),
            results=results,
        )
        for r in results:
            if r.status == StepResult.PASS:
                report.passed += 1
            elif r.status == StepResult.FAIL:
                report.failed += 1
            elif r.status == StepResult.BLOCKED:
                report.blocked += 1
            else:
                report.skipped += 1

        logger.info(
            "执行完成: 总计 %d, 通过 %d, 失败 %d, 阻塞 %d, 待测 %d",
            report.total,
            report.passed,
            report.failed,
            report.blocked,
            report.skipped,
        )
        return report

    def _run_automated_tests(self, analysis: ProjectAnalysis) -> list[CaseExecutionResult]:
        project_path = Path(analysis.project_path)
        framework = analysis.test_framework

        if framework == "pytest":
            return [self._run_pytest(project_path, analysis)]
        if framework in ("jest", "vitest", "mocha"):
            return [self._run_npm_test(project_path, analysis, framework)]

        return []

    @staticmethod
    def _collect_framework_output(results: list[CaseExecutionResult]) -> str:
        parts = []
        for item in results:
            for step in item.steps:
                if step.real:
                    parts.append(step.real)
        return "\n".join(parts)

    def _run_pytest(self, project_path: Path, analysis: ProjectAnalysis) -> CaseExecutionResult:
        title = f"[回归] {analysis.project_name} pytest 自动化执行"
        start = time.perf_counter()
        cmd = ["python", "-m", "pytest", "-v", "--tb=short", "-q"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
            duration = int((time.perf_counter() - start) * 1000)
            output = (proc.stdout or "") + (proc.stderr or "")
            status = StepResult.PASS if proc.returncode == 0 else StepResult.FAIL
            return CaseExecutionResult(
                title=title,
                status=status,
                steps=[
                    TestStepResult(
                        result=status,
                        real=output[-3000:] if output else "无输出",
                    )
                ],
                duration_ms=duration,
                automated=True,
                error="" if proc.returncode == 0 else f"pytest 退出码: {proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            return CaseExecutionResult(
                title=title,
                status=StepResult.FAIL,
                steps=[TestStepResult(result=StepResult.FAIL, real="pytest 执行超时")],
                automated=True,
                error="timeout",
            )
        except FileNotFoundError:
            return CaseExecutionResult(
                title=title,
                status=StepResult.BLOCKED,
                steps=[TestStepResult(result=StepResult.BLOCKED, real="未找到 python/pytest")],
                automated=True,
                error="python not found",
            )

    def _run_npm_test(
        self,
        project_path: Path,
        analysis: ProjectAnalysis,
        framework: str,
    ) -> CaseExecutionResult:
        title = f"[回归] {analysis.project_name} {framework} 自动化执行"
        start = time.perf_counter()
        cmd = ["npm", "test", "--", "--passWithNoTests"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600,
                shell=True,
            )
            duration = int((time.perf_counter() - start) * 1000)
            output = (proc.stdout or "") + (proc.stderr or "")
            status = StepResult.PASS if proc.returncode == 0 else StepResult.FAIL
            return CaseExecutionResult(
                title=title,
                status=status,
                steps=[TestStepResult(result=status, real=output[-3000:] if output else "无输出")],
                duration_ms=duration,
                automated=True,
                error="" if proc.returncode == 0 else f"{framework} 退出码: {proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            return CaseExecutionResult(
                title=title,
                status=StepResult.FAIL,
                steps=[TestStepResult(result=StepResult.FAIL, real="npm test 执行超时")],
                automated=True,
                error="timeout",
            )

    def _blocked_case(self, case: TestCaseDraft, reason: str) -> CaseExecutionResult:
        return CaseExecutionResult(
            case_id=case.zentao_id,
            title=case.title,
            status=StepResult.BLOCKED,
            steps=[TestStepResult(result=StepResult.BLOCKED, real=reason)],
            automated=True,
            error=reason,
        )

    def _manual_placeholder(self, case: TestCaseDraft) -> CaseExecutionResult:
        steps = [
            TestStepResult(
                result=StepResult.NA,
                real="待人工执行：未启用 LLM 执行模式",
            )
            for _ in case.steps
        ]
        return CaseExecutionResult(
            case_id=case.zentao_id,
            title=case.title,
            status=StepResult.NA,
            steps=steps,
            automated=False,
        )

    @staticmethod
    def save_report(report: ExecutionReport, output_path: Path) -> None:
        payload = report.model_dump(mode="json")
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
