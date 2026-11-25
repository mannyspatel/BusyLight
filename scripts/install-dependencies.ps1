#Requires -Version 5.1
<#
.SYNOPSIS
  Installs Python dependencies for the Teams Status Light Controller (BusyLight).

.DESCRIPTION
  Idempotent setup: installs Python via winget when missing, detects Python
  (supported: 3.10–3.12; warns on 3.13+), upgrades pip when needed, and installs
  packages from requirements.txt only when they are missing or below minimum version.
#>

$ErrorActionPreference = "Stop"
$script:InstallerVersion = '1.5'
$script:PythonMinorMin = 10
$script:PythonMinorMax = 12

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

function Import-UserPathFromRegistry {
    try {
        $userPath = (Get-ItemProperty -Path 'HKCU:\Environment' -Name Path -ErrorAction SilentlyContinue).Path
        if ([string]::IsNullOrWhiteSpace($userPath)) {
            return
        }
        $regDirs = $userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $prepend = @()
        foreach ($dir in $regDirs) {
            if ($env:PATH -notlike "*$dir*") {
                $prepend += $dir
            }
        }
        if ($prepend.Count -gt 0) {
            $env:PATH = ($prepend -join ';') + ';' + $env:PATH
        }
    }
    catch {
        # ignore registry read failures
    }
}

function Get-PythonVersionFromOutput {
    param([string[]]$OutputLines)

    if ($null -eq $OutputLines -or $OutputLines.Count -eq 0) {
        return $null
    }
    $combined = ($OutputLines | ForEach-Object { "$_" }) -join "`n"
    if ($combined -match 'Python\s+(\d+)\.(\d+)(?:\.(\d+))?') {
        $patch = 0
        if (-not [string]::IsNullOrWhiteSpace($Matches[3])) {
            $patch = [int]$Matches[3]
        }
        return [pscustomobject]@{
            Major = [int]$Matches[1]
            Minor = [int]$Matches[2]
            Patch = $patch
        }
    }
    return $null
}

function Test-PythonVersionInSupportedRange {
    param($Version)

    if ($null -eq $Version -or $Version.Major -ne 3) {
        return $false
    }
    return ($Version.Minor -ge $script:PythonMinorMin -and $Version.Minor -le $script:PythonMinorMax)
}

function New-PythonHandleFromLauncherCandidate {
    param(
        [string]$Cmd,
        [string[]]$PyArgs,
        [string[]]$VersionOutput
    )

    if ($Cmd -eq 'py') {
        return @{
            Launcher   = 'py'
            PipArgs    = @($PyArgs + @('-m', 'pip'))
            PyArgs     = $PyArgs
            VersionOut = $VersionOutput
        }
    }
    return @{
        Launcher   = 'python'
        PipArgs    = @('-m', 'pip')
        PyArgs     = @()
        VersionOut = $VersionOutput
    }
}

function Find-PythonOnDisk {
    $exePaths = @()
    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    $userPythonRoot = Join-Path $localAppData 'Programs\Python'
    if (Test-Path -LiteralPath $userPythonRoot) {
        Get-ChildItem -LiteralPath $userPythonRoot -Filter 'python.exe' -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { $exePaths += $_.FullName }
    }
    $programFilesPattern = 'C:\Program Files\Python*'
    Get-ChildItem -Path $programFilesPattern -Filter 'python.exe' -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object { $exePaths += $_.FullName }

    $best = $null
    $bestSort = $null

    foreach ($exe in ($exePaths | Select-Object -Unique)) {
        try {
            $output = @(& $exe --version 2>&1 | ForEach-Object { "$_" })
            if ($LASTEXITCODE -ne 0 -or -not (Test-RealPythonVersionOutput -OutputLines $output)) {
                continue
            }
            $ver = Get-PythonVersionFromOutput -OutputLines $output
            if (-not (Test-PythonVersionInSupportedRange -Version $ver)) {
                continue
            }
            $sortKey = [version]"$($ver.Major).$($ver.Minor).$($ver.Patch)"
            if ($null -eq $bestSort -or $sortKey -gt $bestSort) {
                $bestSort = $sortKey
                $best = @{
                    Launcher   = 'exe'
                    Exe        = $exe
                    VersionOut = $output
                }
            }
        }
        catch {
            # try next on-disk candidate
        }
    }
    return $best
}

function Find-PythonExecutable {
    Import-UserPathFromRegistry

    $launcherCandidates = @(
        @{ Cmd = 'py'; VersionArgs = @('-3.12', '--version'); PyArgs = @('-3.12') },
        @{ Cmd = 'py'; VersionArgs = @('-3.11', '--version'); PyArgs = @('-3.11') },
        @{ Cmd = 'py'; VersionArgs = @('-3.10', '--version'); PyArgs = @('-3.10') },
        @{ Cmd = 'py'; VersionArgs = @('-3', '--version'); PyArgs = @('-3') },
        @{ Cmd = 'python'; VersionArgs = @('--version'); PyArgs = @() }
    )

    $fallback = $null

    foreach ($c in $launcherCandidates) {
        try {
            $output = @(& $c.Cmd @($c.VersionArgs) 2>&1 | ForEach-Object { "$_" })
            if ($LASTEXITCODE -ne 0 -or -not (Test-RealPythonVersionOutput -OutputLines $output)) {
                continue
            }
            $handle = New-PythonHandleFromLauncherCandidate -Cmd $c.Cmd -PyArgs $c.PyArgs -VersionOutput $output
            $ver = Get-PythonVersionFromOutput -OutputLines $output
            if (Test-PythonVersionInSupportedRange -Version $ver) {
                return $handle
            }
            if ($null -eq $fallback) {
                $fallback = $handle
            }
        }
        catch {
            # try next
        }
    }

    $onDisk = Find-PythonOnDisk
    if ($null -ne $onDisk) {
        return $onDisk
    }

    return $fallback
}

function Test-PythonVersionSupported {
    param([hashtable]$Python)

    $output = @(Invoke-Python -Python $Python -ScriptArgs @('--version') 2>&1 | ForEach-Object { "$_" })
    $ver = Get-PythonVersionFromOutput -OutputLines $output
    $display = ($output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($display) -and $null -ne $ver) {
        $display = "Python $($ver.Major).$($ver.Minor).$($ver.Patch)"
    }

    if ($null -eq $ver) {
        Write-Warn "Could not parse Python version from: $($output -join ' ')"
        return
    }

    Write-Ok ('Found Python: ' + $display)

    if (Test-PythonVersionInSupportedRange -Version $ver) {
        Write-Ok "Python $($ver.Major).$($ver.Minor) is supported (BusyLight targets 3.$($script:PythonMinorMin)–3.$($script:PythonMinorMax))."
        return
    }

    if ($ver.Minor -ge 13) {
        Write-Host ""
        Write-Host "    WARNING: Python $($ver.Major).$($ver.Minor).$($ver.Patch) is not supported yet." -ForegroundColor Yellow
        Write-Host "    Packages such as pycaw may fail to install on Python 3.13+ (no wheels)." -ForegroundColor Yellow
        Write-Host "    Recommended: install Python 3.12 from python.org or use: py -3.12" -ForegroundColor Yellow
        Write-Host ""
        $reply = Read-Host 'Continue with this Python anyway? (y/N)'
        if ($reply -notmatch '^[Yy]') {
            Write-Host ""
            Write-Host "Install Python 3.12 and run this installer again." -ForegroundColor Yellow
            Write-Host "  winget install -e --id Python.Python.3.12" -ForegroundColor DarkGray
            Write-Host "  py -3.12   (if Python 3.12 is already installed)" -ForegroundColor DarkGray
            exit 1
        }
        Write-Warn "Continuing with unsupported Python $($ver.Major).$($ver.Minor).$($ver.Patch)"
        return
    }

    Write-Host ""
    Write-Host "    WARNING: Python $($ver.Major).$($ver.Minor).$($ver.Patch) is below the minimum (3.$($script:PythonMinorMin))." -ForegroundColor Yellow
    Write-Host "    Install Python 3.12 from python.org or use: py -3.12" -ForegroundColor Yellow
    Write-Host ""
    $reply = Read-Host 'Continue anyway? (y/N)'
    if ($reply -notmatch '^[Yy]') {
        exit 1
    }
    Write-Warn "Continuing with Python $($ver.Major).$($ver.Minor).$($ver.Patch)"
}

function Test-WingetInstallSuccessOutput {
    param([string[]]$OutputLines)

    if ($null -eq $OutputLines -or $OutputLines.Count -eq 0) {
        return $false
    }
    $combined = ($OutputLines | ForEach-Object { "$_" }) -join "`n"
    return ($combined -match '(?i)installed|already installed|found|successfully|no available upgrade')
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

function Install-PythonFromPythonOrg {
    param(
        [string]$Version = '3.12.8'
    )

    $fileName = "python-$Version-amd64.exe"
    # SECURITY-REVIEW: Fixed official python.org FTP URL for the installer binary.
    $url = "https://www.python.org/ftp/python/$Version/$fileName"
    $installerPath = Join-Path $env:TEMP $fileName

    Write-Step "Downloading Python $Version from python.org..."
    Write-Warn "Network access is required for this step."

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $installerPath -UseBasicParsing
        if (-not (Test-Path -LiteralPath $installerPath)) {
            Write-Warn "Download did not produce an installer file."
            return $false
        }
    }
    catch {
        Write-Warn "Could not download Python installer: $($_.Exception.Message)"
        return $false
    }
    finally {
        $ErrorActionPreference = $prevEap
    }

    Write-Step "Installing Python $Version (per-user, Prepends PATH)..."
    $installArgs = @(
        '/quiet',
        'InstallAllUsers=0',
        'PrependPath=1',
        'Include_test=0'
    )
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $proc = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru
        $ok = ($proc.ExitCode -eq 0)
        if (-not $ok) {
            Write-Warn "Python installer exited with code $($proc.ExitCode)."
        }
        return $ok
    }
    catch {
        Write-Warn "Python installer failed: $($_.Exception.Message)"
        return $false
    }
    finally {
        $ErrorActionPreference = $prevEap
        if (Test-Path -LiteralPath $installerPath) {
            Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Show-ManualPythonInstructions {
    Write-Host ""
    Write-Host "Please install Python 3.12 (supported: 3.10–3.12) from:" -ForegroundColor Yellow
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

function Invoke-WingetPythonInstall {
    param([string[]]$ExtraWingetArgs)

    $baseArgs = @(
        'install', '-e', '--id', 'Python.Python.3.12',
        '--accept-package-agreements', '--accept-source-agreements'
    )
    $output = @(& winget @baseArgs @ExtraWingetArgs 2>&1 | ForEach-Object { "$_" })
    return @{
        ExitOk     = ($LASTEXITCODE -eq 0)
        Output     = $output
        OutputMatch = (Test-WingetInstallSuccessOutput -OutputLines $output)
    }
}

function Install-PythonWithWinget {
    Write-Step "Installing Python 3.12 via winget (per-user scope first)..."
    Write-Warn "This may prompt for administrator or IT approval on corporate laptops."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $result = Invoke-WingetPythonInstall -ExtraWingetArgs @('--scope', 'user')
        if (-not ($result.ExitOk -and $result.OutputMatch)) {
            Write-Warn "Per-user winget install did not complete; retrying without --scope user..."
            $result = Invoke-WingetPythonInstall -ExtraWingetArgs @()
        }

        if ($result.ExitOk -and $result.OutputMatch) {
            return $true
        }
        if ($result.ExitOk -and -not $result.OutputMatch) {
            Write-Warn "winget returned success but install may not have completed"
        }
        return $false
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
}

function Show-WingetPythonNotFoundSteps {
    Write-Host ""
    Write-Host "winget indicated Python was installed, but this session still cannot run it." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Try these steps:" -ForegroundColor Yellow
    Write-Host "  1. Settings, Apps, Advanced app settings, App execution aliases" -ForegroundColor Yellow
    Write-Host "     - Turn OFF python.exe and python3.exe so Store stubs do not intercept the command." -ForegroundColor Yellow
    Write-Host "  2. In PowerShell, run: winget list --id Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "     - Confirm the package is listed; if not, install failed or was blocked by policy." -ForegroundColor Yellow
    Write-Host "  3. Install from https://www.python.org/downloads/ with ""Add Python to PATH"" checked." -ForegroundColor Yellow
    Write-Host "  4. Close this window, open a new one, and run the installer again." -ForegroundColor Yellow
    Write-Host ""
}

function Invoke-Python {
    param(
        [hashtable]$Python,
        [string[]]$ScriptArgs
    )
    if ($Python.Launcher -eq 'exe') {
        & $Python.Exe @ScriptArgs
    }
    elseif ($Python.Launcher -eq "py") {
        & py @($Python.PyArgs + $ScriptArgs)
    }
    else {
        & python @ScriptArgs
    }
}

function Invoke-PipInternal {
    param(
        [hashtable]$Python,
        [string[]]$PipSubArgs
    )
    # pip writes package-missing warnings to stderr; with $ErrorActionPreference Stop
    # that becomes NativeCommandError. Continue + merged streams avoids false failures.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Python.Launcher -eq 'exe') {
            $output = @( & $Python.Exe -m pip @PipSubArgs 2>&1 | ForEach-Object { "$_" })
        }
        elseif ($Python.Launcher -eq "py") {
            $output = @( & py @($Python.PyArgs + @("-m", "pip") + $PipSubArgs) 2>&1 | ForEach-Object { "$_" })
        }
        else {
            $output = @( & python -m pip @PipSubArgs 2>&1 | ForEach-Object { "$_" })
        }
        return @{
            Output   = $output
            ExitCode = $LASTEXITCODE
        }
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
}

function Invoke-Pip {
    param(
        [hashtable]$Python,
        [string[]]$PipSubArgs
    )
    $result = Invoke-PipInternal -Python $Python -PipSubArgs $PipSubArgs
    if ($result.ExitCode -ne 0) {
        if ($null -ne $result.Output -and $result.Output.Count -gt 0) {
            Write-Host ""
            Write-Host "    pip output:" -ForegroundColor Yellow
            foreach ($line in $result.Output) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
            Write-Host ""
        }
        $cmd = 'pip ' + ($PipSubArgs -join ' ')
        throw "$cmd failed with exit code $($result.ExitCode)."
    }
    return $result.Output
}

function Get-InstalledPackageVersion {
    param(
        [hashtable]$Python,
        [string]$PackageName
    )
    $result = Invoke-PipInternal -Python $Python -PipSubArgs @("show", $PackageName)
    if ($result.ExitCode -ne 0) { return $null }
    foreach ($line in $result.Output) {
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
    $result = Invoke-PipInternal -Python $Python -PipSubArgs @("--version")
    return ($result.ExitCode -eq 0)
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

    $pipVersionResult = Invoke-PipInternal -Python $Python -PipSubArgs @("--version")
    $pipVersionLine = ($pipVersionResult.Output | Select-Object -First 1)
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

    foreach ($spec in $toInstall) {
        Write-Step "Installing: $spec"
        Invoke-Pip -Python $Python -PipSubArgs @("install", $spec)
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

Write-Step "Looking for Python (prefers py -3.12, then 3.11, 3.10, py -3, python)..."
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
                Import-UserPathFromRegistry
                Refresh-SessionPythonPath
                Start-Sleep -Seconds 2
                Write-Step "Looking for Python after winget install..."
                $python = Find-PythonExecutable
                if ($null -eq $python) {
                    Show-WingetPythonNotFoundSteps
                }
            }
            else {
                Write-Host ""
                Write-Host "winget could not install Python (missing rights, policy, network, or inconclusive output)." -ForegroundColor Red
            }
        }
        else {
            Write-Warn "Skipped automatic Python install via winget."
        }
    }

    if ($null -eq $python) {
        Write-Host ""
        $orgReply = Read-Host 'Download and install Python 3.12 from python.org now? (Y/n)'
        if (Test-WingetInstallYes -Reply $orgReply) {
            $orgInstalled = Install-PythonFromPythonOrg
            if ($orgInstalled) {
                Write-Ok "python.org installer finished"
                Import-UserPathFromRegistry
                Refresh-SessionPythonPath
                Start-Sleep -Seconds 3
                Write-Step "Looking for Python after python.org install..."
                $python = Find-PythonExecutable
            }
            else {
                Write-Host ""
                Write-Host "Could not download or run the python.org installer (network, policy, or permissions)." -ForegroundColor Red
            }
        }
        else {
            Write-Warn "Skipped automatic Python install from python.org."
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

Test-PythonVersionSupported -Python $python

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