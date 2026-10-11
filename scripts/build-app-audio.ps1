# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
<#
.SYNOPSIS
    Builds helpers\app-audio (capturing one program's sound) into vendor\app-audio\app-audio.exe.

.DESCRIPTION
    Needs Visual Studio 2022 Build Tools with the C++ tools and a Windows 10 SDK (2004 or newer).
    EchoSub.spec ships vendor\app-audio when it exists; without it the "Only this program" option is
    not offered. The C runtime is linked in, so the helper needs nothing else on the user's PC.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "helpers\app-audio\app_audio.cpp"
$Target = Join-Path $Root "vendor\app-audio"
New-Item -ItemType Directory -Force $Target | Out-Null

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "Visual Studio C++ Build Tools not found." }
$vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
$build = Join-Path $env:TEMP "echosub-app-audio"
New-Item -ItemType Directory -Force $build | Out-Null
$compile = "cl /nologo /EHsc /O2 /MT /std:c++17 /W4 /Fo`"$build\\`" `"$Source`" /link mmdevapi.lib ole32.lib " +
           "/OUT:`"$Target\app-audio.exe`""
cmd /c "call `"$vcvars`" >nul && $compile"
if ($LASTEXITCODE -ne 0) { throw "app-audio build failed ($LASTEXITCODE)" }
Get-Item (Join-Path $Target "app-audio.exe") | ForEach-Object { "{0}  {1:N0} KB" -f $_.FullName, ($_.Length / 1KB) }
