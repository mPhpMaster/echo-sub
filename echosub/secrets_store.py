# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Keeping an API key in the settings file without keeping it readable.

Windows' own data protection (DPAPI) encrypts the key with the signed-in user's credentials, so the
stored text is useless if the settings file is copied to another account or machine, and nothing
extra has to be installed. The key is only ever decrypted in memory, just before it is used.
"""
import base64
import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

PREFIX = "dpapi:"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _take(blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect(text):
    """The key, encrypted for this Windows user. An empty key stays empty."""
    if not text:
        return ""
    source, _keep_alive = _blob(str(text).encode("utf-8"))
    result = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), ctypes.c_wchar_p("EchoSub"), None,
                                                  None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)):
        raise OSError("Windows could not protect the key")
    return PREFIX + base64.b64encode(_take(result)).decode("ascii")


def unprotect(stored):
    """The key in plain text, or "" when there is none or it cannot be read on this account."""
    if not stored or not str(stored).startswith(PREFIX):
        return ""
    try:
        source, _keep_alive = _blob(base64.b64decode(str(stored)[len(PREFIX):]))
    except ValueError:
        return ""
    result = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)):
        log.info("A stored key could not be read on this Windows account")
        return ""
    return _take(result).decode("utf-8")
