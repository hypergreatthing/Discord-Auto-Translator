@echo off
setlocal
title Discord Auto-Translator - Uninstaller
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall.ps1"
pause
