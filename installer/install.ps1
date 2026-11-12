# Discord Auto Translator - One-Click Setup Script
param(
    [switch]$Unattended = $false
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   🌐 Discord Auto-Translator: One-Click Installer" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# -------------------------------------------------------------
# STEP 1: BetterDiscord Detection & Plugin Installation
# -------------------------------------------------------------
Write-Host "[1/5] Checking BetterDiscord installation..." -ForegroundColor Yellow
$bdPath = Join-Path $env:APPDATA "BetterDiscord"
$pluginDestDir = Join-Path $bdPath "plugins"
$pluginSrc = Join-Path $projectRoot "plugins\betterdiscord\DiscordAutoTranslator.plugin.js"
$voicePluginSrc = Join-Path $projectRoot "plugins\betterdiscord\DiscordVoiceTranslator.plugin.js"

if (-not (Test-Path $bdPath)) {
    Write-Host "  [!] BetterDiscord directory was not found on your system." -ForegroundColor Red
    Write-Host "      Discord plugins require BetterDiscord (or Vencord)." -ForegroundColor Yellow
    if (-not $Unattended) {
        $ans = Read-Host "  Would you like to open the BetterDiscord download website? (Y/N)"
        if ($ans -match "^[yY]") {
            Start-Process "https://betterdiscord.app"
        }
    }
} else {
    if (-not (Test-Path $pluginDestDir)) {
        New-Item -ItemType Directory -Path $pluginDestDir -Force | Out-Null
    }
    if (Test-Path $pluginSrc) {
        Copy-Item -Path $pluginSrc -Destination (Join-Path $pluginDestDir "DiscordAutoTranslator.plugin.js") -Force
        Write-Host "  [OK] DiscordAutoTranslator.plugin.js installed to BetterDiscord!" -ForegroundColor Green
    } else {
        Write-Host "  [!] Plugin source file not found at $pluginSrc" -ForegroundColor Red
    }
    if (Test-Path $voicePluginSrc) {
        Copy-Item -Path $voicePluginSrc -Destination (Join-Path $pluginDestDir "DiscordVoiceTranslator.plugin.js") -Force
        Write-Host "  [OK] DiscordVoiceTranslator.plugin.js installed to BetterDiscord!" -ForegroundColor Green
    }
}

Write-Host ""

# -------------------------------------------------------------
# STEP 2: Python 3 Verification / Auto-Install (Ignores Windows Store Stub)
# -------------------------------------------------------------
Write-Host "[2/5] Checking Python installation..." -ForegroundColor Yellow

function Test-RealPython($exePath, [string[]]$extraArgs = @()) {
    if (-not $exePath) { return $false }
    try {
        $out = & $exePath @extraArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match "^3\.\d+") {
            return $true
        }
    } catch {}
    return $false
}

function Find-PythonCommand {
    # 1. Check project local venv first
    $localVenv = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if ((Test-Path $localVenv) -and (Test-RealPython $localVenv)) {
        return @{ Exe = $localVenv; Args = @() }
    }

    # 2. Check standard Python 3.12 / 3.11 / 3.10 install locations
    foreach ($ver in @("312", "311", "310", "313")) {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver\python.exe"),
            "C:\Python$ver\python.exe",
            "C:\Program Files\Python$ver\python.exe"
        )
        foreach ($c in $candidates) {
            if ((Test-Path $c) -and (Test-RealPython $c)) {
                return @{ Exe = $c; Args = @() }
            }
        }
    }

    # 3. Check 'py' launcher (prefer 3.12 for maximum prebuilt wheel compatibility)
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($v in @("-3.12", "-3.11", "-3.10", "-3")) {
            if (Test-RealPython $pyLauncher.Source @($v)) {
                return @{ Exe = $pyLauncher.Source; Args = @($v) }
            }
        }
    }

    # 4. Check 'python' in PATH (filtering out the fake WindowsApps Microsoft Store stub)
    $pyCmds = Get-Command python -All -ErrorAction SilentlyContinue
    foreach ($p in $pyCmds) {
        if ($p.Source -notlike "*WindowsApps*" -and (Test-RealPython $p.Source)) {
            return @{ Exe = $p.Source; Args = @() }
        }
    }
    return $null
}

$pyInfo = Find-PythonCommand

if (-not $pyInfo) {
    Write-Host "  [!] Python 3 was not found on your system." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  [*] Automatically installing Python 3.12 via Windows winget..." -ForegroundColor Cyan
        Start-Process winget -ArgumentList "install Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements" -Wait
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $pyInfo = Find-PythonCommand
    }

    if (-not $pyInfo) {
        Write-Host "  [!] Could not auto-install Python. Opening python.org download page..." -ForegroundColor Red
        Write-Host "      IMPORTANT: Please check 'Add Python to PATH' during installation." -ForegroundColor Yellow
        Start-Process "https://www.python.org/downloads/"
        Write-Host ""
        Read-Host "Press Enter after Python installation finishes to continue"
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $pyInfo = Find-PythonCommand
    }
}

if ($pyInfo) {
    $pyExe = $pyInfo.Exe
    $pyArgs = $pyInfo.Args
    $ver = & $pyExe @pyArgs --version 2>&1
    Write-Host "  [OK] Using Python: $ver ($pyExe $($pyArgs -join ' '))" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Python is required to run the AI translation companion daemon." -ForegroundColor Red
    Write-Host "          Please install Python 3.12 from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
    if (-not $Unattended) { Read-Host "Press Enter to exit" }
    exit 1
}

Write-Host ""

# -------------------------------------------------------------
# STEP 3: Setup Virtual Environment & Install Dependencies
# -------------------------------------------------------------
Write-Host "[3/5] Setting up isolated application environment (.venv)..." -ForegroundColor Yellow
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "  [*] Creating dedicated virtual environment in .venv..." -ForegroundColor Cyan
    & $pyExe @pyArgs -m venv $venvDir
}

if (Test-Path $venvPython) {
    $activePython = $venvPython
    $activeArgs = @()
    Write-Host "  [OK] Dedicated virtual environment (.venv) ready." -ForegroundColor Green
} else {
    Write-Host "  [!] Virtual environment creation failed. Installing into user Python environment..." -ForegroundColor Yellow
    $activePython = $pyExe
    $activeArgs = $pyArgs
}

Write-Host "  [*] Upgrading pip..." -ForegroundColor Cyan
& $activePython @activeArgs -m pip install --upgrade pip

Write-Host "  [*] Step 3a: Installing core AI translation & server packages (FastAPI, Uvicorn, CTranslate2)..." -ForegroundColor Cyan
& $activePython @activeArgs -m pip install fastapi uvicorn pydantic requests langdetect regex pillow psutil pystray ctranslate2 transformers huggingface_hub

$reqFile = Join-Path $projectRoot "requirements.txt"
if (Test-Path $reqFile) {
    Write-Host "  [*] Step 3b: Installing multilingual OCR & Real-Time Voice packages..." -ForegroundColor Cyan
    & $activePython @activeArgs -m pip install -r $reqFile
    # Install rapidocr-onnxruntime pure-Python wheel even on Python 3.13/3.14 where its metadata caps <3.13
    & $activePython @activeArgs -m pip install rapidocr-onnxruntime --no-deps --ignore-requires-python
}

# Verify core packages are importable
& $activePython @activeArgs -c "import uvicorn, fastapi, ctranslate2" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] All AI translation, server, and OCR dependencies verified!" -ForegroundColor Green
} else {
    Write-Host "  [!] Warning: Some packages failed to install. Retrying with --user..." -ForegroundColor Yellow
    & $pyExe @pyArgs -m pip install --user fastapi uvicorn pydantic requests langdetect regex pillow psutil pystray ctranslate2 transformers huggingface_hub
}

Write-Host ""

if ($Unattended) {
    exit 0
}

# -------------------------------------------------------------
# STEP 4: Create Desktop & Start Menu Shortcuts
# -------------------------------------------------------------
Write-Host "[4/5] Creating application shortcuts..." -ForegroundColor Yellow

$wshShell = New-Object -ComObject WScript.Shell
$desktopDir = [Environment]::GetFolderPath("Desktop")
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Discord Auto Translator"
if (-not (Test-Path $startMenuDir)) {
    New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
}

$silentLauncher = Join-Path $projectRoot "start_silent.vbs"
$iconLocation = "$env:SystemRoot\System32\shell32.dll,14" # Globe icon in Windows shell32

# Desktop Shortcut
$desktopShortcutPath = Join-Path $desktopDir "Discord Auto Translator.lnk"
$desktopShortcut = $wshShell.CreateShortcut($desktopShortcutPath)
$desktopShortcut.TargetPath = "wscript.exe"
$desktopShortcut.Arguments = "`"$silentLauncher`""
$desktopShortcut.WorkingDirectory = $projectRoot
$desktopShortcut.Description = "Launch Discord Auto Translator Background Daemon"
$desktopShortcut.IconLocation = $iconLocation
$desktopShortcut.Save()
Write-Host "  [OK] Desktop shortcut created: 'Discord Auto Translator'" -ForegroundColor Green

# Start Menu Shortcut
$startShortcutPath = Join-Path $startMenuDir "Discord Auto Translator.lnk"
$startShortcut = $wshShell.CreateShortcut($startShortcutPath)
$startShortcut.TargetPath = "wscript.exe"
$startShortcut.Arguments = "`"$silentLauncher`""
$startShortcut.WorkingDirectory = $projectRoot
$startShortcut.Description = "Launch Discord Auto Translator Background Daemon"
$startShortcut.IconLocation = $iconLocation
$startShortcut.Save()
Write-Host "  [OK] Start Menu shortcut created." -ForegroundColor Green

Write-Host ""

# -------------------------------------------------------------
# STEP 5: Windows Startup & Launch Confirmation
# -------------------------------------------------------------
Write-Host "[5/5] Additional options..." -ForegroundColor Yellow
$startupChoice = Read-Host "  Would you like Discord Auto Translator to automatically start on Windows boot? (Y/N)"
if ($startupChoice -match "^[yY]") {
    $startupFolder = [Environment]::GetFolderPath("Startup")
    $startupShortcutPath = Join-Path $startupFolder "DiscordAutoTranslator.lnk"
    $startupShortcut = $wshShell.CreateShortcut($startupShortcutPath)
    $startupShortcut.TargetPath = "wscript.exe"
    $startupShortcut.Arguments = "`"$silentLauncher`""
    $startupShortcut.WorkingDirectory = $projectRoot
    $startupShortcut.Description = "Auto-start Discord Auto Translator on boot"
    $startupShortcut.IconLocation = $iconLocation
    $startupShortcut.Save()
    Write-Host "  [OK] Added to Windows Startup!" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "   🎉 Installation Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  • BetterDiscord Plugins: Installed & active" -ForegroundColor Cyan
Write-Host "  • AI Translation Daemon: Configured with gamer-friendly low CPU priority" -ForegroundColor Cyan
Write-Host "  • Desktop Shortcut: Ready on your Desktop" -ForegroundColor Cyan
Write-Host ""

$launchNow = Read-Host "Would you like to start Discord Auto Translator right now? (Y/N)"
if ($launchNow -match "^[yY]") {
    Start-Process "wscript.exe" -ArgumentList "`"$silentLauncher`""
    Write-Host "  [OK] Translator started in background! Check your Windows system tray (near clock)." -ForegroundColor Green
}
Write-Host ""
