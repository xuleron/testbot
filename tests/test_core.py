"""TestBot 单元测试。"""

from pathlib import Path

import pytest

from testbot.analyzer.project import ProjectAnalyzer
from testbot.config import Settings
from testbot.models.testcase import CaseType, TestCaseDraft, TestCaseStep
from testbot.planner.generator import TestCaseGenerator


def test_analyze_python_project(sample_python_project: Path):
    analyzer = ProjectAnalyzer()
    analysis = analyzer.analyze(sample_python_project)

    assert analysis.project_name == sample_python_project.name
    assert analysis.language == "python"
    assert analysis.test_framework == "pytest"
    assert len(analysis.existing_tests) >= 1


def test_generate_test_cases(sample_python_project: Path):
    settings = Settings(
        TARGET_PROJECT_PATH=str(sample_python_project),
        DEFAULT_CASE_PRIORITY=3,
        DEFAULT_CASE_TYPE=CaseType.FEATURE,
    )
    analyzer = ProjectAnalyzer()
    analysis = analyzer.analyze(sample_python_project)
    generator = TestCaseGenerator(settings)
    cases = generator.generate(analysis)

    assert len(cases) >= 2
    assert any("[冒烟]" in c.title for c in cases)
    assert all(isinstance(c, TestCaseDraft) for c in cases)
    assert all(len(c.steps) >= 1 for c in cases)


def test_testcase_draft_model():
    draft = TestCaseDraft(
        title="示例用例",
        steps=[TestCaseStep(action="操作", expect="预期")],
    )
    assert draft.title == "示例用例"
    assert draft.steps[0].action == "操作"
