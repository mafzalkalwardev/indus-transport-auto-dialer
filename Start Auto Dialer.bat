@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Indus Transports Auto Dialer
cd /d "%~dp0"

if exist "dist\IndusTransports_AutoDialer.exe" (
  start "" "dist\IndusTransports_AutoDialer.exe"
  exit /b 0
)

if exist "IndusTransports_AutoDialer.exe" (
  start "" "IndusTransports_AutoDialer.exe"
  exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No EXE found and Python is not installed.
  echo Run "Install Indus Transports Auto Dialer.bat" first.
  pause
  exit /b 1
)

python autodialer_gui.py
exit /b %ERRORLEVEL%
