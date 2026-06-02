"""失败用例 → 禅道 Bug 转换。"""

from __future__ import annotations

from testbot.config import Settings
from testbot.models.bug import BugDraft
from testbot.models.report import CaseExecutionResult


def build_bug_draft(
    result: CaseExecutionResult,
    settings: Settings,
    *,
    case_id: int | None = None,
) -> BugDraft:
    title = f"[TestBot] {result.title}"[:255]
    lines = [
        f"用例: {result.title}",
        f"执行结果: {result.status.value}",
    ]
    if case_id:
        lines.append(f"禅道用例 ID: {case_id}")
    if result.error:
        lines.append(f"错误信息: {result.error}")
    lines.append("")
    lines.append("步骤详情:")
    for idx, step in enumerate(result.steps, 1):
        lines.append(f"  {idx}. [{step.result.value}] {step.real}")
    lines.append("")
    lines.append("---")
    lines.append("由 TestBot 自动登记")

    return BugDraft(
        title=title,
        steps="\n".join(lines),
        product_id=settings.zentao_product_id,
        project_id=settings.zentao_project_id,
        case_id=case_id,
        type=settings.zentao_bug_type,
        severity=settings.zentao_bug_severity,
        pri=settings.zentao_bug_pri,
        opened_build=settings.zentao_opened_build,
    )
