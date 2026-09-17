# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Translation backends: local NLLB-200 (CTranslate2) or Google Translate."""
import os
import re

from . import config, languages

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？؟])\s+")


class NoTranslator:
    streaming = True

    def translate(self, text, src, tgt):
        return text


class NLLBTranslator:
    streaming = True

    def __init__(self, path, device="cuda"):
        import ctranslate2
        import sentencepiece as spm

        if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            device = "cpu"
        supported = ctranslate2.get_supported_compute_types(device)
        compute_type = "int8_float16" if "int8_float16" in supported else "int8"
        self.translator = ctranslate2.Translator(
            path, device=device, compute_type=compute_type, intra_threads=4
        )
        self.sp = spm.SentencePieceProcessor(model_file=os.path.join(path, "sentencepiece.bpe.model"))

    def translate(self, text, src, tgt):
        src_code, tgt_code = languages.nllb_code(src), languages.nllb_code(tgt)
        if not text or not tgt_code:
            return text
        if not src_code:
            src_code = "eng_Latn"
        sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        batch = [[src_code] + self.sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self.translator.translate_batch(
            batch,
            target_prefix=[[tgt_code]] * len(batch),
            beam_size=2,
            max_decoding_length=200,
            repetition_penalty=1.1,
            no_repeat_ngram_size=4,
        )
        out = []
        for r in results:
            tokens = r.hypotheses[0]
            if tokens and tokens[0] == tgt_code:
                tokens = tokens[1:]
            out.append(self.sp.decode(tokens).strip().lstrip("-–— ").strip())
        return " ".join(out).strip()


class GoogleTranslator:
    streaming = False  # avoid hammering the web API with partial results

    def __init__(self):
        from deep_translator import GoogleTranslator as _GT

        self._cls = _GT
        self._cache = {}

    def translate(self, text, src, tgt):
        if not text:
            return text
        key = languages.google_code(tgt)
        if key not in self._cache:
            self._cache[key] = self._cls(source="auto", target=key)
        return self._cache[key].translate(text) or text


def create(key, device, downloader=None):
    if key == "google":
        return GoogleTranslator()
    if key in config.NLLB_REPOS:
        from .downloads import ModelDownloader

        return NLLBTranslator((downloader or ModelDownloader()).nllb(key), device)
    return NoTranslator()
