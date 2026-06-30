@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Build Indus Transports Auto Dialer
cd /d "%~dp0"

echo ============================================================
echo   INDUS TRANSPORTS LLC — Auto Dialer  |  EXE Build
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo Enable "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

python build.py
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% EQU 0 (
  echo Build finished. EXE is in the dist folder.
) else (
  echo Build failed with exit code %EXITCODE%.
)
pause
exit /b %EXITCODE%
