"""共享测试 fixtures。"""

from pathlib import Path

import pytest

from testbot.analyzer.project import ProjectAnalyzer


@pytest.fixture
def sample_python_project(tmp_path: Path) -> Path:
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\nA sample API project.", encoding="utf-8")
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "main.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_hello(): assert True\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def sample_analysis(sample_python_project: Path):
    root = sample_python_project
    (root / "main.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
    return ProjectAnalyzer().analyze(root)
