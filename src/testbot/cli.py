"""TestBot CLI 入口。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from testbot.config import get_settings
from testbot.llm.client import LLMClient, LLMError
from testbot.planner.factory import PlannerMode
from testbot.workflow.pipeline import TestWorkflow
from testbot.zentao.client import ZenTaoError
from testbot.zentao.unified_client import UnifiedZenTaoClient

app = typer.Typer(
    name="testbot",
    help="TestBot — 阅读项目、编写用例、执行测试、汇报结果（禅道 + LLM）",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_workflow(mode: str | None = None) -> TestWorkflow:
    settings = get_settings()
    planner_mode = mode or settings.planner_mode
    return TestWorkflow(settings, planner_mode=planner_mode)


def _resolve_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    try:
        return PlannerMode(mode).value
    except ValueError as exc:
        raise typer.BadParameter("mode 只能是 llm | rule | full") from exc


@app.command("analyze")
def analyze_cmd(
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="被测项目路径"),
    no_llm: bool = typer.Option(False, "--no-llm", help="跳过 LLM 深度分析"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="规划模式: llm | rule | full"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """阶段1: 分析被测项目（结构扫描 + LLM 理解）。"""
    _setup_logging(verbose)
    workflow = _get_workflow(_resolve_mode(mode))
    path = workflow.settings.resolve_target_path(str(project) if project else None)
    analysis = workflow.analyze(path, use_llm=not no_llm)
    out = workflow.save_analysis(analysis)

    table = Table(title="项目分析结果")
    table.add_column("项", style="cyan")
    table.add_column("值")
    table.add_row("项目名称", analysis.project_name)
    table.add_row("路径", analysis.project_path)
    table.add_row("语言", analysis.language)
    table.add_row("框架", analysis.framework or "-")
    table.add_row("测试框架", analysis.test_framework or "-")
    table.add_row("模块数", str(len(analysis.modules)))
    table.add_row("现有测试", str(len(analysis.existing_tests)))
    if analysis.llm_summary:
        table.add_row("LLM 摘要", analysis.llm_summary[:120] + "...")
        table.add_row("测试重点", ", ".join(analysis.test_focus[:5]) or "-")
    table.add_row("分析报告", str(out))
    console.print(table)


@app.command("plan")
def plan_cmd(
    project: Optional[Path] = typer.Option(None, "--project", "-p"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="用例草稿输出路径"),
    no_llm: bool = typer.Option(False, "--no-llm", help="跳过 LLM 深度分析"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="规划模式: llm | rule | full"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """阶段2: 使用 LLM 生成测试用例草稿。"""
    _setup_logging(verbose)
    workflow = _get_workflow(_resolve_mode(mode))
    path = workflow.settings.resolve_target_path(str(project) if project else None)

    try:
        analysis = workflow.analyze(path, use_llm=not no_llm)
        cases = workflow.plan(analysis, path)
    except LLMError as exc:
        console.print(f"[red]LLM 生成失败: {exc}[/red]")
        raise typer.Exit(1) from exc

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        import json

        output.write_text(
            json.dumps([c.model_dump(mode="json") for c in cases], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        out = output
    else:
        out = workflow.save_cases_draft(cases)

    mode_label = workflow.planner.mode.value
    console.print(f"[green]已生成 {len(cases)} 条测试用例[/green] (模式: {mode_label})")
    console.print(f"保存至: {out}")
    for i, case in enumerate(cases[:10], 1):
        console.print(f"  {i}. {case.title}")
    if len(cases) > 10:
        console.print(f"  ... 共 {len(cases)} 条")


@app.command("sync")
def sync_cmd(
    cases_file: Path = typer.Argument(..., help="用例草稿 JSON 文件"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """阶段3: 将测试用例同步到禅道。"""
    _setup_logging(verbose)
    workflow = _get_workflow()
    cases = workflow.load_cases_draft(cases_file)

    try:
        synced = workflow.sync_cases_to_zentao(cases)
    except ZenTaoError as exc:
        console.print(f"[red]禅道同步失败: {exc}[/red]")
        raise typer.Exit(1) from exc

    synced_path = workflow.save_cases_draft(synced)

    console.print(f"[green]已同步 {len(synced)} 条用例到禅道[/green]")
    console.print(f"已保存同步记录: {synced_path}")
    for case in synced:
        console.print(f"  #{case.zentao_id} {case.title}")


@app.command("run")
def run_cmd(
    project: Optional[Path] = typer.Option(None, "--project", "-p"),
    cases_file: Optional[Path] = typer.Option(None, "--cases", "-c", help="已同步的用例文件（含 zentao_id）"),
    sync: bool = typer.Option(False, "--sync", help="执行后将结果回写禅道"),
    executor: Optional[str] = typer.Option(None, "--executor", "-e", help="执行模式: auto | llm | framework | playwright"),
    no_automation: bool = typer.Option(False, "--no-automation", help="跳过 npm/pytest 等框架测试"),
    no_llm: bool = typer.Option(False, "--no-llm", help="跳过 LLM 深度分析"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="规划模式: llm | rule | full"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """阶段4: 执行测试（LLM 自动判定 + 可选回写禅道）。"""
    _setup_logging(verbose)
    workflow = _get_workflow(_resolve_mode(mode))
    path = workflow.settings.resolve_target_path(str(project) if project else None)

    try:
        analysis = workflow.analyze(path, use_llm=not no_llm)
        if cases_file:
            cases = workflow.load_cases_draft(cases_file)
            console.print(f"已加载 {len(cases)} 条用例: {cases_file}")
        else:
            cases = workflow.plan(analysis, path)
    except LLMError as exc:
        console.print(f"[red]LLM 失败: {exc}[/red]")
        raise typer.Exit(1) from exc

    exec_mode = executor or workflow.settings.executor_mode
    report = workflow.execute(
        analysis,
        cases,
        run_automation=not no_automation,
        executor_mode=exec_mode,
    )
    paths, synced, bugs = workflow.report(report, cases, sync_zentao=sync)

    console.print(f"[green]执行完成[/green] 通过率: {report.pass_rate}%")
    console.print(f"通过 {report.passed} / 失败 {report.failed} / 阻塞 {report.blocked} / 待测 {report.skipped}")
    if sync:
        console.print(f"[green]禅道已登记 {synced} 条结果[/green]")
        if bugs:
            console.print(f"[green]禅道已提 {bugs} 个 Bug[/green]")
    console.print(f"JSON 报告: {paths[0]}")
    console.print(f"Markdown 报告: {paths[1]}")


@app.command("execute")
def execute_cmd(
    cases_file: Path = typer.Argument(..., help="含 zentao_id 的用例 JSON"),
    project: Optional[Path] = typer.Option(None, "--project", "-p"),
    sync: bool = typer.Option(True, "--sync/--no-sync", help="是否回写禅道"),
    executor: Optional[str] = typer.Option(None, "--executor", "-e", help="执行模式: auto | llm | framework | playwright"),
    no_automation: bool = typer.Option(False, "--no-automation"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """对已同步禅道的用例执行测试并登记结果（不重生成用例）。"""
    _setup_logging(verbose)
    workflow = _get_workflow()
    path = workflow.settings.resolve_target_path(str(project) if project else None)
    cases = workflow.load_cases_draft(cases_file)
    console.print(f"加载 {len(cases)} 条用例，其中 {sum(1 for c in cases if c.zentao_id)} 条已关联禅道")

    analysis = workflow.analyze(path, use_llm=False)
    exec_mode = executor or workflow.settings.executor_mode
    report = workflow.execute(
        analysis,
        cases,
        run_automation=not no_automation,
        executor_mode=exec_mode,
    )
    paths, synced, bugs = workflow.report(report, cases, sync_zentao=sync)

    table = Table(title="执行结果")
    table.add_column("项")
    table.add_column("值")
    table.add_row("总计", str(report.total))
    table.add_row("通过", str(report.passed))
    table.add_row("失败", str(report.failed))
    table.add_row("阻塞", str(report.blocked))
    table.add_row("待测", str(report.skipped))
    table.add_row("通过率", f"{report.pass_rate}%")
    if sync:
        table.add_row("禅道结果登记", str(synced))
        table.add_row("禅道 Bug", str(bugs))
    table.add_row("报告", str(paths[1]))
    console.print(table)


@app.command("report")
def report_cmd(
    cases_file: Path = typer.Argument(..., help="含 zentao_id 的用例文件"),
    report_file: Path = typer.Argument(..., help="执行报告 JSON 文件"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """阶段5: 将执行结果回写禅道。"""
    _setup_logging(verbose)
    import json

    from testbot.models.report import ExecutionReport
    from testbot.models.testcase import TestCaseDraft

    workflow = _get_workflow()
    cases = [TestCaseDraft.model_validate(c) for c in json.loads(cases_file.read_text(encoding="utf-8"))]
    report = ExecutionReport.model_validate(json.loads(report_file.read_text(encoding="utf-8")))

    try:
        _, synced, bugs = workflow.report(report, cases, sync_zentao=True)
    except ZenTaoError as exc:
        console.print(f"[red]结果回写失败: {exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]已回写 {synced} 条用例结果到禅道[/green]")
    if bugs:
        console.print(f"[green]已登记 {bugs} 个 Bug 到禅道[/green]")


@app.command("full")
def full_cmd(
    project: Optional[Path] = typer.Option(None, "--project", "-p"),
    no_sync: bool = typer.Option(False, "--no-sync", help="不同步禅道"),
    no_automation: bool = typer.Option(False, "--no-automation"),
    no_llm: bool = typer.Option(False, "--no-llm", help="跳过 LLM，使用规则模式"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="规划模式: llm | rule | full"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """一键执行完整测试流程: 分析 → LLM 写用例 → 执行 → 汇报。"""
    _setup_logging(verbose)
    resolved_mode = "rule" if no_llm else _resolve_mode(mode)
    workflow = _get_workflow(resolved_mode)

    try:
        result = workflow.run_full(
            workflow.settings.resolve_target_path(str(project) if project else None),
            sync_cases=not no_sync,
            run_automation=not no_automation,
            sync_results=not no_sync,
            use_llm=not no_llm,
        )
    except ZenTaoError as exc:
        console.print(f"[red]流程中断（禅道错误）: {exc}[/red]")
        raise typer.Exit(1) from exc
    except LLMError as exc:
        console.print(f"[red]流程中断（LLM 错误）: {exc}[/red]")
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        console.print(f"[red]项目路径错误: {exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title="TestBot 全流程结果")
    table.add_column("指标")
    table.add_column("值", style="green")
    table.add_row("项目", result.analysis.project_name)
    table.add_row("规划模式", workflow.planner.mode.value)
    table.add_row("生成用例", str(len(result.cases)))
    if result.report:
        table.add_row("执行总数", str(result.report.total))
        table.add_row("通过", str(result.report.passed))
        table.add_row("失败", str(result.report.failed))
        table.add_row("通过率", f"{result.report.pass_rate}%")
    table.add_row("禅道回写", str(result.synced_count))
    table.add_row("禅道 Bug", str(result.bugs_filed))
    if result.report_paths:
        table.add_row("报告", str(result.report_paths[1]))
    console.print(table)


@app.command("check-zentao")
def check_zentao_cmd(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """验证禅道连接与配置。"""
    _setup_logging(verbose)
    settings = get_settings()
    console.print(f"禅道地址: {settings.zentao_api_base}")
    console.print(f"项目 ID: {settings.zentao_project_id}")
    if settings.zentao_product_id:
        console.print(f"产品 ID: {settings.zentao_product_id}")
    auth_hint = settings.zentao_auth_mode or "auto"
    if settings.zentao_app_code:
        console.print(f"认证方式: 应用签名 (code={settings.zentao_app_code})")
    elif auth_hint == "session":
        console.print("认证方式: Session 网页登录（适用于禅道 12.x，无需创建应用）")
    else:
        console.print("认证方式: 自动（12.x 使用 Session，16.5+ 使用 REST）")

    try:
        client = UnifiedZenTaoClient(settings)
        token = client.authenticate()
        mode = client.mode
        if mode.startswith("session"):
            console.print(f"[green]连接成功[/green] Session 登录 ({mode})")
        else:
            console.print(f"[green]连接成功[/green] Token: {token[:8]}...")
        ctx = client.context
        console.print(f"[green]已解析[/green] 项目 #{ctx.project_id} → 产品 #{ctx.product_id}")
        modules = client.list_case_modules(ctx.product_id)
        count = len(modules.get("modules", modules)) if isinstance(modules, dict) else 0
        if isinstance(modules, dict) and "modules" not in modules:
            count = len(modules)
        console.print(f"[green]用例模块[/green] 已读取 {count} 个")
    except ZenTaoError as exc:
        console.print(f"[red]连接失败: {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("check-llm")
def check_llm_cmd(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """验证 LLM API 连接与配置。"""
    _setup_logging(verbose)
    settings = get_settings()

    from testbot.llm.providers import resolve_llm_config

    try:
        config = resolve_llm_config(settings)
    except ValueError as exc:
        console.print(f"[red]配置错误: {exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"服务商: {config.provider} ({config.description})")
    console.print(f"API 地址: {config.api_base}")
    console.print(f"模型: {config.model}")
    console.print(f"规划模式: {settings.planner_mode}")
    console.print(f"JSON 模式: {'支持' if config.supports_json_mode else '不支持'}")

    try:
        client = LLMClient(settings)
        status = client.ping()
        console.print(f"[green]LLM 连接成功[/green] 响应: {status}")
    except LLMError as exc:
        console.print(f"[red]LLM 连接失败: {exc}[/red]")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
