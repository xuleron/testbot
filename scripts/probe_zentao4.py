import json

import httpx

from testbot.config import get_settings

s = get_settings()
base = s.zentao_api_base
client = httpx.Client(follow_redirects=True, timeout=15)
client.post(
    f"{base}/user-login.html",
    data={
        "account": s.zentao_account,
        "password": s.zentao_password,
        "keepLogin": "1",
        "verifyRand": "0",
    },
)

headers = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/testcase-create-20.html"}

# 尝试创建模块
for url, data in [
    (f"{base}/tree-maintaincase-20.html", {"moduleName": "TestBotDemo", "parentModuleID": 0}),
    (f"{base}/tree-maintainchild-20-case.html", {"moduleName": "TestBotDemo2", "parentModuleID": 0}),
]:
    r = client.post(url, data=data, headers=headers)
    print("=== POST", url.replace(base, ""))
    print(r.status_code, r.text[:400])

# 尝试创建用例
payload = {
    "product": 20,
    "module": 0,
    "title": "TestBot API 测试用例",
    "type": "feature",
    "pri": 3,
    "precondition": "TestBot 自动创建",
    "steps[0]": "步骤1",
    "expects[0]": "预期1",
    "stepType[0]": "step",
}
r = client.post(f"{base}/testcase-create-20.html", data=payload, headers=headers)
print("=== create case", r.status_code)
print(r.text[:600])
