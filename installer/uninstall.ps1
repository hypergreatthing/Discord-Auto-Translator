# Discord Auto Translator - Uninstaller
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "   🗑️ Discord Auto-Translator: Uninstaller" -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Are you sure you want to uninstall Discord Auto Translator? (Y/N)"
if ($confirm -notmatch "^[yY]") {
    Write-Host "Uninstallation canceled."
    exit 0
}

# 1. Stop background process if running
$port = 49152
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Stopped running background daemon." -ForegroundColor Green
}

# 2. Remove BetterDiscord Plugin
$pluginPath = Join-Path $env:APPDATA "BetterDiscord\plugins\DiscordAutoTranslator.plugin.js"
if (Test-Path $pluginPath) {
    Remove-Item -Path $pluginPath -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed BetterDiscord plugin." -ForegroundColor Green
}

# 3. Remove Desktop Shortcut
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Discord Auto Translator.lnk"
if (Test-Path $desktopShortcut) {
    Remove-Item -Path $desktopShortcut -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed Desktop shortcut." -ForegroundColor Green
}

# 4. Remove Start Menu Shortcut
$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Discord Auto Translator"
if (Test-Path $startMenuDir) {
    Remove-Item -Path $startMenuDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed Start Menu shortcut." -ForegroundColor Green
}

# 5. Remove Startup Shortcut
$startupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "DiscordAutoTranslator.lnk"
if (Test-Path $startupShortcut) {
    Remove-Item -Path $startupShortcut -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed Startup entry." -ForegroundColor Green
}

Write-Host ""
Write-Host "Uninstallation complete! (Project files were left untouched in their folder)." -ForegroundColor Green
Write-Host ""
