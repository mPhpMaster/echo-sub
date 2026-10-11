# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Downloading and installing an update, only when asked. Nothing leaves the machine in these tests."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import config, update_install as u  # noqa: E402

INSTALLER = b"MZ pretend installer" * 1000
GOOD = hashlib.sha256(INSTALLER).hexdigest()


class Reply:
    def __init__(self, body=b"", text=""):
        self.body, self.text = body, text
        self.headers = {"Content-Length": str(len(body))}

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        for i in range(0, len(self.body), 4096):
            yield self.body[i:i + 4096]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Session:
    def __init__(self, checksum=GOOD):
        self.checksum, self.asked = checksum, []

    def get(self, url, stream=False, timeout=None):
        self.asked.append(url)
        if url.endswith(".sha256"):
            return Reply(text=f"{self.checksum} *EchoSub-Setup-9.9.9.exe\n")
        return Reply(body=INSTALLER)


class AddressTest(unittest.TestCase):
    def test_only_the_projects_own_releases(self):
        url, sha = u.asset_urls("1.15.0")
        self.assertEqual(url, "https://github.com/mPhpMaster/echo-sub/releases/download/v1.15.0/"
                              "EchoSub-Setup-1.15.0.exe")
        self.assertEqual(sha, url + ".sha256")

    def test_anything_but_a_version_number_is_refused(self):
        for bad in ("1.15.0/../../x", "", "v1", "1.15.0.exe?x=1"):
            with self.subTest(bad=bad), self.assertRaises(u.UpdateFailed):
                u.asset_urls(bad)

    def test_checksum_files(self):
        self.assertEqual(u.parse_sha256(f"{GOOD.upper()}  EchoSub-Setup.exe"), GOOD)
        self.assertIsNone(u.parse_sha256("no hash here"))


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_a_matching_installer_is_kept(self):
        progress = []
        path = u.download("9.9.9", self.folder, lambda d, t: progress.append(d), session=Session())
        with open(path, "rb") as f:
            self.assertEqual(f.read(), INSTALLER)
        self.assertEqual(progress[-1], len(INSTALLER))

    def test_a_tampered_installer_is_deleted_and_never_run(self):
        with self.assertRaises(u.UpdateFailed):
            u.download("9.9.9", self.folder, session=Session(checksum="0" * 64))
        self.assertEqual(os.listdir(self.folder), [], "nothing is left behind to be run by mistake")

    def test_cancel(self):
        with self.assertRaises(u.UpdateCanceled):
            u.download("9.9.9", self.folder, should_cancel=lambda: True, session=Session())

    def test_the_installer_runs_quietly_and_starts_echosub_again(self):
        command = u.installer_command(r"D:\x\EchoSub-Setup-9.9.9.exe")
        self.assertIn("/SILENT", command)
        self.assertIn("/RELAUNCH=1", command)

    def test_the_installer_knows_the_relaunch_switch(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer",
                               "EchoSub.iss"), encoding="utf-8") as f:
            script = f.read()
        self.assertIn("{param:RELAUNCH|0}", script)
        self.assertIn("runasoriginaluser", script)

    def test_offered_by_default_and_can_be_switched_off(self):
        self.assertTrue(config.DEFAULTS["update_install"])
        self.assertEqual(config.DEFAULTS["update_dir"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
