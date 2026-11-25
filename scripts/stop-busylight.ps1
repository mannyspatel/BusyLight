#Requires -Version 5.1
<#
.SYNOPSIS
  Stop a running BusyLight (pythonw busylight.py) process.
#>

$ErrorActionPreference = "Continue"

function Get-RepoRoot {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
    throw "Cannot determine repo root."
}

$repoRoot = Get-RepoRoot
$launcherName = "busylight.py"
$stopped = 0

Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ($_.CommandLine -and $_.CommandLine -match [regex]::Escape($launcherName)) {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                $stopped += 1
                Write-Host "Stopped PID $($_.ProcessId)" -ForegroundColor Green
            }
            catch {
                Write-Host "Could not stop PID $($_.ProcessId): $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }

if ($stopped -eq 0) {
    Write-Host "No running BusyLight (pythonw busylight.py) process found." -ForegroundColor DarkGray
}
else {
    Write-Host "Stopped $stopped BusyLight process(es)." -ForegroundColor Green
}