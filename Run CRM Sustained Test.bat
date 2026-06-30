@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Indus Transports — CRM Sustained Live Test (Admin)
cd /d "%~dp0"

echo ============================================================
echo   CRM SUSTAINED LIVE TEST  (administrator / QA only)
echo   - Fresh CRM numbers only (no repeats from prior reports)
echo   - 7 minutes, 3 Google Voice lines, sequential dial
echo   - Requires consent to call loaded CRM contacts
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not on PATH.
  pause
  exit /b 1
)

python -c "from src.process_cleanup import cleanup_stale_webengine_processes; cleanup_stale_webengine_processes()" 2>nul
if exist "logs\indus_transports_autodialer.lock" del /f "logs\indus_transports_autodialer.lock"

python scripts/deep_live_test.py --min-minutes 7 --max-parallel 3 --skip-pytest --confirm "I OWN OR HAVE PERMISSION TO CALL THESE NUMBERS"
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% EQU 0 (
  echo QA test finished — check logs\deep_live_test_*_summary.json
) else (
  echo QA test reported issues — review logs\deep_live_test_crm_latest.log
)
pause
exit /b %EXITCODE%
