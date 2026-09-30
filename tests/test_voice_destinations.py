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


class FileTest(unittest.TestCase):
    """A song, picked in the settings, opened with whatever program Windows uses for it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.song = os.path.join(self.dir, "my song.mp3")
        with open(self.song, "wb") as handle:
            handle.write(b"not really audio")
        self.addCleanup(lambda: (os.remove(self.song), os.rmdir(self.dir)))
        self.places = [{"name": "my song", "path": self.song}]

    def test_play_opens_the_file_you_chose(self):
        found = voice_commands.find("alexa play my song", WAKE, folders=self.places)
        self.assertEqual((found["action"], found["target"]), ("open_file", self.song))

    def test_go_to_works_for_a_file_as_well(self):
        found = voice_commands.find("alexa go to my song", WAKE, folders=self.places)
        self.assertEqual(found["action"], "open_file")

    def test_a_folder_is_still_a_folder(self):
        places = [{"name": "tunes", "path": self.dir}]
        found = voice_commands.find("alexa play tunes", WAKE, folders=places)
        self.assertEqual(found["action"], "open_folder", "a folder must not be opened as a file")

    def test_play_the_music_is_still_the_media_key(self):
        found = voice_commands.find("alexa play the music", WAKE, folders=self.places)
        self.assertEqual(found["action"], "media")

    def test_play_music_does_not_open_the_music_folder(self):
        # "Play music" means press play. Only "go to music" should open the folder.
        self.assertEqual(voice_commands.find("alexa play music", WAKE, folders=self.places)["action"], "media")
        self.assertEqual(voice_commands.find("alexa go to music", WAKE, folders=self.places)["action"],
                         "open_folder")

    def test_play_is_only_for_names_you_saved_yourself(self):
        self.assertIsNone(voice_commands.find("alexa play www.a.com", WAKE, folders=self.places),
                          "a web address is not something one plays")
        self.assertIsNone(voice_commands.find("alexa play downloads", WAKE, folders=self.places))

    def test_play_something_unknown_is_still_the_media_key(self):
        found = voice_commands.find("alexa play the next song", WAKE, folders=self.places)
        self.assertEqual(found["action"], "media", "only a name you saved should open a file")

    def test_the_runner_opens_it_and_starts_no_program(self):
        opened, started = [], []
        runner = voice_commands.CommandRunner(file_opener=lambda path: opened.append(path) or True,
                                              program_starter=started.append)
        found = voice_commands.find("alexa play my song", WAKE, folders=self.places)
        self.assertEqual(runner.run(found, now=0), found["label"])
        self.assertEqual((opened, started), ([self.song], []))

    def test_a_forged_file_that_is_not_there_is_refused(self):
        runner = voice_commands.CommandRunner(file_opener=lambda path: True)
        forged = {"key": "go_file:x", "action": "open_file", "target": "Z:\\nope.mp3", "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))

    def test_a_file_that_was_deleted_is_reported_not_crashed(self):
        runner = voice_commands.CommandRunner(file_opener=lambda path: False)
        found = voice_commands.find("alexa play my song", WAKE, folders=self.places)
        self.assertIn("not on this PC", runner.run(found, now=0))


class TypedRowTest(unittest.TestCase):
    """Writing the word and the path by hand, without the file picker."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication

        from echosub import config
        from echosub.settings_dialog import SettingsDialog

        self.app = QApplication.instance() or QApplication([])
        self.dialog = SettingsDialog(dict(config.DEFAULTS))
        self.dir = tempfile.mkdtemp()
        self.song = os.path.join(self.dir, "song.mp3")
        with open(self.song, "wb") as handle:
            handle.write(b"x")
        self.addCleanup(lambda: (os.remove(self.song), os.rmdir(self.dir)))

    def type_row(self, word, path):
        from PySide6.QtWidgets import QTableWidgetItem

        self.dialog._add_go_folder()
        table = self.dialog.go_folder_table
        table.setItem(table.rowCount() - 1, 0, QTableWidgetItem(word))
        table.setItem(table.rowCount() - 1, 1, QTableWidgetItem(path))

    def test_a_typed_word_and_path_are_saved_and_then_play_the_file(self):
        self.type_row("my song", self.song)
        saved = self.dialog.values()["voice_go_folders"]
        self.assertEqual(saved, [{"name": "my song", "path": self.song}])
        found = voice_commands.find("alexa play my song", WAKE, folders=saved)
        self.assertEqual((found["action"], found["target"]), ("open_file", self.song))

    def test_quotes_around_a_pasted_path_are_dropped(self):
        self.type_row("my song", f'"{self.song}"')
        self.assertEqual(self.dialog.values()["voice_go_folders"][0]["path"], self.song)

    def test_a_path_that_is_not_there_is_shown_in_red(self):
        self.type_row("typo", "Z:\\nope\\missing.mp3")
        table = self.dialog.go_folder_table
        self.assertEqual(table.item(0, 1).foreground().color().name().upper(), "#D45B5B")
        self.type_row("real", self.song)
        self.assertNotEqual(table.item(1, 1).foreground().color().name().upper(), "#D45B5B")

    def test_an_empty_row_is_simply_dropped(self):
        self.dialog._add_go_folder()
        self.assertEqual(self.dialog.values()["voice_go_folders"], [])


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
