# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""One stream of audio on its way to captions: what the PC plays, or the microphone.

Each stream keeps its own buffer, its own speech detection and its own live text, but they share
the one speech model, so two streams cost no more than one person talking twice as much. Every
caption carries the name of the stream it came from, which is what colours the microphone's
captions and lets a spoken command be accepted from it.
"""
import logging
import time

import numpy as np

from . import audio

SR = audio.SAMPLE_RATE
SYSTEM, MICROPHONE = "system", "mic"

log = logging.getLogger(__name__)


class AudioStream:
    """The buffer and speech detection of one source, stepped by the engine's loop."""

    def __init__(self, engine, capture, name):
        self.engine = engine
        self.capture = capture
        self.name = name
        self.buf = np.zeros(0, dtype=np.float32)
        self.speech = []
        self.vad_dirty = True
        self.last_vad = 0.0
        self.last_partial_len = 0
        self.last_activity = 0.0
        self.keeping_up = True
        self.dropped_before = getattr(capture, "dropped_sec", 0.0)

    # ---- housekeeping ------------------------------------------------------
    @property
    def max_buffer(self):
        """Only this much audio is held in memory; the rest waits in the catch-up buffer."""
        return max(20.0, 2 * self.engine.cfg["max_segment_sec"])

    def clear(self):
        self.buf = self.buf[:0]
        self.speech, self.vad_dirty, self.last_vad, self.last_partial_len = [], True, 0.0, 0

    def pull(self):
        """Take as much waiting audio as this stream has room for."""
        room = self.max_buffer - len(self.buf) / SR
        chunks = self.capture.take(room) if room > 0 else []
        pulled = sum(chunk.size for chunk in chunks) / SR
        self.keeping_up = pulled <= 0.25  # more than ~0.2 s arrived while the last round ran
        if chunks:
            self.buf = np.concatenate([self.buf] + chunks)
            self.vad_dirty = True
        return pulled

    def dropped(self):
        """Seconds of audio thrown away since the last time this was asked."""
        now_dropped = getattr(self.capture, "dropped_sec", 0.0)
        lost, self.dropped_before = now_dropped - self.dropped_before, now_dropped
        return lost

    # ---- the work ----------------------------------------------------------
    def step(self, now):
        """Look at this stream once. Returns True when it had something to do."""
        engine, cfg = self.engine, self.engine.cfg
        if len(self.buf) < SR * 0.4:
            return False

        if len(self.buf) > SR * self.max_buffer:
            self._skip_ahead(now)

        if self.vad_dirty and now - self.last_vad >= engine._vad_interval(len(self.buf)):
            self.speech, self.vad_dirty, self.last_vad = engine._vad(self.buf), False, now
        idle = max(0.0, now - self.capture.last_audio_time - 0.15)  # nothing is sent while silent

        if not self.speech:
            if len(self.buf) > SR * 2:
                self.buf, self.vad_dirty = self.buf[-int(SR * 0.5):], True
            elif idle > 1.0:
                self.buf, self.vad_dirty = self.buf[:0], True
            self.last_partial_len = 0
            return False

        if now - self.last_activity > 0.3:
            self.last_activity = now
            engine.on_activity()

        start, last_end, tail_silence, duration = self._measure(idle)
        if tail_silence >= cfg["silence_sec"] and self.vad_dirty:
            # About to end a caption on speech regions that may be out of date: check first, so
            # audio that arrived in the meantime is not cut off mid-sentence.
            self.speech, self.vad_dirty, self.last_vad = engine._vad(self.buf), False, time.monotonic()
            if not self.speech:
                return True
            start, last_end, tail_silence, duration = self._measure(idle)

        if tail_silence >= cfg["silence_sec"]:
            cut = min(len(self.buf), last_end + int(SR * 0.2))
            self._finalize(start, cut)
        elif duration >= cfg["max_segment_sec"]:
            self._finalize(start, engine._best_cut(self.speech, len(self.buf), start))
        elif (engine._live_text_enabled() and engine._asr_time < 1.5 and self.keeping_up
              and len(self.buf) - self.last_partial_len >= SR * max(0.7, engine._asr_time)):
            # Live text only when the GPU keeps up and no audio is waiting; otherwise it just
            # delays the finished captions.
            self.last_partial_len = len(self.buf)
            engine._partial(self.buf[start:], self.name)
        else:
            return False
        return True

    def _measure(self, idle):
        start = max(0, self.speech[0]["start"] - int(SR * 0.2))
        last_end = self.speech[-1]["end"]
        return (start, last_end, (len(self.buf) - last_end) / SR + idle, (len(self.buf) - start) / SR)

    def _finalize(self, start, cut):
        self.engine._finalize(self.buf[start:cut], self.speech, start, self.name)
        self.buf, self.vad_dirty, self.last_partial_len = self.buf[cut:], True, 0

    def _skip_ahead(self, now):
        """The catch-up buffer is full: keep the newest audio and say what was lost."""
        engine = self.engine
        keep = int(SR * engine.cfg["max_segment_sec"])
        skipped = (len(self.buf) - keep) / SR
        self.buf, self.vad_dirty, self.last_partial_len = self.buf[-keep:], True, 0
        self.speech, self.last_vad = [], 0.0  # the old speech regions no longer match the buffer
        log.warning("Recognition is behind on %s: skipped %.1f s of audio", self.name, skipped)
        if now - engine._behind_warned > 20:
            engine._behind_warned = now
            engine.on_status(f"Captions are behind — recovery buffer full; skipped {skipped:.0f} s of audio "
                             f"(try Light mode or a smaller speech model)")
