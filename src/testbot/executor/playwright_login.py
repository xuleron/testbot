"""Playwright 登录辅助。"""

from __future__ import annotations

import logging
from typing import Any

from testbot.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_USER_SELECTORS = [
    'input[name="account"]',
    'input[name="username"]',
    'input[name="user"]',
    'input[type="text"]',
    "#account",
    "#username",
    '[placeholder*="账号"]',
    '[placeholder*="用户名"]',
]

DEFAULT_PASS_SELECTORS = [
    'input[name="password"]',
    'input[type="password"]',
    "#password",
    '[placeholder*="密码"]',
]

DEFAULT_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("登录")',
    'button:has-text("登 录")',
    'button:has-text("Login")',
    'a:has-text("登录")',
    ".login-btn",
    "#login",
]


def perform_login(page: Any, settings: Settings) -> str:
    """使用 .env 中的地址与账号密码登录，返回日志说明。"""
    login_url = (settings.target_app_login_url or settings.target_app_url).strip()
    if not login_url:
        raise ValueError("未配置 TARGET_APP_URL 或 TARGET_APP_LOGIN_URL")
    username = settings.target_app_username.strip()
    password = settings.target_app_password
    if not username or not password:
        raise ValueError("未配置 TARGET_APP_USERNAME / TARGET_APP_PASSWORD")

    timeout = settings.browser_timeout_ms
    page.goto(login_url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(500)

    user_sel = _pick_selector(page, _user_selector_list(settings), timeout)
    pass_sel = _pick_selector(page, _pass_selector_list(settings), timeout)
    if not user_sel or not pass_sel:
        raise RuntimeError("未找到登录表单（用户名/密码输入框）")

    page.locator(user_sel).first.fill(username, timeout=timeout)
    page.locator(pass_sel).first.fill(password, timeout=timeout)

    submit_sel = _pick_selector(page, _submit_selector_list(settings), timeout)
    if submit_sel:
        page.locator(submit_sel).first.click(timeout=timeout)
    else:
        page.locator(pass_sel).first.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=timeout)
    page.wait_for_timeout(1000)
    logger.info("浏览器登录完成: %s", page.url)
    return f"已登录 {login_url}，当前页面: {page.url}"


def _user_selector_list(settings: Settings) -> list[str]:
    items = []
    if settings.browser_username_selector.strip():
        items.append(settings.browser_username_selector.strip())
    return items + DEFAULT_USER_SELECTORS


def _pass_selector_list(settings: Settings) -> list[str]:
    items = []
    if settings.browser_password_selector.strip():
        items.append(settings.browser_password_selector.strip())
    return items + DEFAULT_PASS_SELECTORS


def _submit_selector_list(settings: Settings) -> list[str]:
    items = []
    if settings.browser_submit_selector.strip():
        items.append(settings.browser_submit_selector.strip())
    return items + DEFAULT_SUBMIT_SELECTORS


def _pick_selector(page: Any, selectors: list[str], timeout: int) -> str:
    per_try = min(3000, timeout)
    for sel in selectors:
        try:
            if page.locator(sel).first.count() > 0:
                page.locator(sel).first.wait_for(state="visible", timeout=per_try)
                return sel
        except Exception:
            continue
    return ""
