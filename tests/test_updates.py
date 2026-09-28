# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Unit tests for release comparison without contacting GitHub."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import update_ui, updates  # noqa: E402


class UpdateCheckTest(unittest.TestCase):
    def test_detects_a_newer_windows_installer(self):
        update = updates.update_from_release({
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/mPhpMaster/echo-sub/releases/tag/v1.2.0",
            "assets": [{"name": "EchoSub-Setup-1.2.0.exe", "browser_download_url": "https://example.test/setup.exe"}],
        }, "1.0.7")
        self.assertEqual(update.version, "1.2.0")
        self.assertEqual(update.download_url, "https://example.test/setup.exe")

    def test_does_not_offer_the_current_or_an_older_release(self):
        self.assertIsNone(updates.update_from_release({"tag_name": "v1.0.7"}, "1.0.7"))
        self.assertIsNone(updates.update_from_release({"tag_name": "v1.0.6"}, "1.0.7"))

    def test_uses_the_release_page_when_an_installer_is_not_attached(self):
        update = updates.update_from_release({
            "tag_name": "1.1.0", "html_url": "https://example.test/release", "assets": [],
        }, "1.0.7")
        self.assertEqual(update.download_url, "https://example.test/release")

    def test_version_comparison_handles_short_versions(self):
        self.assertTrue(updates.is_newer("1.1", "1.0.9"))
        self.assertFalse(updates.is_newer("1.0", "1.0.0"))


class DailyCheckTest(unittest.TestCase):
    """The automatic check runs once a day and never blocks the interface."""

    def test_it_is_due_when_it_has_never_run(self):
        self.assertTrue(update_ui.is_due(0, now=1000))
        self.assertTrue(update_ui.is_due(None, now=1000))
        self.assertTrue(update_ui.is_due("not a time", now=1000))

    def test_it_is_not_due_again_on_the_same_day(self):
        now = 1_000_000
        self.assertFalse(update_ui.is_due(now - 3600, now=now))
        self.assertTrue(update_ui.is_due(now - update_ui.CHECK_INTERVAL_SEC - 1, now=now))

    def test_a_clock_set_backwards_does_not_block_checks_for_ever(self):
        now = 1_000_000
        self.assertTrue(update_ui.is_due(now + 99999, now=now))

    def test_the_first_check_waits_until_the_app_has_started(self):
        self.assertGreaterEqual(update_ui.FIRST_CHECK_DELAY_MS, 3000)
