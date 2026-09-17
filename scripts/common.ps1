# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
#
# Helpers shared by dev.ps1, build.ps1 and build-installer.ps1 (dot-sourced, not run directly).

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSEdition -eq "Desktop") {
    # Windows PowerShell started from PowerShell 7 inherits PS7's module path and then can't load its own
    # built-in modules (Get-FileHash, Select-Object, ...). Restore the default module path.
    $env:PSModulePath = @(
        (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "WindowsPowerShell\Modules"),
        (Join-Path $env:ProgramFiles "WindowsPowerShell\Modules"),
        [Environment]::GetEnvironmentVariable("PSModulePath", "Machine")
    ) -join ";"
    Import-Module Microsoft.PowerShell.Utility, Microsoft.PowerShell.Management -ErrorAction SilentlyContinue
}
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$PythonW = Join-Path $Venv "Scripts\pythonw.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-Sha256([string]$Path) {
    # .NET instead of Get-FileHash: that cmdlet is missing when Windows PowerShell is started from PowerShell 7
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "") }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed with exit code $LASTEXITCODE" }
}

function Get-AppVersion {
    $init = Get-Content (Join-Path $Root "echosub\__init__.py") -Raw
    if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { throw "Could not read __version__ from echosub\__init__.py" }
    return $Matches[1]
}

function Initialize-Venv {
    if (Test-Path $Python) { return }
    Write-Step "Creating virtual environment (.venv) with Python 3.10"
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        Invoke-Checked $launcher.Source @("-3.10", "-m", "venv", $Venv)
    } else {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { throw "Python 3.10 (64-bit) is required: https://www.python.org/downloads/release/python-31011/" }
        Invoke-Checked $py.Source @("-m", "venv", $Venv)
    }
    $version = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($version -ne "3.10") { throw ".venv uses Python $version; EchoSub needs Python 3.10. Delete .venv and install Python 3.10." }
    Invoke-Checked $Python @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
}

function Install-Requirements([string]$RequirementsFile) {
    # Re-installs only when the requirements file changed since the last successful install.
    $file = Join-Path $Root $RequirementsFile
    $hash = Get-Sha256 $file
    if ($RequirementsFile -eq "requirements-build.txt") {
        $hash += Get-Sha256 (Join-Path $Root "requirements.txt")
    }
    $stamp = Join-Path $Venv (".installed-" + [IO.Path]::GetFileNameWithoutExtension($RequirementsFile))
    if ((Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $hash)) { return }
    Write-Step "Installing dependencies from $RequirementsFile (the first time downloads ~3 GB)"
    Invoke-Checked $Python @("-m", "pip", "install", "-r", $file)
    Set-Content -Path $stamp -Value $hash
}

function Find-InnoSetup {
    $candidates = @(
        (Get-Command iscc -ErrorAction SilentlyContinue | ForEach-Object Source),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) {
        throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php (or: winget install JRSoftware.InnoSetup)."
    }
    return @($candidates)[0]
}

function Format-Size([long]$Bytes) {
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    return "{0:N0} MB" -f ($Bytes / 1MB)
}
