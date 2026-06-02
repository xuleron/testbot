"""禅道模块与上下文测试。"""

from unittest.mock import MagicMock

import pytest

from testbot.config import Settings
from testbot.models.testcase import CaseType, TestCaseDraft, TestCaseStep
from testbot.zentao.context import ProjectContextResolver
from testbot.zentao.module_manager import ModuleManager


def test_module_manager_resolve_existing():
    client = MagicMock()
    client.list_case_modules.return_value = {
        "modules": [
            {"id": 10, "name": "user", "parent": 0},
            {"id": 11, "name": "order", "parent": 0},
        ]
    }
    mgr = ModuleManager(client, product_id=1)
    assert mgr.resolve("user") == 10
    client.create_case_module.assert_not_called()


def test_module_manager_auto_create():
    client = MagicMock()
    client.list_case_modules.return_value = {"modules": []}
    client.create_case_module.return_value = 99
    mgr = ModuleManager(client, product_id=1)
    assert mgr.resolve("payment", source="src/payment/service.py") == 99
    client.create_case_module.assert_called_once()


def test_module_manager_normalize_source_path():
    client = MagicMock()
    client.list_case_modules.return_value = {"modules": []}
    client.create_case_module.return_value = 5
    mgr = ModuleManager(client, product_id=1)
    assert mgr.resolve(None, source="src/api/handler.py") == 5
    client.create_case_module.assert_called_once_with(1, "handler")


def test_collect_module_names():
    cases = [
        TestCaseDraft(title="a", steps=[], module_name="user"),
        TestCaseDraft(title="b", steps=[], source="src/order/main.py"),
    ]
    names = ModuleManager.collect_module_names(cases)
    assert "user" in names
    assert "main" in names


def test_context_resolver_from_project_products():
    settings = Settings(ZENTAO_PROJECT_ID=20, ZENTAO_PRODUCT_ID=0)
    client = MagicMock()
    client.get_project.side_effect = Exception("skip")
    client.get_project_products.return_value = {"products": [{"id": 7, "name": "Demo"}]}

    resolver = ProjectContextResolver(client, settings)
    ctx = resolver.resolve()
    assert ctx.project_id == 20
    assert ctx.product_id == 7


def test_context_resolver_manual_product():
    settings = Settings(ZENTAO_PROJECT_ID=20, ZENTAO_PRODUCT_ID=3)
    client = MagicMock()
    resolver = ProjectContextResolver(client, settings)
    ctx = resolver.resolve()
    assert ctx.product_id == 3
    client.get_project.assert_not_called()
