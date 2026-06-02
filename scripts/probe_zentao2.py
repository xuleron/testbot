import re

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

product_id = s.zentao_product_id or 20
r = client.get(f"{base}/testcase-create-{product_id}.html")
print("status", r.status_code, "url", r.url)
title = re.search(r"<title>(.*?)</title>", r.text)
print("title", title.group(1) if title else "none")
forms = re.findall(r'<form[^>]*action="([^"]*)"', r.text)
print("forms", forms[:5])
for name in ["verifyRand", "productID", "module"]:
    m = re.search(rf'name="{name}"[^>]*value="([^"]*)"', r.text)
    print(name, m.group(1) if m else "N/A")

# 产品用例浏览
r2 = client.get(f"{base}/testcase-browse-{product_id}.html")
print("browse title", re.search(r"<title>(.*?)</title>", r2.text).group(1) if re.search(r"<title>(.*?)</title>", r2.text) else "none")
print("browse deny", "user-deny" in r2.text)

# 检查后台扩展菜单
r3 = client.get(f"{base}/admin.html")
print("admin", r3.status_code, "deny" in r3.text, r3.url)
