# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""One running copy at a time: a named Windows mutex (the installer looks for it) and a local socket."""
import ctypes

from PySide6.QtNetwork import QLocalServer, QLocalSocket

ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183


def claim_mutex(name, kernel32=None):
    """Take the named Windows mutex. Returns (handle, True) for the first copy, (handle, False) if one runs.

    A copy running as administrator owns a mutex an ordinary copy is not allowed to open: Windows
    then answers "access denied" rather than "already exists", and that too means one is running.
    The handle is kept for as long as the app runs; the installer also looks for this mutex.
    """
    if kernel32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not handle:
        return None, error != ERROR_ACCESS_DENIED
    return handle, error != ERROR_ALREADY_EXISTS


def claim_server(qt, key):
    """Returns a QLocalServer if this is the only running copy, else None. The running copy is left alone."""
    probe = QLocalSocket()
    probe.connectToServer(key)
    if probe.waitForConnected(300):
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(key)  # stale socket left by a crash
    server = QLocalServer(qt)
    server.listen(key)
    return server
