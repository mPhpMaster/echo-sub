# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Which graphics card is in this PC, and whether the speech engine can use it.

EchoSub recognizes speech with CTranslate2, which can target a processor or an NVIDIA card and
nothing else — there is no AMD or Intel path in it. On those machines the app quietly fell back to
the processor while the settings still offered "GPU (CUDA)", so people were left to wonder why it
was slow. This exists so the app can say what is really going on — and, when this copy ships the
any-brand Vulkan engine (asr_vulkan), point AMD and Intel owners to it.
"""
import logging
import winreg

log = logging.getLogger(__name__)

_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
VENDORS = (("nvidia", ("nvidia", "geforce", "quadro", "rtx", "gtx")),
           ("amd", ("amd", "radeon", "ryzen", "firepro", "vega")),
           ("intel", ("intel", "iris", "uhd graphics", "hd graphics", "arc")))


def cards():
    """The display adapters Windows knows about, by name."""
    found = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS) as parent:
            for index in range(32):
                try:
                    name = winreg.EnumKey(parent, index)
                except OSError:
                    break
                if not name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(parent, name) as key:
                        description, _type = winreg.QueryValueEx(key, "DriverDesc")
                except OSError:
                    continue
                if description and description not in found:
                    found.append(description)
    except OSError as e:  # no registry, or a Windows that keeps this elsewhere
        log.info("Could not read the list of graphics cards: %s", e)
    return found


def memory_size():
    """The largest card's own memory in bytes, or None. Read from the driver's registry entry, since
    the usual WMI figure stops at 4 GB."""
    sizes = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS) as parent:
            for index in range(32):
                try:
                    name = winreg.EnumKey(parent, index)
                except OSError:
                    break
                if not name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(parent, name) as key:
                        value, _type = winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")
                except OSError:
                    continue
                if isinstance(value, bytes):
                    value = int.from_bytes(value[:8], "little")
                if isinstance(value, int) and value > 0:
                    sizes.append(value)
    except OSError as e:
        log.info("Could not read the graphics memory size: %s", e)
    return max(sizes) if sizes else None


def vendor(names=None):
    """"nvidia", "amd", "intel" or None, preferring a discrete card over built-in graphics."""
    names = cards() if names is None else names
    seen = [v for name in names for v, words in VENDORS if any(w in name.lower() for w in words)]
    for preferred in ("nvidia", "amd", "intel"):
        if preferred in seen:
            return preferred
    return None


def cuda_usable():
    """True when CTranslate2 can really use a card here, not merely when one is fitted."""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception as e:
        log.info("Could not ask CTranslate2 about CUDA: %s", e)
        return False


def vulkan_shipped():
    """Whether this copy includes the graphics-card engine that works on any brand."""
    try:
        from . import asr_vulkan

        return asr_vulkan.available()
    except Exception as e:
        log.info("Could not look for the graphics-card engine: %s", e)
        return False


def note(names=None):
    """What to tell the user about their card, or None when the GPU setting needs no explanation."""
    if cuda_usable():
        return None
    names = cards() if names is None else names
    make = vendor(names)
    card = names[0] if names else "your graphics card"
    if make in ("amd", "intel") and vulkan_shipped():
        return (f"{card}: choose “Graphics card, any brand” below to use it for speech recognition. "
                "The NVIDIA-only engine cannot use it.")
    if make == "amd":
        return (f"{card} cannot be used for speech recognition: the engine EchoSub uses runs on "
                "processors and NVIDIA cards only. Captions will use the processor, which works but "
                "is slower — Light mode helps a great deal there.")
    if make == "intel":
        return (f"{card} cannot be used for speech recognition: the engine EchoSub uses runs on "
                "processors and NVIDIA cards only. Captions will use the processor; try Light mode.")
    if make == "nvidia":
        return (f"{card} was found, but CUDA is not working — usually a driver that needs updating. "
                "Captions will use the processor until it does.")
    return ("No card that can be used for speech recognition was found, so captions will use the "
            "processor. Light mode makes that noticeably faster.")
