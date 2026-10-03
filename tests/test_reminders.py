# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Reminders set by speaking: what is understood, what is refused, and that they come back."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import reminders, voice_commands  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])
NOW = datetime.datetime(2026, 10, 3, 14, 30, 0)


class DelayTest(unittest.TestCase):
    def minutes_away(self, said):
        when, _what = reminders.parse(said, NOW)
        return round((when - NOW).total_seconds() / 60)

    def test_a_number_written_out_or_in_digits(self):
        self.assertEqual(self.minutes_away("me in five minutes to think"), 5)
        self.assertEqual(self.minutes_away("me after 5 minutes to think"), 5)

    def test_hours_and_days(self):
        self.assertEqual(self.minutes_away("me in an hour to stretch"), 60)
        self.assertEqual(self.minutes_away("me in two hours to stretch"), 120)
        self.assertEqual(self.minutes_away("me in two days to pay"), 2 * 24 * 60)

    def test_half_and_a_quarter_of_an_hour(self):
        self.assertEqual(self.minutes_away("me in half an hour to drink water"), 30)
        self.assertEqual(self.minutes_away("me in a quarter of an hour to look"), 15)

    def test_arabic(self):
        said = "بعد خمس دقائق ان اشرب ماء"
        when, what = reminders.parse(said, NOW)
        self.assertEqual(round((when - NOW).total_seconds() / 60), 5)
        self.assertEqual(what, "اشرب ماء")

    def test_what_it_is_about_is_what_followed_to(self):
        _when, what = reminders.parse("me in five minutes to check the oven", NOW)
        self.assertEqual(what, "check the oven")

    def test_it_still_works_without_the_word_to(self):
        _when, what = reminders.parse("me in five minutes the oven", NOW)
        self.assertEqual(what, "the oven")


class ClockTest(unittest.TestCase):
    def at(self, said):
        when, _what = reminders.parse(said, NOW)
        return when

    def test_a_bare_hour_means_the_next_one_there_is(self):
        # At half past two, "at 5" is this afternoon, not tomorrow morning.
        self.assertEqual(self.at("me at 5 to leave"), NOW.replace(hour=17, minute=0))

    def test_minutes_and_the_24_hour_clock(self):
        self.assertEqual(self.at("me at 17:45 to leave"), NOW.replace(hour=17, minute=45))

    def test_am_and_pm_are_obeyed(self):
        self.assertEqual(self.at("me at 3 pm to join"), NOW.replace(hour=15, minute=0))
        self.assertEqual(self.at("me at 9 am to wake"),
                         NOW.replace(hour=9, minute=0) + datetime.timedelta(days=1))

    def test_tomorrow(self):
        self.assertEqual(self.at("me tomorrow at 9 to wake up"),
                         NOW.replace(hour=9, minute=0) + datetime.timedelta(days=1))
        self.assertEqual(self.at("me tomorrow to buy milk"),
                         NOW.replace(hour=9, minute=0) + datetime.timedelta(days=1))

    def test_an_impossible_time_is_refused(self):
        self.assertIsNone(reminders.parse("me at 99:99 to do it", NOW))


class RefusalTest(unittest.TestCase):
    def test_no_time_means_no_reminder(self):
        for said in ("me to buy milk", "me about the thing", "", "   "):
            with self.subTest(said=said):
                self.assertIsNone(reminders.parse(said, NOW), said)

    def test_a_delay_beyond_a_year_is_refused(self):
        self.assertIsNone(reminders.parse("me in 5000 days to do it", NOW))


class StoreTest(unittest.TestCase):
    def rows(self, *offsets):
        return [{"when": (NOW + datetime.timedelta(minutes=m)).isoformat(timespec="seconds"),
                 "what": f"thing {m}"} for m in offsets]

    def test_the_soonest_comes_first(self):
        kept = reminders.valid(self.rows(30, 5, 10))
        self.assertEqual([r["what"] for r in kept], ["thing 5", "thing 10", "thing 30"])

    def test_unreadable_rows_are_dropped(self):
        kept = reminders.valid([{"when": "not a time", "what": "x"}, "junk", None] + self.rows(5))
        self.assertEqual(len(kept), 1)

    def test_due_splits_past_from_future(self):
        ready, waiting = reminders.due(self.rows(-5, 10), NOW)
        self.assertEqual([r["what"] for r in ready], ["thing -5"])
        self.assertEqual([r["what"] for r in waiting], ["thing 10"])

    def test_the_list_is_capped(self):
        self.assertLessEqual(len(reminders.valid(self.rows(*range(200)))), reminders.MAX_REMINDERS)


class SpokenTest(unittest.TestCase):
    def test_it_is_recognized_as_a_command(self):
        command = voice_commands.find("echo sub remind me in five minutes to check the oven")
        self.assertEqual(command["action"], "reminder")
        self.assertEqual(command["what"], "check the oven")

    def test_without_a_time_it_is_not_a_command(self):
        self.assertIsNone(voice_commands.find("echo sub remind me to buy milk"))

    def test_the_runner_only_hands_it_back(self):
        launched, typed = [], []
        runner = voice_commands.CommandRunner(launcher=launched.append, typist=typed.append)
        command = voice_commands.find("echo sub remind me in five minutes to think")
        self.assertIn("Reminder", runner.run(command, now=0))
        self.assertEqual((launched, typed), ([], []))

    def test_a_forged_reminder_with_no_time_is_refused(self):
        runner = voice_commands.CommandRunner()
        forged = {"key": "set_reminder", "action": "reminder", "target": "whenever", "label": "x"}
        self.assertIsNone(runner.run(forged, now=0))


class AppTest(unittest.TestCase):
    def app(self):
        return FakeApp(voice_commands=True, voice_command_delay=0).use_fake_runner()

    def test_setting_one_keeps_it(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub remind me in five minutes to check the oven")
        kept = app_.cfg["reminders"]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["what"], "check the oven")
        self.assertTrue(app_.saved, "it must be written down, not only held in memory")

    def test_it_comes_back_when_it_is_due_and_then_is_gone(self):
        app_ = self.app()
        app_.cfg["reminders"] = [{"when": (NOW - datetime.timedelta(minutes=1)).isoformat(), "what": "drink"}]
        self.assertEqual(app_.check_reminders(NOW), 1)
        self.assertTrue(any("drink" in m for m in app_.tray.messages))
        self.assertEqual(app_.cfg["reminders"], [], "a reminder shown must not come back again")

    def test_one_that_is_not_due_waits(self):
        app_ = self.app()
        app_.cfg["reminders"] = [{"when": (NOW + datetime.timedelta(hours=1)).isoformat(), "what": "later"}]
        self.assertEqual(app_.check_reminders(NOW), 0)
        self.assertEqual(len(app_.cfg["reminders"]), 1)

    def test_one_that_fell_due_while_closed_still_arrives(self):
        app_ = self.app()
        app_.cfg["reminders"] = [{"when": (NOW - datetime.timedelta(days=2)).isoformat(), "what": "old"}]
        self.assertEqual(app_.check_reminders(NOW), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
