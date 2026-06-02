"""项目文件扫描工具。"""

from __future__ import annotations

from pathlib import Path

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
    ".idea",
    ".vscode",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "htmlcov",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".java",
    ".rs",
    ".cs",
    ".vue",
    ".sql",
}

CONFIG_FILES = {
    "README.md",
    "readme.md",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "docker-compose.yml",
    "Dockerfile",
    "openapi.yaml",
    "openapi.json",
    "swagger.yaml",
    "swagger.json",
}


def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def collect_source_files(
    root: Path,
    *,
    max_files: int = 30,
    max_chars: int = 80000,
) -> list[tuple[str, str]]:
    """收集项目源码与配置文件，返回 (相对路径, 内容) 列表。"""
    candidates: list[tuple[int, str, Path]] = []

    for name in CONFIG_FILES:
        path = root / name
        if path.is_file() and not is_ignored(path.relative_to(root)):
            candidates.append((0, name, path))

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if is_ignored(rel):
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if "test" in path.stem.lower() and path.suffix == ".py":
            priority = 3
        elif any(k in str(rel).lower() for k in ("route", "api", "controller", "service", "handler")):
            priority = 1
        elif path.name in ("main.py", "app.py", "index.ts", "index.js"):
            priority = 1
        else:
            priority = 2
        candidates.append((priority, str(rel).replace("\\", "/"), path))

    candidates.sort(key=lambda item: (item[0], len(str(item[2]))))
    selected: list[tuple[str, str]] = []
    total_chars = 0

    for _, rel, path in candidates:
        if len(selected) >= max_files:
            break
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not content.strip():
            continue
        if total_chars + len(content) > max_chars:
            remaining = max_chars - total_chars
            if remaining < 500:
                break
            content = content[:remaining] + "\n# ... (truncated)"
        selected.append((rel, content))
        total_chars += len(content)

    return selected


def collect_files_for_sources(
    root: Path,
    source_hints: list[str],
    *,
    max_files: int = 20,
    max_chars: int = 60000,
) -> list[tuple[str, str]]:
    """按功能点关联路径收集源码，用于分批生成用例。"""
    hints = [h.replace("\\", "/").strip("/") for h in source_hints if h and h.strip()]
    if not hints:
        return collect_source_files(root, max_files=max_files, max_chars=max_chars)

    candidates: list[tuple[int, str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if is_ignored(Path(rel)):
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS and path.name not in CONFIG_FILES:
            continue
        matched = any(h in rel or rel.startswith(h) or h in path.stem for h in hints)
        if not matched:
            continue
        priority = 1 if any(k in rel.lower() for k in ("route", "api", "controller", "view")) else 2
        candidates.append((priority, rel, path))

    if not candidates:
        return collect_source_files(root, max_files=max_files, max_chars=max_chars)

    candidates.sort(key=lambda item: (item[0], len(item[1])))
    selected: list[tuple[str, str]] = []
    total_chars = 0
    for _, rel, path in candidates:
        if len(selected) >= max_files:
            break
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not content.strip():
            continue
        if total_chars + len(content) > max_chars:
            remaining = max_chars - total_chars
            if remaining < 500:
                break
            content = content[:remaining] + "\n# ... (truncated)"
        selected.append((rel, content))
        total_chars += len(content)
    return selected
