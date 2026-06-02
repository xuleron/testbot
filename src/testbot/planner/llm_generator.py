"""LLM 驱动的测试用例生成器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.llm.prompts import PLAN_SYSTEM, PLAN_USER
from testbot.models.project import ProjectAnalysis
from testbot.models.testcase import CaseType, TestCaseDraft, TestCaseStep, normalize_case_type
from testbot.utils.project_files import collect_source_files

logger = logging.getLogger(__name__)


class LLMCaseItem(BaseModel):
    title: str
    type: CaseType = CaseType.FEATURE
    pri: int = 3
    precondition: str = ""
    source: str = ""
    module_name: str = ""
    steps: list[TestCaseStep]

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> CaseType:
        return normalize_case_type(value)

    @field_validator("pri")
    @classmethod
    def clamp_pri(cls, value: int) -> int:
        return max(1, min(4, value))


class LLMCasesResponse(BaseModel):
    cases: list[LLMCaseItem]


class LLMTestCaseGenerator:
    """使用 LLM 阅读项目并生成测试用例。"""

    def __init__(self, settings: Settings, client: LLMClient | None = None):
        self.settings = settings
        self.client = client or LLMClient(settings)

    def generate(self, analysis: ProjectAnalysis, project_path: Path | None = None) -> list[TestCaseDraft]:
        path = project_path or Path(analysis.project_path)
        files = collect_source_files(
            path,
            max_files=self.settings.llm_context_max_files,
            max_chars=self.settings.llm_context_max_chars,
        )
        source_context = self._format_files(files)
        analysis_json = json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2)

        messages = [
            {"role": "system", "content": PLAN_SYSTEM},
            {
                "role": "user",
                "content": PLAN_USER.format(
                    analysis_json=analysis_json,
                    source_context=source_context,
                    min_cases=self.settings.llm_min_cases,
                    max_cases=self.settings.llm_max_cases,
                ),
            },
        ]

        logger.info("正在调用 LLM 生成测试用例...")
        raw = self.client.chat(messages, json_mode=True)
        data = self.client.parse_json(raw, array_key="cases")
        response = LLMCasesResponse.model_validate(data)

        defaults = self._base_defaults()
        cases: list[TestCaseDraft] = []
        for item in response.cases:
            cases.append(
                TestCaseDraft(
                    title=item.title,
                    steps=item.steps,
                    precondition=item.precondition,
                    pri=item.pri,
                    type=item.type,
                    source=item.source,
                    module_name=item.module_name or item.source,
                    **defaults,
                )
            )

        logger.info("LLM 已生成 %d 条测试用例", len(cases))
        return cases

    def _base_defaults(self) -> dict:
        return {
            "project": self.settings.zentao_project_id or None,
            "execution": self.settings.zentao_execution_id or None,
            "module": self.settings.zentao_module_id or None,
        }

    @staticmethod
    def _format_files(files: list[tuple[str, str]]) -> str:
        parts = []
        for rel, content in files:
            parts.append(f"### {rel}\n```\n{content}\n```")
        return "\n\n".join(parts) if parts else "(无可用源码)"
