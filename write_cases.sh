#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   ./write_cases.sh
#   ./write_cases.sh /path/to/project

PROJECT="${1:-.}"

echo "[1/2] 生成测试用例（full模式）..."
testbot plan --mode full --project "$PROJECT"

LATEST="$(ls -t .reports/cases_*.json 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST}" ]]; then
  echo "未找到 .reports/cases_*.json，无法同步到禅道。"
  exit 1
fi

echo "[2/2] 同步用例到禅道: ${LATEST}"
testbot sync "${LATEST}"

echo "完成。"
