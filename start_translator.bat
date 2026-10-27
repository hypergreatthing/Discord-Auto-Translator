@echo off
title Discord Auto Translator - Companion Daemon
cd /d "%~dp0"
echo ========================================================
echo  Starting Discord Auto Translator (Gamer-Friendly AI)
echo ========================================================
echo.
echo Process Priority: BELOW_NORMAL (Yields CPU to games)
echo Background Server: http://127.0.0.1:49152
echo Tray Icon: Check your Windows Taskbar / System Tray
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m backend.main
) else (
    python -m backend.main
)
pause
