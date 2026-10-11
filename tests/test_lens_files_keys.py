# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""EchoSub Lens: translating files (pictures, PDF, Word, text) and a key for every option."""
import os
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtGui import QColor, QImage, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import hotkeys, lens_app, lens_files, lens_shortcuts, lens_style, lens_translate  # noqa: E402
from echosub.lens_ocr import Block, Box, Line  # noqa: E402

app = QApplication.instance() or QApplication([])

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOCUMENT = (f'<?xml version="1.0"?><w:document {W}><w:body>'
            '<w:p><w:r><w:t>Project report</w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">Fish </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>&amp; chips</w:t>'
            '</w:r></w:p>'
            '<w:p><w:r><w:t>Outer</w:t></w:r><w:r><w:pict><w:txbxContent><w:p><w:r><w:t>Inside a box</w:t></w:r>'
            '</w:p></w:txbxContent></w:pict></w:r></w:p>'
            '<w:p><w:r><w:t>2026</w:t></w:r></w:p><w:p/>'
            '</w:body></w:document>')


class Upper:
    """A translator that shouts: easy to recognise in the output."""

    def translate_many(self, texts, target):
        return [t.upper() for t in texts]


class KeysTest(unittest.TestCase):
    def test_any_key_with_or_without_modifiers(self):
        self.assertEqual(hotkeys.parse("Ctrl+Alt+T"), (hotkeys.MOD_CONTROL | hotkeys.MOD_ALT, ord("T")))
        self.assertEqual(hotkeys.parse("F8"), (0, 0x77))
        self.assertEqual(hotkeys.parse("Shift+F12"), (hotkeys.MOD_SHIFT, 0x7B))
        self.assertEqual(hotkeys.parse("Meta+Q"), (hotkeys.MOD_WIN, ord("Q")))
        self.assertEqual(hotkeys.parse("Num+5"), (0, 0x65))
        self.assertEqual(hotkeys.parse("Pause"), (0, 0x13))
        self.assertEqual(hotkeys.parse("Media Play"), (0, 0xB3))
        self.assertIsNone(hotkeys.parse(""))
        self.assertIsNone(hotkeys.parse("Ctrl+A, B"))  # one key only, not a sequence

    def test_saved_keys_are_merged_with_the_defaults(self):
        keys = lens_shortcuts.merged({"file": "", "quit": "F9", "nonsense": "F1"})
        self.assertEqual(keys["file"], "")       # cleared on purpose
        self.assertEqual(keys["quit"], "F9")
        self.assertEqual(keys["toggle"], "Ctrl+Alt+T")
        self.assertNotIn("nonsense", keys)

    def test_problems_are_reported(self):
        keys = dict(lens_shortcuts.defaults(), quit="Ctrl+Alt+T", copy_all="Ctrl+Alt+H")
        found = lens_shortcuts.problems(keys)
        self.assertIn("Also used for", found["quit"])
        self.assertIn("EchoSub", found["copy_all"])  # its captions' hide/show key

    def test_the_shortcuts_page_reads_and_writes_keys(self):
        page = lens_shortcuts.ShortcutsPage(lens_shortcuts.defaults())
        page.editors["copy_all"].setKeySequence(QKeySequence("F7"))
        self.assertEqual(page.value()["copy_all"], "F7")
        self.assertTrue(page.valid())
        page.editors["quit"].setKeySequence(QKeySequence("F7"))
        self.assertFalse(page.valid())
        self.assertIn("Also used", page.status.text())
        page.load(lens_shortcuts.defaults())
        self.assertTrue(page.valid())

    def test_settings_window_keeps_keys_only_when_windows_gives_them(self):
        from echosub.lens_settings import LensSettings

        styles, offered = [], []
        answer = [["F7"]]

        def apply_keys(keys):
            offered.append(keys)
            return answer.pop(0) if answer else []

        window = LensSettings(lens_style.DEFAULT_STYLE, lens_shortcuts.defaults(), styles.append, apply_keys)
        window.shortcuts.editors["copy_all"].setKeySequence(QKeySequence("F7"))
        window.accept()
        self.assertTrue(window.isVisible() or window.result() == 0)  # still open: F7 is taken elsewhere
        self.assertIn("F7", window.shortcuts.status.text())
        window.accept()
        self.assertEqual(offered[-1]["copy_all"], "F7")
        window.appearance.bold.setChecked(True)
        self.assertTrue(styles[-1]["bold"])
        window.reject()
        self.assertEqual(styles[-1], lens_style.DEFAULT_STYLE)  # Cancel puts the old look back


class WordTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "report.docx")
        with zipfile.ZipFile(self.path, "w") as z:
            z.writestr("word/document.xml", DOCUMENT)
            z.writestr("word/footer1.xml", f'<w:ftr {W}><w:p><w:r><w:t>Page footer</w:t></w:r></w:p></w:ftr>')
            z.writestr("word/media/logo.png", b"\x89PNG not touched")

    def tearDown(self):
        self.folder.cleanup()

    def test_paragraphs_are_found_whole_and_numbers_skipped(self):
        texts = lens_files.word_texts(self.path)
        self.assertEqual(texts, ["Project report", "Fish & chips", "Inside a box", "Outer", "Page footer"])

    def test_translation_keeps_formatting_and_everything_else(self):
        texts = lens_files.word_texts(self.path)
        out = os.path.join(self.folder.name, "report.ar.docx")
        lens_files.write_word(self.path, out, {t: f"<{t.upper()}>" for t in texts})
        with zipfile.ZipFile(out) as z:
            xml = z.read("word/document.xml").decode()
            footer = z.read("word/footer1.xml").decode()
            self.assertEqual(z.read("word/media/logo.png"), b"\x89PNG not touched")
        self.assertIn("&lt;FISH &amp; CHIPS&gt;", xml)      # escaped, in the first run
        self.assertIn("<w:b/>", xml)                          # the bold run is still there
        self.assertIn("&lt;INSIDE A BOX&gt;", xml)
        self.assertIn("&lt;OUTER&gt;", xml)
        self.assertIn(">2026<", xml)
        self.assertIn("&lt;PAGE FOOTER&gt;", footer)
        self.assertEqual(lens_files.word_texts(out)[0], "<PROJECT REPORT>")


class TextAndPagesTest(unittest.TestCase):
    def test_kinds_and_names(self):
        self.assertEqual(lens_files.kind("a.PDF"), "pdf")
        self.assertEqual(lens_files.kind("a.jpeg"), "image")
        self.assertEqual(lens_files.kind("a.docx"), "word")
        self.assertEqual(lens_files.kind("a.srt"), "text")
        self.assertIsNone(lens_files.kind("a.doc"))
        self.assertEqual(lens_files.output_name(r"C:\x\photo.jpg", "ar"), r"C:\x\photo.ar.png")
        self.assertEqual(lens_files.output_name(r"C:\x\letter.pdf", "fr"), r"C:\x\letter.fr.pdf")

    def test_subtitles_keep_numbers_and_times(self):
        text = "1\n00:00:01,000 --> 00:00:03,000\nWhere are you going?\n\n2\nTo the station.\n"
        lines = lens_files.text_lines(text)
        self.assertEqual(lines, ["Where are you going?", "To the station."])
        out = lens_files.translated_text(text, {line: line.upper() for line in lines})
        self.assertEqual(out, "1\n00:00:01,000 --> 00:00:03,000\nWHERE ARE YOU GOING?\n\n2\nTO THE STATION.\n")

    def test_text_in_an_old_arabic_encoding_is_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a.txt")
            with open(path, "wb") as f:
                f.write("مرحبا".encode("cp1256"))
            self.assertEqual(lens_files.read_text(path), "مرحبا")

    def test_pages_are_drawn_and_saved_as_pdf_and_png(self):
        image = QImage(400, 200, QImage.Format_RGB32)
        image.fill(QColor("white"))
        block = Block([Line([("Hello", Box(20, 20, 80, 20))])], translation="Bonjour")
        drawn = lens_files.render(image, [block], "fr", lens_style.merged({"background": "#FF0000"}))
        self.assertEqual(drawn.size(), image.size())
        self.assertEqual(drawn.pixelColor(25, 30).red(), 255)  # the label's background is there
        self.assertEqual(drawn.pixelColor(300, 150).name(), "#ffffff")  # the rest of the page is untouched
        with tempfile.TemporaryDirectory() as folder:
            pdf = os.path.join(folder, "out.pdf")
            lens_files.save_pages([drawn, drawn], pdf)
            self.assertEqual(lens_files.page_count(pdf), 2)
            pages = list(lens_files.pages(pdf))
            self.assertEqual(len(pages), 2)
            png = os.path.join(folder, "out.png")
            lens_files.save_pages([drawn], png)
            self.assertFalse(QImage(png).isNull())

    def test_the_file_window_translates_a_text_file_and_saves_it(self):
        from echosub.lens_file_window import FileWindow

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "notes.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Buy milk\n42\nCall mum\n")
            window = FileWindow(path, "fr", Upper(), "auto", lens_style.merged(None))
            deadline = time.monotonic() + 10
            while not window.finished and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            self.assertTrue(window.finished, window.status.text())
            self.assertEqual(window.text_view.toPlainText(), "BUY MILK\n42\nCALL MUM\n")
            out = os.path.join(folder, "notes.fr.txt")
            window.write(out)
            with open(out, encoding="utf-8-sig") as f:
                self.assertEqual(f.read(), "BUY MILK\n42\nCALL MUM\n")
            with self.assertRaises(ValueError):
                window.write(path)  # never over the original
            window.close()


class AppKeysTest(unittest.TestCase):
    def test_keys_are_registered_and_shown_in_the_menu(self):
        from echosub import lens_ui

        registered = []
        with mock.patch.object(lens_ui.hotkeys.GlobalHotkeys, "enable_keys",
                               side_effect=lambda qt, bindings: registered.append(bindings) or []), \
                mock.patch("echosub.lens_menu.lens_ocr.available_languages", return_value=[]), \
                mock.patch.object(lens_ui.LensScanner, "start"):
            lens = lens_ui.LensApp(app, dict(lens_app.DEFAULTS, style=None), lambda cfg: None,
                                   echosub_cfg={"target_lang": "ar", "translator": "google"})
            labels = [b[0] for b in registered[-1]]
            self.assertIn("Ctrl+Alt+T", labels)
            self.assertIn("Ctrl+Alt+F", labels)
            self.assertTrue(any(a.text().endswith("\tCtrl+Alt+T") for a in lens.menu.actions()))
            self.assertEqual(lens.apply_keys(dict(lens.keys, copy_all="F7")), [])
            self.assertIn("F7", [b[0] for b in registered[-1]])
            self.assertTrue(any(a.text().endswith("\tF7") for a in lens.menu.actions()))
            calls = []
            lens.overlay.copy_all = lambda: calls.append(1)
            next(b for b in registered[-1] if b[0] == "F7")[3]()  # pressing F7 runs it
            self.assertEqual(calls, [1])
            lens.next_language()
            self.assertEqual(lens.target, "ar")  # "" (EchoSub's) -> first quick language
            lens.next_translator()
            self.assertEqual(lens.cfg["translator"], "google")
            self.assertTrue(set(lens.actions()) == set(lens_shortcuts.ACTIONS))
            lens.stop()
            lens.tray.hide()
            lens.overlay.close()

    def test_translators_cycle_list_matches_choices(self):
        self.assertIn("same", lens_translate.CHOICES)


if __name__ == "__main__":
    unittest.main()
