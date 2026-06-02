"""Playwright 动作与断言测试（无需安装浏览器）。"""

from testbot.executor.playwright_actions import PlaywrightAction, verify_expectation


class FakePage:
    def __init__(self, text: str):
        self._text = text

    class _Body:
        def __init__(self, text: str):
            self._text = text

        def inner_text(self, timeout=0):
            return self._text

    def locator(self, sel: str):
        return self

    @property
    def first(self):
        return self

    def inner_text(self, timeout=0):
        return self._text


def test_verify_expectation_keyword_match():
    page = FakePage("用户登录成功，欢迎回来")
    assert verify_expectation(page, "登录成功") is True
    assert verify_expectation(page, "完全不相关") is False


def test_playwright_action_model():
    action = PlaywrightAction.model_validate({"type": "click", "selector": "#btn"})
    assert action.type == "click"
