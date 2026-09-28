# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""`EchoSub.exe --self-test [file.wav]` — checks the GPU, models and pipeline without opening any window.

Loads the speech, translation and speaker models from the current settings, transcribes and translates the
WAV file (if given), and writes the results to the log. Exit code 0 = everything worked.
"""
import logging
import time
import wave

log = logging.getLogger("echosub.selftest")


def _load_wav(path):
    import numpy as np
    import soxr

    with wave.open(path) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("self-test WAV must be 16-bit PCM")
    audio = np.frombuffer(frames, np.int16).astype(np.float32) / 32768
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return soxr.resample(audio, rate, 16000).astype(np.float32) if rate != 16000 else audio


def run(wav_path=None):
    from . import __version__, asr, config, downloads, engine, speaker, tashkeel, translate

    cfg = config.load()
    ok = True
    log.info("Self-test: EchoSub %s, data folder %s, models %s", __version__, config.DATA_DIR, config.MODELS_DIR)
    try:
        import ctranslate2
        cuda_devices = ctranslate2.get_cuda_device_count()
        log.info("Self-test: CUDA devices: %d, compute types: %s", cuda_devices,
                 sorted(ctranslate2.get_supported_compute_types("cuda")) if cuda_devices else "-")

        def on_download(event):
            if event["state"] != "progress" or event["done"] == event["total"]:
                log.info("Self-test: download %s %s: %s of %s", event["title"], event["state"],
                         downloads.human_size(event["done"]), downloads.human_size(event["total"]))

        downloader = downloads.ModelDownloader(on_event=on_download)
        t = time.monotonic()
        model = engine.effective_whisper_model(cfg)  # honours light mode
        transcriber = asr.Transcriber(downloader.whisper(model), cfg["device"])
        log.info("Self-test: speech model %s loaded on %s/%s in %.1f s", model, transcriber.device,
                 transcriber.compute_type, time.monotonic() - t)

        t = time.monotonic()
        translator = translate.create(cfg["translator"], transcriber.device, downloader)
        log.info("Self-test: translator %s loaded in %.1f s", cfg["translator"], time.monotonic() - t)

        tracker = None
        if cfg["speaker_detection"]:
            t = time.monotonic()
            tracker = speaker.SpeakerTracker(cfg["speaker_threshold"], downloader.speaker())
            log.info("Self-test: speaker model loaded in %.1f s", time.monotonic() - t)

        if wav_path:
            audio = _load_wav(wav_path)
            t = time.monotonic()
            text, lang, prob, _ = transcriber.transcribe(audio)
            log.info("Self-test: recognized [%s %.2f] in %.2f s: %s", lang, prob, time.monotonic() - t, text)
            if not text:
                raise RuntimeError("no speech recognized in the self-test WAV")
            t = time.monotonic()
            translated = translator.translate(text, lang, cfg["target_lang"])
            log.info("Self-test: translated to %s in %.2f s: %s", cfg["target_lang"], time.monotonic() - t, translated)
            if cfg.get("arabic_diacritics", "off") != "off" and cfg["target_lang"] in tashkeel.ARABIC_LANGUAGES:
                t = time.monotonic()
                diacritizer = tashkeel.Diacritizer(downloader.tashkeel())
                voweled = diacritizer.diacritize(translated)
                log.info("Self-test: Arabic diacritics in %.2f s: %s", time.monotonic() - t, voweled)
                if voweled == translated:
                    raise RuntimeError("diacritics were not added")
            if tracker is not None:
                log.info("Self-test: speaker id %s", tracker.identify(audio))
    except Exception:
        log.exception("Self-test FAILED")
        ok = False
    log.info("Self-test %s", "PASSED" if ok else "FAILED")
    return 0 if ok else 1
