"""Playwright 浏览器 E2E 执行器。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from testbot.config import Settings
from testbot.executor.playwright_actions import (
    BrowserCasePlan,
    BrowserStepPlan,
    execute_actions,
    page_snapshot,
    verify_expectation,
)
from testbot.executor.playwright_login import perform_login
from testbot.llm.client import LLMClient
from testbot.llm.prompts import BROWSER_STEP_SYSTEM, BROWSER_STEP_USER
from testbot.models.project import ProjectAnalysis
from testbot.models.report import CaseExecutionResult
from testbot.models.testcase import StepResult, TestCaseDraft, TestCaseStep, TestStepResult

logger = logging.getLogger(__name__)


class PlaywrightNotInstalledError(RuntimeError):
    """Playwright 未安装。"""


class PlaywrightCaseExecutor:
    """拉起浏览器，登录后按用例步骤执行 Playwright 操作。"""

    def __init__(self, settings: Settings, client: LLMClient | None = None):
        self.settings = settings
        self.client = client or LLMClient(settings)

    def execute(
        self,
        analysis: ProjectAnalysis,
        cases: list[TestCaseDraft],
        project_path: Path | None = None,
    ) -> list[CaseExecutionResult]:
        sync_playwright = self._import_playwright()
        max_cases = self.settings.llm_exec_max_cases
        target_cases = cases[:max_cases] if max_cases > 0 else cases
        if max_cases > 0 and len(cases) > max_cases:
            logger.warning("浏览器执行限制为 %d 条（共 %d 条）", max_cases, len(cases))

        results: list[CaseExecutionResult] = []
        logger.info("启动 Playwright 浏览器（headless=%s）...", self.settings.browser_headless)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.settings.browser_headless,
                slow_mo=self.settings.browser_slow_mo,
            )
            context = browser.new_context(
                viewport={
                    "width": self.settings.browser_viewport_width,
                    "height": self.settings.browser_viewport_height,
                },
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.set_default_timeout(self.settings.browser_timeout_ms)

            try:
                login_log = perform_login(page, self.settings)
                logger.info(login_log)
            except Exception as exc:
                logger.error("浏览器登录失败: %s", exc)
                browser.close()
                return [self._blocked_case(c, f"登录失败: {exc}") for c in target_cases]

            for idx, case in enumerate(target_cases, 1):
                logger.info("浏览器执行 [%d/%d]: %s", idx, len(target_cases), case.title[:60])
                results.append(self._run_case(page, case, analysis))
                if idx % 5 == 0:
                    self._reset_to_home(page)

            browser.close()

        return results

    def _run_case(
        self,
        page: Any,
        case: TestCaseDraft,
        analysis: ProjectAnalysis,
    ) -> CaseExecutionResult:
        start = time.perf_counter()
        step_results: list[TestStepResult] = []
        overall = StepResult.PASS
        last_error = ""

        steps = case.steps or [TestCaseStep(action=case.title, expect="功能正常")]
        for step_idx, step in enumerate(steps, 1):
            try:
                snapshot = page_snapshot(page)
                plan = self._plan_step(case, step, snapshot, analysis)
                logs = execute_actions(
                    page,
                    plan.actions,
                    default_timeout=self.settings.browser_timeout_ms,
                )
                passed = verify_expectation(page, step.expect)
                status = StepResult.PASS if passed else StepResult.FAIL
                real = "; ".join(logs) if logs else plan.note
                if not passed:
                    real += f" | 未满足预期: {step.expect[:200]}"
                    overall = StepResult.FAIL
                    last_error = step.expect
            except Exception as exc:
                status = StepResult.FAIL
                real = str(exc)
                overall = StepResult.FAIL
                last_error = str(exc)
                logger.warning("用例步骤失败 %s #%d: %s", case.title, step_idx, exc)

            step_results.append(TestStepResult(result=status, real=real))
            if status == StepResult.FAIL:
                break

        duration = int((time.perf_counter() - start) * 1000)
        return CaseExecutionResult(
            case_id=case.zentao_id,
            title=case.title,
            status=overall,
            steps=step_results,
            duration_ms=duration,
            automated=True,
            error=last_error,
        )

    def _plan_step(
        self,
        case: TestCaseDraft,
        step: TestCaseStep,
        snapshot: dict[str, str],
        analysis: ProjectAnalysis,
    ) -> BrowserStepPlan:
        messages = [
            {"role": "system", "content": BROWSER_STEP_SYSTEM},
            {
                "role": "user",
                "content": BROWSER_STEP_USER.format(
                    project_name=analysis.project_name,
                    case_title=case.title,
                    precondition=case.precondition or "无",
                    step_action=step.action,
                    step_expect=step.expect,
                    page_url=snapshot["url"],
                    page_title=snapshot["title"],
                    page_text=snapshot["text"],
                ),
            },
        ]
        raw = self.client.chat(messages, json_mode=True, max_tokens=2048)
        data = self.client.parse_json(raw, array_key="actions")
        if isinstance(data, dict) and "actions" in data:
            return BrowserStepPlan.model_validate(data)
        if isinstance(data, dict) and "steps" in data:
            plan = BrowserCasePlan.model_validate(data)
            return plan.steps[0] if plan.steps else BrowserStepPlan()
        return BrowserStepPlan.model_validate(data)

    def _reset_to_home(self, page: Any) -> None:
        home = self.settings.target_app_url.strip()
        if not home:
            return
        try:
            page.goto(home, wait_until="domcontentloaded", timeout=self.settings.browser_timeout_ms)
            page.wait_for_timeout(500)
        except Exception as exc:
            logger.debug("回到首页失败: %s", exc)

    @staticmethod
    def _blocked_case(case: TestCaseDraft, reason: str) -> CaseExecutionResult:
        return CaseExecutionResult(
            case_id=case.zentao_id,
            title=case.title,
            status=StepResult.BLOCKED,
            steps=[TestStepResult(result=StepResult.BLOCKED, real=reason)],
            automated=True,
            error=reason,
        )

    @staticmethod
    def _import_playwright():
        try:
            from playwright.sync_api import sync_playwright

            return sync_playwright
        except ImportError as exc:
            raise PlaywrightNotInstalledError(
                "未安装 Playwright。请执行:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            ) from exc

