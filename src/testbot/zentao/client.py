"""禅道 REST API 客户端。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from testbot.config import Settings
from testbot.models.testcase import TestCaseDraft, TestStepResult
from testbot.models.zentao_context import ProjectContext
from testbot.zentao.auth import ZenTaoAuthError, ZenTaoAuthenticator

logger = logging.getLogger(__name__)


class ZenTaoError(Exception):
    """禅道 API 调用异常。"""


class ZenTaoClient:
    """封装禅道 v1/v2 API。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = ZenTaoAuthenticator(settings)
        self._context: ProjectContext | None = None

    @property
    def api_base(self) -> str:
        return self.settings.zentao_api_base

    @property
    def context(self) -> ProjectContext:
        if self._context is None:
            from testbot.zentao.context import ProjectContextResolver

            self._context = ProjectContextResolver(self, self.settings).resolve()
        return self._context

    def authenticate(self) -> str:
        try:
            return self.auth.get_rest_token()
        except ZenTaoAuthError as exc:
            raise ZenTaoError(str(exc)) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        api_version: str = "v2",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.api_base}/api.php/{api_version}{path}"
        merged_params = self.auth.merge_sign_params(params)
        try:
            headers = self.auth.request_headers()
        except ZenTaoAuthError as exc:
            raise ZenTaoError(str(exc)) from exc

        with httpx.Client(timeout=60) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=merged_params or None,
                json=json,
            )
            if response.status_code >= 400:
                raise ZenTaoError(
                    f"禅道 API 错误 [{response.status_code}] {method} {path}: {response.text}"
                )
            if not response.content:
                return {}
            data = response.json()
            if isinstance(data, dict) and data.get("errcode"):
                raise ZenTaoError(f"禅道 API 错误: {data.get('errmsg', data)}")
            return data

    # ---------- 项目 / 产品 ----------

    def get_project(self, project_id: int, *, api_version: str = "v2") -> dict[str, Any]:
        data = self._request("GET", f"/projects/{project_id}", api_version=api_version)
        if isinstance(data, dict) and "project" in data and isinstance(data["project"], dict):
            return data["project"]
        return data if isinstance(data, dict) else {}

    def get_project_products(self, project_id: int, *, api_version: str = "v2") -> Any:
        try:
            return self._request("GET", f"/projects/{project_id}/products", api_version=api_version)
        except ZenTaoError:
            return {}

    def list_products(self, *, page: int = 1, limit: int = 200) -> dict[str, Any]:
        try:
            return self._request(
                "GET",
                "/products",
                api_version="v2",
                params={"pageID": page, "recPerPage": limit},
            )
        except ZenTaoError:
            return self._request("GET", "/products", api_version="v1")

    # ---------- 用例模块 ----------

    def list_case_modules(self, product_id: int) -> Any:
        return self._request(
            "GET",
            "/modules",
            api_version="v1",
            params={"type": "case", "id": product_id},
        )

    def create_case_module(self, product_id: int, name: str, *, parent: int = 0) -> int:
        payloads = [
            {"type": "case", "root": product_id, "name": name, "parent": parent},
            {"type": "case", "id": product_id, "name": name, "parent": parent},
            {"type": "case", "root": str(product_id), "name": name, "parent": parent},
        ]
        last_error: Exception | None = None
        for payload in payloads:
            try:
                data = self._request("POST", "/modules", api_version="v1", json=payload)
                module_id = self._extract_created_id(data)
                if module_id:
                    return module_id
            except ZenTaoError as exc:
                last_error = exc
        raise ZenTaoError(f"创建用例模块 '{name}' 失败: {last_error}")

    @staticmethod
    def _extract_created_id(data: Any) -> int:
        if isinstance(data, dict):
            for key in ("id", "moduleID", "moduleId"):
                if data.get(key):
                    return int(data[key])
            if data.get("status") == "success" and data.get("id"):
                return int(data["id"])
            nested = data.get("module") or data.get("data")
            if isinstance(nested, dict) and nested.get("id"):
                return int(nested["id"])
        return 0

    # ---------- 测试用例 ----------

    def create_testcase(self, draft: TestCaseDraft, *, module_id: int | None = None) -> int:
        ctx = self.context
        resolved_module = module_id
        if resolved_module is None:
            resolved_module = draft.module if draft.module is not None else 0

        payload = {
            "productID": ctx.product_id,
            "title": draft.title,
            "module": resolved_module,
            "story": draft.story or 0,
            "pri": draft.pri,
            "type": draft.type.value,
            "precondition": draft.precondition,
            "steps": [s.action for s in draft.steps],
            "expects": [s.expect for s in draft.steps],
            "stepType": ["step"] * len(draft.steps),
            "project": draft.project or ctx.project_id,
        }
        if ctx.execution_id:
            payload["execution"] = draft.execution or ctx.execution_id

        data = self._request("POST", "/testcases", json=payload)
        if data.get("status") != "success":
            raise ZenTaoError(f"创建用例失败: {data}")
        case_id = int(data["id"])
        logger.info("已创建禅道用例 #%s: %s (模块 #%s)", case_id, draft.title, resolved_module)
        return case_id

    def get_testcase(self, case_id: int) -> dict[str, Any]:
        return self._request("GET", f"/testcases/{case_id}")

    def list_project_testcases(
        self,
        project_id: int | None = None,
        *,
        page: int = 1,
        limit: int = 100,
    ) -> dict[str, Any]:
        pid = project_id or self.context.project_id
        return self._request(
            "GET",
            f"/projects/{pid}/testcases",
            params={"pageID": page, "recPerPage": limit},
        )

    def submit_case_result(
        self,
        case_id: int,
        steps: list[TestStepResult],
        *,
        testtask_id: int | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        task_id = testtask_id if testtask_id is not None else self.settings.zentao_testtask_id
        if task_id:
            params["testtask"] = task_id
        if version is not None:
            params["version"] = version

        payload = {
            "steps": [{"result": s.result.value, "real": s.real} for s in steps],
        }
        return self._request(
            "POST",
            f"/testcases/{case_id}/results",
            api_version="v1",
            params=params or None,
            json=payload,
        )

    def create_testtask(
        self,
        name: str,
        build_id: int,
        *,
        begin: str,
        end: str,
        execution_id: int | None = None,
        desc: str = "",
    ) -> int:
        ctx = self.context
        payload = {
            "productID": ctx.product_id,
            "name": name,
            "build": build_id,
            "begin": begin,
            "end": end,
            "desc": desc,
        }
        exec_id = execution_id or ctx.execution_id
        if exec_id:
            payload["execution"] = exec_id

        data = self._request("POST", "/testtasks", json=payload)
        if data.get("status") != "success":
            raise ZenTaoError(f"创建测试单失败: {data}")
        return int(data["id"])
