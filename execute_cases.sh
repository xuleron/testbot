#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   ./execute_cases.sh
#   ./execute_cases.sh .reports/cases_xxx.json
#   ./execute_cases.sh .reports/cases_xxx.json /path/to/project

CASES="${1:-}"
PROJECT="${2:-.}"

if [[ -z "${CASES}" ]]; then
  CASES="$(ls -t .reports/cases_*.json 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${CASES}" ]]; then
  echo "未找到用例文件，请先执行 write_cases.sh 或手动传入 cases 文件路径。"
  exit 1
fi

echo "执行并回写禅道: ${CASES}"
if ! testbot execute "${CASES}" --project "${PROJECT}" --sync --executor playwright; then
  echo
  echo "执行中断/失败，可用以下命令补提交最新报告到禅道:"
  echo "  ./submit_latest.sh \"${CASES}\""
  exit 1
fi
