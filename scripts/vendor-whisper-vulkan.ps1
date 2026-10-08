# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
<#
.SYNOPSIS
    Builds whisper.cpp with its Vulkan backend and puts whisper-server.exe and its libraries in vendor\whisper-vulkan.

.DESCRIPTION
    This is the speech engine behind "Graphics card, any brand" (AMD, Intel and NVIDIA). EchoSub.spec ships
    vendor\whisper-vulkan when it exists; without it the app is built as before and the option is not offered.

    Needs: Visual Studio 2022 Build Tools (C++), the Vulkan SDK (https://vulkan.lunarg.com/), git, and
    CMake + Ninja (pip install cmake ninja is enough).

.PARAMETER WorkDir
    Where whisper.cpp is cloned and built. Keep it off C: if space is short.

.PARAMETER Tag
    The whisper.cpp release to build.

.PARAMETER VulkanSdk
    The Vulkan SDK folder; defaults to $env:VULKAN_SDK.

.PARAMETER SkipBuild
    Only copy an existing build from WorkDir.
#>
param(
    [string]$WorkDir = "D:\DevTools\whisper.cpp",
    [string]$Tag = "v1.9.5",
    [string]$VulkanSdk = $env:VULKAN_SDK,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Bin = Join-Path $WorkDir "build-vulkan\bin"
$Target = Join-Path $Root "vendor\whisper-vulkan"

if (-not $SkipBuild) {
    if (-not $VulkanSdk -or -not (Test-Path (Join-Path $VulkanSdk "Bin\glslc.exe"))) {
        throw "Vulkan SDK not found. Install it from https://vulkan.lunarg.com/ or pass -VulkanSdk."
    }
    if (-not (Test-Path $WorkDir)) {
        git clone --depth 1 --branch $Tag https://github.com/ggml-org/whisper.cpp.git $WorkDir
    }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw "Visual Studio C++ Build Tools not found." }
    $vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
    $cmake = "cmake -S `"$WorkDir`" -B `"$WorkDir\build-vulkan`" -G Ninja -DCMAKE_BUILD_TYPE=Release " +
             "-DGGML_VULKAN=ON -DWHISPER_BUILD_SERVER=ON -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_BUILD_TESTS=OFF " +
             "-DGGML_NATIVE=OFF -DBUILD_SHARED_LIBS=ON && cmake --build `"$WorkDir\build-vulkan`" -j 8"
    cmd /c "call `"$vcvars`" && set VULKAN_SDK=$VulkanSdk && set PATH=$VulkanSdk\Bin;%PATH% && $cmake"
    if ($LASTEXITCODE -ne 0) { throw "whisper.cpp build failed ($LASTEXITCODE)" }
}

if (-not (Test-Path (Join-Path $Bin "whisper-server.exe"))) { throw "whisper-server.exe not found in $Bin" }
New-Item -ItemType Directory -Force $Target | Out-Null
Get-ChildItem $Target | Remove-Item -Force
Copy-Item (Join-Path $Bin "whisper-server.exe") $Target
Get-ChildItem $Bin -Filter *.dll | Copy-Item -Destination $Target
Copy-Item (Join-Path $WorkDir "LICENSE") (Join-Path $Target "LICENSE-whisper.cpp.txt")

# The Visual C++ runtime (and its OpenMP library) it was built against, so it runs on a PC without them.
# vulkan-1.dll is not copied: it comes with every graphics driver, and must match the installed one.
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -property installationPath
$redist = Get-ChildItem (Join-Path $vs "VC\Redist\MSVC") -Directory | Where-Object Name -match '^\d' |
    Sort-Object { [version]$_.Name } | Select-Object -Last 1
foreach ($dll in "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "vcomp140.dll") {
    $found = Get-ChildItem (Join-Path $redist.FullName "x64") -Recurse -Filter $dll | Select-Object -First 1
    if (-not $found) { throw "$dll not found in $($redist.FullName)" }
    Copy-Item $found.FullName $Target
}
Write-Host "vendor\whisper-vulkan:" -ForegroundColor Green
Get-ChildItem $Target | ForEach-Object { "  {0,-32} {1,8:N0} KB" -f $_.Name, ($_.Length / 1KB) }
