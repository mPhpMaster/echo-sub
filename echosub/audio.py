# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Capture whatever is playing on a Windows output device (WASAPI loopback)."""
import logging
import queue
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio
import soxr

from .audio_backlog import DiskAudioBacklog

SAMPLE_RATE = 16000
MAX_QUEUED_SEC = 60.0  # RAM queue; old audio is moved into the recovery buffer first
DEFAULT_BACKLOG_SEC = 600.0  # session-only disk recovery buffer
SPILL_INTERVAL_SEC = 0.2     # how often the writer thread moves waiting audio out of memory

log = logging.getLogger(__name__)


def list_loopback_devices():
    p = pyaudio.PyAudio()
    try:
        return [(d["index"], d["name"]) for d in p.get_loopback_device_info_generator()]
    finally:
        p.terminate()


def list_input_devices():
    """Microphones and other recording devices, as (index, name)."""
    p = pyaudio.PyAudio()
    try:
        devices = []
        for index in range(p.get_device_count()):
            info = p.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) > 0 and not info.get("isLoopbackDevice"):
                devices.append((index, str(info["name"])))
        return devices
    finally:
        p.terminate()


def find_input_device(pa, name):
    """The recording device with this exact name, or None when it is not plugged in."""
    for index in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(index)
        if str(info.get("name")) == name and int(info.get("maxInputChannels", 0)) > 0:
            return info
    return None


def find_loopback_device(pa, name):
    """The loopback device with this exact name, or None when it is not plugged in."""
    for device in pa.get_loopback_device_info_generator():
        if device["name"] == name:
            return device
    return None


def device_available(name):
    """Is that sound device here right now? Used to move back after it was unplugged."""
    try:
        pa = pyaudio.PyAudio()
    except Exception:
        return False
    try:
        return find_loopback_device(pa, name) is not None
    except Exception:
        return False
    finally:
        pa.terminate()


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

    def __init__(self, device="default", backlog_seconds=DEFAULT_BACKLOG_SEC, backlog_dir=None, kind="loopback"):
        self.device = device
        self.kind = kind  # "loopback" = what the PC plays, "input" = a microphone
        self.queue = queue.Queue()
        self.device_name = None
        self.using_fallback = False  # the chosen device was missing, so another one is in use
        self.last_audio_time = 0.0
        self.dropped_sec = 0.0   # audio discarded only after the recovery buffer fills
        self.spilled_sec = 0.0   # audio safely moved from RAM to the recovery buffer
        self._queued_sec = 0.0
        self._last_drop_log = 0.0
        self._pa = None
        self._stream = None
        self._resampler = None
        self._channels = 2
        self._queue_lock = threading.Lock()
        self._backlog = (DiskAudioBacklog(SAMPLE_RATE, backlog_seconds, directory=backlog_dir)
                         if backlog_seconds > 0 else None)
        self._spill_stop = threading.Event()
        self._spill_thread = None

    def start(self):
        """Open the device. On failure nothing is left behind, so the next try starts clean.

        A half-open PortAudio instance keeps its own stale list of devices, which is why a card
        that is unplugged and plugged back in used to keep failing with "Invalid device info".
        """
        pa = pyaudio.PyAudio()
        try:
            info = self._find_device(pa)
            self.using_fallback = info is None and self.device != "default"
            if info is None:
                info = self._default_device(pa)

            self.device_name = info["name"]
            self._channels = max(1, int(info["maxInputChannels"]))
            rate = int(info["defaultSampleRate"])
            self._resampler = soxr.ResampleStream(rate, SAMPLE_RATE, 1, dtype="float32")
            self._stream = pa.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=rate,
                input=True,
                input_device_index=info["index"],
                frames_per_buffer=int(rate * 0.05),
                stream_callback=self._callback,
            )
            self._stream.start_stream()
        except Exception:
            self._release(pa)
            raise
        self._pa = pa
        if self._backlog is not None:
            self._spill_stop.clear()
            self._spill_thread = threading.Thread(target=self._spill_worker, name="audio-spill", daemon=True)
            self._spill_thread.start()

    def _find_device(self, pa):
        if self.device == "default":
            return None
        if self.kind == "input":
            return find_input_device(pa, self.device)
        return find_loopback_device(pa, self.device)

    def _default_device(self, pa):
        if self.kind == "input":
            return pa.get_default_input_device_info()
        return pa.get_default_wasapi_loopback()

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
            self._queue_audio(out)
            self.last_audio_time = time.monotonic()
        return (None, pyaudio.paContinue)

    def take(self, max_seconds=None):
        """Audio captured since the last call, oldest first, at most `max_seconds` of it.

        Audio that waited on disk comes first and is handed over in slices, so the engine's own
        buffer (and the speech detection that scans it) stays small on a slow machine.
        """
        with self._queue_lock:
            chunks, seconds = [], 0.0
            if self._backlog is not None and not self._backlog.empty():
                chunks = self._backlog.take(max_seconds)
                seconds = sum(chunk.size for chunk in chunks) / SAMPLE_RATE
                if not self._backlog.empty():
                    return chunks  # older audio is still on disk: taking live audio now would reorder it
            while max_seconds is None or seconds < max_seconds:
                try:
                    chunk = self.queue.get_nowait()
                except queue.Empty:
                    break
                chunks.append(chunk)
                seconds += chunk.size / SAMPLE_RATE
                self._queued_sec = max(0.0, self._queued_sec - chunk.size / SAMPLE_RATE)
            return chunks

    @property
    def backlog(self):
        """The catch-up buffer, or None when it is switched off."""
        return self._backlog

    def pending_sec(self):
        """Audio waiting to be recognized, in memory and on disk."""
        with self._queue_lock:
            waiting = self._queued_sec
        return waiting + (self._backlog.seconds() if self._backlog is not None else 0.0)

    def _queue_audio(self, chunk):
        """Called from the sound card's callback: keep it cheap, never touch the disk here."""
        with self._queue_lock:
            self.queue.put(chunk)
            self._queued_sec += chunk.size / SAMPLE_RATE
            if self._backlog is None:
                self._drop_old_locked()

    def _drop_old_locked(self):
        """Without a recovery buffer there is nowhere to put old audio, so it goes."""
        while self._queued_sec > MAX_QUEUED_SEC:
            try:
                old = self.queue.get_nowait()
            except queue.Empty:
                self._queued_sec = 0.0
                return
            self._queued_sec = max(0.0, self._queued_sec - old.size / SAMPLE_RATE)
            self.dropped_sec += old.size / SAMPLE_RATE
        self._log_drops()

    def _spill_worker(self):
        """Moves audio that waited too long in memory onto disk, away from the audio callback."""
        while not self._spill_stop.wait(SPILL_INTERVAL_SEC):
            self.spill_once()

    def spill_once(self):
        """One pass of memory -> disk; returns the seconds moved (used by the tests)."""
        if self._backlog is None:
            return 0.0
        moved = 0.0
        while True:
            with self._queue_lock:
                if self._queued_sec <= MAX_QUEUED_SEC:
                    break
                try:
                    old = self.queue.get_nowait()
                except queue.Empty:
                    self._queued_sec = 0.0
                    break
                seconds = old.size / SAMPLE_RATE
                self._queued_sec = max(0.0, self._queued_sec - seconds)
            self.spilled_sec += seconds  # the disk write itself stays outside the queue lock
            self.dropped_sec += self._backlog.append(old)
            moved += seconds
        self._log_drops()
        return moved

    def _log_drops(self):
        now = time.monotonic()
        if self.dropped_sec >= 1 and now - self._last_drop_log > 10:
            self._last_drop_log = now
            log.warning("Dropped %.1f s of audio in total: the engine cannot keep up", self.dropped_sec)

    def stop(self):
        self._spill_stop.set()
        if self._spill_thread is not None:
            self._spill_thread.join(timeout=2)
            self._spill_thread = None
        try:
            self._release(self._pa)
        finally:
            self._pa = None
            if self._backlog is not None:
                self._backlog.close()
                self._backlog = None

    def _release(self, pa):
        """Close the stream and hand PortAudio back, whatever state opening left behind."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                log.debug("Stopping the audio stream failed", exc_info=True)
            try:
                stream.close()
            except Exception:
                log.debug("Closing the audio stream failed", exc_info=True)
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                log.debug("Releasing PortAudio failed", exc_info=True)
