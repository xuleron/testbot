"""测试结果汇报。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from testbot.config import Settings, get_settings
from testbot.models.report import CaseExecutionResult, ExecutionReport
from testbot.models.testcase import StepResult, TestStepResult
from testbot.reporter.bug_reporter import build_bug_draft
from testbot.zentao.unified_client import UnifiedZenTaoClient

logger = logging.getLogger(__name__)


class ResultReporter:
    """将执行结果写入本地报告并同步到禅道。"""

    def __init__(self, zentao: UnifiedZenTaoClient | None = None, settings: Settings | None = None):
        self.zentao = zentao
        self.settings = settings or get_settings()

    def build_markdown_report(self, report: ExecutionReport) -> str:
        lines = [
            f"# TestBot 测试报告",
            "",
            f"- **项目**: `{report.project_path}`",
            f"- **开始时间**: {report.started_at.isoformat()}",
            f"- **结束时间**: {report.finished_at.isoformat() if report.finished_at else '-'}",
            f"- **总计**: {report.total}",
            f"- **通过**: {report.passed}",
            f"- **失败**: {report.failed}",
            f"- **阻塞**: {report.blocked}",
            f"- **待执行/跳过**: {report.skipped}",
            f"- **通过率**: {report.pass_rate}%",
            f"- **已提 Bug**: {report.bugs_filed}",
            "",
            "## 用例明细",
            "",
        ]
        for idx, result in enumerate(report.results, 1):
            icon = {
                StepResult.PASS: "✅",
                StepResult.FAIL: "❌",
                StepResult.BLOCKED: "🚫",
                StepResult.NA: "⏳",
            }.get(result.status, "❓")
            auto_tag = " [自动化]" if result.automated else " [手工]"
            lines.append(f"### {idx}. {icon} {result.title}{auto_tag}")
            if result.case_id:
                lines.append(f"- 禅道用例 ID: {result.case_id}")
            if result.bug_id:
                lines.append(f"- 禅道 Bug ID: {result.bug_id}")
            if result.error:
                lines.append(f"- 错误: `{result.error}`")
            if result.duration_ms:
                lines.append(f"- 耗时: {result.duration_ms} ms")
            for step_idx, step in enumerate(result.steps, 1):
                lines.append(f"  - 步骤 {step_idx}: **{step.result.value}** — {step.real[:200]}")
            lines.append("")
        return "\n".join(lines)

    def save_reports(self, report: ExecutionReport, output_dir: Path) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = output_dir / f"report_{timestamp}.json"
        md_path = output_dir / f"report_{timestamp}.md"

        json_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(self.build_markdown_report(report), encoding="utf-8")
        logger.info("报告已保存: %s, %s", json_path, md_path)
        return json_path, md_path

    def sync_to_zentao(
        self,
        report: ExecutionReport,
        case_id_map: dict[str, int] | None = None,
    ) -> int:
        if not self.zentao:
            raise RuntimeError("未配置禅道客户端，无法同步结果")

        case_id_map = case_id_map or {}
        synced = 0
        skipped = 0
        failed = 0
        total = len(report.results)

        for idx, result in enumerate(report.results, 1):
            case_id = result.case_id or case_id_map.get(result.title)
            if not case_id:
                skipped += 1
                continue
            if result.status == StepResult.NA:
                skipped += 1
                continue

            steps = result.steps or [
                TestStepResult(result=result.status, real=result.error or result.status.value)
            ]
            try:
                self.zentao.submit_case_result(case_id, steps)
                synced += 1
                if synced % 25 == 0 or idx == total:
                    logger.info("禅道回写进度: %d/%d 已登记", synced, total)
            except Exception as exc:
                failed += 1
                if failed <= 3:
                    logger.error("同步用例 #%s 失败: %s", case_id, exc)
                elif failed == 4:
                    logger.error("后续同步错误将不再逐条打印...")

        logger.info("禅道回写完成: 成功 %d, 跳过 %d, 失败 %d", synced, skipped, failed)
        return synced

    def file_bugs_to_zentao(
        self,
        report: ExecutionReport,
        case_id_map: dict[str, int] | None = None,
    ) -> int:
        if not self.zentao or not self.settings.zentao_auto_create_bugs:
            return 0

        case_id_map = case_id_map or {}
        filed = 0
        failed = 0
        seen_cases: set[int] = set()

        for result in report.results:
            should_file = result.status == StepResult.FAIL
            if self.settings.zentao_bug_on_blocked and result.status == StepResult.BLOCKED:
                should_file = True
            if not should_file:
                continue

            case_id = result.case_id or case_id_map.get(result.title)
            if case_id and case_id in seen_cases:
                continue
            if case_id:
                seen_cases.add(case_id)

            draft = build_bug_draft(result, self.settings, case_id=case_id)
            try:
                bug_id = self.zentao.create_bug(draft)
                result.bug_id = bug_id or None
                filed += 1
                if filed % 10 == 0:
                    logger.info("Bug 登记进度: 已提交 %d 个", filed)
            except Exception as exc:
                failed += 1
                if failed <= 3:
                    logger.error("提 Bug 失败 (%s): %s", result.title[:50], exc)

        report.bugs_filed = filed
        logger.info("Bug 登记完成: 成功 %d, 失败 %d", filed, failed)
        return filed

    @staticmethod
    def sync_all(
        report: ExecutionReport,
        cases: list,
        zentao: UnifiedZenTaoClient,
        settings: Settings | None = None,
    ) -> tuple[int, int]:
        """回写用例结果并登记 Bug，返回 (结果数, Bug数)。"""
        reporter = ResultReporter(zentao, settings)
        id_map = ResultReporter.map_cases_by_title(cases)
        synced = reporter.sync_to_zentao(report, id_map)
        bugs = reporter.file_bugs_to_zentao(report, id_map)
        return synced, bugs

    @staticmethod
    def map_cases_by_title(cases: list) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for case in cases:
            if getattr(case, "zentao_id", None):
                mapping[case.title] = case.zentao_id
        return mapping
