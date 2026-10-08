# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""How much of the PC EchoSub is using: processor, memory, graphics card and its memory, disk.

Everything is counted for EchoSub together with the programs it started — the graphics-card
speech engine runs as one of them — so the numbers are what EchoSub really costs.

The processor, memory and disk come from psutil. The graphics card comes from the same Windows
performance counters Task Manager reads ("GPU Engine" and "GPU Process Memory"), through the PDH
library; on a Windows without them the graphics-card figures are simply left out.
"""
import collections
import ctypes
import logging
import os
import re
import sys
import threading
import time
from ctypes import wintypes

import psutil

log = logging.getLogger(__name__)

INTERVAL = 2.0   # seconds between samples
Sample = collections.namedtuple("Sample", "cpu ram gpu vram disk")  # %, bytes, % or None, bytes or None, bytes/s
ENGINE_PID = re.compile(r"pid_(\d+)_.*engtype_([^_\s]+)", re.IGNORECASE)
MEMORY_PID = re.compile(r"pid_(\d+)_", re.IGNORECASE)


def human_bytes(n):
    if n is None:
        return "–"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def summary(sample):
    """One short line: "CPU 12% · RAM 1.4 GB · GPU 35% · VRAM 1.9 GB · Disk 0.2 MB/s"."""
    if sample is None:
        return ""
    parts = [f"CPU {sample.cpu:.0f}%", f"RAM {human_bytes(sample.ram)}"]
    if sample.gpu is not None:
        parts.append(f"GPU {sample.gpu:.0f}%")
    if sample.vram is not None:
        parts.append(f"VRAM {human_bytes(sample.vram)}")
    parts.append(f"Disk {human_bytes(sample.disk)}/s")
    return " · ".join(parts)


# ---- the graphics card, through Windows performance counters ----------------

class _CounterValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _CounterItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _CounterValue)]


PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2


class GpuCounters:
    """Per-process graphics-card use and memory, as Task Manager shows them."""

    def __init__(self):
        self.ok = False
        if sys.platform != "win32":
            return
        try:
            self._pdh = ctypes.WinDLL("pdh")
            self._query = ctypes.c_void_p()
            if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)):
                return
            self._engine = self._add(r"\GPU Engine(*)\Utilization Percentage")
            self._memory = self._add(r"\GPU Process Memory(*)\Dedicated Usage")
            self.ok = self._engine is not None or self._memory is not None
            if self.ok:
                self._pdh.PdhCollectQueryData(self._query)  # a rate needs a first reading to compare with
        except OSError as e:
            log.info("Graphics-card counters are not available: %s", e)

    def _add(self, path):
        counter = ctypes.c_void_p()
        if self._pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(counter)):
            log.info("Windows has no counter %s", path)
            return None
        return counter

    def _values(self, counter):
        """[(instance name, value)] for a wildcard counter."""
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        flags = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        status = self._pdh.PdhGetFormattedCounterArrayW(counter, flags, ctypes.byref(size), ctypes.byref(count), None)
        if status & 0xFFFFFFFF != PDH_MORE_DATA or not size.value:  # PDH codes are unsigned
            return []
        buffer = (ctypes.c_byte * size.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(counter, flags, ctypes.byref(size), ctypes.byref(count), buffer):
            return []
        items = ctypes.cast(buffer, ctypes.POINTER(_CounterItem))
        return [(items[i].szName or "", items[i].FmtValue.doubleValue) for i in range(count.value)
                if items[i].FmtValue.CStatus in (0, 1)]  # valid, or valid but new

    def read(self, pids):
        """(% of the busiest engine, dedicated memory in bytes) for these processes, or (None, None)."""
        if not self.ok or self._pdh.PdhCollectQueryData(self._query):
            return None, None
        pids = {str(pid) for pid in pids}
        gpu = vram = None
        if self._engine is not None:
            # Task Manager's figure: each kind of engine (3D, compute, copy, video) added up across
            # the processes, then the busiest kind.
            by_engine = collections.Counter()
            for name, value in self._values(self._engine):
                found = ENGINE_PID.search(name)
                if found and found.group(1) in pids:
                    by_engine[found.group(2).lower()] += value
            gpu = min(100.0, max(by_engine.values(), default=0.0))
        if self._memory is not None:
            vram = 0
            for name, value in self._values(self._memory):
                found = MEMORY_PID.search(name)
                if found and found.group(1) in pids:
                    vram += value
        return gpu, vram

    def close(self):
        if getattr(self, "_query", None):
            self._pdh.PdhCloseQuery(self._query)
            self._query = None


# ---- sampling ----------------------------------------------------------------

class Sampler:
    """Reads one Sample at a time for a process and everything it started."""

    def __init__(self, pid=None, gpu=None):
        self.process = psutil.Process(pid or os.getpid())
        self.gpu = gpu if gpu is not None else GpuCounters()
        self.cpus = psutil.cpu_count() or 1
        self._known = {}
        self._last_io, self._last_at = None, None

    def _processes(self):
        """EchoSub and its children, keeping each psutil.Process so its CPU time keeps counting."""
        try:
            current = [self.process] + self.process.children(recursive=True)
        except psutil.Error:
            current = [self.process]
        kept = {}
        for proc in current:
            kept[proc.pid] = self._known.get(proc.pid, proc)
        self._known = kept
        return list(kept.values())

    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        cpu = ram = 0.0
        io_total = 0
        alive = []
        for proc in self._processes():
            try:
                with proc.oneshot():
                    cpu += proc.cpu_percent(None)
                    ram += proc.memory_info().rss
                    io = proc.io_counters()
                    io_total += io.read_bytes + io.write_bytes
                alive.append(proc.pid)
            except psutil.Error:
                continue
        disk = 0.0
        if self._last_io is not None and now > self._last_at:
            disk = max(0.0, (io_total - self._last_io) / (now - self._last_at))
        self._last_io, self._last_at = io_total, now
        gpu, vram = self.gpu.read(alive)
        return Sample(min(100.0, cpu / self.cpus), ram, gpu, vram, disk)


class UsageMonitor:
    """Samples in the background every couple of seconds; `latest` is always the newest Sample.

    Displays read `latest` on their own timers rather than being sent anything, so a window that
    has closed is never reached from here.
    """

    def __init__(self, interval=INTERVAL):
        self.interval = interval
        self.latest = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="usage", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            sampler = Sampler()
        except Exception as e:  # never let a counter take the app down
            log.info("Usage figures are not available: %s", e)
            return
        sampler.sample()  # the first reading only sets the starting point for rates
        while not self._stop.wait(self.interval):
            try:
                self.latest = sampler.sample()
            except Exception as e:
                log.debug("Could not read usage: %s", e)
        sampler.gpu.close()


_shared = None


def shared():
    """The one monitor the whole app reads from, started on first use."""
    global _shared
    if _shared is None:
        _shared = UsageMonitor().start()
    return _shared
