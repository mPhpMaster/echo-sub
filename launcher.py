# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Entry point for the PyInstaller build (EchoSub.exe)."""
import sys

if "--lens" in sys.argv:  # EchoSub Lens: the screen translator, in a process of its own
    from echosub.lens_app import main
else:
    from echosub.main import main

if __name__ == "__main__":
    sys.exit(main())
