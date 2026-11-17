# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Google Translate's free web endpoints, asked directly.

Google now answers the page deep_translator used (translate.google.com/m) with a "sorry" captcha
page, which looked like rate limiting. The JSON endpoints Google's own browser extension and
widgets use still answer, so EchoSub asks those: the first, then the second if the first fails.
"""
import requests

ENDPOINTS = (
    ("https://translate.googleapis.com/translate_a/single", {"client": "gtx", "dt": "t"}),
    ("https://clients5.google.com/translate_a/t", {"client": "dict-chrome-ex"}),
)
TIMEOUT = 10  # s
MAX_CHARS = 5000


class TooManyRequests(Exception):
    """Google refused for now (429, or its captcha page)."""


class RequestFailed(Exception):
    pass


def _refused(response):
    return response.status_code == 429 or "/sorry/" in response.url


def parse(url, data):
    """The translated text from either endpoint's JSON answer."""
    if "translate_a/single" in url:
        parts = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else []
        return "".join(part[0] for part in parts if isinstance(part, list) and part and isinstance(part[0], str))
    first = data[0] if isinstance(data, list) and data else ""
    if isinstance(first, list):  # [translation, detected language]
        first = first[0] if first else ""
    return first if isinstance(first, str) else ""


def translate(text, target, session=None):
    """`text` in `target` (a Google language code). Raises TooManyRequests or RequestFailed."""
    text = (text or "")[:MAX_CHARS]
    if not text.strip():
        return text
    session = session or requests
    refused, problem = False, None
    for url, params in ENDPOINTS:
        try:
            response = session.post(url, params={**params, "sl": "auto", "tl": target}, data={"q": text},
                                    timeout=TIMEOUT)
            if _refused(response):
                refused = True
                continue
            response.raise_for_status()
            result = parse(url, response.json())
        except (requests.RequestException, ValueError, TypeError, IndexError) as e:
            problem = e
            continue
        if result.strip():
            return result
    if refused:
        raise TooManyRequests()
    raise RequestFailed(f"Google Translate did not answer ({problem or 'empty answer'})")
