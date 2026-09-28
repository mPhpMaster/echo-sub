# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Safe, lightweight checks for published EchoSub installer releases."""
from dataclasses import dataclass
import json
import re
from urllib.request import Request, urlopen

from . import APP_NAME, REPOSITORY_URL

LATEST_RELEASE_URL = "https://api.github.com/repos/mPhpMaster/echo-sub/releases/latest"
CHECK_TIMEOUT_SEC = 4


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    release_url: str


def check(current_version, opener=urlopen):
    """Return a newer official release, or None. Network failures are raised to the caller."""
    request = Request(LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": APP_NAME})
    with opener(request, timeout=CHECK_TIMEOUT_SEC) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return update_from_release(payload, current_version)


def update_from_release(release, current_version):
    """Build an update notification only for a newer release with a Windows installer."""
    version = str(release.get("tag_name") or "").strip().lstrip("vV")
    if not version or not is_newer(version, current_version):
        return None
    release_url = str(release.get("html_url") or REPOSITORY_URL)
    download_url = release_url
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "")
        if name.startswith("echosub-setup-") and name.endswith(".exe") and url:
            download_url = url
            break
    return UpdateInfo(version, download_url, release_url)


def is_newer(candidate, current):
    """Compare normal dotted app versions without pulling a packaging dependency into the installer."""
    return _version_key(candidate) > _version_key(current)


def _version_key(value):
    numbers = [int(part) for part in re.findall(r"\d+", str(value))]
    return tuple((numbers + [0, 0, 0])[:3])
