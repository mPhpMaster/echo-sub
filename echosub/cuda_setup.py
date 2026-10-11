# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Make pip-installed CUDA runtime DLLs (cuBLAS / cuDNN) visible to CTranslate2.

Must run before ctranslate2 / faster_whisper are imported.
"""
import os

from . import config


def setup():
    os.environ.setdefault("HF_HOME", config.MODELS_DIR)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    # Python's packages, an older build's own copy, or the copy downloaded on first use (cuda_libs)
    from . import cuda_libs

    cuda_libs.make_visible()
