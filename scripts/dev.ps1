# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
<#
.SYNOPSIS
    Runs EchoSub from source for development.

.DESCRIPTION
    Creates .venv (Python 3.10) and installs requirements.txt when needed, then starts EchoSub with its
    log shown in this console. Settings, models, logs and transcripts are kept in the project folder
    (unless -DataDir is given), separate from an installed copy, which uses %LOCALAPPDATA%\EchoSub.

.PARAMETER DebugLog
    Also log Whisper confidence details and recognized text for every segment (ECHOSUB_DEBUG=1).

.PARAMETER DataDir
    Use another folder for settings, models, logs and transcripts.

.PARAMETER NoConsole
    Start EchoSub in the background with pythonw (no console window).

.PARAMETER SkipInstall
    Don't check or install dependencies.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -DebugLog
#>
param(
    [switch]$DebugLog,
    [string]$DataDir,
    [switch]$NoConsole,
    [switch]$SkipInstall
)

. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root

if (-not $SkipInstall) {
    Initialize-Venv
    Install-Requirements "requirements.txt"
}
if (-not (Test-Path $Python)) { throw ".venv is missing; run without -SkipInstall first." }

$env:PYTHONIOENCODING = "utf-8"
if ($DebugLog) { $env:ECHOSUB_DEBUG = "1" } else { Remove-Item Env:ECHOSUB_DEBUG -ErrorAction SilentlyContinue }
if ($DataDir) { $env:ECHOSUB_DATA_DIR = (New-Item -ItemType Directory -Force -Path $DataDir).FullName }

Write-Step "Starting EchoSub $(Get-AppVersion) from source"
if ($NoConsole) {
    Start-Process -FilePath $PythonW -ArgumentList "-m", "echosub" -WorkingDirectory $Root
    Write-Host "EchoSub is starting in the background. Look for its icon next to the clock."
} else {
    Write-Host "Press Ctrl+C here, or use Exit in the tray menu, to stop." -ForegroundColor DarkGray
    & $Python -m echosub
    exit $LASTEXITCODE
}
