# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""NVIDIA's CUDA libraries, fetched the first time an NVIDIA card is used — not shipped to everyone.

They are 2 GB of the app, and only a PC with an NVIDIA card can use them, so the installer leaves
them out. On such a PC they are downloaded once (about 1.3 GB, in the same window as the models, with
the same cancel and resume), from NVIDIA's own packages on PyPI. The addresses and SHA-256 hashes are
written here; a file that does not match is deleted. Only the DLLs are kept.
"""
import glob
import hashlib
import logging
import os
import site
import sys
import zipfile

from . import config

log = logging.getLogger(__name__)

# NVIDIA's packages, the same versions the app was built and tested with (see requirements.txt)
PACKAGES = (
    ("cublas", "https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393"
               "e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
     "623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661"),
    ("cudnn", "https://files.pythonhosted.org/packages/c5/ee/baebebf270df5a57830e40879b4016de47ca43961095cf18b7749452"
              "150f/nvidia_cudnn_cu12-9.26.0.51-py3-none-win_amd64.whl",
     "010abb90f513fc6e2b6e9278d56f594b87922fff80737434ab415da609db8311"),
    ("cuda_nvrtc", "https://files.pythonhosted.org/packages/52/de/823919be3b9d0ccbf1f784035423c5f18f4267fb0123558d58"
                   "b813c6ec86/nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-win_amd64.whl",
     "72972ebdcf504d69462d3bcd67e7b81edd25d0fb85a2c46d3ea3517666636349"),
)
KEY_DLL = "cublas64_12.dll"
TITLE = "NVIDIA graphics-card libraries (once)"


def folder():
    return os.path.join(config.MODELS_DIR, "cuda")


def search_roots():
    """Where the libraries may already be: the downloaded folder, the app itself, or Python's packages."""
    roots = [folder()]
    if getattr(sys, "frozen", False):
        roots.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))  # older, bundled builds
    roots += site.getsitepackages() + [os.path.join(sys.prefix, "Lib", "site-packages")]
    return roots


def library_dirs():
    return [d for root in search_roots() for d in glob.glob(os.path.join(root, "nvidia", "*", "bin"))]


def available():
    return any(os.path.exists(os.path.join(d, KEY_DLL)) for d in library_dirs())


def make_visible():
    """Let CTranslate2 find the libraries; safe to call again after a download."""
    for d in library_dirs():
        try:
            os.add_dll_directory(d)
        except OSError:
            continue
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(wheel, name, into):
    """Keep only nvidia/<name>/bin/*.dll from a wheel."""
    prefix = f"nvidia/{name}/bin/"
    target = os.path.join(into, "nvidia", name, "bin")
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(wheel) as z:
        for member in z.namelist():
            base = os.path.basename(member)
            if member.startswith(prefix) and base.lower().endswith(".dll") and "/" not in member[len(prefix):]:
                with z.open(member) as src, open(os.path.join(target, base), "wb") as out:
                    while True:
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        out.write(block)


def download(downloader, packages=PACKAGES):
    """Fetch, check and unpack whatever is missing. DownloadCanceled is passed on to the caller."""
    from .downloads import DownloadFailed

    root = folder()
    os.makedirs(root, exist_ok=True)
    missing = [(name, url, sha) for name, url, sha in packages
               if not os.path.exists(os.path.join(root, f".{name}.complete"))]
    if not missing:
        return
    files = []
    for name, url, _sha in missing:
        size = downloader._remote_size(url)
        files.append((url, os.path.join(root, url.rsplit("/", 1)[1]), size, f"{name} (NVIDIA)"))
    downloader._run(TITLE, files, sum(size for _, _, size, _ in files))
    for (name, _url, sha), (_url2, wheel, _size, _label) in zip(missing, files):
        if sha256_of(wheel) != sha:
            os.remove(wheel)
            raise DownloadFailed(f"the NVIDIA {name} package did not match its published checksum")
        unpack(wheel, name, root)
        os.remove(wheel)
        open(os.path.join(root, f".{name}.complete"), "w").close()
    make_visible()
    log.info("NVIDIA libraries are ready in %s", root)


def needed(cfg):
    """True when this PC should fetch them now: an NVIDIA card, the card chosen, and allowed to."""
    if cfg.get("device") != "cuda" or not cfg.get("cuda_download", True) or available():
        return False
    from . import gpu

    return gpu.vendor() == "nvidia"
