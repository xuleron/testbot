"""禅道认证：REST Token / 应用签名。"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx

from testbot.config import Settings

logger = logging.getLogger(__name__)


class ZenTaoAuthError(Exception):
    """禅道认证异常。"""


class ZenTaoAuthenticator:
    """支持 REST Token 与应用集成签名两种认证。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._rest_token: str | None = None
        self._last_sign_time: int = 0
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    @property
    def uses_app_sign(self) -> bool:
        return bool(self.settings.zentao_app_code and self.settings.zentao_app_secret)

    @property
    def api_base(self) -> str:
        return self.settings.zentao_api_base

    def sign_params(self) -> dict[str, str]:
        """生成应用集成签名参数: token = md5(code + secret + time)。"""
        if not self.uses_app_sign:
            raise ZenTaoAuthError("未配置 ZENTAO_APP_CODE / ZENTAO_APP_SECRET")

        now = int(time.time())
        if now <= self._last_sign_time:
            now = self._last_sign_time + 1
        self._last_sign_time = now

        code = self.settings.zentao_app_code
        secret = self.settings.zentao_app_secret
        token = hashlib.md5(f"{code}{secret}{now}".encode()).hexdigest()
        return {"code": code, "time": str(now), "token": token}

    def get_rest_token(self) -> str:
        if self._rest_token:
            return self._rest_token

        url = f"{self.api_base}/api.php/v1/tokens"
        payload = {
            "account": self.settings.zentao_account,
            "password": self.settings.zentao_password,
        }
        params = self.sign_params() if self.uses_app_sign else None

        response = self._client.post(
            url,
            params=params,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            errmsg = data.get("errmsg") or data
            if "code" in str(errmsg):
                raise ZenTaoAuthError(
                    "禅道要求应用签名认证。请在禅道后台【二次开发 → 应用】创建应用，"
                    "并配置 ZENTAO_APP_CODE 和 ZENTAO_APP_SECRET"
                )
            raise ZenTaoAuthError(f"获取 Token 失败: {data}")

        self._rest_token = token
        mode = "应用签名+REST" if self.uses_app_sign else "REST"
        logger.info("禅道 Token 认证成功 (%s)", mode)
        return token

    def request_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Token": self.get_rest_token(),
        }

    def merge_sign_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(params or {})
        if self.uses_app_sign:
            merged.update(self.sign_params())
        return merged

    def ping(self) -> str:
        token = self.get_rest_token()
        return token[:8] + "..."
