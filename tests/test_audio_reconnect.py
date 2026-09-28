# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Unplugging the sound card and plugging it back in, with a stand-in for PortAudio.

A failed attempt used to leave a PortAudio instance behind, and every one of them keeps its own
list of devices from the moment it started, which is why a card that came back kept failing with
"Invalid device info".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import audio, config, engine  # noqa: E402

USB = "Speakers (USB Audio Device) [Loopback]"
BUILT_IN = "Speakers (Realtek) [Loopback]"


def device(name, index):
    return {"name": name, "index": index, "maxInputChannels": 2, "defaultSampleRate": 48000}


class FakePortAudio:
    """One PyAudio instance: it sees the devices that existed when it was created."""

    instances = []
    devices = []
    fail_open = False

    def __init__(self):
        self.visible = list(FakePortAudio.devices)
        self.terminated = False
        self.streams = []
        FakePortAudio.instances.append(self)

    def get_loopback_device_info_generator(self):
        return iter(self.visible)

    def get_default_wasapi_loopback(self):
        if not self.visible:
            raise OSError("[Errno -9996] Invalid device info")
        return self.visible[-1]

    def open(self, **kwargs):
        if FakePortAudio.fail_open:
            raise OSError("[Errno -9996] Invalid device info")
        stream = FakeStream()
        self.streams.append(stream)
        return stream

    def terminate(self):
        self.terminated = True


class FakeStream:
    def __init__(self):
        self.active = True
        self.closed = False

    def start_stream(self):
        pass

    def stop_stream(self):
        self.active = False

    def close(self):
        self.closed = True

    def is_active(self):
        return self.active


class FakeResampler:
    def __init__(self, *args, **kwargs):
        pass

    def resample_chunk(self, pcm):
        return pcm


class ReconnectTest(unittest.TestCase):
    def setUp(self):
        self.real_pyaudio, self.real_soxr = audio.pyaudio, audio.soxr
        audio.pyaudio = type("pyaudio", (), {"PyAudio": FakePortAudio, "paInt16": 8, "paContinue": 0})
        audio.soxr = type("soxr", (), {"ResampleStream": FakeResampler})
        FakePortAudio.instances = []
        FakePortAudio.devices = [device(BUILT_IN, 1), device(USB, 2)]
        FakePortAudio.fail_open = False

    def tearDown(self):
        audio.pyaudio, audio.soxr = self.real_pyaudio, self.real_soxr

    def test_a_failed_attempt_does_not_leave_portaudio_behind(self):
        FakePortAudio.fail_open = True
        capture = audio.LoopbackCapture(USB, backlog_seconds=0)
        with self.assertRaises(OSError):
            capture.start()
        self.assertTrue(all(pa.terminated for pa in FakePortAudio.instances),
                        "a PortAudio instance was left open after a failed attempt")

    def test_repeated_failures_do_not_pile_up(self):
        FakePortAudio.fail_open = True
        for _ in range(5):
            capture = audio.LoopbackCapture(USB, backlog_seconds=0)
            with self.assertRaises(OSError):
                capture.start()
        self.assertEqual([pa for pa in FakePortAudio.instances if not pa.terminated], [])

    def test_a_missing_device_falls_back_to_the_default_one(self):
        FakePortAudio.devices = [device(BUILT_IN, 1)]  # the USB card was unplugged
        capture = audio.LoopbackCapture(USB, backlog_seconds=0)
        capture.start()
        try:
            self.assertTrue(capture.using_fallback)
            self.assertEqual(capture.device_name, BUILT_IN)
        finally:
            capture.stop()

    def test_the_chosen_device_is_used_when_it_is_there(self):
        capture = audio.LoopbackCapture(USB, backlog_seconds=0)
        capture.start()
        try:
            self.assertFalse(capture.using_fallback)
            self.assertEqual(capture.device_name, USB)
        finally:
            capture.stop()

    def test_stopping_releases_everything(self):
        capture = audio.LoopbackCapture(USB, backlog_seconds=0)
        capture.start()
        capture.stop()
        self.assertTrue(all(pa.terminated for pa in FakePortAudio.instances))
        self.assertTrue(all(stream.closed for pa in FakePortAudio.instances for stream in pa.streams))
        capture.stop()  # stopping twice must not raise

    def test_device_available_sees_the_card_come_back(self):
        FakePortAudio.devices = [device(BUILT_IN, 1)]
        self.assertFalse(audio.device_available(USB))
        FakePortAudio.devices = [device(BUILT_IN, 1), device(USB, 2)]
        self.assertTrue(audio.device_available(USB))


class SwitchBackTest(unittest.TestCase):
    """While on a stand-in device, the engine watches for the user's own device to return."""

    def _engine(self, device_name, using_fallback):
        cfg = dict(config.DEFAULTS, audio_device=device_name)
        e = engine.CaptionEngine(cfg, lambda *a: None, lambda *a: None, lambda *a: None, lambda *a: None)
        e._capture = type("Capture", (), {"using_fallback": using_fallback, "device_name": BUILT_IN})()
        return e

    def test_it_switches_back_when_the_device_returns(self):
        e = self._engine(USB, using_fallback=True)
        real_available = audio.device_available
        try:
            audio.device_available = lambda name: name == USB
            self.assertTrue(e._should_switch_device())
            audio.device_available = lambda name: False
            self.assertFalse(e._should_switch_device())
        finally:
            audio.device_available = real_available

    def test_it_does_not_keep_checking_while_the_chosen_device_is_in_use(self):
        e = self._engine(USB, using_fallback=False)
        checked = []
        real_available = audio.device_available
        try:
            audio.device_available = lambda name: checked.append(name) or True
            self.assertFalse(e._should_switch_device())
            self.assertEqual(checked, [], "the device list was searched for nothing")
        finally:
            audio.device_available = real_available

    def test_the_default_device_is_still_followed(self):
        e = self._engine("default", using_fallback=False)
        real_name = audio.default_output_name
        try:
            audio.default_output_name = lambda: "Headphones"
            self.assertTrue(e._should_switch_device())
            audio.default_output_name = lambda: BUILT_IN.split(" [")[0]
            self.assertFalse(e._should_switch_device())
        finally:
            audio.default_output_name = real_name


if __name__ == "__main__":
    unittest.main(verbosity=2)
