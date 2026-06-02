"""LLM 驱动的测试用例执行器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.llm.prompts import EXECUTE_SYSTEM, EXECUTE_USER
from testbot.models.project import ProjectAnalysis
from testbot.models.report import CaseExecutionResult
from testbot.models.testcase import StepResult, TestCaseDraft, TestCaseStep, TestStepResult
from testbot.planner.llm_generator import LLMTestCaseGenerator
from testbot.utils.project_files import collect_files_for_sources

logger = logging.getLogger(__name__)


class LLMExecutionItem(BaseModel):
    title: str
    status: StepResult = StepResult.NA
    real: str = ""
    steps: list[TestStepResult] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> StepResult:
        if isinstance(value, StepResult):
            return value
        key = str(value or "n/a").strip().lower()
        mapping = {
            "pass": StepResult.PASS,
            "passed": StepResult.PASS,
            "success": StepResult.PASS,
            "ok": StepResult.PASS,
            "通过": StepResult.PASS,
            "fail": StepResult.FAIL,
            "failed": StepResult.FAIL,
            "failure": StepResult.FAIL,
            "失败": StepResult.FAIL,
            "blocked": StepResult.BLOCKED,
            "block": StepResult.BLOCKED,
            "阻塞": StepResult.BLOCKED,
            "n/a": StepResult.NA,
            "na": StepResult.NA,
            "skip": StepResult.NA,
            "skipped": StepResult.NA,
            "待测": StepResult.NA,
        }
        return mapping.get(key, StepResult.NA)


class LLMExecutionResponse(BaseModel):
    results: list[LLMExecutionItem]


class LLMCaseExecutor:
    """使用 LLM 结合源码/测试输出，自动判定用例执行结果。"""

    def __init__(self, settings: Settings, client: LLMClient | None = None):
        self.settings = settings
        self.client = client or LLMClient(settings)

    def execute(
        self,
        analysis: ProjectAnalysis,
        cases: list[TestCaseDraft],
        project_path: Path | None = None,
        *,
        framework_output: str = "",
    ) -> list[CaseExecutionResult]:
        if not cases:
            return []

        path = project_path or Path(analysis.project_path)
        batch_size = max(1, self.settings.llm_exec_batch_size)
        max_cases = self.settings.llm_exec_max_cases
        target_cases = cases[:max_cases] if max_cases > 0 else cases

        if max_cases > 0 and len(cases) > max_cases:
            logger.warning("已限制执行用例数为 %d（共 %d 条）", max_cases, len(cases))

        logger.info("LLM 自动执行 %d 条用例（每批 %d 条）...", len(target_cases), batch_size)
        results: list[CaseExecutionResult] = []
        total_batches = (len(target_cases) + batch_size - 1) // batch_size

        for batch_no, start in enumerate(range(0, len(target_cases), batch_size), 1):
            batch = target_cases[start : start + batch_size]
            try:
                batch_results = self._execute_batch(
                    analysis,
                    path,
                    batch,
                    batch_no,
                    total_batches,
                    framework_output=framework_output,
                )
                results.extend(batch_results)
                logger.info(
                    "执行批次 %d/%d 完成（累计 %d/%d 条）",
                    batch_no,
                    total_batches,
                    len(results),
                    len(target_cases),
                )
            except Exception as exc:
                logger.error("执行批次 %d/%d 失败: %s", batch_no, total_batches, exc)
                for case in batch:
                    results.append(self._blocked_result(case, str(exc)))

        return results

    def _execute_batch(
        self,
        analysis: ProjectAnalysis,
        path: Path,
        batch: list[TestCaseDraft],
        batch_no: int,
        batch_total: int,
        *,
        framework_output: str,
    ) -> list[CaseExecutionResult]:
        source_hints = [c.source for c in batch if c.source] + [c.module_name for c in batch if c.module_name]
        files = collect_files_for_sources(
            path,
            source_hints,
            max_files=self.settings.llm_context_max_files,
            max_chars=self.settings.llm_context_max_chars,
        )
        source_context = LLMTestCaseGenerator._format_files(files)
        cases_json = json.dumps(
            [c.model_dump(mode="json") for c in batch],
            ensure_ascii=False,
            indent=2,
        )
        analysis_summary = json.dumps(
            {
                "project_name": analysis.project_name,
                "language": analysis.language,
                "framework": analysis.framework,
                "test_framework": analysis.test_framework,
                "llm_summary": analysis.llm_summary or analysis.readme_summary[:500],
            },
            ensure_ascii=False,
            indent=2,
        )
        app_url = self.settings.target_app_url.strip()
        app_section = f"\n## 被测应用地址\n{app_url}\n" if app_url else ""
        framework_section = (
            f"\n## 自动化测试输出（如有）\n```\n{framework_output[-8000:]}\n```\n"
            if framework_output
            else ""
        )

        messages = [
            {"role": "system", "content": EXECUTE_SYSTEM},
            {
                "role": "user",
                "content": EXECUTE_USER.format(
                    analysis_summary=analysis_summary,
                    cases_json=cases_json,
                    source_context=source_context,
                    app_section=app_section,
                    framework_section=framework_section,
                    batch_no=batch_no,
                    batch_total=batch_total,
                ),
            },
        ]

        raw = self.client.chat(messages, json_mode=True, max_tokens=self.settings.llm_max_tokens)
        data = self.client.parse_json(raw, array_key="results")
        response = LLMExecutionResponse.model_validate(data)

        by_title = {item.title.strip().lower(): item for item in response.results}
        results: list[CaseExecutionResult] = []
        for case in batch:
            item = by_title.get(case.title.strip().lower())
            if item is None:
                for key, candidate in by_title.items():
                    if key in case.title.strip().lower() or case.title.strip().lower() in key:
                        item = candidate
                        break
            if item is None:
                results.append(self._blocked_result(case, "LLM 未返回该用例的执行结果"))
                continue

            steps = item.steps or [
                TestStepResult(result=item.status, real=item.real or item.status.value)
            ]
            if len(steps) < len(case.steps):
                steps.extend(
                    TestStepResult(result=StepResult.NA, real="未执行")
                    for _ in range(len(case.steps) - len(steps))
                )

            overall = item.status
            if overall == StepResult.NA and steps:
                if any(s.result == StepResult.FAIL for s in steps):
                    overall = StepResult.FAIL
                elif all(s.result == StepResult.PASS for s in steps):
                    overall = StepResult.PASS

            results.append(
                CaseExecutionResult(
                    case_id=case.zentao_id,
                    title=case.title,
                    status=overall,
                    steps=steps,
                    automated=True,
                    error="" if overall != StepResult.FAIL else item.real[:500],
                )
            )
        return results

    @staticmethod
    def _blocked_result(case: TestCaseDraft, reason: str) -> CaseExecutionResult:
        return CaseExecutionResult(
            case_id=case.zentao_id,
            title=case.title,
            status=StepResult.BLOCKED,
            steps=[TestStepResult(result=StepResult.BLOCKED, real=reason)],
            automated=True,
            error=reason,
        )
