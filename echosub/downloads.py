# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Model downloads with byte-level progress, cancel and resume.

Models already on disk are used as-is (including an existing Hugging Face cache), so nothing is downloaded
twice and EchoSub works offline once everything is there. New downloads go to plain folders under
models/downloads/, written as `.part` files that are resumed after a cancel or a network error.
"""
import fnmatch
import json
import logging
import os
import time
import zipfile

import requests

from . import config

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024
PROGRESS_INTERVAL = 0.2  # seconds between progress events

WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
NLLB_SKIP = [".gitattributes", "README.md"]
SPEAKER_MODEL = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
TASHKEEL_URL = "https://github.com/abjadai/catt/releases/download/v2/eo_model_onnx.zip"
SPEAKER_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
               + SPEAKER_MODEL)


class DownloadCanceled(Exception):
    pass


class DownloadFailed(Exception):
    pass


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


class ModelDownloader:
    """on_event(dict) receives: state (start|progress|finished|canceled|failed), title, file,
    done, total (bytes), speed (bytes/s), eta (s), error."""

    def __init__(self, on_event=None, should_cancel=None, models_dir=None):
        self.on_event = on_event or (lambda event: None)
        self.should_cancel = should_cancel or (lambda: False)
        self.models_dir = models_dir or config.MODELS_DIR
        self.session = None

    # ---- public ------------------------------------------------------------
    def whisper(self, name):
        """Local folder of a faster-whisper model ('large-v3-turbo', ...), downloading it if needed."""
        if os.path.isdir(name):
            return name
        from faster_whisper.utils import _MODELS

        repo = _MODELS.get(name)
        if repo is None:
            raise DownloadFailed(f"unknown speech model '{name}'")
        return self._repo(repo, f"Speech recognition model ({name})", include=WHISPER_FILES)

    def nllb(self, key):
        return self._repo(config.NLLB_REPOS[key], f"Translation model ({key.upper()})", exclude=NLLB_SKIP)

    def speaker(self):
        folder = os.path.join(self.models_dir, "speaker")
        path = os.path.join(folder, SPEAKER_MODEL)
        if os.path.exists(path):
            return path
        os.makedirs(folder, exist_ok=True)
        title = "Speaker detection model"
        total = self._remote_size(SPEAKER_URL)
        self._run(title, [(SPEAKER_URL, path, total, os.path.basename(path))], total)
        return path

    def tashkeel(self):
        """Folder with the CATT encoder-only ONNX model for Arabic diacritics."""
        folder = os.path.join(self.models_dir, "tashkeel", "catt-eo")
        marker = os.path.join(folder, ".complete")
        if os.path.exists(marker):
            return folder
        os.makedirs(folder, exist_ok=True)
        archive = os.path.join(folder, "eo_model_onnx.zip")
        total = self._remote_size(TASHKEEL_URL)
        self._run("Arabic diacritics model", [(TASHKEEL_URL, archive, total, "eo_model_onnx.zip")], total)
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder)
        os.remove(archive)
        if not os.path.exists(os.path.join(folder, "encoder.onnx")):
            raise DownloadFailed("the diacritics model archive did not contain encoder.onnx")
        open(marker, "w").close()
        return folder

    # ---- repositories ---------------------------------------------------------
    def _repo(self, repo, title, include=None, exclude=None):
        cached = self._hf_cache(repo, include)
        if cached:
            return cached
        folder = os.path.join(self.models_dir, "downloads", repo.replace("/", "--"))
        marker = os.path.join(folder, ".complete")
        if os.path.exists(marker):
            return folder

        from huggingface_hub import HfApi, hf_hub_url

        try:
            info = HfApi().model_info(repo, files_metadata=True)
        except Exception as e:
            raise DownloadFailed(f"could not reach Hugging Face to download {title.lower()}: {e}") from e
        files = []
        for sibling in info.siblings:
            name = sibling.rfilename
            if include and not any(fnmatch.fnmatch(name, pattern) for pattern in include):
                continue
            if exclude and name in exclude:
                continue
            files.append((hf_hub_url(repo, name, revision=info.sha), os.path.join(folder, name), sibling.size or 0, name))
        if not files:
            raise DownloadFailed(f"no model files found in {repo}")
        os.makedirs(folder, exist_ok=True)
        self._run(title, files, sum(size for _, _, size, _ in files))
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"repo": repo, "revision": info.sha, "files": [name for *_, name in files]}, f)
        return folder

    def _hf_cache(self, repo, include):
        """A complete copy in the Hugging Face cache (from earlier versions or other apps), if there is one."""
        try:
            from huggingface_hub import snapshot_download

            path = snapshot_download(repo, allow_patterns=include, local_files_only=True,
                                     cache_dir=os.path.join(self.models_dir, "hub"))
        except Exception:
            return None
        needed = "model.bin"
        return path if os.path.exists(os.path.join(path, needed)) else None

    # ---- transfer --------------------------------------------------------------
    def _remote_size(self, url):
        try:
            r = self._http().head(url, allow_redirects=True, timeout=20)
            return int(r.headers.get("Content-Length", 0))
        except Exception:
            return 0

    def _http(self):
        if self.session is None:
            self.session = requests.Session()
            try:
                from huggingface_hub.utils import build_hf_headers
                self.session.headers.update(build_hf_headers())
            except Exception:
                self.session.headers["User-Agent"] = "EchoSub"
        return self.session

    def _run(self, title, files, total):
        state = {"title": title, "total": total, "done": 0, "started": time.monotonic(), "last_emit": 0.0,
                 "resumed": 0}
        for _, dest, size, _ in files:
            part = dest + ".part"
            if os.path.exists(dest) and (not size or os.path.getsize(dest) == size):
                state["done"] += os.path.getsize(dest)
            elif os.path.exists(part):
                state["done"] += os.path.getsize(part)
        state["resumed"] = state["done"]
        log.info("Downloading %s (%s, %s already on disk)", title, human_size(total), human_size(state["done"]))
        self._emit("start", state, "")
        try:
            for url, dest, size, name in files:
                self._file(url, dest, size, name, state)
        except DownloadCanceled:
            log.info("Download of %s canceled at %s of %s", title, human_size(state["done"]), human_size(total))
            self._emit("canceled", state, "")
            raise
        except Exception as e:
            log.exception("Download of %s failed", title)
            self._emit("failed", state, "", error=str(e))
            raise DownloadFailed(f"downloading {title.lower()} failed: {e}") from e
        self._emit("finished", state, "", force=True)
        log.info("Downloaded %s", title)

    def _file(self, url, dest, size, name, state):
        if os.path.exists(dest) and (not size or os.path.getsize(dest) == size):
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        part = dest + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if size and have > size:
            os.remove(part)
            state["done"] -= have
            have = 0
        if not size or have < size:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with self._http().get(url, headers=headers, stream=True, timeout=(15, 60), allow_redirects=True) as r:
                if have and r.status_code == 200:  # server ignored the range: start this file over
                    state["done"] -= have
                    have = 0
                    mode = "wb"
                elif r.status_code in (200, 206):
                    mode = "ab" if have else "wb"
                else:
                    raise DownloadFailed(f"HTTP {r.status_code} for {name}")
                with open(part, mode) as f:
                    for chunk in r.iter_content(CHUNK):
                        if self.should_cancel():
                            raise DownloadCanceled()
                        if not chunk:
                            continue
                        f.write(chunk)
                        state["done"] += len(chunk)
                        self._emit("progress", state, name)
        if size and os.path.getsize(part) != size:
            raise DownloadFailed(f"{name} is incomplete ({human_size(os.path.getsize(part))} of {human_size(size)})")
        os.replace(part, dest)

    def _emit(self, kind, state, name, force=False, error=""):
        now = time.monotonic()
        if kind == "progress" and not force and now - state["last_emit"] < PROGRESS_INTERVAL:
            return
        state["last_emit"] = now
        elapsed = max(0.001, now - state["started"])
        speed = (state["done"] - state["resumed"]) / elapsed
        remaining = max(0, state["total"] - state["done"])
        self.on_event({
            "state": kind, "title": state["title"], "file": name, "done": state["done"], "total": state["total"],
            "speed": speed, "eta": remaining / speed if speed > 1 else None, "error": error,
        })
