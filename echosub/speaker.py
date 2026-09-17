# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Online speaker tracking with CAM++ voice embeddings (sherpa-onnx, CPU)."""
import os
import time
import urllib.request

import numpy as np

from . import config

MODEL_NAME = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/" + MODEL_NAME
)
SR = 16000
MAX_SPEAKERS = 8


def ensure_model():
    folder = os.path.join(config.MODELS_DIR, "speaker")
    path = os.path.join(folder, MODEL_NAME)
    if not os.path.exists(path):
        os.makedirs(folder, exist_ok=True)
        tmp = path + ".part"
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, path)
    return path


class SpeakerTracker:
    """Assigns a stable small integer id to each distinct voice heard."""

    def __init__(self, threshold=0.55, model_path=None):
        import sherpa_onnx

        self.threshold = threshold
        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=model_path or ensure_model(), num_threads=2)
        )
        self.speakers = {}  # id -> {"emb": unit vector, "weight": seconds, "last": time}
        self.last_id = None

    def embed(self, audio):
        stream = self.extractor.create_stream()
        stream.accept_waveform(SR, audio)
        stream.input_finished()
        e = np.asarray(self.extractor.compute(stream), dtype=np.float32)
        return e / (np.linalg.norm(e) + 1e-9)

    def identify(self, audio):
        duration = len(audio) / SR
        emb = self.embed(audio)
        best_id, best_sim = None, -1.0
        for sid, s in self.speakers.items():
            sim = float(emb @ s["emb"])
            if sim > best_sim:
                best_id, best_sim = sid, sim

        # Short clips give noisy embeddings: be lenient and never create a new voice from them
        short = duration < 1.5
        threshold = self.threshold - 0.15 if short else self.threshold
        if best_id is not None and best_sim >= threshold:
            sid = best_id
        elif short and (self.last_id is not None or best_id is not None):
            sid = self.last_id if self.last_id is not None else best_id
        else:
            sid = self._new_speaker(emb)

        s = self.speakers[sid]
        if not short or sid == best_id:
            w = min(s["weight"], 30.0)
            mixed = s["emb"] * w + emb * duration
            s["emb"] = mixed / (np.linalg.norm(mixed) + 1e-9)
            s["weight"] = w + duration
        s["last"] = time.monotonic()
        self.last_id = sid
        return sid

    def _new_speaker(self, emb):
        if len(self.speakers) >= MAX_SPEAKERS:
            # Recycle the voice not heard for the longest time (keeps its color slot)
            sid = min(self.speakers, key=lambda k: self.speakers[k]["last"])
        else:
            sid = len(self.speakers)
        self.speakers[sid] = {"emb": emb, "weight": 0.0, "last": time.monotonic()}
        return sid
