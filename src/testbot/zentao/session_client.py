"""禅道 12.x Session + PATH_INFO 网页 API 客户端。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from testbot.config import Settings
from testbot.models.bug import BugDraft
from testbot.models.testcase import TestCaseDraft, TestStepResult
from testbot.models.zentao_context import ProjectContext

logger = logging.getLogger(__name__)


class SessionZenTaoError(Exception):
    """Session API 异常。"""


class SessionZenTaoClient:
    """适用于禅道 12.x（无 REST API / 无应用集成）。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.Client(follow_redirects=True, timeout=60)
        self._logged_in = False
        self._context: ProjectContext | None = None

    @property
    def base(self) -> str:
        return self.settings.zentao_api_base

    @property
    def context(self) -> ProjectContext:
        if self._context is None:
            project_id = self.settings.zentao_project_id
            product_id = self.settings.zentao_product_id
            if product_id <= 0:
                if project_id <= 0:
                    raise SessionZenTaoError("请配置 ZENTAO_PRODUCT_ID（禅道 12.x 无法自动从项目解析产品）")
                product_id = project_id
                logger.warning(
                    "未配置 ZENTAO_PRODUCT_ID，暂用项目 ID #%s 作为产品 ID（若不同请在 .env 中显式设置）",
                    project_id,
                )
            self._context = ProjectContext(
                project_id=project_id or product_id,
                product_id=product_id,
            )
        return self._context

    def authenticate(self) -> str:
        if self._logged_in:
            return "session"

        login_page = self._client.get(f"{self.base}/user-login.html")
        match = re.search(r'name="verifyRand"\s+value="(\d+)"', login_page.text)
        verify_rand = match.group(1) if match else "0"

        response = self._client.post(
            f"{self.base}/user-login.html",
            data={
                "account": self.settings.zentao_account,
                "password": self.settings.zentao_password,
                "keepLogin": "1",
                "verifyRand": verify_rand,
            },
        )
        cookies = dict(self._client.cookies)
        if "za" not in cookies:
            raise SessionZenTaoError("禅道 Session 登录失败，请检查账号密码")
        self._logged_in = True
        logger.info("禅道 Session 登录成功 (版本兼容模式 12.x)")
        return "session"

    def _ajax_headers(self, referer: str) -> dict[str, str]:
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }

    def _parse_json_response(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if "user-deny" in text:
                raise SessionZenTaoError("当前账号无此操作权限")
            raise SessionZenTaoError(f"无法解析禅道响应: {text[:200]}")

    def list_case_modules(self, product_id: int) -> dict[str, int]:
        """从创建页 JSON 提取 模块名 -> ID。"""
        self.authenticate()
        referer = f"{self.base}/testcase-create-{product_id}.html"
        response = self._client.get(
            f"{self.base}/testcase-create-{product_id}.json",
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("status") != "success":
            return {}

        inner = json.loads(data["data"]) if isinstance(data.get("data"), str) else data.get("data", {})
        mapping: dict[str, int] = {}
        menu = inner.get("moduleOptionMenu") or inner.get("modules")
        if isinstance(menu, list):
            for item in menu:
                if isinstance(item, dict) and "name" in item and "id" in item:
                    mapping[str(item["name"]).strip()] = int(item["id"])
                elif isinstance(item, str) and item.strip() and item.strip() != "/":
                    mapping[item.strip()] = 0
        elif isinstance(menu, str):
            for match in re.finditer(r'value="(\d+)"[^>]*>([^<]+)<', menu):
                name = match.group(2).strip()
                if name and name != "/":
                    mapping[name] = int(match.group(1))
        return mapping

    def create_case_module(self, product_id: int, name: str, *, parent: int = 0) -> int:
        """尝试创建模块；无权限时返回 0。"""
        self.authenticate()
        referer = f"{self.base}/testcase-browse-{product_id}.html"
        for path in (
            f"tree-maintainchild-{product_id}-case.html",
            f"tree-maintaincase-{product_id}.html",
        ):
            response = self._client.post(
                f"{self.base}/{path}",
                data={"moduleName": name, "parentModuleID": parent},
                headers=self._ajax_headers(referer),
            )
            if "user-deny" not in response.text:
                modules = self.list_case_modules(product_id)
                if name in modules:
                    return modules[name]
        logger.warning("无权限创建禅道模块 '%s'，将使用根目录", name)
        return 0

    def create_testcase(self, draft: TestCaseDraft, *, module_id: int | None = None) -> int:
        self.authenticate()
        ctx = self.context
        product_id = ctx.product_id
        referer = f"{self.base}/testcase-create-{product_id}.html"

        payload: dict[str, Any] = {
            "product": product_id,
            "module": module_id if module_id is not None else (draft.module or 0),
            "title": draft.title,
            "type": draft.type.value,
            "pri": draft.pri,
            "precondition": draft.precondition,
            "story": draft.story or 0,
        }
        for idx, step in enumerate(draft.steps):
            payload[f"steps[{idx}]"] = step.action
            payload[f"expects[{idx}]"] = step.expect
            payload[f"stepType[{idx}]"] = "step"

        response = self._client.post(
            f"{self.base}/testcase-create-{product_id}.html",
            data=payload,
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("result") != "success":
            raise SessionZenTaoError(f"创建用例失败: {data}")

        case_id = self._find_case_id_by_title(product_id, draft.title)
        logger.info("已创建禅道用例 #%s: %s (产品 #%s)", case_id or "?", draft.title, product_id)
        return case_id

    def _find_case_id_by_title(self, product_id: int, title: str) -> int:
        referer = f"{self.base}/testcase-browse-{product_id}.html"
        response = self._client.get(
            f"{self.base}/testcase-browse-{product_id}--all-0-id_desc.json",
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("status") != "success":
            return 0
        inner = json.loads(data["data"]) if isinstance(data.get("data"), str) else data.get("data", {})
        cases = inner.get("cases") or {}
        if isinstance(cases, dict):
            for case in cases.values():
                if isinstance(case, dict) and case.get("title") == title:
                    return int(case.get("id") or 0)
        return 0

    def _get_case_version(self, case_id: int) -> int:
        referer = f"{self.base}/testcase-view-{case_id}.html"
        response = self._client.get(
            f"{self.base}/testcase-view-{case_id}.json",
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("status") != "success":
            return 1
        inner = json.loads(data["data"]) if isinstance(data.get("data"), str) else data.get("data", {})
        case = inner.get("case") or inner.get("testcase") or {}
        if isinstance(case, dict):
            return int(case.get("version") or 1)
        return 1

    @staticmethod
    def _map_step_result(result: str) -> str:
        mapping = {
            "pass": "pass",
            "fail": "fail",
            "blocked": "blocked",
            "n/a": "n/a",
        }
        return mapping.get(str(result).lower(), "n/a")

    def submit_case_result(
        self,
        case_id: int,
        steps: list[TestStepResult],
        *,
        testtask_id: int | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        self.authenticate()
        version = version or self._get_case_version(case_id)
        task_id = testtask_id if testtask_id is not None else self.settings.zentao_testtask_id

        overall = "pass"
        if any(s.result.value == "fail" for s in steps):
            overall = "fail"
        elif any(s.result.value == "blocked" for s in steps):
            overall = "blocked"
        elif all(s.result.value in ("n/a",) for s in steps):
            overall = "n/a"

        summary = steps[-1].real if steps else overall
        payload: dict[str, Any] = {
            "caseID": case_id,
            "version": version,
            "result": overall,
            "real": summary[:2000],
        }
        for idx, step in enumerate(steps):
            payload[f"results[{idx}]"] = self._map_step_result(step.result.value)
            payload[f"reals[{idx}]"] = step.real[:1000]

        referer = f"{self.base}/testcase-view-{case_id}.html"
        candidates = []
        if task_id:
            candidates.append(f"testcase-run-{case_id}-{version}-{task_id}.html")
        candidates.extend(
            [
                f"testcase-run-{case_id}-{version}.html",
                f"testcase-run-{case_id}.html",
            ]
        )

        last_error = ""
        for path in candidates:
            response = self._client.post(
                f"{self.base}/{path}",
                data=payload,
                headers=self._ajax_headers(referer),
            )
            text = response.text
            if "user-deny" in text:
                last_error = "当前账号无「执行用例/登记结果」权限，请联系管理员开通 testcase-run"
                continue
            if "alert(" in text and "success" not in text.lower():
                match = re.search(r"alert\('([^']+)", text)
                last_error = match.group(1) if match else text[:200]
                continue
            try:
                data = self._parse_json_response(text)
            except SessionZenTaoError:
                if response.status_code == 200 and "success" in text.lower():
                    logger.info("已登记禅道用例 #%s 结果: %s", case_id, overall)
                    return {"status": "success", "result": overall}
                last_error = text[:200]
                continue
            if data.get("result") == "success" or data.get("status") == "success":
                logger.info("已登记禅道用例 #%s 结果: %s", case_id, overall)
                return data
            last_error = str(data)

        raise SessionZenTaoError(f"登记用例 #{case_id} 结果失败: {last_error}")

    def create_bug(self, draft: BugDraft) -> int:
        self.authenticate()
        ctx = self.context
        product_id = draft.product_id or ctx.product_id
        referer = f"{self.base}/bug-create-{product_id}.html"

        payload: dict[str, Any] = {
            "product": product_id,
            "module": draft.module_id,
            "title": draft.title[:255],
            "type": draft.type,
            "severity": draft.severity,
            "pri": draft.pri,
            "steps": draft.steps[:8000],
            "openedBuild": draft.opened_build,
        }
        project_id = draft.project_id or self.settings.zentao_project_id
        if project_id:
            payload["project"] = project_id
        if draft.case_id:
            payload["case"] = draft.case_id
            payload["caseVersion"] = draft.case_version

        response = self._client.post(
            f"{self.base}/bug-create-{product_id}.html",
            data=payload,
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("result") != "success":
            if "user-deny" in response.text:
                raise SessionZenTaoError("当前账号无提 Bug 权限")
            raise SessionZenTaoError(f"创建 Bug 失败: {data}")

        bug_id = self._find_bug_id_by_title(product_id, draft.title)
        logger.info("已创建禅道 Bug #%s: %s", bug_id or "?", draft.title)
        return bug_id

    def _find_bug_id_by_title(self, product_id: int, title: str) -> int:
        referer = f"{self.base}/bug-browse-{product_id}.html"
        response = self._client.get(
            f"{self.base}/bug-browse-{product_id}--unclosed-0-id_desc.json",
            headers=self._ajax_headers(referer),
        )
        data = self._parse_json_response(response.text)
        if data.get("status") != "success":
            return 0
        inner = json.loads(data["data"]) if isinstance(data.get("data"), str) else data.get("data", {})
        bugs = inner.get("bugs") or {}
        if isinstance(bugs, dict):
            for bug in bugs.values():
                if isinstance(bug, dict) and bug.get("title") == title:
                    return int(bug.get("id") or 0)
        return 0
