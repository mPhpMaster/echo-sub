# Contributing to EchoSub

Thanks for your interest in improving EchoSub! Bug reports, feature ideas, translations of the docs and code contributions are all welcome.

## Reporting bugs

Open an issue at https://github.com/mPhpMaster/echo-sub/issues and include:

- What you did, what you expected, and what happened instead.
- Your EchoSub version (menu → *About EchoSub…*), Windows version, GPU model and driver version.
- The relevant part of the log file: menu → *Open log file* (`%LOCALAPPDATA%\EchoSub\logs\echosub.log`). Remove anything private before posting.

## Suggesting features

Open an issue describing the problem you want solved and how you imagine it working. Screenshots or mock-ups help a lot.

## Development setup

```powershell
git clone https://github.com/mPhpMaster/echo-sub.git
cd echo-sub
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

`dev.ps1` creates a virtual environment with Python 3.10, installs the dependencies and starts EchoSub with logs in the console. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the architecture and build scripts.

## Pull requests

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Create a branch from `main`, keep the change focused, and follow the existing code style (PEP 8, 120-character lines, descriptive names, comments that explain *why*).
3. Add the license header to new source files:
   ```python
   # SPDX-License-Identifier: GPL-3.0-only
   # Copyright (C) 2026 Mohammad Al-Safadi
   ```
4. Test your change by running the app (`scripts\dev.ps1`) and, if it touches packaging, a build (`scripts\build.ps1`).
5. Describe what changed and why in the pull request, with screenshots for UI changes.

## License of contributions and copyright

EchoSub is Copyright © 2026 Mohammad Al-Safadi and licensed under the GNU General Public License v3.0.

To keep the project's copyright in one place, **by submitting a contribution you agree that you assign the copyright of your contribution to Mohammad Al-Safadi**, and that it will be distributed under the GPL-3.0 as part of EchoSub. You confirm that the contribution is your own work (or that you have the right to submit it) and that it does not include code under a license incompatible with the GPL-3.0. Contributors are credited in the release notes and commit history.

If you cannot agree to this, please open an issue describing the change instead — the maintainer can implement it independently.

## Code of Conduct

Everyone taking part in the project is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
