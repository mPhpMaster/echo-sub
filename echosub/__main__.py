# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""`python -m echosub` starts the app; `python -m echosub --lens` starts EchoSub Lens."""
import sys

if "--lens" in sys.argv:
    from echosub.lens_app import main
else:
    from echosub.main import main

sys.exit(main())
