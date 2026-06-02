"""LLM JSON 响应解析与修复。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _read_json_object(text: str, start: int) -> tuple[dict[str, Any] | None, int]:
    """从 start 位置的 `{` 开始读取一个完整 JSON 对象。"""
    if start >= len(text) or text[start] != "{":
        return None, start

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = text[start : i + 1]
                try:
                    return json.loads(snippet), i + 1
                except json.JSONDecodeError:
                    return None, i + 1
    return None, len(text)


def salvage_object_array(text: str, *, key: str = "features") -> list[dict[str, Any]]:
    """从截断的 JSON 中尽量 salvage 出完整的数组对象。"""
    pattern = rf'"{re.escape(key)}"\s*:\s*\['
    match = re.search(pattern, text)
    if not match:
        return []

    items: list[dict[str, Any]] = []
    i = match.end()
    while i < len(text):
        while i < len(text) and text[i] in " \n\r\t,":
            i += 1
        if i >= len(text) or text[i] == "]":
            break
        if text[i] != "{":
            break
        obj, i = _read_json_object(text, i)
        if obj is None:
            break
        items.append(obj)
    return items


def _close_truncated_json(text: str) -> str:
    """尝试为被截断的 JSON 补齐括号。"""
    snippet = text.strip()
    if not snippet:
        return snippet

    in_string = False
    escape = False
    stack: list[str] = []

    for ch in snippet:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            if stack[-1] == ch:
                stack.pop()

    if in_string:
        snippet += '"'
    snippet += "".join(reversed(stack))
    return snippet


def parse_json_lenient(content: str, *, array_key: str | None = None) -> Any:
    """尽可能解析 LLM 返回的 JSON，支持截断修复与数组 salvage。"""
    text = content.strip()
    if not text:
        raise ValueError("空内容")

    attempts = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        attempts.append(text[start : end + 1])
    attempts.append(_close_truncated_json(text[start:] if start != -1 else text))

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        attempts.insert(0, fenced.group(1).strip())

    last_error: json.JSONDecodeError | None = None
    for candidate in attempts:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    if array_key:
        salvaged = salvage_object_array(text, key=array_key)
        if salvaged:
            logger.warning(
                "JSON 已截断，已从 %s 数组中 salvage %d 条记录",
                array_key,
                len(salvaged),
            )
            return {array_key: salvaged}

    if last_error:
        raise last_error
    raise ValueError(f"无法解析 JSON: {text[:500]}")
