"""JSON 解析容错测试。"""

import json

import pytest

from testbot.llm.json_utils import parse_json_lenient, salvage_object_array


def test_parse_json_lenient_normal():
    data = parse_json_lenient('{"features": [{"name": "登录"}]}', array_key="features")
    assert data["features"][0]["name"] == "登录"


def test_parse_json_lenient_salvage_truncated_features():
    text = """{
  "features": [
    {"name": "功能A", "module": "a", "source": "a.ts"},
    {"name": "功能B", "module": "b", "source": "b.ts"},
    {"name": "功能C", "module": "c", "source": "c.ts"
"""
    data = parse_json_lenient(text, array_key="features")
    assert len(data["features"]) >= 2
    assert data["features"][0]["name"] == "功能A"
    assert data["features"][1]["name"] == "功能B"


def test_salvage_object_array():
    text = '{"features": [{"name": "x"}, {"name": "y"}, {"name": "z'
    items = salvage_object_array(text, key="features")
    assert len(items) == 2
    assert items[1]["name"] == "y"
