# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Make pip-installed CUDA runtime DLLs (cuBLAS / cuDNN) visible to CTranslate2.

Must run before ctranslate2 / faster_whisper are imported.
"""
import glob
import os
import site
import sys

from . import config


def setup():
    os.environ.setdefault("HF_HOME", config.MODELS_DIR)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    roots = set(site.getsitepackages())
    roots.add(os.path.join(sys.prefix, "Lib", "site-packages"))
    if getattr(sys, "frozen", False):
        roots.add(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))  # bundled nvidia/*/bin
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
