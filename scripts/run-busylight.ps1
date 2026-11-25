#Requires -Version 5.1
<#
.SYNOPSIS
  Start BusyLight (single instance) when on home Wi-Fi.
#>

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
    throw "Cannot determine repo root."
}

function Get-ConfigValue {
    param(
        [string]$ConfigPath,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        return $null
    }
    $pattern = '(?m)^' + [regex]::Escape($Key) + ':\s*(.+)$'
    $raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
    if ($raw -match $pattern) {
        return $Matches[1].Trim().Trim('"').Trim("'")
    }
    return $null
}

function Get-ConnectedWifiSsid {
    try {
        $output = @(netsh wlan show interfaces 2>&1 | ForEach-Object { "$_" })
        $text = $output -join "`n"
        if ($text -notmatch '(?is)State\s*:\s*connected') {
            return $null
        }
        if ($text -match '(?im)^\s*SSID\s*:\s*(.+)$') {
            return $Matches[1].Trim()
        }
    }
    catch {
        return $null
    }
    return $null
}

function Find-Pythonw {
    $candidates = @(
        @{ Cmd = 'py'; Args = @('-3.12', '-c', 'import sys; print(sys.executable)') },
        @{ Cmd = 'py'; Args = @('-3', '-c', 'import sys; print(sys.executable)') },
        @{ Cmd = 'python'; Args = @('-c', 'import sys; print(sys.executable)') }
    )
    foreach ($c in $candidates) {
        try {
            $exe = (& $c.Cmd @($c.Args) 2>&1 | Select-Object -First 1).ToString().Trim()
            if ([string]::IsNullOrWhiteSpace($exe)) { continue }
            $dir = Split-Path -Parent $exe
            $pythonw = Join-Path $dir 'pythonw.exe'
            if (Test-Path -LiteralPath $pythonw) {
                return $pythonw
            }
        }
        catch {
            continue
        }
    }
    $fallback = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($null -ne $fallback) {
        return $fallback.Source
    }
    return $null
}

$repoRoot = Get-RepoRoot
$configPath = Join-Path $repoRoot "config.yaml"
$examplePath = Join-Path $repoRoot "config.yaml.example"

if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host "config.yaml not found. Copy config.yaml.example to config.yaml and edit." -ForegroundColor Red
    Write-Host "  Example: $examplePath" -ForegroundColor DarkGray
    exit 1
}

$homeSsid = Get-ConfigValue -ConfigPath $configPath -Key 'home_wifi_ssid'
if ([string]::IsNullOrWhiteSpace($homeSsid)) {
    Write-Host "home_wifi_ssid is not set in config.yaml." -ForegroundColor Red
    exit 1
}

$currentSsid = Get-ConnectedWifiSsid
if ($currentSsid -ne $homeSsid) {
    Write-Host "Not on home Wi-Fi (expected '$homeSsid', current '$currentSsid'). Not starting BusyLight." -ForegroundColor Yellow
    exit 0
}

$pythonw = Find-Pythonw
if ([string]::IsNullOrWhiteSpace($pythonw)) {
    Write-Host "pythonw.exe not found. Run scripts\install-dependencies.ps1 first." -ForegroundColor Red
    exit 1
}

$mutexName = "Global\BusyLight-BusyLightV2"
$createdNew = $false
$mutex = New-Object System.Threading.Mutex($false, $mutexName, [ref]$createdNew)
if (-not $mutex.WaitOne(0, $false)) {
    Write-Host "BusyLight is already running." -ForegroundColor DarkGray
    exit 0
}

$launcher = Join-Path $repoRoot "busylight.py"
if (-not (Test-Path -LiteralPath $launcher)) {
    Write-Host "busylight.py not found at $launcher" -ForegroundColor Red
    exit 1
}

Set-Location -LiteralPath $repoRoot
Start-Process -FilePath $pythonw -ArgumentList @($launcher) -WorkingDirectory $repoRoot -WindowStyle Hidden
Write-Host "Started BusyLight via pythonw." -ForegroundColor Green
exit 0