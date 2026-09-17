# Third-Party Notices

EchoSub is Copyright © 2026 Mohammad Al-Safadi and licensed under the GNU General Public License v3.0 (see [LICENSE](LICENSE)).

EchoSub is built on the open-source software and AI models listed below. Each component remains under its own license; the copyright belongs to its respective authors. Full license texts are available at the linked project pages (and, for bundled Python packages, inside each package's `*.dist-info` folder).

## Software bundled with EchoSub

| Component | License | Project |
|---|---|---|
| Python 3.10 | PSF License | https://www.python.org |
| PySide6 / Qt for Python, shiboken6 (Qt 6) | LGPL-3.0 | https://www.qt.io/qt-for-python |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| Silero VAD (bundled in faster-whisper) | MIT | https://github.com/snakers4/silero-vad |
| ONNX Runtime | MIT | https://onnxruntime.ai |
| sherpa-onnx | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| PyAudioWPatch (includes PortAudio, MIT) | Apache-2.0 | https://github.com/s0d3s/PyAudioWPatch |
| python-soxr (includes libsoxr) | LGPL-2.1-or-later | https://github.com/dofuuz/python-soxr |
| SentencePiece | Apache-2.0 | https://github.com/google/sentencepiece |
| Hugging Face Hub client | Apache-2.0 | https://github.com/huggingface/huggingface_hub |
| tokenizers | Apache-2.0 | https://github.com/huggingface/tokenizers |
| deep-translator | MIT | https://github.com/nidhaloff/deep_translator |
| NumPy | BSD-3-Clause | https://numpy.org |
| PyAV (FFmpeg bindings; FFmpeg is LGPL) | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| pycaw | MIT | https://github.com/AndreMiras/pycaw |
| comtypes | MIT | https://github.com/enthought/comtypes |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| requests | Apache-2.0 | https://requests.readthedocs.io |
| CATT tokenizer code (`echosub/tashkeel/tokenizer.py`, `bw2ar.py`), adapted | Apache-2.0 — Copyright Abjad AI / Faris Alasmary | https://github.com/abjadai/catt |
| Arabic constants (`echosub/tashkeel/utils.py`) | BSD — Copyright 2003 Arabeyes, Mohammed Elzubeir; 2019 Faris Abdullah Alasmary | https://github.com/abjadai/catt |
| tqdm | MPL-2.0 AND MIT | https://github.com/tqdm/tqdm |
| NVIDIA cuBLAS, cuDNN, NVRTC runtime libraries | NVIDIA proprietary (redistributable runtime components under the NVIDIA CUDA / cuDNN license agreements) | https://developer.nvidia.com/cuda-zone |

The LGPL components (Qt / PySide6, libsoxr, FFmpeg) are used as separate, dynamically loaded libraries. You may replace them with your own builds; the complete corresponding source of EchoSub is available at https://github.com/mPhpMaster/echo-sub.

## AI models downloaded on first use

These models are **not** included in the installer; EchoSub downloads them from Hugging Face / GitHub when first needed and stores them in `%LOCALAPPDATA%\EchoSub\models`.

| Model | Used for | License |
|---|---|---|
| OpenAI Whisper (large-v3-turbo, large-v3, medium, small, base) — CTranslate2 conversions by Mobius Labs / Systran | Speech recognition | MIT |
| Meta NLLB-200 distilled 600M / 1.3B — CTranslate2 conversions by JustFrederik | Offline translation | **CC-BY-NC-4.0 (non-commercial use only)** |
| 3D-Speaker CAM++ speaker-verification model (via sherpa-onnx releases) | Telling speakers apart | Apache-2.0 |
| CATT encoder-only diacritization model (Abjad AI, via GitHub releases) — only when Arabic diacritics are turned on | Arabic diacritics (تشكيل) | Apache-2.0 |

If you use EchoSub commercially, switch the translation engine to Google Translate (Settings → Language & Engine) or replace NLLB with a model whose license allows commercial use.

## Online service (optional)

When the **Google Translate** engine is selected, caption text is sent to Google's translation service and is subject to Google's terms. This engine is off by default.

## Artwork

- Country flag images (`echosub/flags/`) — from [flagcdn.com](https://flagcdn.com), public domain.
- EchoSub icon — original artwork, Copyright © 2026 Mohammad Al-Safadi, GPL-3.0.
