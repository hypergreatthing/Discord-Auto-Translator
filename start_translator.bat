@echo off
setlocal
title Discord Auto Translator - Companion Daemon
cd /d "%~dp0"
echo ========================================================
echo  Starting Discord Auto Translator (Gamer-Friendly AI)
echo ========================================================
echo.

rem Self-healing check: if .venv doesn't exist or uvicorn isn't installed yet,
rem automatically run the setup script so start_translator.bat works out of the box!
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [*] First-time launch detected ^(.venv not created yet^).
    echo [*] Running automatic environment setup...
    echo.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" -Unattended
)

"%VENV_PY%" -c "import uvicorn, fastapi, ctranslate2" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Installing missing Python packages into .venv...
    if exist "%VENV_PY%" (
        "%VENV_PY%" -m pip install --upgrade pip
        "%VENV_PY%" -m pip install fastapi uvicorn pydantic requests langdetect regex pillow psutil pystray ctranslate2 transformers huggingface_hub
        "%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
    ) else (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" -Unattended
    )
)

echo Process Priority: BELOW_NORMAL (Yields CPU to games)
echo Background Server: http://127.0.0.1:49152
echo Tray Icon: Check your Windows Taskbar / System Tray
echo.

if exist "%VENV_PY%" (
    "%VENV_PY%" -m backend.main
) else (
    python -m backend.main
)
pause
