@echo off
:: System Diagnostics API — Elevated Launcher
:: This service requires administrator privileges to access:
:: GPU engine data, WMI hardware counters, Windows Services,
:: memory hardware reserved, and WiFi signal strength.

net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:run
echo.
echo  System Diagnostics API
echo  Running with administrator privileges
echo  API available at: http://localhost:8000
echo  API docs at:      http://localhost:8000/docs
echo.
echo  Set your API key in config.yaml before connecting an LLM.
echo.
cd /d "%~dp0"
uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
