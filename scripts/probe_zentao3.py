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

product_id = 20
headers = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/testcase-browse-{product_id}.html"}

json_urls = [
    f"{base}/testcase-ajaxGetModules-{product_id}.json?root={product_id}",
    f"{base}/tree-browse-{product_id}-case.json",
    f"{base}/testcase-create-{product_id}.json",
    f"{base}/api.php/v1/modules?type=case&id={product_id}",
]

for url in json_urls:
    r = client.get(url, headers=headers)
    print("---", url.replace(base, ""))
    print(r.status_code, r.headers.get("content-type", ""))
    print(r.text[:500])
    print()
