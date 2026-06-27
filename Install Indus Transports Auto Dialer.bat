@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Install Indus Transports Auto Dialer
cd /d "%~dp0"

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting administrator permission for Python install if needed...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

if not exist "IndusTransports-Client-Setup.ps1" (
  echo [ERROR] IndusTransports-Client-Setup.ps1 not found in this folder.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0IndusTransports-Client-Setup.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% EQU 0 (
  echo Installation complete. Use the desktop shortcut to start.
) else (
  echo Installation failed with exit code %EXITCODE%.
)
pause
exit /b %EXITCODE%
