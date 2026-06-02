"""测试用例生成器工厂。"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from testbot.config import Settings
from testbot.llm.client import LLMClient
from testbot.models.project import ProjectAnalysis
from testbot.models.testcase import TestCaseDraft
from testbot.planner.full_coverage import FullCoverageGenerator
from testbot.planner.generator import TestCaseGenerator
from testbot.planner.llm_generator import LLMTestCaseGenerator


class PlannerMode(str, Enum):
    LLM = "llm"
    RULE = "rule"
    FULL = "full"


class CasePlanner:
    """统一用例规划入口，默认使用 LLM。"""

    def __init__(self, settings: Settings, mode: PlannerMode | str | None = None):
        self.settings = settings
        raw_mode = mode or settings.planner_mode
        self.mode = PlannerMode(raw_mode)
        self._llm_client: LLMClient | None = None

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient(self.settings)
        return self._llm_client

    def generate(self, analysis: ProjectAnalysis, project_path: Path | None = None) -> list[TestCaseDraft]:
        if self.mode == PlannerMode.FULL:
            generator = FullCoverageGenerator(self.settings, self.llm_client)
            return generator.generate(analysis, project_path)
        if self.mode == PlannerMode.LLM:
            generator = LLMTestCaseGenerator(self.settings, self.llm_client)
            return generator.generate(analysis, project_path)
        generator = TestCaseGenerator(self.settings)
        return generator.generate(analysis)
