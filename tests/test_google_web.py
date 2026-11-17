# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Google Translate through its JSON endpoints: the answer, a refusal, and falling back to the second endpoint."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from echosub import google_web, translate  # noqa: E402


class Answer:
    def __init__(self, url, status=200, data=None, redirected_to=None):
        self.url = redirected_to or url
        self.status_code = status
        self._data = data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        if self._data is None:
            raise ValueError("not JSON")
        return self._data


class FakeSession:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def post(self, url, params=None, data=None, timeout=None):
        self.asked.append((url, params, data))
        make = self.answers.pop(0)
        return make(url)


SINGLE = [[["مرحبا. ", "Hello. ", None], ["\nالى اللقاء", "\nBye", None]], None, "en"]


class GoogleWebTest(unittest.TestCase):
    def test_the_sentences_are_put_back_together_with_their_lines(self):
        session = FakeSession(lambda url: Answer(url, data=SINGLE))
        self.assertEqual(google_web.translate("Hello.\nBye", "ar", session), "مرحبا. \nالى اللقاء")
        url, params, data = session.asked[0]
        self.assertIn("translate_a/single", url)
        self.assertEqual((params["tl"], params["sl"], data["q"]), ("ar", "auto", "Hello.\nBye"))

    def test_the_second_endpoint_when_the_first_fails(self):
        session = FakeSession(lambda url: Answer(url, status=500), lambda url: Answer(url, data=[["Bonjour", "en"]]))
        self.assertEqual(google_web.translate("Hello", "fr", session), "Bonjour")
        self.assertIn("clients5", session.asked[1][0])

    def test_the_captcha_page_counts_as_a_refusal(self):
        sorry = "https://www.google.com/sorry/index?continue=x"
        session = FakeSession(lambda url: Answer(url, status=429, redirected_to=sorry),
                              lambda url: Answer(url, status=429))
        with self.assertRaises(google_web.TooManyRequests):
            google_web.translate("Hello", "fr", session)

    def test_no_answer_at_all(self):
        session = FakeSession(lambda url: Answer(url, data=None), lambda url: Answer(url, data=[]))
        with self.assertRaises(google_web.RequestFailed):
            google_web.translate("Hello", "fr", session)

    def test_nothing_to_translate_asks_nothing(self):
        session = FakeSession()
        self.assertEqual(google_web.translate("  ", "fr", session), "  ")
        self.assertEqual(session.asked, [])


class TranslatorTest(unittest.TestCase):
    def test_a_refusal_means_offline_for_now(self):
        t = translate.GoogleTranslator(("NLLB-600M", lambda: Offline()))
        t.RETRY_DELAYS = ()
        t._session = FakeSession(lambda url: Answer(url, status=429), lambda url: Answer(url, status=429))
        notes = []
        t.notify = notes.append
        self.assertEqual(t.translate("hello", "en", "ar"), "HELLO")
        self.assertIn("translating offline", notes[-1])

    def test_no_internet_means_offline_too_with_its_own_words(self):
        t = translate.GoogleTranslator(("NLLB-600M", lambda: Offline()))
        t._session = FakeSession(lambda url: Answer(url, status=500), lambda url: Answer(url, status=500))
        notes = []
        t.notify = notes.append
        self.assertEqual(t.translate("hello", "en", "ar"), "HELLO")
        self.assertIn("not answering", notes[-1])
        self.assertEqual(len(t._session.asked), 2, "no retries: they would only wait")
        self.assertEqual(t.translate("bye", "en", "ar"), "BYE", "paused: not asked again for a while")
        self.assertEqual(len(t._session.asked), 2)

    def test_google_answers(self):
        t = translate.GoogleTranslator()
        t._session = FakeSession(lambda url: Answer(url, data=SINGLE))
        self.assertEqual(t.translate("Hello.\nBye", "en", "ar"), "مرحبا. \nالى اللقاء")


class Offline:
    def translate(self, text, src, tgt):
        return text.upper()


if __name__ == "__main__":
    unittest.main(verbosity=2)
