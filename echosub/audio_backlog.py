# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Session-only disk queue for audio that arrives while recognition is behind."""
from collections import deque
import logging
import os
import shutil
import tempfile
import threading
import time

import numpy as np

PREFIX = "echosub-audio-backlog-"
STALE_AFTER_SEC = 6 * 60 * 60  # a folder this old belongs to a session that was killed

log = logging.getLogger(__name__)


def usable_root(directory):
    """The folder the buffer will live in, or None when the chosen one cannot be used.

    The user can point this at a fast drive; if that drive is missing or read-only (an external
    disk that is not plugged in, for example), the caller falls back to the Windows temp folder
    rather than losing the buffer.
    """
    if not directory or not str(directory).strip():
        return tempfile.gettempdir()
    root = os.path.abspath(os.path.expandvars(os.path.expanduser(str(directory).strip())))
    try:
        os.makedirs(root, exist_ok=True)
        probe = tempfile.NamedTemporaryFile(dir=root, prefix=PREFIX, suffix=".probe", delete=True)
        probe.close()
    except OSError as e:
        log.warning("Cannot use %s for the catch-up buffer: %s", root, e)
        return None
    return root


def remove_stale_directories(root=None, now=None):
    """Delete buffers left behind by a session that never closed (a crash or a forced shutdown).

    Returns the folders removed. Folders of a session that may still be running are left alone.
    """
    root = root or tempfile.gettempdir()
    now = time.time() if now is None else now
    removed = []
    try:
        names = os.listdir(root)
    except OSError:
        return removed
    for name in names:
        path = os.path.join(root, name)
        if not name.startswith(PREFIX) or not os.path.isdir(path):
            continue
        try:
            if now - os.path.getmtime(path) < STALE_AFTER_SEC:
                continue
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            removed.append(path)
    return removed


class DiskAudioBacklog:
    """Preserve queued audio on disk and return it in capture order.

    This is a recovery buffer, not a recording feature.  All files are removed
    when the capture closes.
    """

    def __init__(self, sample_rate, max_seconds, segment_seconds=1.0, directory=None):
        self.sample_rate = sample_rate
        self.max_samples = max(0, int(max_seconds * sample_rate))
        self.segment_samples = max(sample_rate // 4, int(segment_seconds * sample_rate))
        root = usable_root(directory)
        self.using_fallback = root is None  # the chosen drive was not usable
        if root is None:
            root = tempfile.gettempdir()
        remove_stale_directories(root)
        if root != tempfile.gettempdir():
            remove_stale_directories()  # older sessions may have written to the temp folder
        self._directory = tempfile.mkdtemp(prefix=PREFIX, dir=root)
        log.info("Catch-up audio buffer: %s", self._directory)
        self._segments = deque()
        self._write_buffer = np.zeros(0, dtype=np.float32)
        self._stored_samples = 0
        self._next_id = 0
        self._lock = threading.Lock()

    def append(self, chunk):
        """Append `chunk`; return seconds dropped when the disk limit is full."""
        chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.size == 0:
            return 0.0
        if self.max_samples <= 0:
            return chunk.size / self.sample_rate
        with self._lock:
            self._write_buffer = np.concatenate((self._write_buffer, chunk))
            self._flush_locked()
            return self._trim_locked() / self.sample_rate

    def seconds(self):
        """How much audio is waiting on disk."""
        with self._lock:
            return (self._stored_samples + self._write_buffer.size) / self.sample_rate

    def empty(self):
        return self.seconds() <= 0

    def take(self, max_seconds=None):
        """Read saved audio oldest first (at most `max_seconds`), deleting the files as it goes.

        Handing everything over at once would make the engine hold minutes of audio in memory and
        scan all of it for speech, so the caller asks for as much as it can work on now.
        """
        limit = None if max_seconds is None else max(0, int(max_seconds * self.sample_rate))
        with self._lock:
            self._flush_locked(force=True)
            chunks, taken = [], 0
            while self._segments:
                if limit is not None and taken >= limit:
                    break
                path, samples = self._segments.popleft()
                taken += samples
                try:
                    chunk = np.fromfile(path, dtype=np.float32, count=samples)
                finally:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                self._stored_samples -= samples
                if chunk.size:
                    chunks.append(chunk)
            self._stored_samples = max(0, self._stored_samples)
            return chunks

    @property
    def directory(self):
        """Where this session's audio is being kept."""
        return self._directory

    def close(self):
        with self._lock:
            self._segments.clear()
            self._write_buffer = np.zeros(0, dtype=np.float32)
            self._stored_samples = 0
        shutil.rmtree(self._directory, ignore_errors=True)

    def _flush_locked(self, force=False):
        while self._write_buffer.size >= self.segment_samples or (force and self._write_buffer.size):
            count = min(self.segment_samples, self._write_buffer.size)
            chunk, self._write_buffer = self._write_buffer[:count], self._write_buffer[count:]
            path = os.path.join(self._directory, f"{self._next_id:08d}.f32")
            self._next_id += 1
            np.ascontiguousarray(chunk, dtype=np.float32).tofile(path)
            self._segments.append((path, count))
            self._stored_samples += count

    def _trim_locked(self):
        dropped = 0
        while self._stored_samples > self.max_samples and self._segments:
            path, samples = self._segments.popleft()
            self._stored_samples -= samples
            dropped += samples
            try:
                os.remove(path)
            except OSError:
                pass
        return dropped
