# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The reminders list in the settings, and the alert that is hard to miss."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from echosub import config, reminder_alert, reminders, voice_commands  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])
NOW = datetime.datetime(2026, 10, 3, 14, 30, 0)
SOON = (NOW + datetime.timedelta(hours=2)).isoformat(timespec="seconds")
PAST = (NOW - datetime.timedelta(hours=2)).isoformat(timespec="seconds")
BOTH = [{"when": SOON, "what": "water the plants"},
        {"when": PAST, "what": "take the bread out", "done": PAST}]


class ListTest(unittest.TestCase):
    def dialog(self, rows=BOTH):
        dialog = SettingsDialog(dict(config.DEFAULTS, reminders=rows))
        self.addCleanup(dialog.close)
        return dialog

    def test_both_the_waiting_and_the_finished_are_listed(self):
        table = self.dialog().reminder_table
        self.assertEqual(table.rowCount(), 2)
        shown = {table.item(row, 1).text(): table.item(row, 2).text() for row in range(2)}
        self.assertEqual(shown, {"take the bread out": "Done", "water the plants": "Waiting"})

    def test_they_survive_being_opened_and_saved(self):
        self.assertEqual(self.dialog().values()["reminders"], reminders.valid(BOTH))

    def test_the_words_can_be_changed(self):
        from PySide6.QtWidgets import QTableWidgetItem

        dialog = self.dialog()
        row = [r for r in range(2) if dialog.reminder_table.item(r, 2).text() == "Waiting"][0]
        dialog.reminder_table.setItem(row, 1, QTableWidgetItem("water the garden"))
        self.assertIn("water the garden", [e["what"] for e in dialog.values()["reminders"]])

    def test_the_time_can_be_changed(self):
        from PySide6.QtCore import QDateTime

        dialog = self.dialog()
        row = [r for r in range(2) if dialog.reminder_table.item(r, 2).text() == "Waiting"][0]
        later = NOW + datetime.timedelta(days=3)
        dialog.reminder_table.cellWidget(row, 0).setDateTime(QDateTime(later))
        kept = [e for e in dialog.values()["reminders"] if e["what"] == "water the plants"][0]
        self.assertEqual(datetime.datetime.fromisoformat(kept["when"]), later)

    def test_a_finished_one_cannot_be_retimed(self):
        dialog = self.dialog()
        row = [r for r in range(2) if dialog.reminder_table.item(r, 2).text() == "Done"][0]
        self.assertFalse(dialog.reminder_table.cellWidget(row, 0).isEnabled())

    def test_one_can_be_added_by_hand(self):
        dialog = self.dialog([])
        dialog._add_reminder()
        from PySide6.QtWidgets import QTableWidgetItem

        dialog.reminder_table.setItem(0, 1, QTableWidgetItem("call the dentist"))
        kept = dialog.values()["reminders"]
        self.assertEqual([e["what"] for e in kept], ["call the dentist"])
        self.assertNotIn("done", kept[0], "a new one is waiting, not finished")

    def test_one_can_be_removed(self):
        dialog = self.dialog()
        dialog.reminder_table.selectRow(0)
        dialog._remove_reminder()
        self.assertEqual(len(dialog.values()["reminders"]), 1)

    def test_the_finished_ones_can_be_cleared_in_one_go(self):
        dialog = self.dialog()
        dialog._clear_finished_reminders()
        kept = dialog.values()["reminders"]
        self.assertEqual([e["what"] for e in kept], ["water the plants"])

    def test_there_is_a_tab_for_them(self):
        tabs = self.dialog().findChild(QTabWidget)
        self.assertIn("Reminders", [tabs.tabText(i) for i in range(tabs.count())])


class SpokenTest(unittest.TestCase):
    def test_asking_for_the_list_is_a_command(self):
        for said in ("echo sub my reminders", "echo sub show my reminders", "echo sub list reminders",
                     "echo sub تذكيراتي"):
            with self.subTest(said=said):
                command = voice_commands.find(said)
                self.assertIsNotNone(command, said)
                self.assertEqual(command["key"], "show_reminders", said)

    def test_setting_one_is_still_setting_one(self):
        command = voice_commands.find("echo sub remind me in five minutes to think")
        self.assertEqual(command["action"], "reminder")

    def test_the_app_opens_the_settings_at_that_tab(self):
        app_ = FakeApp(voice_commands=True, voice_command_delay=0).use_fake_runner()
        opened = []
        app_._open_settings = lambda show_tab=None, **kw: opened.append(show_tab)
        app_._handle_voice_command("echo sub show my reminders")
        self.assertEqual(opened, ["Reminders"])


class AlertTest(unittest.TestCase):
    def alert(self, what="take the bread out"):
        alert = reminder_alert.ReminderAlert(what)
        self.addCleanup(alert.close)
        return alert

    def test_it_says_what_the_reminder_was(self):
        self.assertEqual(self.alert().message.text(), "take the bread out")

    def test_it_is_large_and_stays_in_front(self):
        from PySide6.QtCore import Qt

        alert = self.alert()
        self.assertTrue(alert.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertGreater(alert.message.font().pointSizeF(), alert.font().pointSizeF())

    def test_done_closes_it_and_says_so(self):
        alert = self.alert()
        answered = []
        alert.dismissed.connect(lambda: answered.append(True))
        alert._dismiss()
        self.assertEqual(answered, [True])
        self.assertFalse(alert.isVisible())

    def test_snoozing_asks_for_it_again_later(self):
        alert = self.alert()
        minutes = []
        alert.snoozed.connect(minutes.append)
        alert._snooze()
        self.assertEqual(minutes, [reminder_alert.SNOOZE_MINUTES])

    def test_an_empty_reminder_still_says_something(self):
        self.assertEqual(self.alert("").message.text(), "Reminder")

    def test_the_app_snoozes_by_setting_another_one(self):
        app_ = FakeApp(voice_commands=True).use_fake_runner()
        app_.cfg["reminders"] = []
        app_._snooze_reminder("drink water", 5)
        kept = reminders.waiting(app_.cfg["reminders"])
        self.assertEqual([e["what"] for e in kept], ["drink water"])
        self.assertGreater(datetime.datetime.fromisoformat(kept[0]["when"]), datetime.datetime.now())


if __name__ == "__main__":
    unittest.main(verbosity=2)
