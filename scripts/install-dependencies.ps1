#Requires -Version 5.1
<#
.SYNOPSIS
  Installs Python dependencies for the Teams Status Light Controller (BusyLight).

.DESCRIPTION
  Idempotent setup: installs Python via winget when missing, detects Python,
  upgrades pip when needed, and installs packages from requirements.txt only
  when they are missing or below minimum version.
#>

$ErrorActionPreference = "Stop"
$script:InstallerVersion = '1.2'

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ('==> ' + $Message) -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Skip {
    param([string]$Message)
    Write-Host "    SKIP: $Message" -ForegroundColor DarkGray
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    NOTE: $Message" -ForegroundColor Yellow
}

function Get-RepoRoot {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
    throw "Cannot determine repo root (run this script with: powershell -File scripts\install-dependencies.ps1)"
}

function Test-RealPythonVersionOutput {
    param([string[]]$OutputLines)

    if ($null -eq $OutputLines -or $OutputLines.Count -eq 0) {
        return $false
    }

    $combined = ($OutputLines | ForEach-Object { "$_" }) -join "`n"
    if ($combined -match "Microsoft Store" -or $combined -match "run without arguments to install") {
        return $false
    }
    if ($combined -notmatch "Python 3\.") {
        return $false
    }
    return $true
}

function Find-PythonExecutable {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3", "--version") },
        @{ Cmd = "python"; Args = @("--version") }
    )

    foreach ($c in $candidates) {
        try {
            $output = @(& $c.Cmd @($c.Args) 2>&1 | ForEach-Object { "$_" })
            if ($LASTEXITCODE -eq 0 -and (Test-RealPythonVersionOutput -OutputLines $output)) {
                if ($c.Cmd -eq "py") {
                    return @{ Launcher = "py"; PipArgs = @("-3", "-m", "pip"); PyArgs = @("-3") }
                }
                return @{ Launcher = "python"; PipArgs = @("-m", "pip"); PyArgs = @() }
            }
        }
        catch {
            # try next
        }
    }
    return $null
}

function Test-WingetAvailable {
    try {
        $null = Get-Command winget -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Add-PythonPathEntries {
    param([string[]]$Directories)

    foreach ($dir in $Directories) {
        if (-not [string]::IsNullOrWhiteSpace($dir) -and (Test-Path -LiteralPath $dir)) {
            if ($env:PATH -notlike "*$dir*") {
                $env:PATH = "$dir;$env:PATH"
            }
        }
    }
}

function Refresh-SessionPythonPath {
    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    $candidates = @(
        Join-Path $localAppData 'Programs\Python\Python312'
        Join-Path $localAppData 'Programs\Python\Python312\Scripts'
        'C:\Program Files\Python312'
        'C:\Program Files\Python312\Scripts'
        'C:\Program Files (x86)\Python312'
        'C:\Program Files (x86)\Python312\Scripts'
    )

    foreach ($root in @(
            Join-Path $localAppData 'Programs\Python'
            'C:\Program Files\Python312'
            'C:\Program Files (x86)\Python312'
        )) {
        if (Test-Path -LiteralPath $root) {
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $candidates += $_.FullName
                $scripts = Join-Path $_.FullName 'Scripts'
                if (Test-Path -LiteralPath $scripts) {
                    $candidates += $scripts
                }
            }
        }
    }

    Add-PythonPathEntries -Directories ($candidates | Select-Object -Unique)
}

function Show-ManualPythonInstructions {
    Write-Host ""
    Write-Host "Please install Python 3.7 or newer from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "During setup, check ""Add Python to PATH""." -ForegroundColor Yellow
    Write-Host "Use the installer from python.org - not the Microsoft Store app execution alias stubs." -ForegroundColor Yellow
    Write-Host ""
    Write-Host 'Optional: Settings, Apps, Advanced app settings, App execution aliases -' -ForegroundColor DarkGray
    Write-Host "turn off python.exe and python3.exe so Windows does not intercept the python command." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Then run this installer again." -ForegroundColor Yellow
}

function Test-WingetInstallYes {
    param([string]$Reply)
    if ([string]::IsNullOrWhiteSpace($Reply)) {
        return $true
    }
    if ($Reply -match '^[Yy]') {
        return $true
    }
    if ($Reply -match '^[Nn]') {
        return $false
    }
    return $true
}

function Install-PythonWithWinget {
    Write-Step "Installing Python 3.12 via winget..."
    Write-Warn "This may prompt for administrator or IT approval on corporate laptops."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
}

function Invoke-Python {
    param(
        [hashtable]$Python,
        [string[]]$ScriptArgs
    )
    if ($Python.Launcher -eq "py") {
        & py @($Python.PyArgs + $ScriptArgs)
    }
    else {
        & python @ScriptArgs
    }
}

function Invoke-Pip {
    param(
        [hashtable]$Python,
        [string[]]$PipSubArgs
    )
    if ($Python.Launcher -eq "py") {
        & py @($Python.PyArgs + @("-m", "pip") + $PipSubArgs)
    }
    else {
        & python -m pip @PipSubArgs
    }
}

function Get-InstalledPackageVersion {
    param(
        [hashtable]$Python,
        [string]$PackageName
    )
    $lines = Invoke-Pip -Python $Python -PipSubArgs @("show", $PackageName) 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    foreach ($line in $lines) {
        if ($line -match "^Version:\s*(.+)$") {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Test-VersionSatisfiesMinimum {
    param(
        [string]$Installed,
        [string]$Minimum
    )
    if ([string]::IsNullOrWhiteSpace($Installed)) { return $false }

    try {
        $installedV = [version]$Installed
        $minV = [version]$Minimum
        return ($installedV -ge $minV)
    }
    catch {
        # Date-style versions (e.g. pycaw 20230407) may not parse as System.Version.
        if ($Installed -match "^\d+$" -and $Minimum -match "^\d+$") {
            return ([int64]$Installed -ge [int64]$Minimum)
        }
        return ($Installed -ge $Minimum)
    }
}

function Parse-RequirementLine {
    param([string]$Line)
    $trimmed = $Line.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
        return $null
    }
    if ($trimmed -match "^([A-Za-z0-9_.\-]+)\s*>=\s*(.+)$") {
        return @{
            Name = $Matches[1]
            Minimum = $Matches[2].Trim()
            Spec = $trimmed
        }
    }
    if ($trimmed -match "^([A-Za-z0-9_.\-]+)") {
        return @{
            Name = $Matches[1]
            Minimum = $null
            Spec = $trimmed
        }
    }
    return $null
}

function Test-PipUsable {
    param([hashtable]$Python)
    try {
        Invoke-Pip -Python $Python -PipSubArgs @("--version") | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Update-PipIfNeeded {
    param([hashtable]$Python)
    if (-not (Test-PipUsable -Python $Python)) {
        Write-Warn "pip is not available; bootstrapping with ensurepip..."
        Invoke-Python -Python $Python -ScriptArgs @("-m", "ensurepip", "--upgrade")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to bootstrap pip. Install Python from python.org and ensure 'Add Python to PATH' is checked."
        }
    }

    $pipVersionLine = (Invoke-Pip -Python $Python -PipSubArgs @("--version") | Select-Object -First 1)
    if ($pipVersionLine -match "pip (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 21) {
            Write-Step "Upgrading pip (current: $pipVersionLine)"
            Invoke-Pip -Python $Python -PipSubArgs @("install", "--upgrade", "pip")
            if ($LASTEXITCODE -ne 0) {
                throw "pip upgrade failed."
            }
            Write-Ok "pip upgraded"
        }
        else {
            Write-Skip "pip is recent enough ($pipVersionLine)"
        }
    }
}

function Install-Requirements {
    param(
        [hashtable]$Python,
        [string]$RequirementsPath
    )
    if (-not (Test-Path $RequirementsPath)) {
        throw "requirements.txt not found at: $RequirementsPath"
    }

    $toInstall = @()
    $lines = Get-Content -Path $RequirementsPath

    foreach ($line in $lines) {
        $req = Parse-RequirementLine -Line $line
        if ($null -eq $req) { continue }

        $installed = Get-InstalledPackageVersion -Python $Python -PackageName $req.Name
        if ($null -ne $installed) {
            if ($null -ne $req.Minimum) {
                if (Test-VersionSatisfiesMinimum -Installed $installed -Minimum $req.Minimum) {
                    Write-Skip "$($req.Name) $installed (meets $($req.Spec))"
                    continue
                }
                Write-Warn "$($req.Name) $installed is below $($req.Spec); will upgrade"
            }
            else {
                Write-Skip "$($req.Name) $installed already installed"
                continue
            }
        }
        else {
            Write-Warn "$($req.Name) not installed; will install $($req.Spec)"
        }
        $toInstall += $req.Spec
    }

    if ($toInstall.Count -eq 0) {
        Write-Ok "All required packages are already satisfied."
        return
    }

    Write-Step "Installing: $($toInstall -join ', ')"
    Invoke-Pip -Python $Python -PipSubArgs @("install", $toInstall)
    if ($LASTEXITCODE -ne 0) {
        throw "One or more package installations failed."
    }
    Write-Ok "Package installation complete"
}

# --- Main ---
Clear-Host
Write-Host "============================================================" -ForegroundColor White
Write-Host ('  BusyLight - Install Python and Dependencies (installer v' + $script:InstallerVersion + ')') -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White

$repoRoot = Get-RepoRoot
$requirementsFile = Join-Path $repoRoot "requirements.txt"

Write-Step "Looking for Python (py -3 or python)..."
$python = Find-PythonExecutable

if ($null -eq $python) {
    Write-Host ""
    Write-Host "Python was not found on this system." -ForegroundColor Red

    $wingetInstalled = $false
    if (Test-WingetAvailable) {
        Write-Host ""
        $reply = Read-Host 'Install Python 3.12 via winget now? (Y/n)'
        if (Test-WingetInstallYes -Reply $reply) {
            $wingetInstalled = Install-PythonWithWinget
            if ($wingetInstalled) {
                Write-Ok "winget reported Python installation finished"
                Refresh-SessionPythonPath
                Write-Step "Looking for Python after winget install..."
                $python = Find-PythonExecutable
            }
            else {
                Write-Host ""
                Write-Host "winget could not install Python (missing rights, policy, or network)." -ForegroundColor Red
            }
        }
        else {
            Write-Warn "Skipped automatic Python install via winget."
        }
    }

    if ($null -eq $python) {
        Show-ManualPythonInstructions
        if (-not (Test-WingetAvailable)) {
            Write-Host ""
            Write-Warn "winget is not available on this PC; use python.org or ask IT to install Python 3.12."
        }
        exit 1
    }
}

$versionOut = Invoke-Python -Python $python -ScriptArgs @("--version")
Write-Ok ('Found Python: ' + ($versionOut -join ' '))

Write-Step "Checking pip..."
Update-PipIfNeeded -Python $python

Write-Step "Checking packages from requirements.txt..."
Install-Requirements -Python $python -RequirementsPath $requirementsFile

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup finished successfully!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next step - run the controller from this folder:" -ForegroundColor White
Write-Host "  python teams_light_controller.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "Repo root: $repoRoot" -ForegroundColor DarkGray
Read-Host 'Press Enter to close'