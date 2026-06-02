@echo off
setlocal enabledelayedexpansion

REM 用法:
REM   write_cases.bat
REM   write_cases.bat "D:\Projects\6Q\oa"

set "PROJECT=%~1"
if "%PROJECT%"=="" set "PROJECT=."

echo [1/2] 生成测试用例（full模式）...
testbot plan --mode full --project "%PROJECT%"
if errorlevel 1 (
  echo 生成用例失败。
  exit /b 1
)

for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem .reports -Filter 'cases_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set "LATEST=%%F"

if not defined LATEST (
  echo 未找到 .reports\cases_*.json，无法同步到禅道。
  exit /b 1
)

echo [2/2] 同步用例到禅道: %LATEST%
testbot sync "%LATEST%"
if errorlevel 1 (
  echo 同步禅道失败。
  exit /b 1
)

echo 完成。
