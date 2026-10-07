# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Choosing a model from what a service lists. No request ever leaves the machine during these tests."""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echosub import ai_models, ai_providers  # noqa: E402

GEMINI = ["models/embedding-001", "models/gemini-2.5-flash", "models/gemini-2.5-pro", "models/gemini-3.8-flash",
          "models/gemini-3.8-flash-lite", "models/gemini-3.8-pro", "models/gemini-4.0-flash-preview",
          "models/imagen-4.0-generate", "models/veo-3.0-generate", "models/gemini-3.8-flash-tts"]
OPENAI = ["gpt-4o-mini", "gpt-4o-2024-08-06", "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-mini-2025-08-07",
          "dall-e-3", "whisper-1", "tts-1", "text-embedding-3-large", "gpt-realtime", "omni-moderation-latest",
          "gpt-4o-transcribe", "gpt-image-1", "babbage-002"]


class RankingTest(unittest.TestCase):
    def test_models_that_cannot_answer_are_left_out(self):
        listed = ai_models.newest_first(OPENAI)
        for name in ("dall-e-3", "whisper-1", "tts-1", "text-embedding-3-large", "gpt-realtime",
                     "omni-moderation-latest", "gpt-4o-transcribe", "gpt-image-1", "babbage-002"):
            self.assertNotIn(name, listed)
        self.assertIn("gpt-5-mini", listed)

    def test_the_newest_come_first(self):
        listed = ai_models.newest_first(name.split("/")[1] for name in GEMINI)
        self.assertEqual(listed[0], "gemini-4.0-flash-preview")
        self.assertLess(listed.index("gemini-3.8-flash"), listed.index("gemini-2.5-flash"),
                        "a retired older model sinks below the current one")

    def test_the_default_is_current_fast_and_released(self):
        self.assertEqual(ai_models.best(name.split("/")[1] for name in GEMINI), "gemini-3.8-flash")
        self.assertEqual(ai_models.best(OPENAI), "gpt-5-mini")
        self.assertEqual(ai_models.best(["deepseek-chat", "deepseek-reasoner"]), "deepseek-chat")

    def test_nothing_to_choose_from(self):
        self.assertIsNone(ai_models.best([]))
        self.assertIsNone(ai_models.best(["whisper-1", "tts-1"]))

    def test_versions(self):
        self.assertEqual(ai_models.version("gemini-3.8-flash"), (3, 8))
        self.assertEqual(ai_models.version("gpt-4o-2024-08-06"), (4,))
        self.assertEqual(ai_models.version("deepseek-chat"), ())


class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ChosenForYouTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.models = OPENAI
        self.fail_next_answer = False
        real = ai_providers.urllib.request.urlopen
        self.addCleanup(lambda: setattr(ai_providers.urllib.request, "urlopen", real))
        self.addCleanup(ai_providers._picked.clear)
        ai_providers._picked.clear()

        def fake(request, timeout=None):
            self.sent.append(request)
            if request.full_url.endswith("/models"):
                body = {"data": [{"id": name} for name in self.models]}
            elif self.fail_next_answer:
                self.fail_next_answer = False
                raise ai_providers.urllib.error.HTTPError(request.full_url, 404, "gone", {}, FakeReply(b"{}"))
            else:
                body = {"choices": [{"message": {"content": "ok"}}]}
            return FakeReply(json.dumps(body).encode("utf-8"))

        ai_providers.urllib.request.urlopen = fake

    def asked_model(self):
        return json.loads(self.sent[-1].data)["model"]

    def test_with_no_model_chosen_the_best_one_is_used(self):
        self.assertEqual(ai_providers.ask("openai", "", "k", "", "s", "q"), "ok")
        self.assertEqual(self.asked_model(), "gpt-5-mini")

    def test_the_list_is_asked_for_once(self):
        ai_providers.ask("openai", "", "k", "", "s", "q")
        ai_providers.ask("openai", "", "k", "", "s", "q")
        self.assertEqual(sum(r.full_url.endswith("/models") for r in self.sent), 1)

    def test_a_model_you_chose_is_never_replaced(self):
        ai_providers.ask("openai", "gpt-4o-mini", "k", "", "s", "q")
        self.assertEqual(self.asked_model(), "gpt-4o-mini")
        self.assertFalse(any(r.full_url.endswith("/models") for r in self.sent))

    def test_a_withdrawn_choice_is_made_again(self):
        self.fail_next_answer = True
        with self.assertRaises(ai_providers.AiError):
            ai_providers.ask("openai", "", "k", "", "s", "q")
        self.models = ["gpt-6-mini"]
        ai_providers.ask("openai", "", "k", "", "s", "q")
        self.assertEqual(self.asked_model(), "gpt-6-mini")

    def test_nothing_usable_says_to_choose(self):
        self.models = ["whisper-1"]
        with self.assertRaises(ai_providers.AiError) as caught:
            ai_providers.ask("openai", "", "k", "", "s", "q")
        self.assertIn("Choose a model", str(caught.exception))

    def test_without_a_key_nothing_is_sent(self):
        with self.assertRaises(ai_providers.AiError):
            ai_providers.ask("openai", "", "", "", "s", "q")
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
