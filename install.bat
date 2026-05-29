@echo off
echo ============================================================
echo   INDUS TRANSPORTS LLC Auto Dialer Pro — Setup
echo ============================================================
echo.
echo Installing Python packages (PyQt6 + WebEngine = ~500MB)...
echo This will take a few minutes depending on your connection.
echo.
python -m pip install --upgrade pip
python -m pip install PyQt6 PyQt6-WebEngine
python -m pip install pandas openpyxl Pillow pyperclip
echo.
echo ============================================================
echo   Setup complete! Run the app with:
echo     python autodialer_gui.py
echo ============================================================
pause
