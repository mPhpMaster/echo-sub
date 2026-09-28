# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Speech recognition with faster-whisper (auto language detection)."""
import logging
import os
import re

import ctranslate2
from faster_whisper import WhisperModel

from .transcript_quality import is_hallucination, is_implausibly_fast

DEBUG = bool(os.environ.get("ECHOSUB_DEBUG"))
log = logging.getLogger(__name__)


def pick_compute_type(device):
    if device == "cpu":
        return "int8"
    supported = ctranslate2.get_supported_compute_types("cuda")
    # Pascal GPUs (GTX 10xx) have no efficient float16 -> int8 is fastest there
    for ct in ("int8_float16", "int8", "float32"):
        if ct in supported:
            return ct
    return "float32"


class Transcriber:
    def __init__(self, model_name, device="cuda"):
        if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            device = "cpu"
        self.device = device
        self.compute_type = pick_compute_type(device)
        self.model = WhisperModel(
            model_name, device=device, compute_type=self.compute_type,
            cpu_threads=6 if device == "cpu" else 4,
        )

    def transcribe(self, audio, language=None, final=True, prompt=None):
        """Returns (text, language, language_probability, all_language_probs).

        `prompt` is the previous sentence, which helps Whisper keep names and punctuation consistent.
        """
        segments, info = self.model.transcribe(
            audio,
            language=language,
            task="transcribe",
            initial_prompt=prompt or None,
            beam_size=1,
            temperature=[0.0, 0.2, 0.4] if final else 0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        parts = []
        for seg in segments:
            if DEBUG:
                log.debug("seg dur=%.1fs lang=%s:%.2f nsp=%.2f lp=%.2f cr=%.2f %r", len(audio) / 16000,
                          info.language, info.language_probability, seg.no_speech_prob, seg.avg_logprob,
                          seg.compression_ratio, seg.text)
            # A slightly stricter joint gate than Whisper's built-in filter.  It does not reject
            # quiet real speech merely because one of the two signals is uncertain.
            if seg.no_speech_prob > 0.5 and seg.avg_logprob < -0.6:
                continue
            if seg.compression_ratio > 2.6:
                continue
            parts.append(seg.text.strip())
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if is_hallucination(text) or is_implausibly_fast(text, len(audio) / 16000):
            text = ""
        # Very short clips with an unsure language guess are usually noise read as "Thank you."
        if language is None and len(audio) < 16000 * 1.2 and info.language_probability < 0.5:
            text = ""
        return text, info.language, info.language_probability, info.all_language_probs
