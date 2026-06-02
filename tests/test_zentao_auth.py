"""禅道应用签名认证测试。"""

import hashlib

from testbot.config import Settings
from testbot.zentao.auth import ZenTaoAuthenticator


def test_sign_params():
    settings = Settings(
        ZENTAO_APP_CODE="testbot",
        ZENTAO_APP_SECRET="abc123secret",
    )
    auth = ZenTaoAuthenticator(settings)
    params1 = auth.sign_params()
    params2 = auth.sign_params()

    assert params1["code"] == "testbot"
    assert int(params2["time"]) > int(params1["time"])

    expected = hashlib.md5(
        f"{params1['code']}{settings.zentao_app_secret}{params1['time']}".encode()
    ).hexdigest()
    assert params1["token"] == expected


def test_uses_app_sign():
    settings = Settings(ZENTAO_APP_CODE="x", ZENTAO_APP_SECRET="y")
    auth = ZenTaoAuthenticator(settings)
    assert auth.uses_app_sign is True

    settings2 = Settings(ZENTAO_APP_CODE="", ZENTAO_APP_SECRET="")
    auth2 = ZenTaoAuthenticator(settings2)
    assert auth2.uses_app_sign is False
