# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Telling the truth about the graphics card, instead of offering CUDA to a machine without it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import gpu  # noqa: E402

AMD = ["AMD Radeon RX 7800 XT"]
INTEL = ["Intel(R) UHD Graphics 770"]
NVIDIA = ["NVIDIA GeForce RTX 4070"]


class VendorTest(unittest.TestCase):
    def test_each_make_is_recognized(self):
        self.assertEqual(gpu.vendor(AMD), "amd")
        self.assertEqual(gpu.vendor(INTEL), "intel")
        self.assertEqual(gpu.vendor(NVIDIA), "nvidia")

    def test_more_names_for_the_same_makes(self):
        self.assertEqual(gpu.vendor(["Radeon(TM) Vega 8 Graphics"]), "amd")
        self.assertEqual(gpu.vendor(["NVIDIA GeForce GTX 1060 6GB"]), "nvidia")
        self.assertEqual(gpu.vendor(["Intel(R) Arc(TM) A770"]), "intel")

    def test_a_discrete_card_wins_over_built_in_graphics(self):
        self.assertEqual(gpu.vendor(INTEL + AMD), "amd")
        self.assertEqual(gpu.vendor(INTEL + NVIDIA), "nvidia")

    def test_something_unknown_is_not_guessed_at(self):
        self.assertIsNone(gpu.vendor(["Parsec Virtual Display Adapter"]))
        self.assertIsNone(gpu.vendor([]))

    def test_this_pc_is_read_without_crashing(self):
        self.assertIsInstance(gpu.cards(), list)
        self.assertIn(gpu.vendor(), ("nvidia", "amd", "intel", None))


class NoteTest(unittest.TestCase):
    """What a machine is told. On a PC with working CUDA there is nothing to say."""

    def setUp(self):
        self._real = gpu.cuda_usable
        gpu.cuda_usable = lambda: False
        self.addCleanup(lambda: setattr(gpu, "cuda_usable", self._real))

    def test_an_amd_machine_is_told_why_plainly(self):
        note = gpu.note(AMD)
        self.assertIn("Radeon", note)
        self.assertIn("NVIDIA cards only", note)
        self.assertIn("Light mode", note, "it should say what to do about it")

    def test_an_intel_machine_too(self):
        self.assertIn("Intel", gpu.note(INTEL))

    def test_an_nvidia_machine_without_working_cuda_is_told_it_is_the_driver(self):
        self.assertIn("driver", gpu.note(NVIDIA))

    def test_a_machine_with_no_known_card(self):
        self.assertIn("processor", gpu.note([]))

    def test_nothing_is_said_when_the_card_does_work(self):
        gpu.cuda_usable = self._real
        if gpu.cuda_usable():
            self.assertIsNone(gpu.note())


class SettingsTest(unittest.TestCase):
    def test_the_option_no_longer_promises_any_graphics_card(self):
        from PySide6.QtWidgets import QApplication

        from echosub import config
        from echosub.settings_dialog import SettingsDialog

        QApplication.instance() or QApplication([])
        dialog = SettingsDialog(dict(config.DEFAULTS))
        self.addCleanup(dialog.close)
        labels = [dialog.device.itemText(i) for i in range(dialog.device.count())]
        self.assertTrue(any("NVIDIA only" in label for label in labels), labels)
        self.assertEqual([dialog.device.itemData(i) for i in range(dialog.device.count())],
                         ["cuda", "cpu"], "the stored values must not change")


if __name__ == "__main__":
    unittest.main(verbosity=2)
