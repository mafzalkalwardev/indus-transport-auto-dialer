@echo off
echo ============================================================
echo   INDUS TRANSPORTS LLC — Auto Dialer  |  Developer Setup
echo ============================================================
echo.
echo For end users, use: Install Indus Transports Auto Dialer.bat
echo For EXE build, use: Build Auto Dialer.bat
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo ============================================================
echo   Setup complete! Run:
echo     Start Auto Dialer.bat
echo   or:
echo     python autodialer_gui.py
echo ============================================================
pause
