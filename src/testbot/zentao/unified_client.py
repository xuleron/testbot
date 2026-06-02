"""禅道客户端统一入口，自动选择 REST 或 Session 模式。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from testbot.config import Settings
from testbot.models.bug import BugDraft
from testbot.models.testcase import TestCaseDraft, TestStepResult
from testbot.models.zentao_context import ProjectContext
from testbot.zentao.client import ZenTaoClient, ZenTaoError
from testbot.zentao.session_client import SessionZenTaoClient, SessionZenTaoError

logger = logging.getLogger(__name__)


class ZenTaoBackend(Protocol):
    def authenticate(self) -> str: ...
    @property
    def context(self) -> ProjectContext: ...
    def list_case_modules(self, product_id: int) -> Any: ...
    def create_case_module(self, product_id: int, name: str, *, parent: int = 0) -> int: ...
    def create_testcase(self, draft: TestCaseDraft, *, module_id: int | None = None) -> int: ...
    def submit_case_result(
        self,
        case_id: int,
        steps: list[TestStepResult],
        *,
        testtask_id: int | None = None,
        version: int | None = None,
    ) -> dict[str, Any]: ...


class UnifiedZenTaoClient:
    """根据禅道版本与配置，自动选择 REST 或 Session 后端。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._backend: ZenTaoBackend | None = None
        self._mode: str | None = None

    def _select_backend(self) -> ZenTaoBackend:
        if self._backend:
            return self._backend

        mode = (self.settings.zentao_auth_mode or "auto").lower()
        if mode == "session":
            self._backend = SessionZenTaoClient(self.settings)
            self._mode = "session"
            return self._backend

        if mode == "rest":
            self._backend = ZenTaoClient(self.settings)
            self._mode = "rest"
            return self._backend

        # auto: 有应用签名或明确 REST 时先试 REST，否则直接用 Session
        if self.settings.zentao_app_code and self.settings.zentao_app_secret:
            self._backend = ZenTaoClient(self.settings)
            self._mode = "rest+app"
            return self._backend

        # 默认 Session（兼容禅道 12.x）
        self._backend = SessionZenTaoClient(self.settings)
        self._mode = "session"
        logger.info("使用禅道 Session 模式 (适用于 12.x，无需创建应用)")
        return self._backend

    @property
    def mode(self) -> str:
        self._select_backend()
        return self._mode or "unknown"

    @property
    def context(self) -> ProjectContext:
        return self._select_backend().context

    def authenticate(self) -> str:
        backend = self._select_backend()
        try:
            return backend.authenticate()
        except SessionZenTaoError as exc:
            raise ZenTaoError(str(exc)) from exc

    def list_case_modules(self, product_id: int) -> Any:
        backend = self._select_backend()
        result = backend.list_case_modules(product_id)
        if isinstance(result, dict) and result and isinstance(next(iter(result.values())), int):
            if all(isinstance(k, str) for k in result):
                return {"modules": [{"id": v, "name": k} for k, v in result.items()]}
        return result

    def create_testcase(self, draft: TestCaseDraft, *, module_id: int | None = None) -> int:
        try:
            return self._select_backend().create_testcase(draft, module_id=module_id)
        except SessionZenTaoError as exc:
            raise ZenTaoError(str(exc)) from exc

    def create_case_module(self, product_id: int, name: str, *, parent: int = 0) -> int:
        try:
            return self._select_backend().create_case_module(product_id, name, parent=parent)
        except SessionZenTaoError as exc:
            raise ZenTaoError(str(exc)) from exc

    def submit_case_result(
        self,
        case_id: int,
        steps: list[TestStepResult],
        *,
        testtask_id: int | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self._select_backend().submit_case_result(
                case_id, steps, testtask_id=testtask_id, version=version
            )
        except SessionZenTaoError as exc:
            raise ZenTaoError(str(exc)) from exc

    def create_bug(self, draft: BugDraft) -> int:
        backend = self._select_backend()
        if isinstance(backend, SessionZenTaoClient):
            try:
                return backend.create_bug(draft)
            except SessionZenTaoError as exc:
                raise ZenTaoError(str(exc)) from exc
        raise ZenTaoError("当前禅道模式暂不支持 REST 提 Bug，请使用 Session 模式")
    def get_project(self, project_id: int, *, api_version: str = "v2") -> dict[str, Any]:
        if isinstance(self._select_backend(), ZenTaoClient):
            return self._select_backend().get_project(project_id, api_version=api_version)
        return {}

    def get_project_products(self, project_id: int, *, api_version: str = "v2") -> Any:
        if isinstance(self._select_backend(), ZenTaoClient):
            return self._select_backend().get_project_products(project_id, api_version=api_version)
        return {}

    def list_products(self, *, page: int = 1, limit: int = 200) -> dict[str, Any]:
        if isinstance(self._select_backend(), ZenTaoClient):
            return self._select_backend().list_products(page=page, limit=limit)
        return {}
