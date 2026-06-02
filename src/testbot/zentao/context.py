"""从项目 ID 解析禅道产品等上下文。"""

from __future__ import annotations

import logging
from typing import Any

from testbot.config import Settings
from testbot.models.zentao_context import ProjectContext
from testbot.zentao.client import ZenTaoClient, ZenTaoError

logger = logging.getLogger(__name__)


class ProjectContextResolver:
    """仅需项目 ID，自动解析产品 ID。"""

    def __init__(self, client: ZenTaoClient, settings: Settings):
        self.client = client
        self.settings = settings
        self._cache: ProjectContext | None = None

    def resolve(self) -> ProjectContext:
        if self._cache:
            return self._cache

        project_id = self.settings.zentao_project_id
        if not project_id:
            raise ZenTaoError("未配置 ZENTAO_PROJECT_ID")

        product_id = self.settings.zentao_product_id
        if product_id <= 0:
            product_id = self._resolve_product_id(project_id)
            logger.info("已从项目 #%s 解析产品 ID: %s", project_id, product_id)

        self._cache = ProjectContext(
            project_id=project_id,
            product_id=product_id,
            execution_id=self.settings.zentao_execution_id or 0,
        )
        return self._cache

    def _resolve_product_id(self, project_id: int) -> int:
        for resolver in (
            self._from_project_detail_v2,
            self._from_project_detail_v1,
            self._from_project_products_v2,
            self._from_project_products_v1,
            self._from_products_scan,
        ):
            product_id = resolver(project_id)
            if product_id:
                return product_id
        raise ZenTaoError(
            f"无法从项目 #{project_id} 解析产品 ID，请在 .env 中手动设置 ZENTAO_PRODUCT_ID"
        )

    def _from_project_detail_v2(self, project_id: int) -> int:
        try:
            data = self.client.get_project(project_id, api_version="v2")
            return self._extract_product_id(data)
        except Exception:
            return 0

    def _from_project_detail_v1(self, project_id: int) -> int:
        try:
            data = self.client.get_project(project_id, api_version="v1")
            return self._extract_product_id(data)
        except Exception:
            return 0

    def _from_project_products_v2(self, project_id: int) -> int:
        try:
            return self._first_product_id(
                self.client.get_project_products(project_id, api_version="v2")
            )
        except Exception:
            return 0

    def _from_project_products_v1(self, project_id: int) -> int:
        try:
            return self._first_product_id(
                self.client.get_project_products(project_id, api_version="v1")
            )
        except Exception:
            return 0

    def _from_products_scan(self, project_id: int) -> int:
        try:
            data = self.client.list_products()
        except Exception:
            return 0
        products = data.get("products", data if isinstance(data, list) else [])
        if isinstance(products, dict):
            products = list(products.values())

        for item in products:
            if not isinstance(item, dict):
                continue
            linked = item.get("projects") or item.get("project") or item.get("linkedProjects")
            if self._matches_project(linked, project_id):
                return int(item.get("id") or item.get("productID") or 0)
        return 0

    @staticmethod
    def _extract_product_id(data: dict[str, Any]) -> int:
        if not isinstance(data, dict):
            return 0

        for key in ("product", "productID", "productId"):
            value = data.get(key)
            if value:
                return int(value)

        products = data.get("products") or data.get("linkedProducts") or data.get("productList")
        return ProjectContextResolver._first_product_id(products)

    @staticmethod
    def _first_product_id(products: Any) -> int:
        if products is None:
            return 0
        if isinstance(products, int):
            return products
        if isinstance(products, str) and products.isdigit():
            return int(products)
        if isinstance(products, dict):
            if "id" in products:
                return int(products["id"])
            for key in ("products", "productList", "data"):
                if key in products:
                    nested = ProjectContextResolver._first_product_id(products[key])
                    if nested:
                        return nested
            if products:
                first_key = next(iter(products))
                if str(first_key).isdigit():
                    return int(first_key)
                value = products[first_key]
                if isinstance(value, dict) and "id" in value:
                    return int(value["id"])
        if isinstance(products, list) and products:
            first = products[0]
            if isinstance(first, int):
                return first
            if isinstance(first, str) and first.isdigit():
                return int(first)
            if isinstance(first, dict):
                return int(first.get("id") or first.get("productID") or 0)
        return 0

    @staticmethod
    def _matches_project(linked: Any, project_id: int) -> bool:
        if linked is None:
            return False
        if isinstance(linked, int):
            return linked == project_id
        if isinstance(linked, str):
            return str(project_id) in linked.split(",")
        if isinstance(linked, list):
            return project_id in [int(x) for x in linked if str(x).isdigit()]
        if isinstance(linked, dict):
            return str(project_id) in linked or project_id in linked.values()
        return False
