# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""A phrase of your own that starts a program you wrote down, with no shell in between."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config, voice_actions, voice_commands  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402
from echosub.settings_voice_commands import RUN_KEY  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])
SAVED = [{"phrase": "movie mode", "run": 'notepad.exe "D:\\my notes.txt"'}]
WAKE = ("alexa",)


class SplittingTest(unittest.TestCase):
    def test_a_windows_path_keeps_its_backslashes(self):
        self.assertEqual(voice_actions.split_command_line(r'notepad.exe "D:\my notes.txt"'),
                         ["notepad.exe", r"D:\my notes.txt"])

    def test_plain_arguments_split_on_spaces(self):
        self.assertEqual(voice_actions.split_command_line("code --new-window ."),
                         ["code", "--new-window", "."])

    def test_shell_punctuation_is_only_ever_an_argument(self):
        # No shell runs this, so these are characters in an argument, not a second command.
        self.assertEqual(voice_actions.split_command_line("prog a && del b"),
                         ["prog", "a", "&&", "del", "b"])
        self.assertEqual(voice_actions.split_command_line("prog > out.txt"), ["prog", ">", "out.txt"])

    def test_an_empty_line_names_nothing(self):
        for line in ("", "   ", '""'):
            self.assertEqual(voice_actions.split_command_line(line), [], repr(line))


class MatchingTest(unittest.TestCase):
    def test_your_phrase_starts_your_program(self):
        found = voice_commands.find("alexa movie mode", WAKE, custom_commands=SAVED)
        self.assertEqual((found["action"], found["target"]), ("run", SAVED[0]["run"]))

    def test_the_whole_phrase_has_to_match(self):
        self.assertIsNone(voice_commands.find("alexa movie mode please", WAKE, custom_commands=SAVED))

    def test_built_in_actions_still_work_alongside(self):
        both = SAVED + [{"phrase": "quiet", "command": "pause_captions"}]
        found = voice_commands.find("alexa quiet", WAKE, custom_commands=both)
        self.assertEqual(found["key"], "pause_captions")

    def test_a_row_with_neither_is_dropped(self):
        kept = voice_commands.valid_custom_commands(
            [{"phrase": "x"}, {"phrase": "y", "command": "not a real key"}, {"phrase": "", "run": "prog"}])
        self.assertEqual(kept, [])

    def test_nothing_that_was_said_reaches_the_program_line(self):
        found = voice_commands.find("alexa movie mode", WAKE, custom_commands=SAVED)
        self.assertEqual(found["target"], SAVED[0]["run"], "the saved line must be passed through untouched")


class RunnerTest(unittest.TestCase):
    def test_the_runner_starts_exactly_what_was_saved(self):
        started, launched = [], []
        runner = voice_commands.CommandRunner(program_starter=started.append, launcher=launched.append)
        found = voice_commands.find("alexa movie mode", WAKE, custom_commands=SAVED)
        self.assertEqual(runner.run(found, now=0), found["label"])
        self.assertEqual((started, launched), ([SAVED[0]["run"]], []))

    def test_a_forged_empty_line_is_refused(self):
        runner = voice_commands.CommandRunner(program_starter=lambda line: None)
        self.assertIsNone(runner.run({"key": "run:x", "action": "run", "target": "  ", "label": "x"}, now=0))

    def test_a_forged_line_that_is_not_text_is_refused(self):
        runner = voice_commands.CommandRunner(program_starter=lambda line: None)
        self.assertIsNone(runner.run({"key": "run:x", "action": "run", "target": None, "label": "x"}, now=0))


class AppTest(unittest.TestCase):
    def test_it_waits_out_the_countdown_like_any_other_command(self):
        started = []
        app_ = FakeApp(voice_commands=True, voice_command_delay=3, voice_custom_commands=SAVED)
        app_._voice_runner = voice_commands.CommandRunner(app_action=app_._run_app_command,
                                                          program_starter=started.append)
        self.assertIsNotNone(app_._handle_voice_command("echo sub movie mode"))
        self.assertEqual(started, [], "a program must not start before you can cancel it")
        app_._notice.fire_now()
        self.assertEqual(started, [SAVED[0]["run"]])

    def test_cancelling_stops_the_program_starting(self):
        started = []
        app_ = FakeApp(voice_commands=True, voice_command_delay=3, voice_custom_commands=SAVED)
        app_._voice_runner = voice_commands.CommandRunner(app_action=app_._run_app_command,
                                                          program_starter=started.append)
        app_._handle_voice_command("echo sub movie mode")
        self.assertTrue(app_.cancel_pending_command())
        app_._notice.fire_now()
        self.assertEqual(started, [])


class SettingsTest(unittest.TestCase):
    def test_a_typed_program_line_survives_a_round_trip(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, voice_custom_commands=SAVED))
        self.assertEqual(dialog.values()["voice_custom_commands"], SAVED)

    def test_choosing_a_built_in_action_clears_the_program_box(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, voice_custom_commands=SAVED))
        combo = dialog.voice_custom_table.cellWidget(0, 1)
        line = dialog.voice_custom_table.cellWidget(0, 2)
        self.assertTrue(line.isEnabled())
        combo.setCurrentIndex(combo.findData("pause_captions"))
        self.assertFalse(line.isEnabled())
        self.assertEqual(dialog.values()["voice_custom_commands"],
                         [{"phrase": "movie mode", "command": "pause_captions"}])

    def test_the_program_box_is_the_one_that_starts_enabled_for_a_new_row(self):
        dialog = SettingsDialog(dict(config.DEFAULTS))
        dialog._add_voice_custom_command()
        combo = dialog.voice_custom_table.cellWidget(0, 1)
        self.assertNotEqual(combo.currentData(), RUN_KEY, "a new row should not default to running a program")


if __name__ == "__main__":
    unittest.main(verbosity=2)
