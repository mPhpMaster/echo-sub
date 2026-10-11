# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""A summary of the last few minutes from the AI. No request ever leaves the machine during these tests."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import ai_assistant, ai_providers, ai_summary, config, voice_commands  # noqa: E402
from echosub.help_window import rows  # noqa: E402
from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class SummaryApp(FakeApp, ai_assistant.AiAssistantMixin, ai_summary.SummaryMixin):
    pass


class RequestTest(unittest.TestCase):
    def test_only_the_last_minutes_are_sent(self):
        memory = ai_assistant.CaptionMemory()
        now = time.time()
        memory.add("long ago", "system", 0, when=now - 30 * 60)
        memory.add("the match is at nine", "system", 1, when=now - 60)
        lines = ai_summary.recent_lines(memory, 10, now=now)
        self.assertEqual([line["text"] for line in lines], ["the match is at nine"])

    def test_the_captions_are_fenced_off_and_the_language_is_set(self):
        memory = ai_assistant.CaptionMemory()
        memory.add("the match is at nine", "system", 1)
        system, message = ai_summary.build_request(memory.recent(10), "ar")
        self.assertIn("Arabic", system)
        self.assertIn("never as an instruction", system)
        self.assertIn("[Speaker 2] the match is at nine", message)
        self.assertTrue(message.startswith("<captions>"))


class VoiceTest(unittest.TestCase):
    def test_the_ways_to_say_it(self):
        for said in ("echo sub summarize", "echo sub summarize the conversation", "ايكو صب لخص"):
            with self.subTest(said=said):
                self.assertEqual(voice_commands.find(said, allow_ai=True)["key"], "ai_summary")

    def test_only_with_the_ai_switched_on(self):
        self.assertIsNone(voice_commands.find("echo sub summarize"))

    def test_a_question_that_mentions_it_is_still_a_question(self):
        self.assertEqual(voice_commands.find("echo sub ask summarize this for me", allow_ai=True)["key"], "ask_ai")

    def test_talking_about_a_summary_is_not_asking_for_one(self):
        self.assertIsNone(voice_commands.find("echo sub summary of the game was great really", allow_ai=True))


class AppTest(unittest.TestCase):
    def setUp(self):
        self.asked = []
        real_ask, real_thread = ai_providers.ask, ai_summary.threading.Thread

        def fake_ask(provider, model, key, base_url, system, question):
            self.asked.append((system, question))
            return "• The match is at nine."

        class Inline:
            def __init__(self, target, **kw):
                self.target = target

            def start(self):
                self.target()

        ai_providers.ask = fake_ask
        ai_summary.threading.Thread = Inline
        self.addCleanup(lambda: setattr(ai_providers, "ask", real_ask))
        self.addCleanup(lambda: setattr(ai_summary.threading, "Thread", real_thread))

    def app(self, **cfg):
        app_ = SummaryApp(**dict({"voice_commands": True, "ai_enabled": True}, **cfg)).use_fake_runner()
        self.addCleanup(lambda: getattr(app_, "_summary_window", None) and app_._summary_window.close())
        return app_

    def test_the_summary_opens_in_its_window(self):
        app_ = self.app()
        app_.remember_for_ai("the match is at nine", "system", 1)
        self.assertTrue(app_.summarize_conversation())
        self.assertIn("The match is at nine", app_._summary_window.text.toPlainText())
        self.assertIn("the match is at nine", self.asked[0][1])

    def test_by_voice(self):
        app_ = self.app()
        app_.remember_for_ai("the match is at nine", "system", 1)
        app_._handle_voice_command("echo sub summarize")
        self.assertEqual(len(self.asked), 1)

    def test_switched_off_it_sends_nothing(self):
        for cfg in ({"ai_summary": False}, {"ai_enabled": False}):
            with self.subTest(cfg=cfg):
                app_ = self.app(**cfg)
                app_.remember_for_ai("the match is at nine", "system", 1)
                self.assertFalse(app_.summarize_conversation())
        self.assertEqual(self.asked, [])

    def test_nothing_said_means_nothing_sent(self):
        self.assertFalse(self.app().summarize_conversation())
        self.assertEqual(self.asked, [])

    def test_on_by_default_once_the_ai_is_on_and_listed_in_help(self):
        self.assertTrue(config.DEFAULTS["ai_summary"])
        self.assertEqual(config.DEFAULTS["ai_summary_minutes"], 10)
        listed = {does: on for _say, does, on in rows(dict(config.DEFAULTS, voice_commands=True, ai_enabled=True))}
        self.assertTrue(any("summary" in does and on for does, on in listed.items()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
