@echo off
setlocal
title Discord Auto-Translator - Installer
cd /d "%~dp0"

rem Common mistake: double-clicking this file while still inside the downloaded ZIP.
rem Windows then copies only this one file to a temp folder, so the rest of the project is missing.
if not exist "%~dp0installer\install.ps1" (
    echo.
    echo ============================================================
    echo   Please EXTRACT the ZIP file first!
    echo ============================================================
    echo.
    echo   1. Close this window.
    echo   2. Right-click the downloaded ZIP file and choose "Extract All..."
    echo   3. Pick a permanent place, e.g. your Documents folder.
    echo   4. Open the extracted folder and double-click Easy_Install.bat again.
    echo.
    pause
    exit /b 1
)

echo Launching One-Click Installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] An error occurred during setup.
    pause
)
