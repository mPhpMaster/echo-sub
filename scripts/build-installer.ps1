# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
<#
.SYNOPSIS
    Builds EchoSub and packages it into a Windows installer (dist\installer\EchoSub-Setup-<version>.exe).

.DESCRIPTION
    Runs scripts\build.ps1 (unless -SkipBuild), then compiles installer\EchoSub.iss with Inno Setup 6.
    Prints the installer's size and SHA-256 hash (publish the hash next to the download).

.PARAMETER Clean
    Passed to build.ps1: build from scratch.

.PARAMETER SkipBuild
    Reuse the existing dist\EchoSub instead of building again.

.PARAMETER SkipInstall
    Passed to build.ps1: don't check or install dependencies.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1 -SkipBuild
#>
param(
    [switch]$Clean,
    [switch]$SkipBuild,
    [switch]$SkipInstall
)

. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $Root
$started = Get-Date
$version = Get-AppVersion

if (-not $SkipBuild) {
    $buildArgs = @{}
    if ($Clean) { $buildArgs["Clean"] = $true }
    if ($SkipInstall) { $buildArgs["SkipInstall"] = $true }
    & (Join-Path $PSScriptRoot "build.ps1") @buildArgs
}
if (-not (Test-Path (Join-Path $Root "dist\EchoSub\EchoSub.exe"))) {
    throw "dist\EchoSub\EchoSub.exe not found. Run scripts\build.ps1 first (or drop -SkipBuild)."
}

$iscc = Find-InnoSetup
Write-Step "Compiling the installer with Inno Setup (compressing ~2 GB takes several minutes)"
Invoke-Checked $iscc @("/Q", "/DAppVersion=$version", (Join-Path $Root "installer\EchoSub.iss"))

$setup = Join-Path $Root "dist\installer\EchoSub-Setup-$version.exe"
if (-not (Test-Path $setup)) { throw "Inno Setup finished but $setup is missing." }
$hash = Get-Sha256 $setup
Set-Content -Path "$setup.sha256" -Value "$hash  EchoSub-Setup-$version.exe"
Write-Step "Installer ready"
Write-Host "  File:     $setup"
Write-Host "  Size:     $(Format-Size (Get-Item $setup).Length)"
Write-Host "  SHA-256:  $hash"
Write-Host "  Duration: $([int]((Get-Date) - $started).TotalMinutes) min $([int]((Get-Date) - $started).Seconds) s"
