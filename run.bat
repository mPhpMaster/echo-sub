@echo off
rem Starts EchoSub from source without a console window.
rem First-time setup: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo EchoSub is not set up yet. Run: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe -m echosub
