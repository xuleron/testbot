"""禅道用例模块自动管理。"""

from __future__ import annotations

import logging
import re
from typing import Any

from testbot.zentao.client import ZenTaoError
from testbot.zentao.unified_client import UnifiedZenTaoClient

logger = logging.getLogger(__name__)

SPECIAL_MODULES = {
    "smoke": "冒烟测试",
    "entry_points": "入口测试",
    "existing_tests": "回归测试",
}


class ModuleManager:
    """根据被测系统模块，在禅道用例库中自动创建/匹配模块。"""

    def __init__(self, client: UnifiedZenTaoClient, product_id: int):
        self.client = client
        self.product_id = product_id
        self._name_to_id: dict[str, int] = {}
        self._loaded = False

    def prepare(self, module_names: list[str]) -> None:
        self._ensure_loaded()
        for name in module_names:
            normalized = self._normalize_name(name)
            if normalized and normalized not in self._name_to_id:
                self._create_module(normalized)

    def resolve(self, module_name: str | None, *, source: str = "") -> int:
        self._ensure_loaded()
        name = self._pick_name(module_name, source)
        if not name:
            return 0
        if name not in self._name_to_id:
            self._create_module(name)
        return self._name_to_id.get(name, 0)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        modules = self.client.list_case_modules(self.product_id)
        self._name_to_id = self._flatten_modules(modules)
        self._loaded = True
        logger.info("已加载禅道用例模块 %d 个", len(self._name_to_id))

    def _flatten_modules(self, modules: Any) -> dict[str, int]:
        mapping: dict[str, int] = {}

        def walk(items: Any) -> None:
            if isinstance(items, dict):
                if "name" in items and "id" in items:
                    name = str(items["name"]).strip()
                    module_id = int(items["id"])
                    if name and name != "/":
                        mapping[name] = module_id
                for value in items.values():
                    walk(value)
            elif isinstance(items, list):
                for item in items:
                    walk(item)

        walk(modules)
        return mapping

    def _create_module(self, name: str) -> None:
        try:
            module_id = self.client.create_case_module(self.product_id, name)
            self._name_to_id[name] = module_id
            logger.info("已创建禅道用例模块 #%s: %s", module_id, name)
        except ZenTaoError as exc:
            logger.warning("创建模块 '%s' 失败，将使用根目录: %s", name, exc)

    @staticmethod
    def _normalize_name(name: str) -> str:
        name = name.strip()
        if not name:
            return ""
        if name in SPECIAL_MODULES:
            return SPECIAL_MODULES[name]
        # 路径转模块名: src/demo/main.py -> main
        base = name.replace("\\", "/").rstrip("/").split("/")[-1]
        base = re.sub(r"\.(py|ts|js|tsx|jsx|go|java|rs)$", "", base, flags=re.I)
        return base or name

    @classmethod
    def _pick_name(cls, module_name: str | None, source: str) -> str:
        if module_name and module_name.strip():
            return cls._normalize_name(module_name)
        if source and source.strip():
            return cls._normalize_name(source)
        return ""

    @classmethod
    def collect_module_names(cls, cases: list) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for case in cases:
            for candidate in (getattr(case, "module_name", None), getattr(case, "source", None)):
                name = cls._normalize_name(str(candidate or ""))
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        return names
