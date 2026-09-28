# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Tests for the lightweight disk recovery buffer without audio hardware."""
import os
import shutil
import sys
import tempfile
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import audio_backlog  # noqa: E402
from echosub.audio_backlog import DiskAudioBacklog  # noqa: E402


class DiskAudioBacklogTest(unittest.TestCase):
    def test_returns_audio_in_capture_order(self):
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1)
        try:
            backlog.append(np.array([1, 2, 3], dtype=np.float32))
            backlog.append(np.array([4, 5, 6, 7], dtype=np.float32))
            chunks = backlog.take()
            self.assertEqual(np.concatenate(chunks).tolist(), [1, 2, 3, 4, 5, 6, 7])
        finally:
            backlog.close()

    def test_discards_only_after_the_configured_recovery_window_is_full(self):
        backlog = DiskAudioBacklog(10, 2, segment_seconds=1)
        try:
            dropped = sum(backlog.append(np.ones(10, dtype=np.float32)) for _ in range(3))
            self.assertAlmostEqual(dropped, 1.0)
            self.assertEqual(sum(chunk.size for chunk in backlog.take()), 20)
        finally:
            backlog.close()


class SessionOnlyTest(unittest.TestCase):
    """The buffer is a recovery window, never a recording: it must not outlive the session."""

    def test_the_files_are_gone_after_close(self):
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1)
        backlog.append(np.ones(30, dtype=np.float32))
        directory = backlog._directory
        self.assertTrue(os.listdir(directory), "nothing was written to check")
        backlog.close()
        self.assertFalse(os.path.exists(directory), "the temporary folder survived the session")

    def test_reading_the_audio_deletes_it_as_it_goes(self):
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1)
        try:
            backlog.append(np.ones(40, dtype=np.float32))
            backlog.take()
            self.assertEqual(os.listdir(backlog._directory), [], "audio stayed on disk after it was read")
            self.assertTrue(backlog.empty())
        finally:
            backlog.close()

    def test_a_buffer_left_by_a_killed_session_is_cleaned_up(self):
        root = tempfile.mkdtemp()
        try:
            stale = os.path.join(root, audio_backlog.PREFIX + "old")
            fresh = os.path.join(root, audio_backlog.PREFIX + "running")
            other = os.path.join(root, "someone-elses-folder")
            for path in (stale, fresh, other):
                os.makedirs(path)
            old_time = time.time() - audio_backlog.STALE_AFTER_SEC - 60
            os.utime(stale, (old_time, old_time))
            removed = audio_backlog.remove_stale_directories(root)
            self.assertEqual(removed, [stale])
            self.assertTrue(os.path.exists(fresh), "a buffer of a running session was deleted")
            self.assertTrue(os.path.exists(other), "an unrelated folder was deleted")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ChosenDriveTest(unittest.TestCase):
    """The user can point the buffer at a fast drive; a drive that cannot be used must not break it."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_buffer_is_written_where_the_user_asked(self):
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1, directory=self.root)
        try:
            backlog.append(np.ones(30, dtype=np.float32))
            self.assertFalse(backlog.using_fallback)
            self.assertTrue(backlog.directory.startswith(self.root), backlog.directory)
            self.assertTrue(os.listdir(backlog.directory), "no audio was written to the chosen folder")
        finally:
            backlog.close()
        self.assertEqual(os.listdir(self.root), [], "the session folder was left on the user's drive")

    def test_a_folder_that_does_not_exist_yet_is_created(self):
        wanted = os.path.join(self.root, "echosub", "buffer")
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1, directory=wanted)
        try:
            self.assertFalse(backlog.using_fallback)
            self.assertTrue(backlog.directory.startswith(wanted))
        finally:
            backlog.close()

    def test_an_unusable_drive_falls_back_to_the_temp_folder(self):
        missing = os.path.join(self.root, "file-not-a-folder")
        with open(missing, "w", encoding="utf-8") as f:
            f.write("x")
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1, directory=missing)
        try:
            self.assertTrue(backlog.using_fallback, "an unusable folder was accepted")
            self.assertTrue(backlog.directory.startswith(tempfile.gettempdir()))
            backlog.append(np.ones(20, dtype=np.float32))
            self.assertEqual(sum(c.size for c in backlog.take()), 20, "audio was lost after the fallback")
        finally:
            backlog.close()

    def test_an_empty_setting_means_the_temp_folder(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                self.assertEqual(audio_backlog.usable_root(value), tempfile.gettempdir())

    def test_buffers_left_on_the_chosen_drive_are_cleaned_up(self):
        stale = os.path.join(self.root, audio_backlog.PREFIX + "old")
        os.makedirs(stale)
        old_time = time.time() - audio_backlog.STALE_AFTER_SEC - 60
        os.utime(stale, (old_time, old_time))
        backlog = DiskAudioBacklog(10, 10, segment_seconds=1, directory=self.root)
        try:
            self.assertFalse(os.path.exists(stale), "an old buffer was left on the user's drive")
        finally:
            backlog.close()
