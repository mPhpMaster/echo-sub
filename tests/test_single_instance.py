# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Opening EchoSub while it already runs does nothing at all."""
import ctypes
import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import main  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "Windows mutexes")
class SingleInstanceTest(unittest.TestCase):
    def setUp(self):
        self.name = f"EchoSubTest-{uuid.uuid4()}"
        self.handles = []
        self.addCleanup(lambda: [ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(h)) for h in self.handles])

    def claim(self):
        handle, first = main.claim_mutex(self.name)
        self.handles.append(handle)
        return first

    def test_the_first_copy_runs(self):
        self.assertTrue(self.claim())

    def test_a_second_copy_does_not(self):
        self.claim()
        self.assertFalse(self.claim())

    def test_once_the_first_has_closed_it_can_start_again(self):
        self.claim()
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handles.pop()))
        self.assertTrue(self.claim())

    def test_a_second_copy_never_asks_the_first_to_do_anything(self):
        self.assertFalse(hasattr(main.App, "activate_from_second_instance"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
