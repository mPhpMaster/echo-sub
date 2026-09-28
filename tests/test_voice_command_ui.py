# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""How the app reacts to a spoken command: only when switched on, only from finished captions."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from echosub import config, voice_commands  # noqa: E402
from echosub.voice_command_ui import VoiceCommandMixin  # noqa: E402


class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text, icon=None, timeout=0):
        self.messages.append(text)


class FakeAction:
    def __init__(self):
        self.checked = None

    def setChecked(self, value):
        self.checked = value


class FakeOverlay:
    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class FakeApp(VoiceCommandMixin):
    def __init__(self, **overrides):
        self.cfg = dict(config.DEFAULTS)
        self.cfg.update(overrides)
        self.tray = FakeTray()
        self.overlay = FakeOverlay()
        self.act_pause = FakeAction()
        self.act_show = FakeAction()
        self._paused = False
        self._voice_runner = None
        self.saved = 0
        self.launched, self.closed = [], []
        self._unknown_command_at = 0.0

    def _save(self):
        self.saved += 1

    def use_fake_runner(self):
        self._voice_runner = voice_commands.CommandRunner(
            app_action=self._run_app_command, launcher=self.launched.append, closer=self.closed.append)
        return self


class VoiceCommandAppTest(unittest.TestCase):
    def test_nothing_happens_while_the_feature_is_off(self):
        app = FakeApp().use_fake_runner()
        self.assertIsNone(app._handle_voice_command("echo sub open calculator"))
        self.assertEqual(app.launched, [])

    def test_a_command_runs_when_the_feature_is_on(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        self.assertEqual(app._handle_voice_command("echo sub open calculator")["key"], "open_calculator")
        self.assertEqual(app.launched, [voice_commands.APPS["calculator"]])
        self.assertTrue(app.tray.messages)

    def test_ordinary_captions_are_left_alone(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        for caption in ("so I opened the calculator and typed the number",
                        "he told me to close the calculator afterwards", ""):
            self.assertIsNone(app._handle_voice_command(caption))
        self.assertEqual(app.launched, [])

    def test_commands_are_ignored_while_captions_are_paused(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        app._paused = True
        self.assertIsNone(app._handle_voice_command("echo sub open calculator"))
        self.assertEqual(app.launched, [])

    def test_echosub_controls_go_through_the_menu_actions(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        app._handle_voice_command("echo sub pause captions")
        self.assertTrue(app.act_pause.checked)
        app._handle_voice_command("echo sub hide captions")
        self.assertFalse(app.act_show.checked)
        app._handle_voice_command("echo sub clear captions")
        self.assertEqual(app.overlay.cleared, 1)

    def test_the_users_own_wake_word_is_used(self):
        app = FakeApp(voice_commands=True, voice_command_wake="computer").use_fake_runner()
        self.assertIsNotNone(app._handle_voice_command("computer open notepad"))
        self.assertEqual(app.launched, [voice_commands.APPS["notepad"]])

    def test_several_wake_words_can_be_listed(self):
        """The same name is written differently in each language: "mama, ماما"."""
        app = FakeApp(voice_commands=True, voice_command_wake="mama, ماما").use_fake_runner()
        self.assertIsNotNone(app._handle_voice_command("mama open calculator"))
        self.assertIsNotNone(app._handle_voice_command("ماما افتح المفكرة"))
        self.assertIsNone(app._handle_voice_command("open calculator"))
        self.assertEqual(app._wake_word(), "mama")

    def test_help_shows_the_available_actions(self):
        app = FakeApp(voice_commands=True, voice_command_wake="alexa").use_fake_runner()
        self.assertEqual(app._handle_voice_command("alexa help")["key"], "voice_help")
        self.assertTrue(any("calculator" in message for message in app.tray.messages))

    def test_a_saved_custom_phrase_runs_its_approved_action(self):
        app = FakeApp(voice_commands=True, voice_custom_commands=[
            {"phrase": "show calculator", "command": "open_calculator"},
        ]).use_fake_runner()
        self.assertEqual(app._handle_voice_command("echo sub show calculator")["key"], "open_calculator")
        self.assertEqual(app.launched, [voice_commands.APPS["calculator"]])

    def test_a_short_wake_word_is_not_heard_inside_another_word(self):
        app = FakeApp(voice_commands=True, voice_command_wake="mama").use_fake_runner()
        self.assertIsNone(app._handle_voice_command("mamamia open calculator"))
        self.assertIsNone(app._handle_voice_command("grandmama open calculator"))
        self.assertIsNotNone(app._handle_voice_command("mama, open calculator"))

    def test_an_empty_wake_word_falls_back_to_the_built_in_ones(self):
        app = FakeApp(voice_commands=True, voice_command_wake="   ").use_fake_runner()
        self.assertIsNotNone(app._handle_voice_command("echo sub open calculator"))

    def test_it_says_so_when_the_wake_word_was_heard_but_the_command_was_not(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        self.assertIsNone(app._handle_voice_command("echo sub do something weird"))
        self.assertTrue(any("Not a command" in message and "do something weird" in message
                            for message in app.tray.messages), app.tray.messages)
        self.assertEqual(app.launched, [])

    def test_it_stays_quiet_when_nobody_said_the_wake_word(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        app._handle_voice_command("they were talking about the calculator")
        app._handle_voice_command("")
        self.assertEqual(app.tray.messages, [])

    def test_it_does_not_repeat_the_same_notice_for_every_caption(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        for _ in range(4):
            app._handle_voice_command("echo sub something it cannot do")
        self.assertEqual(len(app.tray.messages), 1, app.tray.messages)

    def test_a_recognized_command_says_nothing_about_not_understanding(self):
        app = FakeApp(voice_commands=True).use_fake_runner()
        app._handle_voice_command("echo sub open calculator")
        self.assertFalse(any("Not a command" in message for message in app.tray.messages))

    def test_a_command_can_be_spoken_into_the_microphone(self):
        app = FakeApp(voice_commands=True, mic_commands=True).use_fake_runner()
        self.assertIsNotNone(app._handle_voice_command("echo sub open calculator", source="mic"))
        self.assertEqual(app.launched, [voice_commands.APPS["calculator"]])

    def test_the_microphone_can_be_captioned_without_being_obeyed(self):
        app = FakeApp(voice_commands=True, mic_commands=False).use_fake_runner()
        self.assertIsNone(app._handle_voice_command("echo sub open calculator", source="mic"))
        self.assertEqual(app.launched, [])
        self.assertIsNotNone(app._handle_voice_command("echo sub open calculator", source="system"))

    def test_a_failure_is_reported_and_does_not_crash_the_app(self):
        app = FakeApp(voice_commands=True)
        app._voice_runner = voice_commands.CommandRunner(
            app_action=app._run_app_command,
            launcher=lambda app: (_ for _ in ()).throw(OSError("no such program")))
        self.assertIsNone(app._handle_voice_command("echo sub open calculator"))
        self.assertTrue(any("Could not run" in message for message in app.tray.messages))

    def test_only_finished_captions_can_run_a_command(self):
        """Live text is a guess; it must never reach the command handler."""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "echosub", "main.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        final = re.search(r"def _on_final\(.*?\n\n", source, re.S).group(0)
        partial = re.search(r"def _on_partial\(.*?\n\n", source, re.S).group(0)
        self.assertIn("_handle_voice_command", final)
        self.assertNotIn("_handle_voice_command", partial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
