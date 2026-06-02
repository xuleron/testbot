#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   ./submit_latest.sh
#   ./submit_latest.sh .reports/cases_xxx.json .reports/report_xxx.json

CASES="${1:-}"
REPORT="${2:-}"

if [[ -z "${CASES}" ]]; then
  CASES="$(ls -t .reports/cases_*.json 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${REPORT}" ]]; then
  REPORT="$(ls -t .reports/report_*.json 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${CASES}" ]]; then
  echo "未找到 cases 文件（.reports/cases_*.json）。"
  exit 1
fi

if [[ -z "${REPORT}" ]]; then
  echo "未找到 report 文件（.reports/report_*.json）。"
  exit 1
fi

echo "补提交到禅道:"
echo "  cases : ${CASES}"
echo "  report: ${REPORT}"
testbot report "${CASES}" "${REPORT}"

