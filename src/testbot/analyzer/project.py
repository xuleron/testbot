"""被测项目分析器。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from testbot.models.project import ProjectAnalysis, ProjectModule

logger = logging.getLogger(__name__)

LANGUAGE_HINTS: dict[str, list[str]] = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "javascript": ["package.json"],
    "typescript": ["tsconfig.json"],
    "java": ["pom.xml", "build.gradle"],
    "go": ["go.mod"],
    "rust": ["Cargo.toml"],
    "csharp": ["*.csproj", "*.sln"],
}

TEST_FRAMEWORK_HINTS: dict[str, list[str]] = {
    "pytest": ["pytest.ini", "conftest.py"],
    "unittest": [],
    "jest": ["jest.config.js", "jest.config.ts"],
    "vitest": ["vitest.config.ts"],
    "mocha": [".mocharc.json"],
    "junit": [],
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".reports",
    ".testbot",
}


class ProjectAnalyzer:
    """扫描被测项目，提取结构、语言、现有测试等信息。"""

    def analyze(self, project_path: Path) -> ProjectAnalysis:
        if not project_path.exists():
            raise FileNotFoundError(f"项目路径不存在: {project_path}")
        if not project_path.is_dir():
            raise NotADirectoryError(f"项目路径不是目录: {project_path}")

        language = self._detect_language(project_path)
        test_framework = self._detect_test_framework(project_path, language)
        framework = self._detect_app_framework(project_path, language)
        modules = self._scan_modules(project_path, language)
        existing_tests = self._find_existing_tests(project_path, language)
        entry_points = self._find_entry_points(project_path, language)
        dependencies = self._read_dependencies(project_path, language)
        readme_summary = self._read_readme(project_path)

        analysis = ProjectAnalysis(
            project_path=str(project_path),
            project_name=project_path.name,
            language=language,
            framework=framework,
            test_framework=test_framework,
            readme_summary=readme_summary,
            modules=modules,
            existing_tests=existing_tests,
            entry_points=entry_points,
            dependencies=dependencies,
        )
        logger.info(
            "项目分析完成: %s (%s), 模块 %d 个, 现有测试 %d 个",
            analysis.project_name,
            language,
            len(modules),
            len(existing_tests),
        )
        return analysis

    def _detect_language(self, root: Path) -> str:
        for lang, markers in LANGUAGE_HINTS.items():
            for marker in markers:
                if "*" in marker:
                    if list(root.glob(marker)):
                        return lang
                elif (root / marker).exists():
                    return lang
        py_files = list(root.rglob("*.py"))
        if py_files:
            return "python"
        js_files = list(root.rglob("*.ts")) + list(root.rglob("*.js"))
        if js_files:
            return "javascript"
        return "unknown"

    def _detect_test_framework(self, root: Path, language: str) -> str:
        for framework, markers in TEST_FRAMEWORK_HINTS.items():
            for marker in markers:
                if (root / marker).exists():
                    return framework
        if language == "python":
            req = root / "requirements.txt"
            if req.exists() and "pytest" in req.read_text(encoding="utf-8", errors="ignore"):
                return "pytest"
        if language in ("javascript", "typescript"):
            pkg = root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8"))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    for name in ("jest", "vitest", "mocha"):
                        if name in deps:
                            return name
                except json.JSONDecodeError:
                    pass
        return ""

    def _detect_app_framework(self, root: Path, language: str) -> str:
        if language == "python":
            for name in ("django", "flask", "fastapi"):
                req = root / "requirements.txt"
                if req.exists() and name in req.read_text(encoding="utf-8", errors="ignore").lower():
                    return name
            if (root / "manage.py").exists():
                return "django"
        if language in ("javascript", "typescript"):
            pkg = root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8"))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    for name in ("next", "react", "vue", "express", "nestjs"):
                        if name in deps:
                            return name
                except json.JSONDecodeError:
                    pass
        return ""

    def _scan_modules(self, root: Path, language: str) -> list[ProjectModule]:
        modules: list[ProjectModule] = []

        if language == "python":
            for candidate in ("src", "app", root.name):
                base = root / candidate
                if base.is_dir() and candidate != root.name or (candidate == root.name and base == root):
                    if candidate == root.name:
                        base = root
                    for item in sorted(base.iterdir()):
                        if item.name.startswith(".") or item.name in IGNORE_DIRS:
                            continue
                        if item.is_dir() and (item / "__init__.py").exists():
                            modules.append(
                                ProjectModule(
                                    name=item.name,
                                    path=str(item.relative_to(root)),
                                    kind="package",
                                    summary=f"Python 包: {item.name}",
                                )
                            )
                        elif item.suffix == ".py" and item.name not in ("__init__.py", "setup.py"):
                            modules.append(
                                ProjectModule(
                                    name=item.stem,
                                    path=str(item.relative_to(root)),
                                    kind="module",
                                    summary=f"Python 模块: {item.name}",
                                )
                            )
                    if modules:
                        break

        elif language in ("javascript", "typescript"):
            for candidate in ("src", "app", "lib"):
                base = root / candidate
                if base.is_dir():
                    for item in sorted(base.rglob("*")):
                        if any(p.name in IGNORE_DIRS for p in item.parents):
                            continue
                        if item.is_file() and item.suffix in (".ts", ".tsx", ".js", ".jsx"):
                            rel = item.relative_to(root)
                            if "test" in item.stem.lower() or ".spec." in item.name:
                                continue
                            modules.append(
                                ProjectModule(
                                    name=item.stem,
                                    path=str(rel),
                                    kind="source",
                                    summary=f"源文件: {rel}",
                                )
                            )
                    if modules:
                        break

        # 通用：API 路由目录
        for api_dir in root.rglob("api"):
            if api_dir.is_dir() and api_dir.parent.name in ("src", "app", root.name):
                rel = api_dir.relative_to(root)
                modules.append(
                    ProjectModule(
                        name="api",
                        path=str(rel),
                        kind="api",
                        summary="API 路由目录",
                    )
                )
                break

        return modules[:50]

    def _find_existing_tests(self, root: Path, language: str) -> list[str]:
        patterns: list[str] = []
        if language == "python":
            patterns = ["test_*.py", "*_test.py"]
        elif language in ("javascript", "typescript"):
            patterns = ["*.test.ts", "*.test.js", "*.spec.ts", "*.spec.js"]

        tests: list[str] = []
        for pattern in patterns:
            for path in root.rglob(pattern):
                if any(p.name in IGNORE_DIRS for p in path.parents):
                    continue
                tests.append(str(path.relative_to(root)))
        return sorted(tests)[:100]

    def _find_entry_points(self, root: Path, language: str) -> list[str]:
        candidates = [
            "main.py",
            "app.py",
            "manage.py",
            "index.js",
            "index.ts",
            "main.go",
            "src/main.py",
            "src/index.ts",
        ]
        found = []
        for name in candidates:
            path = root / name
            if path.exists():
                found.append(name)
        return found

    def _read_dependencies(self, root: Path, language: str) -> list[str]:
        deps: list[str] = []
        if language == "python":
            for fname in ("requirements.txt", "requirements-dev.txt"):
                path = root / fname
                if path.exists():
                    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            deps.append(line.split("==")[0].split(">=")[0].strip())
        elif language in ("javascript", "typescript"):
            pkg = root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8"))
                    deps = list(data.get("dependencies", {}).keys())[:30]
                except json.JSONDecodeError:
                    pass
        return deps

    def _read_readme(self, root: Path) -> str:
        for name in ("README.md", "README.rst", "README.txt", "readme.md"):
            path = root / name
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")
                text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
                text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
                return text[:2000].strip()
        return ""
