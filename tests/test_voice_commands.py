# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Spoken commands: only the listed ones ever run, and only after the wake word.

EchoSub listens to whatever the PC plays, so these tests care most about what must *not* happen.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import config, voice_commands  # noqa: E402


class WakeWordTest(unittest.TestCase):
    def test_a_command_needs_the_wake_word_first(self):
        self.assertIsNone(voice_commands.find("open calculator"))
        self.assertIsNone(voice_commands.find("please open the calculator for me"))
        self.assertEqual(voice_commands.find("echo sub open calculator")["key"], "open_calculator")

    def test_the_wake_word_survives_punctuation_and_capitals(self):
        self.assertEqual(voice_commands.find("Echo Sub, open the calculator please!")["key"], "open_calculator")

    def test_the_command_must_follow_the_wake_word_closely(self):
        far = "echo sub " + "word " * voice_commands.MAX_WORDS_AFTER_WAKE + "open calculator"
        self.assertIsNone(voice_commands.find(far))

    def test_everyday_wordings_are_understood(self):
        for sentence, key in (
                ("echo sub please close the calculator now", "close_calculator"),
                ("echo sub can you open the calculator", "open_calculator"),
                ("echo sub start notepad", "open_notepad"),
                ("echo sub exit notepad", "close_notepad"),
                ("echo sub stop the captions", "pause_captions"),
                ("echo sub show the box", "show_captions")):
            with self.subTest(sentence=sentence):
                self.assertEqual(voice_commands.find(sentence)["key"], key)

    def test_an_app_word_without_an_action_does_nothing(self):
        self.assertIsNone(voice_commands.find("echo sub the calculator is on the table"))

    def test_arabic_commands_work(self):
        self.assertEqual(voice_commands.find("إيكو صب افتح الحاسبة")["key"], "open_calculator")
        self.assertEqual(voice_commands.find("ايكو صب أغلق الحاسبة")["key"], "close_calculator")

    def test_pc_is_a_built_in_wake_word_in_english_and_arabic(self):
        self.assertEqual(voice_commands.find("PC open calculator")["key"], "open_calculator")
        self.assertEqual(voice_commands.find("بي سي افتح الحاسبة")["key"], "open_calculator")

    def test_help_is_available_after_a_wake_word(self):
        self.assertEqual(voice_commands.find("alexa help")["key"], "voice_help")

    def test_a_short_wake_word_is_not_heard_inside_other_words(self):
        """Someone may pick a wake word as short as "da"; ordinary speech must not trigger it."""
        self.assertEqual(voice_commands.find("da open calculator", ("da",))["key"], "open_calculator")
        for sentence in ("today the calculator is open", "panda open calculator",
                         "I updated a calculator yesterday"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(voice_commands.find(sentence, ("da",)))

    def test_a_custom_wake_word_is_used(self):
        self.assertEqual(voice_commands.find("computer open notepad", ("computer",))["key"], "open_notepad")
        self.assertIsNone(voice_commands.find("computer open notepad", ("jarvis",)))

    def test_a_custom_phrase_only_maps_to_an_approved_action(self):
        custom = [{"phrase": "calculator please", "command": "open_calculator"}]
        found = voice_commands.find_detail("echo sub calculator please", custom_commands=custom)[0]
        self.assertEqual(found["key"], "open_calculator")
        unsafe = [{"phrase": "do it", "command": "open_terminal"}]
        self.assertIsNone(voice_commands.find_detail("echo sub do it", custom_commands=unsafe)[0])

    def test_key_presses_are_disabled_unless_explicitly_allowed(self):
        self.assertIsNone(voice_commands.find_detail("echo sub press a b c")[0])
        found = voice_commands.find_detail("echo sub press a b c", allow_key_presses=True)[0]
        self.assertEqual(found["target"], ("A", "B", "C"))
        self.assertIsNone(voice_commands.find_detail("echo sub press ctrl c", allow_key_presses=True)[0])

    def test_media_commands_accept_short_arabic_and_english_phrases(self):
        self.assertEqual(voice_commands.find("maya stop music", ("maya",))["key"], "media_stop")
        self.assertEqual(voice_commands.find("مايا ارفع الصوت", ("مايا",))["key"], "media_volume_up")
        self.assertEqual(voice_commands.find("maya next song", ("maya",))["key"], "media_next")

    def test_short_arabic_commands_control_echosub_without_hijacking_media(self):
        self.assertEqual(voice_commands.find("مايا وقف", ("مايا",))["key"], "pause_captions")
        self.assertEqual(voice_commands.find("مايا طفي", ("مايا",))["key"], "pause_captions")
        self.assertEqual(voice_commands.find("مايا اشتغل", ("مايا",))["key"], "resume_captions")
        self.assertEqual(voice_commands.find("مايا وقف الموسيقى", ("مايا",))["key"], "media_stop")


class OtherLanguagesTest(unittest.TestCase):
    """EchoSub captions about a hundred languages, so it should take commands in them too."""

    SENTENCES = {
        "echo sub ouvre la calculatrice": "open_calculator",          # French
        "echo sub ferme la calculatrice": "close_calculator",
        "echo sub abre la calculadora": "open_calculator",            # Spanish
        "echo sub cierra el bloc de notas": "close_notepad",
        "echo sub öffne den rechner": "open_calculator",              # German
        "echo sub schließe den rechner": "close_calculator",
        "echo sub apri la calcolatrice": "open_calculator",           # Italian
        "echo sub abra a calculadora": "open_calculator",             # Portuguese
        "echo sub hesap makinesini kapat": "close_calculator",        # Turkish (with its endings)
        "echo sub открой калькулятор": "open_calculator",             # Russian
        "echo sub закрой блокнот": "close_notepad",
        "echo sub باز کن ماشین حساب": "open_calculator",               # Persian
        "echo sub कैलकुलेटर खोलो": "open_calculator",                    # Hindi
        "echo sub buka kalkulator": "open_calculator",                # Indonesian
        "echo sub 打开计算器": "open_calculator",                        # Chinese, written without spaces
        "echo sub 关闭记事本": "close_notepad",
        "echo sub 電卓を開いて": "open_calculator",                       # Japanese
        "echo sub 계산기 열어": "open_calculator",                        # Korean
        "echo sub arrête les sous-titres": "pause_captions",          # caption controls
        "echo sub oculta los subtítulos": "hide_captions",
        "echo sub altyazıları duraklat": "pause_captions",
        "echo sub останови субтитры": "pause_captions",
        "echo sub 暂停字幕": "pause_captions",
        "echo sub 자막 숨겨": "hide_captions",
        "echo sub اخف الترجمات": "hide_captions",
    }

    def test_commands_in_other_languages(self):
        for sentence, key in self.SENTENCES.items():
            with self.subTest(sentence=sentence):
                found = voice_commands.find(sentence)
                self.assertIsNotNone(found, f"not understood: {sentence}")
                self.assertEqual(found["key"], key)

    def test_a_word_that_merely_starts_like_a_command_word_is_ignored(self):
        self.assertIsNone(voice_commands.find("echo sub calcium is important for bones"))
        self.assertIsNone(voice_commands.find("echo sub the calculation was wrong"))

    def test_a_language_is_not_mixed_up_with_an_action(self):
        self.assertIsNone(voice_commands.find("echo sub the subtitles are in French"))


class HarmlessOnlyTest(unittest.TestCase):
    """Anything outside the list must be ignored, even after the wake word."""

    HARMFUL = [
        "echo sub shut down the computer", "echo sub restart windows", "echo sub log off",
        "echo sub delete all files", "echo sub delete my documents", "echo sub format c",
        "echo sub open command prompt", "echo sub open cmd", "echo sub open powershell",
        "echo sub run rm -rf /", "echo sub install this program", "echo sub disable the firewall",
        "echo sub open regedit", "echo sub send the file to john", "echo sub empty the recycle bin",
        "echo sub turn off windows defender", "echo sub open my bank account", "echo sub type my password",
    ]

    def test_harmful_commands_are_not_recognized(self):
        for sentence in self.HARMFUL:
            with self.subTest(sentence=sentence):
                self.assertIsNone(voice_commands.find(sentence))

    def test_the_list_holds_only_harmless_actions(self):
        # "press_enter" is the one action here that reaches outside EchoSub, and it is deliberate:
        # typed text may never contain a new line, so pressing Enter has to be asked for by name.
        # It is unreachable unless typing is switched on, which the tests below hold it to.
        for command in voice_commands.COMMANDS:
            with self.subTest(command=command["key"]):
                self.assertIn(command["action"],
                              ("open_app", "close_app", "app", "help", "media", "open_link", "press_enter"))
                if command["action"] in ("open_app", "close_app"):
                    self.assertIn(command["target"], voice_commands.APPS)

    def test_typing_and_enter_do_nothing_until_they_are_switched_on(self):
        for sentence in ("echo sub type my password", "echo sub type hello there", "echo sub press enter"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(voice_commands.find(sentence), "typing is off by default")
                self.assertIsNotNone(voice_commands.find(sentence, allow_typing=True), sentence)

    def test_the_apps_are_everyday_ones_with_no_way_to_run_anything_else(self):
        """Opening an app is harmless; a terminal or a registry editor is not, and must stay out."""
        forbidden = {"cmd", "command prompt", "powershell", "terminal", "regedit", "registry editor",
                     "control panel", "services", "wmic", "python", "explorer.exe /select"}
        self.assertTrue(set(voice_commands.APPS).isdisjoint(forbidden))
        for name, app in voice_commands.APPS.items():
            with self.subTest(app=name):
                self.assertNotIn(app["launch"].lower(),
                                 {"cmd.exe", "powershell.exe", "wt.exe", "regedit.exe", "wmic.exe"})
                self.assertIn(app["close"], ("polite", "force"))
                self.assertTrue(app["words"], f"{name} has no words to say")

    def test_apps_that_can_hold_unsaved_work_are_never_forced_shut(self):
        for name in ("notepad", "paint", "chrome", "edge", "vs code", "character map"):
            with self.subTest(app=name):
                self.assertEqual(voice_commands.APPS[name]["close"], "polite")

    def test_closing_file_explorer_leaves_the_desktop_alone(self):
        """The desktop and the taskbar are windows of Explorer too, so only folders may be closed."""
        self.assertTrue(voice_commands.APPS["files"].get("window_classes"))

    def test_every_app_can_be_opened_and_closed_by_voice(self):
        keys = {command["key"] for command in voice_commands.COMMANDS}
        for name in voice_commands.APPS:
            with self.subTest(app=name):
                self.assertIn(f"open_{name}", keys)
                self.assertIn(f"close_{name}", keys)

    def test_a_program_outside_the_list_is_refused(self):
        with self.assertRaises(ValueError):
            voice_commands.start_program({"launch": "cmd.exe", "processes": ("cmd.exe",), "close": "force"})
        with self.assertRaises(ValueError):
            voice_commands.close_program({"launch": "cmd.exe", "processes": ("cmd.exe",), "close": "force"})

    def test_an_app_that_is_not_installed_is_reported_and_not_guessed_at(self):
        nowhere = dict(voice_commands.APPS["firefox"], launch="this-program-does-not-exist.exe", paths=())
        voice_commands.APPS["__test__"] = nowhere
        try:
            with self.assertRaises(voice_commands.AppNotInstalled):
                voice_commands.start_program(nowhere)
        finally:
            del voice_commands.APPS["__test__"]


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.launched, self.closed, self.app_calls = [], [], []
        self.runner = voice_commands.CommandRunner(
            app_action=lambda target: self.app_calls.append(target) or True,
            launcher=self.launched.append,
            closer=lambda names, mode: self.closed.append((names, mode)) or True)

    def command(self, key):
        return voice_commands.command(key)

    def test_opening_and_closing_use_the_entries_from_the_list(self):
        self.runner.run(self.command("open_calculator"), now=0)
        self.runner.run(self.command("close_notepad"), now=10)
        self.assertEqual(self.launched, [voice_commands.APPS["calculator"]])
        self.assertEqual(self.closed, [(voice_commands.APPS["notepad"], "polite")])

    def test_an_app_that_is_not_installed_tells_the_user(self):
        def launcher(app):
            raise voice_commands.AppNotInstalled(app["launch"])

        runner = voice_commands.CommandRunner(launcher=launcher)
        self.assertEqual(runner.run(self.command("open_firefox"), now=0),
                         "Firefox is not installed on this PC")

    def test_closing_says_so_when_the_app_was_not_open(self):
        runner = voice_commands.CommandRunner(closer=lambda names, mode: False)
        self.assertEqual(runner.run(self.command("close_calculator"), now=0), "Calculator was not open")

    def test_echosub_commands_go_through_the_app(self):
        message = self.runner.run(self.command("pause_captions"), now=0)
        self.assertEqual(self.app_calls, ["pause"])
        self.assertEqual(message, "Captions paused")

    def test_the_same_command_is_not_repeated_immediately(self):
        self.assertTrue(self.runner.run(self.command("open_calculator"), now=100))
        self.assertIsNone(self.runner.run(self.command("open_calculator"), now=101),
                          "a repeated caption ran the command twice")
        self.assertTrue(self.runner.run(self.command("open_calculator"),
                                        now=101 + voice_commands.REPEAT_COOLDOWN_SEC))
        self.assertEqual(self.launched, [voice_commands.APPS["calculator"]] * 2)

    def test_a_command_that_is_not_on_the_list_is_refused(self):
        forged = {"key": "wipe_disk", "action": "open_app", "target": "calculator", "label": "x"}
        self.assertIsNone(self.runner.run(forged, now=0))
        self.assertEqual(self.launched, [])

    def test_a_safe_key_sequence_uses_the_injected_key_presser(self):
        pressed = []
        runner = voice_commands.CommandRunner(key_presser=lambda keys: pressed.extend(keys))
        command = voice_commands.find_detail("echo sub press a 2", allow_key_presses=True)[0]
        self.assertEqual(runner.run(command, now=0), "Pressed A 2")
        self.assertEqual(pressed, ["A", "2"])

    def test_media_commands_use_the_injected_media_controller(self):
        media = []
        runner = voice_commands.CommandRunner(media_controller=media.append)
        command = voice_commands.find("echo sub next song")
        self.assertEqual(runner.run(command, now=0), "Next track")
        self.assertEqual(media, ["next"])


class SettingsTest(unittest.TestCase):
    def test_voice_commands_are_off_until_the_user_turns_them_on(self):
        self.assertFalse(config.DEFAULTS["voice_commands"])

    def test_there_is_a_default_wake_word(self):
        self.assertTrue(config.DEFAULTS["voice_command_wake"].strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
