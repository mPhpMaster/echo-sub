# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
#
# PyInstaller build of EchoSub (one-folder app). Run through scripts\build.ps1, which also creates
# build\version_info.txt and the icon.
import glob
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(SPECPATH)
SITE = os.path.join(ROOT, ".venv", "Lib", "site-packages")

# NVIDIA CUDA runtime DLLs, kept in nvidia\<package>\bin like in site-packages (echosub.cuda_setup finds them there).
# nvblas is not used by CTranslate2.
nvidia_binaries = []
for package in ("cublas", "cudnn", "cuda_nvrtc"):
    for dll in glob.glob(os.path.join(SITE, "nvidia", package, "bin", "*.dll")):
        if not os.path.basename(dll).lower().startswith("nvblas"):
            nvidia_binaries.append((dll, f"nvidia/{package}/bin"))

datas = [
    (os.path.join(ROOT, "echosub", "assets"), "echosub/assets"),
    (os.path.join(ROOT, "echosub", "flags"), "echosub/flags"),
]
datas += collect_data_files("faster_whisper")          # Silero VAD model
datas += collect_data_files("sherpa_onnx")
for doc in ("LICENSE", "README.md", "PRIVACY.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md"):
    datas.append((os.path.join(ROOT, doc), "."))

binaries = nvidia_binaries
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("sherpa_onnx")

hiddenimports = (
    collect_submodules("pycaw")
    + collect_submodules("sherpa_onnx")
    + ["pyaudiowpatch", "sentencepiece", "soxr", "deep_translator", "comtypes.stream"]
)

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow", "IPython", "pytest",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick3D",
              "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EchoSub",
    icon=os.path.join(ROOT, "echosub", "assets", "echosub.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EchoSub",
)
