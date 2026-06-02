import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from testbot.config import get_settings
from testbot.models.testcase import CaseType, TestCaseDraft, TestCaseStep


def login(client: httpx.Client, base: str, account: str, password: str) -> None:
    login_page = client.get(f"{base}/user-login.html", timeout=30)
    match = re.search(r'name="verifyRand"\s+value="(\d+)"', login_page.text)
    verify_rand = match.group(1) if match else "0"
    client.post(
        f"{base}/user-login.html",
        data={
            "account": account,
            "password": password,
            "keepLogin": "1",
            "verifyRand": verify_rand,
        },
        timeout=30,
    )


def parse_outer_json(text: str) -> dict:
    outer = json.loads(text)
    if isinstance(outer, dict) and "data" in outer and isinstance(outer["data"], str):
        return json.loads(outer["data"])
    return outer


def fetch_case_list(client: httpx.Client, base: str, product_id: int) -> list[dict]:
    headers = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/testcase-browse-{product_id}.html"}
    r = client.get(f"{base}/testcase-browse-{product_id}--all-0-id_desc.json", headers=headers, timeout=60)
    inner = parse_outer_json(r.text)
    cases = inner.get("cases") or {}
    if isinstance(cases, dict):
        # cases: { "579": { ... } }
        out = []
        for _, c in cases.items():
            if isinstance(c, dict):
                out.append(c)
        return out
    return []


def normalize_case_type(value: str) -> CaseType:
    if not value:
        return CaseType.FEATURE
    key = str(value).strip().lower()
    try:
        return CaseType(key)
    except ValueError:
        # 兜底：把未知类型当成 feature（不影响执行与展示）
        return CaseType.FEATURE


def fetch_case_detail(client: httpx.Client, base: str, case_id: int) -> dict:
    headers = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/testcase-view-{case_id}.html"}
    r = client.get(f"{base}/testcase-view-{case_id}.json", headers=headers, timeout=60)
    inner = parse_outer_json(r.text)
    return inner.get("case") if isinstance(inner, dict) else {}


def export_cases(product_id: int, limit: int, output: Path) -> None:
    settings = get_settings()
    base = settings.zentao_api_base
    if not settings.zentao_account or not settings.zentao_password:
        raise SystemExit("请在 .env 配置 ZENTAO_ACCOUNT / ZENTAO_PASSWORD")

    client = httpx.Client(follow_redirects=True, timeout=60)
    login(client, base, settings.zentao_account, settings.zentao_password)

    all_cases = fetch_case_list(client, base, product_id)
    if limit and limit > 0:
        all_cases = all_cases[:limit]

    exported: list[TestCaseDraft] = []
    for idx, case in enumerate(all_cases, 1):
        case_id = int(case.get("id") or case.get("caseID") or 0)
        if not case_id:
            continue
        title = str(case.get("title") or "").strip()
        if not title:
            continue

        detail = fetch_case_detail(client, base, case_id)
        steps_dict = detail.get("steps") or {}
        steps: list[TestCaseStep] = []
        if isinstance(steps_dict, dict):
            # keys like "2469", "2470"
            for step_key in sorted(steps_dict.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                s = steps_dict.get(step_key)
                if not isinstance(s, dict):
                    continue
                action = str(s.get("desc") or "").strip()
                expect = str(s.get("expect") or "").strip()
                if not action and not expect:
                    continue
                steps.append(TestCaseStep(action=action or "步骤", expect=expect or "期望"))

        if not steps:
            # 没取到步骤也导出一个占位，保证结构完整
            steps = [TestCaseStep(action="未获取到步骤", expect="未获取到期望")]

        exported.append(
            TestCaseDraft(
                zentao_id=case_id,
                title=title,
                steps=steps,
                precondition=str(detail.get("precondition") or case.get("precondition") or ""),
                pri=int(case.get("pri") or 3),
                type=normalize_case_type(str(detail.get("type") or case.get("type") or "feature")),
                module_name=str(case.get("module") or ""),
            )
        )

        if idx % 10 == 0:
            print(f"已导出 {idx}/{len(all_cases)}: case #{case_id} - {title[:30]}")

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.model_dump(mode="json") for c in exported]
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"导出完成: {len(exported)} 条 → {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="从禅道导出测试用例（含 steps），生成可执行 cases json。")
    parser.add_argument("--product-id", type=int, default=0, help="禅道产品ID（默认从 .env 读取）")
    parser.add_argument("--limit", type=int, default=0, help="限制导出条数（0=不限制）")
    parser.add_argument("--output", type=str, default="", help="输出路径（默认 .reports/cases_export_时间戳.json）")
    args = parser.parse_args()

    settings = get_settings()
    product_id = args.product_id or settings.zentao_product_id
    if product_id <= 0:
        raise SystemExit("未配置/解析到 ZENTAO_PRODUCT_ID，请先在 .env 配置它")

    if args.output:
        output = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path(settings.report_output_dir) / f"cases_export_zentao_{product_id}_{ts}.json"

    export_cases(product_id=product_id, limit=args.limit, output=output)


if __name__ == "__main__":
    main()

