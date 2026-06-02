"""Playwright 浏览器操作模型与执行。"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

ActionType = Literal[
    "click",
    "fill",
    "press",
    "goto",
    "wait",
    "wait_for_selector",
    "expect_text",
    "expect_url",
    "select",
]


class PlaywrightAction(BaseModel):
    type: ActionType
    selector: str = ""
    value: str = ""
    timeout_ms: int = 0

    # LLM 生成的 value 有时是数字（例如 2000 毫秒），这里统一转成字符串，避免 Pydantic 校验失败。
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float, bool)):
            return str(v)
        return str(v)

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, v: Any) -> str:
        return cls._coerce_str(v)


class BrowserStepPlan(BaseModel):
    actions: list[PlaywrightAction] = Field(default_factory=list)
    note: str = ""


class BrowserStepResult(BaseModel):
    status: str = "pass"
    real: str = ""


class BrowserCasePlan(BaseModel):
    steps: list[BrowserStepPlan]


def page_snapshot(page: Any, *, max_chars: int = 5000) -> dict[str, str]:
    try:
        title = page.title()
    except Exception:
        title = ""
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()[:max_chars]
    return {"url": page.url, "title": title, "text": text}


def execute_actions(page: Any, actions: list[PlaywrightAction], *, default_timeout: int) -> list[str]:
    logs: list[str] = []
    for action in actions:
        timeout = action.timeout_ms or default_timeout
        msg = _run_action(page, action, timeout)
        logs.append(msg)
    return logs


def _run_action(page: Any, action: PlaywrightAction, timeout: int) -> str:
    atype = action.type
    sel = action.selector.strip()
    val = action.value

    if atype == "goto":
        page.goto(val or sel, wait_until="domcontentloaded", timeout=timeout)
        return f"goto {val or sel}"

    if atype == "wait":
        ms = int(val) if str(val).isdigit() else 1000
        page.wait_for_timeout(ms)
        return f"wait {ms}ms"

    if atype == "wait_for_selector":
        if not sel:
            raise ValueError("wait_for_selector 缺少 selector")
        page.wait_for_selector(sel, timeout=timeout)
        return f"wait_for_selector {sel}"

    if not sel:
        raise ValueError(f"{atype} 缺少 selector")

    locator = page.locator(sel).first

    if atype == "click":
        locator.click(timeout=timeout)
        return f"click {sel}"
    if atype == "fill":
        locator.fill(val, timeout=timeout)
        return f"fill {sel}"
    if atype == "press":
        locator.press(val or "Enter", timeout=timeout)
        return f"press {sel} {val}"
    if atype == "select":
        locator.select_option(val, timeout=timeout)
        return f"select {sel}={val}"
    if atype == "expect_text":
        page.wait_for_function(
            "(args) => document.body && document.body.innerText.includes(args.text)",
            arg={"text": val},
            timeout=timeout,
        )
        return f"expect_text {val[:80]}"
    if atype == "expect_url":
        page.wait_for_function(
            "(url) => window.location.href.includes(url)",
            arg=val,
            timeout=timeout,
        )
        return f"expect_url {val}"

    raise ValueError(f"未知操作: {atype}")


def verify_expectation(page: Any, expect: str) -> bool:
    expect = expect.strip()
    if not expect:
        return True
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""
    body_lower = body.lower()
    expect_lower = expect.lower()
    if expect_lower in body_lower:
        return True
    keywords = [w for w in re.split(r"[\s，,、；;]+", expect) if len(w) >= 2]
    if keywords:
        hit = sum(1 for w in keywords if w.lower() in body_lower)
        return hit >= max(1, len(keywords) // 2)
    return False
