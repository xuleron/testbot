import re

import httpx

from testbot.config import get_settings

s = get_settings()
base = s.zentao_api_base
client = httpx.Client(follow_redirects=True, timeout=15)

login_page = client.get(f"{base}/user-login.html")
match = re.search(r'name="verifyRand"\s+value="(\d+)"', login_page.text)
rand = match.group(1) if match else "0"
print("verifyRand", rand)

r = client.post(
    f"{base}/user-login.html",
    data={
        "account": s.zentao_account,
        "password": s.zentao_password,
        "keepLogin": "1",
        "verifyRand": rand,
    },
)
print("login", r.status_code, "url", r.url)
print("cookies", dict(client.cookies))

# 检查 PATH_INFO 路由（requestType=PATH_INFO）
paths = [
    f"{base}/project-testcase-20.html",
    f"{base}/testcase-ajaxGetModules-20.json",
    f"{base}/testcase-create-20.html",
    f"{base}/api.php/v1/tokens",
]
for url in paths:
    r = client.get(url) if "tokens" not in url else client.post(
        url,
        json={"account": s.zentao_account, "password": s.zentao_password},
        headers={"Content-Type": "application/json"},
    )
    print("---", url.replace(base, ""))
    print(r.status_code, r.text[:250].replace("\n", " "))

# 检查 config 里的版本
ver = re.search(r'"version"\s*:\s*"([^"]+)"', login_page.text)
print("version hint", ver.group(1) if ver else "unknown")
