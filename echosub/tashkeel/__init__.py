# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Arabic diacritization (تشكيل) with the CATT encoder-only ONNX model, on the CPU.

The model only understands Arabic letters, so each caption's Arabic words are diacritized together (for
context) and put back in their original places — punctuation, digits and non-Arabic text stay untouched.
"""
import logging
import re

import numpy as np

log = logging.getLogger(__name__)

ARABIC_LANGUAGES = {"ar", "ary"}
_ARABIC_WORD = re.compile("[ء-غـ-يً-ْٰ]+")
_STRIP = re.compile("[ـً-ْٰ]")  # tatweel, existing harakat, dagger alif
_MAX_CHARS = 400  # characters per model call; longer captions are split at word boundaries


class Diacritizer:
    def __init__(self, model_dir, threads=2):
        import os

        import onnxruntime as ort

        from .tokenizer import TashkeelTokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        providers = ["CPUExecutionProvider"]
        self.encoder = ort.InferenceSession(os.path.join(model_dir, "encoder.onnx"), options, providers=providers)
        self.decoder = ort.InferenceSession(os.path.join(model_dir, "decoder.onnx"), options, providers=providers)
        self.tokenizer = TashkeelTokenizer()
        self.pad = self.tokenizer.letters_map["<PAD>"]
        self.space = self.tokenizer.letters_map[" "]
        self.no_tashkeel = self.tokenizer.tashkeel_map[self.tokenizer.no_tashkeel_tag]

    def diacritize(self, text):
        """Returns `text` with harakat on its Arabic words (unchanged if something doesn't line up)."""
        matches = [m for m in _ARABIC_WORD.finditer(text) if _STRIP.sub("", m.group())]
        if not matches:
            return text
        words = [_STRIP.sub("", m.group()) for m in matches]
        voweled = []
        for chunk in self._chunks(words):
            out = self._run(" ".join(chunk)).split(" ")
            if len(out) != len(chunk):
                log.debug("tashkeel word count mismatch (%d vs %d); leaving caption as is", len(out), len(chunk))
                return text
            voweled.extend(out)
        pieces, last = [], 0
        for m, word in zip(matches, voweled):
            pieces.append(text[last:m.start()])
            pieces.append(word)
            last = m.end()
        pieces.append(text[last:])
        return "".join(pieces)

    @staticmethod
    def _chunks(words):
        chunk, size = [], 0
        for w in words:
            if chunk and size + len(w) + 1 > _MAX_CHARS:
                yield chunk
                chunk, size = [], 0
            chunk.append(w)
            size += len(w) + 1
        if chunk:
            yield chunk

    def _run(self, sentence):
        ids, _ = self.tokenizer.encode(sentence, test_match=False)
        src = ids[1:-1][None, :]  # encoder-only model: no BOS/EOS
        mask = (src != self.pad).reshape(1, 1, 1, -1)
        mask = np.repeat(mask, src.shape[1], axis=2) & np.repeat((src != self.pad).reshape(1, 1, -1, 1), src.shape[1], axis=3)
        enc = self.encoder.run(None, {"src": src, "src_mask": mask})[0]
        logits = self.decoder.run(None, {"enc_src": enc})[0]
        predictions = np.argmax(logits, axis=-1)
        predictions[src == self.space] = self.no_tashkeel
        return self.tokenizer.decode(src, predictions)[0]
