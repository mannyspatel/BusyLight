# Launcher: double-click or run from Explorer to install BusyLight Python dependencies.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "scripts\install-dependencies.ps1"

if (-not (Test-Path $installer)) {
    Write-Host "Could not find: $installer" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Set-Location $scriptDir
& $installer
Read-Host "Press Enter to close"