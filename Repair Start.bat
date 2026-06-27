@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Repair Indus Transports Auto Dialer
cd /d "%~dp0"

echo ============================================================
echo   Indus Transports Auto Dialer — Repair
echo ============================================================
echo.

if exist "scripts\clean_workspace.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\clean_workspace.ps1"
)

if not exist "logs" mkdir logs
if not exist "data" mkdir data
if not exist "chrome_profiles" mkdir chrome_profiles

where python >nul 2>&1
if not errorlevel 1 (
  echo Reinstalling Python packages...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
)

echo.
echo Repair complete. Starting the app...
call "%~dp0Start Auto Dialer.bat"
