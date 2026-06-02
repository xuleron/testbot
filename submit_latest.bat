@echo off
setlocal

REM 用法:
REM   submit_latest.bat
REM   submit_latest.bat ".reports\cases_xxx.json" ".reports\report_xxx.json"

set "CASES=%~1"
set "REPORT=%~2"

if "%CASES%"=="" (
  for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem .reports -Filter 'cases_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set "CASES=%%F"
)

if "%REPORT%"=="" (
  for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem .reports -Filter 'report_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set "REPORT=%%F"
)

if "%CASES%"=="" (
  echo 未找到 cases 文件（.reports\cases_*.json）。
  exit /b 1
)

if "%REPORT%"=="" (
  echo 未找到 report 文件（.reports\report_*.json）。
  exit /b 1
)

echo 补提交到禅道:
echo   cases : %CASES%
echo   report: %REPORT%
testbot report "%CASES%" "%REPORT%"

