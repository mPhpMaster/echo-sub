# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""How big the language label is, and the dot that keeps it apart from the caption."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import config  # noqa: E402
from echosub.caption_widgets import Badge, LABEL_SIZE_MAX, LABEL_SIZE_MIN  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def badge(**options):
    font = QFont()
    font.setPointSizeF(20)
    options.setdefault("position", "before")
    position = options.pop("position")
    return Badge("en", options.pop("kind", "flag_name"), position, font, prominent=True, **options)


class SizeTest(unittest.TestCase):
    def test_bigger_means_a_bigger_font_and_flag(self):
        normal, big = badge(), badge(size=1.6)
        self.assertGreater(big.font.pointSizeF(), normal.font.pointSizeF())
        self.assertGreater(big.flag_height, normal.flag_height, "the flag should grow with the name")
        self.assertGreater(big.width, normal.width)

    def test_smaller_means_smaller(self):
        self.assertLess(badge(size=0.5).font.pointSizeF(), badge().font.pointSizeF())

    def test_the_size_is_kept_within_sensible_limits(self):
        self.assertAlmostEqual(badge(size=99).font.pointSizeF(), badge(size=LABEL_SIZE_MAX).font.pointSizeF())
        self.assertAlmostEqual(badge(size=0.01).font.pointSizeF(), badge(size=LABEL_SIZE_MIN).font.pointSizeF())

    def test_the_settings_keep_each_size_separately(self):
        cfg = dict(config.DEFAULTS, original_label_size=150, translation_label_size=70)
        values = SettingsDialog(cfg).values()
        self.assertEqual((values["original_label_size"], values["translation_label_size"]), (150, 70))


class DotTest(unittest.TestCase):
    def test_it_faces_the_words_in_english(self):
        self.assertEqual(badge(position="before").dot_side, "right")
        self.assertEqual(badge(position="after").dot_side, "left")

    def test_and_the_other_way_round_in_arabic(self):
        self.assertEqual(badge(position="before", rtl=True).dot_side, "left")
        self.assertEqual(badge(position="after", rtl=True).dot_side, "right")

    def test_a_label_above_or_below_needs_none(self):
        self.assertIsNone(badge(position="above").dot_side)
        self.assertIsNone(badge(position="below").dot_side)

    def test_it_can_be_switched_off(self):
        self.assertIsNone(badge(separator=False).dot_side)
        self.assertEqual(badge(separator=False).pieces, ["flag", "text"])

    def test_it_never_becomes_part_of_the_label_text(self):
        self.assertEqual(badge().text, "English", "the dot is drawn beside the name, not added to it")

    def test_it_takes_room_so_nothing_overlaps(self):
        self.assertGreater(badge().width, badge(separator=False).width)

    def test_a_flag_on_its_own_still_gets_one(self):
        only_flag = badge(kind="flag")
        self.assertEqual(only_flag.pieces, ["flag", "dot"])

    def test_it_is_on_unless_switched_off(self):
        self.assertTrue(config.DEFAULTS["label_separator"])
        self.assertTrue(SettingsDialog(dict(config.DEFAULTS)).values()["label_separator"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
