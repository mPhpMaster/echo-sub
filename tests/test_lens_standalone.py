# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The standalone EchoSub Lens opens instead of the built-in one when it is installed."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import lens_app, lens_standalone  # noqa: E402

EXE = r"D:\Programs\EchoSub Lens\EchoSubLens.exe"


class FakeKey:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    """Just enough of winreg: {(hive, view): InstallLocation}; missing keys raise OSError like the real one."""
    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = "HKCU", "HKLM"
    KEY_READ, KEY_WOW64_64KEY, KEY_WOW64_32KEY = 1, 256, 512

    def __init__(self, values):
        self.values = values
        self.opened = []

    def OpenKey(self, hive, path, reserved, access):
        assert path == lens_standalone.UNINSTALL_KEY
        view = access & ~self.KEY_READ
        self.opened.append((hive, view))
        if (hive, view) not in self.values:
            raise FileNotFoundError(path)
        return FakeKey(self.values[(hive, view)])

    def QueryValueEx(self, key, name):
        assert name == "InstallLocation"
        return key.value, 1


class RegistryLookupTest(unittest.TestCase):
    def folders(self, values):
        fake = FakeWinreg(values)
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            return lens_standalone.registry_folders(), fake

    def test_uninstall_key_is_the_standalone_installers_appid(self):
        self.assertTrue(lens_standalone.UNINSTALL_KEY.endswith(
            r"\Uninstall\{B3D7A1E4-5C2F-4F6B-9E8A-7D1C0B4E2F63}_is1"))

    def test_per_user_comes_before_per_machine(self):
        folders, fake = self.folders({("HKLM", 256): "C:\\Program Files\\EchoSub Lens\\",
                                      ("HKCU", 256): "D:\\Programs\\EchoSub Lens\\"})
        self.assertEqual(folders, ["D:\\Programs\\EchoSub Lens\\", "C:\\Program Files\\EchoSub Lens\\"])
        self.assertEqual(fake.opened[0][0], "HKCU")

    def test_32_bit_view_and_blank_values(self):
        folders, _ = self.folders({("HKLM", 512): "E:\\Apps\\EchoSub Lens", ("HKCU", 256): "  "})
        self.assertEqual(folders, ["E:\\Apps\\EchoSub Lens"])

    def test_nothing_installed(self):
        self.assertEqual(self.folders({})[0], [])

    def test_fallback_folders(self):
        folders = lens_standalone.fallback_folders({"LOCALAPPDATA": r"C:\Users\me\AppData\Local"})
        self.assertEqual(folders, [os.path.join(r"C:\Users\me\AppData\Local", "Programs", "EchoSub Lens"),
                                   os.path.join("D:\\", "Programs", "EchoSub Lens")])
        self.assertEqual(lens_standalone.fallback_folders({}), [os.path.join("D:\\", "Programs", "EchoSub Lens")])


class FindTest(unittest.TestCase):
    def test_registry_wins_over_fallbacks(self):
        with tempfile.TemporaryDirectory() as reg, tempfile.TemporaryDirectory() as fallback:
            for folder in (reg, fallback):
                open(os.path.join(folder, "EchoSubLens.exe"), "wb").close()
            exe = lens_standalone.find_standalone(lambda: [reg], lambda: [fallback])
            self.assertEqual(exe, os.path.join(reg, "EchoSubLens.exe"))

    def test_registry_folder_without_the_exe_falls_back(self):
        with tempfile.TemporaryDirectory() as reg, tempfile.TemporaryDirectory() as fallback:
            open(os.path.join(fallback, "EchoSubLens.exe"), "wb").close()
            exe = lens_standalone.find_standalone(lambda: [reg], lambda: [fallback])
            self.assertEqual(exe, os.path.join(fallback, "EchoSubLens.exe"))

    def test_not_installed(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(lens_standalone.find_standalone(lambda: [], lambda: [empty]))

    def test_menu_text_names_the_lens_that_opens(self):
        self.assertEqual(lens_standalone.menu_text(lambda: EXE), "Screen translation (EchoSub Lens)…")
        self.assertEqual(lens_standalone.menu_text(lambda: None), "EchoSub Lens: translate the screen…")


class LaunchDecisionTest(unittest.TestCase):
    def test_standalone_opens_when_installed(self):
        builtin, launch = mock.Mock(return_value=True), mock.Mock(return_value=True)
        self.assertEqual(lens_standalone.open_lens(builtin, ["a.pdf"], lambda: EXE, launch), "standalone")
        launch.assert_called_once_with(EXE, ["a.pdf"])
        builtin.assert_not_called()

    def test_builtin_when_not_installed(self):
        builtin, launch = mock.Mock(return_value=True), mock.Mock()
        self.assertEqual(lens_standalone.open_lens(builtin, (), lambda: None, launch), "builtin")
        launch.assert_not_called()

    def test_builtin_when_the_standalone_fails_to_start(self):
        builtin = mock.Mock(return_value=True)
        self.assertEqual(lens_standalone.open_lens(builtin, (), lambda: EXE, lambda exe, args: False), "builtin")
        builtin.assert_called_once()

    def test_none_when_nothing_starts(self):
        self.assertIsNone(lens_standalone.open_lens(lambda: False, (), lambda: None))

    def test_never_starts_itself(self):
        launch = mock.Mock(return_value=True)
        self.assertEqual(lens_standalone.open_lens(lambda: True, (), lambda: sys.executable, launch), "builtin")
        launch.assert_not_called()

    def test_launch_is_detached_without_a_console(self):
        popen = mock.Mock()
        self.assertTrue(lens_standalone.launch_standalone(EXE, ["a.pdf"], popen))
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [EXE, "a.pdf"])
        self.assertEqual(kwargs["cwd"], os.path.dirname(EXE))
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        if sys.platform == "win32":
            self.assertEqual(kwargs["creationflags"], 0x00000008 | 0x00000200)

    def test_launch_failure_is_reported(self):
        self.assertFalse(lens_standalone.launch_standalone(EXE, (), mock.Mock(side_effect=OSError("gone"))))


class LensFlagTest(unittest.TestCase):
    """`EchoSub.exe --lens` (the Start menu shortcut) hands over to the standalone Lens."""

    def test_hands_over_with_the_files(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = os.path.join(folder, "report.pdf")
            open(doc, "wb").close()
            launch = mock.Mock(return_value=True)
            with mock.patch.object(lens_standalone, "find_standalone", lambda: EXE), \
                    mock.patch.object(lens_standalone, "launch_standalone", launch):
                self.assertTrue(lens_app.open_standalone_instead(["--lens", doc]))
            launch.assert_called_once_with(EXE, [doc])

    def test_builtin_starts_when_not_installed(self):
        with mock.patch.object(lens_standalone, "find_standalone", lambda: None):
            self.assertFalse(lens_app.open_standalone_instead(["--lens"]))

    def test_builtin_flag_keeps_the_builtin_lens(self):
        find = mock.Mock(return_value=EXE)
        with mock.patch.object(lens_standalone, "find_standalone", find):
            self.assertFalse(lens_app.open_standalone_instead(["--lens", "--builtin-lens"]))
        find.assert_not_called()


if __name__ == "__main__":
    unittest.main()
