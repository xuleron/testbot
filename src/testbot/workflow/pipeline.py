"""TestBot 标准测试工作流。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from testbot.analyzer.llm_analyzer import LLMProjectAnalyzer
from testbot.analyzer.project import ProjectAnalyzer
from testbot.config import Settings
from testbot.executor.runner import TestExecutor
from testbot.models.project import ProjectAnalysis
from testbot.models.report import ExecutionReport
from testbot.models.testcase import TestCaseDraft
from testbot.planner.factory import CasePlanner, PlannerMode
from testbot.reporter.zentao_reporter import ResultReporter
from testbot.zentao.module_manager import ModuleManager
from testbot.zentao.unified_client import UnifiedZenTaoClient

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    analysis: ProjectAnalysis
    cases: list[TestCaseDraft] = field(default_factory=list)
    report: ExecutionReport | None = None
    report_paths: tuple[Path, Path] | None = None
    synced_count: int = 0
    bugs_filed: int = 0


class TestWorkflow:
    """
    标准测试流程:
    1. 分析被测项目（结构扫描 + LLM 理解）
    2. LLM 设计并生成测试用例
    3. 同步用例到禅道
    4. 执行测试
    5. 生成报告并回写禅道
    """

    def __init__(self, settings: Settings, planner_mode: PlannerMode | str | None = None):
        self.settings = settings
        self.analyzer = ProjectAnalyzer()
        self.llm_analyzer = LLMProjectAnalyzer(settings)
        self.planner = CasePlanner(settings, mode=planner_mode)
        self.executor = TestExecutor(settings)
        self.reporter = ResultReporter()
        self._zentao: UnifiedZenTaoClient | None = None

    @property
    def zentao(self) -> UnifiedZenTaoClient:
        if self._zentao is None:
            self._zentao = UnifiedZenTaoClient(self.settings)
            self.reporter.zentao = self._zentao
            self.reporter.settings = self.settings
        return self._zentao

    def analyze(self, project_path: Path | None = None, *, use_llm: bool | None = None) -> ProjectAnalysis:
        path = project_path or self.settings.resolve_target_path()
        analysis = self.analyzer.analyze(path)

        should_use_llm = self.settings.use_llm_analyze if use_llm is None else use_llm
        if should_use_llm and self.planner.mode in (PlannerMode.LLM, PlannerMode.FULL):
            analysis = self.llm_analyzer.enrich(analysis, path)
        return analysis

    def plan(self, analysis: ProjectAnalysis, project_path: Path | None = None) -> list[TestCaseDraft]:
        path = project_path or Path(analysis.project_path)
        return self.planner.generate(analysis, path)

    def sync_cases_to_zentao(self, cases: list[TestCaseDraft]) -> list[TestCaseDraft]:
        ctx = self.zentao.context
        logger.info(
            "禅道上下文: 项目 #%s, 产品 #%s",
            ctx.project_id,
            ctx.product_id,
        )

        module_mgr: ModuleManager | None = None
        if self.settings.zentao_auto_create_modules:
            module_mgr = ModuleManager(self.zentao, ctx.product_id)
            module_mgr.prepare(ModuleManager.collect_module_names(cases))

        synced: list[TestCaseDraft] = []
        for case in cases:
            module_id = 0
            if module_mgr:
                module_id = module_mgr.resolve(case.module_name, source=case.source)
            elif case.module is not None:
                module_id = case.module
            elif self.settings.zentao_module_id:
                module_id = self.settings.zentao_module_id

            case_id = self.zentao.create_testcase(case, module_id=module_id)
            updated = case.model_copy(update={"zentao_id": case_id, "module": module_id})
            synced.append(updated)
        return synced

    def execute(
        self,
        analysis: ProjectAnalysis,
        cases: list[TestCaseDraft],
        *,
        run_automation: bool = True,
        executor_mode: str | None = None,
    ) -> ExecutionReport:
        return self.executor.execute(
            analysis,
            cases,
            run_automation=run_automation,
            executor_mode=executor_mode,
        )

    def report(
        self,
        execution_report: ExecutionReport,
        cases: list[TestCaseDraft],
        *,
        sync_zentao: bool = True,
    ) -> tuple[tuple[Path, Path], int, int]:
        output_dir = self.settings.ensure_report_dir()
        synced = 0
        bugs = 0
        if sync_zentao:
            synced, bugs = ResultReporter.sync_all(
                execution_report, cases, self.zentao, self.settings
            )
            execution_report.bugs_filed = bugs
        paths = self.reporter.save_reports(execution_report, output_dir)
        return paths, synced, bugs

    def run_full(
        self,
        project_path: Path | None = None,
        *,
        sync_cases: bool = True,
        run_automation: bool = True,
        sync_results: bool = True,
        use_llm: bool | None = None,
    ) -> WorkflowResult:
        logger.info("=== TestBot 全流程开始 ===")
        path = project_path or self.settings.resolve_target_path()

        analysis = self.analyze(path, use_llm=use_llm)
        cases = self.plan(analysis, path)

        if sync_cases:
            logger.info("正在同步 %d 条用例到禅道...", len(cases))
            cases = self.sync_cases_to_zentao(cases)

        execution_report = self.execute(analysis, cases, run_automation=run_automation)
        report_paths, synced, bugs = self.report(
            execution_report,
            cases,
            sync_zentao=sync_results and sync_cases,
        )

        logger.info("=== TestBot 全流程完成 ===")
        return WorkflowResult(
            analysis=analysis,
            cases=cases,
            report=execution_report,
            report_paths=report_paths,
            synced_count=synced,
            bugs_filed=bugs,
        )

    def save_analysis(self, analysis: ProjectAnalysis, output_dir: Path | None = None) -> Path:
        out = output_dir or self.settings.ensure_report_dir()
        path = out / f"analysis_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(
            json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def save_cases_draft(self, cases: list[TestCaseDraft], output_dir: Path | None = None) -> Path:
        out = output_dir or self.settings.ensure_report_dir()
        path = out / f"cases_{datetime.now():%Y%m%d_%H%M%S}.json"
        payload = [c.model_dump(mode="json") for c in cases]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_cases_draft(self, path: Path) -> list[TestCaseDraft]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TestCaseDraft.model_validate(item) for item in data]
