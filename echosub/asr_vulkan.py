# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Speech recognition on any graphics card — AMD, Intel or NVIDIA — through Vulkan.

The usual engine (faster-whisper on CTranslate2) can use a processor or an NVIDIA card and nothing
else. This one runs whisper.cpp built with its Vulkan backend, which every current AMD, Intel and
NVIDIA driver supports. It is a separate program, `whisper-server.exe`, shipped with EchoSub: it is
started on this PC with the chosen model, listens on 127.0.0.1 only, and is handed one stretch of
speech at a time. Nothing goes over the network; the address is local and the port is picked at
random each time.

`VulkanTranscriber.transcribe` answers exactly like `asr.Transcriber.transcribe`, so the rest of
the app does not need to know which engine is running.
"""
import atexit
import ctypes
import io
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import wave
import zlib

import numpy as np
import requests

from . import config, whisper_languages
from .transcript_quality import is_hallucination, is_implausibly_fast

log = logging.getLogger(__name__)

SERVER_EXE = "whisper-server.exe"
STARTUP_TIMEOUT = 180   # seconds; a large model on a slow disk takes a while to load
REQUEST_TIMEOUT = 120
SAMPLE_RATE = 16000
# Below this length the language is checked separately, with how sure it is; that costs a second pass,
# but on a short clip it is what tells a word from noise read as "Thank you." Longer clips skip it.
SURE_LANGUAGE_UNDER = 3.0
GPU_LINE = re.compile(r"ggml_vulkan:\s*\d+\s*=\s*(.+?)\s*\(")

# The compressed (quantized) whisper.cpp versions of each model: close to the full ones in
# accuracy, far smaller and faster — which matters most on built-in Intel graphics.
GGML_FILES = {
    "large-v3-turbo": "ggml-large-v3-turbo-q5_0.bin",
    "large-v3": "ggml-large-v3-q5_0.bin",
    "medium": "ggml-medium-q5_0.bin",
    "small": "ggml-small-q8_0.bin",
    "base": "ggml-base-q8_0.bin",
}


class VulkanUnavailable(Exception):
    """The Vulkan engine is not shipped with this copy, or could not start."""


def server_folder():
    """Where whisper-server.exe and its libraries are: next to the app, or under vendor/ from source."""
    candidates = []
    if os.environ.get("ECHOSUB_WHISPER_VULKAN"):
        candidates.append(os.environ["ECHOSUB_WHISPER_VULKAN"])
    if config.FROZEN:
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "whisper-vulkan"))
    candidates.append(os.path.join(os.path.dirname(config.PACKAGE_DIR), "vendor", "whisper-vulkan"))
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, SERVER_EXE)):
            return folder
    return None


def available():
    return server_folder() is not None


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wav_bytes(audio):
    """16 kHz mono float samples as a 16-bit WAV file in memory."""
    samples = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes((samples * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def compression_ratio(text):
    """How repetitive the text is, as Whisper measures it; a loop of the same words scores high."""
    data = text.encode("utf-8")
    return len(data) / len(zlib.compress(data)) if data else 0.0


def read_answer(answer, language, audio_seconds):
    """(text, language, probability, all probabilities) from the server's verbose JSON."""
    probs = {str(code): float(p) for code, p in (answer.get("language_probabilities") or {}).items()}
    ranked = sorted(probs.items(), key=lambda item: item[1], reverse=True)
    if language:
        lang, prob = language, 1.0
    elif ranked:
        lang, prob = ranked[0]
    else:  # a longer clip: the language the transcription itself settled on
        lang = whisper_languages.code(answer.get("language"))
        prob = 1.0 if lang else 0.0
    parts = []
    for seg in answer.get("segments") or []:
        text = str(seg.get("text", "")).strip()
        # The same gates as the usual engine: a stretch that is probably silence, or a loop
        if float(seg.get("no_speech_prob", 0)) > 0.5 and float(seg.get("avg_logprob", 0)) < -0.6:
            continue
        if compression_ratio(text) > 2.6:
            continue
        parts.append(text)
    if not answer.get("segments") and answer.get("text"):
        parts.append(str(answer["text"]).strip())
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if is_hallucination(text) or is_implausibly_fast(text, audio_seconds):
        text = ""
    if language is None and audio_seconds < 1.2 and prob < 0.5:
        text = ""
    return text, lang, prob, ranked


class _ChildProcesses:
    """A Windows job that closes whisper-server with EchoSub, even if EchoSub crashes."""

    def __init__(self):
        self.handle = None
        if sys.platform != "win32":
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            handle = kernel32.CreateJobObjectW(None, None)

            class Limits(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                            ("SchedulingClass", ctypes.c_uint32)]

            class Extended(ctypes.Structure):
                _fields_ = [("Basic", Limits), ("Io", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            info = Extended()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if kernel32.SetInformationJobObject(ctypes.c_void_p(handle), 9, ctypes.byref(info), ctypes.sizeof(info)):
                self.handle = handle
                self._kernel32 = kernel32
        except Exception as e:  # without it the server is still closed on a normal exit
            log.info("Could not tie whisper-server to EchoSub's lifetime: %s", e)

    def add(self, process):
        if self.handle:
            self._kernel32.AssignProcessToJobObject(ctypes.c_void_p(self.handle), ctypes.c_void_p(int(process._handle)))


_children = None


class VulkanTranscriber:
    device = "vulkan"
    compute_type = "ggml"

    def __init__(self, model_path, threads=4):
        self.folder = server_folder()
        if self.folder is None:
            raise VulkanUnavailable("this copy of EchoSub does not include the graphics-card engine")
        self.model_path, self.threads = model_path, threads
        self.gpu_name = None
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.trust_env = False  # never through a proxy: the server is on this PC
        self._log = None
        atexit.register(self.close)
        self._start()

    def _start(self):
        global _children
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        log_path = os.path.join(config.DATA_DIR, "logs", "whisper-server.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if self._log is not None and not self._log.closed:
            self._log.close()
        self._log = open(log_path, "w", encoding="utf-8", errors="replace")
        folder = self.folder
        command = [os.path.join(folder, SERVER_EXE), "-m", self.model_path, "--host", "127.0.0.1",
                   "--port", str(self.port), "-t", str(self.threads), "-nt"]
        log.info("Starting the graphics-card engine: %s", " ".join(command))
        self.process = subprocess.Popen(command, cwd=folder, stdout=self._log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if _children is None:
            _children = _ChildProcesses()
        _children.add(self.process)
        self._wait_until_ready(log_path)

    def _wait_until_ready(self, log_path):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise VulkanUnavailable(f"the graphics-card engine stopped while starting ({self._tail(log_path)})")
            try:
                if self._session.get(self.url + "/", timeout=2).status_code < 500:
                    self.gpu_name = self._find_gpu(log_path)
                    self.compute_type = self.gpu_name or "processor"  # shown as "VULKAN / <card>"
                    log.info("Graphics-card engine ready on %s (%s)", self.url, self.gpu_name or "no Vulkan device")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
        self.close()
        raise VulkanUnavailable("the graphics-card engine took too long to start")

    @staticmethod
    def _read(log_path):
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def _find_gpu(self, log_path):
        found = GPU_LINE.search(self._read(log_path))
        return found.group(1) if found else None

    def _tail(self, log_path):
        lines = [line for line in self._read(log_path).splitlines() if line.strip()]
        return lines[-1][:200] if lines else "no output"

    def transcribe(self, audio, language=None, final=True, prompt=None):
        """Returns (text, language, language_probability, all_language_probs), like asr.Transcriber."""
        seconds = len(audio) / SAMPLE_RATE
        fields = {
            "response_format": "verbose_json",
            "language": language or "auto",
            "no_language_probabilities": "false" if not language and seconds < SURE_LANGUAGE_UNDER else "true",
            "temperature": "0.0",
            "temperature_inc": "0.2" if final else "0.0",
            "no_speech_thold": "0.6",
            "no_timestamps": "true",
            "prompt": prompt or "",
        }
        with self._lock:
            try:
                reply = self._post(fields, audio)
            except requests.ConnectionError:
                # The engine stopped (a driver reset, or closed from outside): start it again once
                # and try the same speech, rather than losing every caption from here on.
                log.warning("The graphics-card engine stopped; starting it again")
                self.close()
                self._start()
                reply = self._post(fields, audio)
        reply.raise_for_status()
        return read_answer(reply.json(), language, seconds)

    def _post(self, fields, audio):
        if self.process.poll() is not None:
            raise requests.ConnectionError("the graphics-card engine is not running")
        return self._session.post(self.url + "/inference", data=fields, timeout=REQUEST_TIMEOUT,
                                  files={"file": ("speech.wav", wav_bytes(audio), "audio/wav")})

    def close(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
        log_file = getattr(self, "_log", None)
        if log_file is not None and not log_file.closed:
            log_file.close()


def load(downloader, model, on_status=None):
    """The graphics-card engine for `model`, or — if it cannot run here — the usual one on the processor.

    A failed download or a cancel is passed on; anything else falls back, so captions keep working.
    """
    from . import asr, downloads

    on_status = on_status or (lambda text: None)
    try:
        engine = VulkanTranscriber(downloader.whisper_ggml(model))
        if not engine.gpu_name:
            on_status("No graphics card answered through Vulkan — the engine is running on the processor")
        return engine
    except (downloads.DownloadCanceled, downloads.DownloadFailed):
        raise
    except Exception as e:
        log.exception("The graphics-card engine could not start")
        on_status(f"Could not use the graphics card ({e}) — switching to the processor")
        return asr.Transcriber(downloader.whisper(model), "cpu")
