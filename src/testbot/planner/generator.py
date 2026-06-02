"""基于项目分析结果生成测试用例。"""

from __future__ import annotations

import logging

from testbot.config import Settings
from testbot.models.project import ProjectAnalysis, ProjectModule
from testbot.models.testcase import CaseType, TestCaseDraft, TestCaseStep

logger = logging.getLogger(__name__)


class TestCaseGenerator:
    """按标准测试流程，从项目分析结果生成测试用例草稿。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def generate(self, analysis: ProjectAnalysis) -> list[TestCaseDraft]:
        cases: list[TestCaseDraft] = []
        cases.extend(self._smoke_cases(analysis))
        cases.extend(self._module_cases(analysis))
        cases.extend(self._entry_point_cases(analysis))
        cases.extend(self._existing_test_cases(analysis))
        logger.info("已生成 %d 条测试用例草稿", len(cases))
        return cases

    def _base_defaults(self) -> dict:
        if not self.settings:
            return {"pri": 3, "type": CaseType.FEATURE}
        return {
            "pri": self.settings.default_case_priority,
            "type": self.settings.default_case_type,
            "project": self.settings.zentao_project_id or None,
            "execution": self.settings.zentao_execution_id or None,
            "module": self.settings.zentao_module_id or None,
        }

    def _smoke_cases(self, analysis: ProjectAnalysis) -> list[TestCaseDraft]:
        defaults = self._base_defaults()
        steps = [
            TestCaseStep(
                action=f"进入项目目录 {analysis.project_name}，确认依赖已安装",
                expect="依赖安装成功，无报错",
            ),
            TestCaseStep(
                action="执行项目构建/启动命令（如有）",
                expect="构建或启动成功",
            ),
            TestCaseStep(
                action="访问主要入口或运行主程序",
                expect="程序正常响应，无崩溃",
            ),
        ]
        precondition = "测试环境已就绪"
        if analysis.readme_summary:
            precondition += f"；参考 README: {analysis.readme_summary[:200]}"

        return [
            TestCaseDraft(
                title=f"[冒烟] {analysis.project_name} 基本可用性验证",
                precondition=precondition,
                steps=steps,
                source="smoke",
                module_name="冒烟测试",
                **defaults,
            )
        ]

    def _module_cases(self, analysis: ProjectAnalysis) -> list[TestCaseDraft]:
        defaults = self._base_defaults()
        cases: list[TestCaseDraft] = []

        for module in analysis.modules:
            cases.append(self._module_case(module, analysis, defaults))

        return cases

    def _module_case(
        self,
        module: ProjectModule,
        analysis: ProjectAnalysis,
        defaults: dict,
    ) -> TestCaseDraft:
        if module.kind == "api":
            steps = [
                TestCaseStep(
                    action=f"调用 {module.path} 下的主要 API 接口",
                    expect="接口返回预期状态码与数据结构",
                ),
                TestCaseStep(
                    action="传入非法/边界参数",
                    expect="接口返回合理错误信息，不导致服务崩溃",
                ),
            ]
            case_type = CaseType.INTERFACE
        else:
            steps = [
                TestCaseStep(
                    action=f"定位并阅读模块 {module.path}",
                    expect="模块结构清晰，职责明确",
                ),
                TestCaseStep(
                    action=f"针对 {module.name} 的核心功能进行验证",
                    expect="功能行为符合设计预期",
                ),
                TestCaseStep(
                    action="验证异常输入或边界条件",
                    expect="系统正确处理异常，无未捕获错误",
                ),
            ]
            case_type = CaseType.FEATURE

        return TestCaseDraft(
            title=f"[{module.kind}] {module.name} 功能验证",
            precondition=f"项目 {analysis.project_name} 已部署/可运行；语言: {analysis.language}",
            steps=steps,
            type=case_type,
            source=module.path,
            module_name=module.name,
            **{k: v for k, v in defaults.items() if k != "type"},
        )

    def _entry_point_cases(self, analysis: ProjectAnalysis) -> list[TestCaseDraft]:
        if not analysis.entry_points:
            return []

        defaults = self._base_defaults()
        steps = [
            TestCaseStep(
                action=f"通过入口 {ep} 启动/访问应用",
                expect="入口可用，应用正常初始化",
            )
            for ep in analysis.entry_points[:3]
        ]
        return [
            TestCaseDraft(
                title=f"[入口] {analysis.project_name} 入口点验证",
                precondition="运行环境配置正确",
                steps=steps,
                source="entry_points",
                module_name="入口测试",
                **defaults,
            )
        ]

    def _existing_test_cases(self, analysis: ProjectAnalysis) -> list[TestCaseDraft]:
        if not analysis.existing_tests:
            return []

        defaults = self._base_defaults()
        framework = analysis.test_framework or "自动化测试框架"
        steps = [
            TestCaseStep(
                action=f"使用 {framework} 执行现有测试: {t}",
                expect="测试执行完成，结果可读取",
            )
            for t in analysis.existing_tests[:5]
        ]
        return [
            TestCaseDraft(
                title=f"[回归] {analysis.project_name} 现有自动化测试回归",
                precondition=f"已安装 {framework} 及项目依赖",
                steps=steps,
                type=CaseType.UNIT,
                source="existing_tests",
                module_name="回归测试",
                **{k: v for k, v in defaults.items() if k != "type"},
            )
        ]
