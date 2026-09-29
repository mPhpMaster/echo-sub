# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""“Go to …”: a web address opens in the browser, a name opens a folder, nothing else is allowed."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import voice_commands, voice_destinations  # noqa: E402

WAKE = ("alexa",)


class AddressTest(unittest.TestCase):
    def test_a_plain_address_is_opened_over_https(self):
        found = voice_commands.find("alexa go to www.a.com", WAKE)
        self.assertEqual((found["action"], found["target"]), ("open_url", "https://www.a.com"))

    def test_capitals_and_punctuation_around_it_do_not_matter(self):
        found = voice_commands.find("Alexa, go to www.a.com.", WAKE)
        self.assertEqual(found["target"], "https://www.a.com")

    def test_a_dictated_address_is_understood(self):
        found = voice_commands.find("alexa go to www dot example dot com", WAKE)
        self.assertEqual(found["target"], "https://www.example.com")

    def test_a_path_on_the_site_is_kept(self):
        found = voice_commands.find("alexa go to example.com/watch/1", WAKE)
        self.assertEqual(found["target"], "https://example.com/watch/1")

    def test_http_is_kept_when_it_was_said(self):
        self.assertEqual(voice_destinations.spoken_url("http://x.org"), "http://x.org")

    def test_only_the_web_is_reachable(self):
        for said in ("file:///c:/windows", "javascript:alert(1)", "data:text/html,x", "about:config",
                     "\\\\server\\share", "user:pass@evil.com", "ftp://x.org", "c:\\windows\\system32"):
            with self.subTest(said=said):
                self.assertIsNone(voice_destinations.spoken_url(said), said)
                self.assertIsNone(voice_commands.find(f"alexa go to {said}", WAKE), said)

    def test_words_that_are_not_an_address_open_nothing(self):
        self.assertIsNone(voice_commands.find("alexa go to nowhere at all", WAKE))

    def test_it_still_needs_the_wake_word(self):
        self.assertIsNone(voice_commands.find("go to www.a.com", WAKE))


class FolderTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, self.dir)
        self.folders = [{"name": "work", "path": self.dir}]

    def test_a_folder_you_added_is_opened_by_the_name_you_gave_it(self):
        found = voice_commands.find("alexa go to work", WAKE, folders=self.folders)
        self.assertEqual((found["action"], found["target"]), ("open_folder", self.dir))

    def test_your_own_windows_folders_work_without_being_added(self):
        found = voice_commands.find("alexa go to downloads", WAKE)
        self.assertEqual(found["action"], "open_folder")
        self.assertTrue(os.path.isdir(found["target"]), found["target"])

    def test_arabic_names_work_too(self):
        found = voice_commands.find("alexa \u0627\u0630\u0647\u0628 \u0627\u0644\u0649 "
                                    "\u0627\u0644\u062a\u0646\u0632\u064a\u0644\u0627\u062a", WAKE)
        self.assertEqual(found["action"], "open_folder")

    def test_a_name_that_is_not_on_the_list_opens_nothing(self):
        self.assertIsNone(voice_commands.find("alexa go to secrets", WAKE, folders=self.folders))

    def test_a_spoken_path_is_never_used_as_a_path(self):
        for said in ("c:\\users", "d:/private", "..\\..\\windows", "/etc/passwd"):
            with self.subTest(said=said):
                self.assertIsNone(voice_commands.find(f"alexa go to {said}", WAKE, folders=self.folders))

    def test_broken_rows_are_dropped(self):
        kept = voice_destinations.valid_folders(
            [{"name": "", "path": "x"}, {"name": "y", "path": ""}, "junk", None,
             {"name": " Work ", "path": " C:\\w "}, {"name": "WORK", "path": "C:\\other"}])
        self.assertEqual(kept, [{"name": "Work", "path": "C:\\w"}], "blanks or duplicates got through")

    def test_the_list_is_capped(self):
        many = [{"name": f"n{i}", "path": f"C:\\{i}"} for i in range(60)]
        self.assertEqual(len(voice_destinations.valid_folders(many)), voice_destinations.MAX_FOLDERS)


class RunnerTest(unittest.TestCase):
    def test_the_runner_only_hands_the_address_to_the_browser(self):
        opened, launched = [], []
        runner = voice_commands.CommandRunner(url_opener=opened.append, launcher=launched.append)
        found = voice_commands.find("alexa go to www.a.com", WAKE)
        self.assertEqual(runner.run(found, now=0), found["label"])
        self.assertEqual((opened, launched), (["https://www.a.com"], []))

    def test_a_forged_address_is_refused(self):
        runner = voice_commands.CommandRunner(url_opener=lambda url: None)
        forged = {"key": "go_url:x", "action": "open_url", "target": "file:///c:/windows", "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))

    def test_a_forged_folder_that_is_not_there_is_refused(self):
        runner = voice_commands.CommandRunner(folder_opener=lambda path: True)
        forged = {"key": "go_folder:x", "action": "open_folder", "target": "Z:\\nope", "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))

    def test_a_folder_that_vanished_is_reported_not_crashed(self):
        runner = voice_commands.CommandRunner(folder_opener=lambda path: False)
        with tempfile.TemporaryDirectory() as folder:
            found = voice_commands.find("alexa go to work", WAKE, folders=[{"name": "work", "path": folder}])
            self.assertIn("not on this PC", runner.run(found, now=0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
