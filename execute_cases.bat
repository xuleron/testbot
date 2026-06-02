@echo off
setlocal

REM 用法:
REM   execute_cases.bat
REM   execute_cases.bat ".reports\cases_xxx.json"
REM   execute_cases.bat ".reports\cases_xxx.json" "D:\Projects\6Q\oa"

set "CASES=%~1"
set "PROJECT=%~2"

if "%CASES%"=="" (
  for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem .reports -Filter 'cases_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set "CASES=%%F"
)

if "%PROJECT%"=="" set "PROJECT=."

if "%CASES%"=="" (
  echo 未找到用例文件，请先执行 write_cases.bat 或手动传入 cases 文件路径。
  exit /b 1
)

echo 执行并回写禅道: %CASES%
testbot execute "%CASES%" --project "%PROJECT%" --sync --executor playwright
if errorlevel 1 (
  echo.
  echo 执行中断/失败，可用以下命令补提交最新报告到禅道:
  echo   .\submit_latest.bat "%CASES%"
  exit /b 1
)
