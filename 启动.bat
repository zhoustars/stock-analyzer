@echo off
title A-Stock Analyzer
cd /d d:\aitest\stock

echo ==================================================
echo   A-Stock Analyzer Starting...
echo ==================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install dependencies on first run
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [INFO] First run, installing dependencies...
    pip install -r requirements.txt
    echo.
)

:: Kill process occupying port 5000 (avoid port conflict on re-launch)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo [INFO] Killing old process on port 5000, PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

:: Start Flask
echo [START] Server starting...
echo [INFO] Browser will open: http://127.0.0.1:5000
echo [INFO] Press Ctrl+C to stop
echo.

:: Open browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

python web_app.py

pause
