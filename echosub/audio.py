# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Capture whatever is playing on a Windows output device (WASAPI loopback)."""
import logging
import queue
import time

import numpy as np
import pyaudiowpatch as pyaudio
import soxr

SAMPLE_RATE = 16000
MAX_QUEUED_SEC = 60.0  # audio kept waiting for the engine; older audio is dropped instead of piling up

log = logging.getLogger(__name__)


def list_loopback_devices():
    p = pyaudio.PyAudio()
    try:
        return [(d["index"], d["name"]) for d in p.get_loopback_device_info_generator()]
    finally:
        p.terminate()


_com_threads = set()


def default_output_name():
    """Friendly name of the current default playback device, straight from Core Audio.

    PortAudio only enumerates devices once per process while a stream is open,
    so it can't be used to notice the user switching speakers/headphones.
    """
    import threading

    import comtypes
    from pycaw.pycaw import AudioUtilities

    tid = threading.get_ident()
    if tid not in _com_threads:
        comtypes.CoInitialize()
        _com_threads.add(tid)
    try:
        dev = AudioUtilities.GetSpeakers()
        name = getattr(dev, "FriendlyName", None)
        if name is None:
            name = AudioUtilities.CreateDevice(dev).FriendlyName
        return name
    except Exception:
        return None


class LoopbackCapture:
    """Pushes mono float32 16 kHz chunks into `self.queue`."""

    def __init__(self, device="default"):
        self.device = device
        self.queue = queue.Queue()
        self.device_name = None
        self.last_audio_time = 0.0
        self.dropped_sec = 0.0   # audio thrown away because the engine was too far behind
        self._queued_sec = 0.0
        self._last_drop_log = 0.0
        self._pa = None
        self._stream = None
        self._resampler = None
        self._channels = 2

    def start(self):
        self._pa = pyaudio.PyAudio()
        info = None
        if self.device != "default":
            for d in self._pa.get_loopback_device_info_generator():
                if d["name"] == self.device:
                    info = d
                    break
        if info is None:
            info = self._pa.get_default_wasapi_loopback()

        self.device_name = info["name"]
        self._channels = max(1, int(info["maxInputChannels"]))
        rate = int(info["defaultSampleRate"])
        self._resampler = soxr.ResampleStream(rate, SAMPLE_RATE, 1, dtype="float32")
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=rate,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=int(rate * 0.05),
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def is_healthy(self):
        """False once the stream has died (e.g. the device was unplugged or disabled)."""
        try:
            return self._stream is not None and self._stream.is_active()
        except Exception:
            return False

    def _callback(self, data, frame_count, time_info, status):
        pcm = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if self._channels > 1:
            pcm = pcm.reshape(-1, self._channels).mean(axis=1)
        out = self._resampler.resample_chunk(pcm)
        if out.size:
            self._drop_old_audio()
            self.queue.put(out)
            self._queued_sec += out.size / SAMPLE_RATE
            self.last_audio_time = time.monotonic()
        return (None, pyaudio.paContinue)

    def take(self):
        """All audio captured since the last call, oldest first."""
        chunks = []
        while True:
            try:
                chunk = self.queue.get_nowait()
            except queue.Empty:
                break
            chunks.append(chunk)
            self._queued_sec = max(0.0, self._queued_sec - chunk.size / SAMPLE_RATE)
        return chunks

    def _drop_old_audio(self):
        """Never let more than MAX_QUEUED_SEC of audio wait: the oldest is dropped first."""
        while self._queued_sec > MAX_QUEUED_SEC:
            try:
                chunk = self.queue.get_nowait()
            except queue.Empty:
                self._queued_sec = 0.0
                return
            seconds = chunk.size / SAMPLE_RATE
            self._queued_sec -= seconds
            self.dropped_sec += seconds
        now = time.monotonic()
        if self.dropped_sec and now - self._last_drop_log > 10:
            self._last_drop_log = now
            log.warning("Dropped %.0f s of audio in total: the engine cannot keep up", self.dropped_sec)

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        finally:
            self._stream = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None
