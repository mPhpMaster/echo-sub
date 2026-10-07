# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Asking an AI about recent captions. No request ever leaves the machine during these tests."""
import io
import json
import os
import sys
import unittest
import urllib.error
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared FakeApp harness
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ECHOSUB_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from echosub import ai_assistant, ai_providers, config, secrets_store, voice_commands  # noqa: E402
from echosub.settings_dialog import SettingsDialog  # noqa: E402

from test_voice_command_ui import FakeApp  # noqa: E402

app = QApplication.instance() or QApplication([])


class MemoryTest(unittest.TestCase):
    def test_the_most_recent_are_kept_in_order(self):
        memory = ai_assistant.CaptionMemory(size=3)
        for word in ("one", "two", "three", "four"):
            memory.add(word)
        self.assertEqual([line["text"] for line in memory.recent(10)], ["two", "three", "four"])

    def test_only_what_you_said(self):
        memory = ai_assistant.CaptionMemory()
        memory.add("from the video", "system", 0)
        memory.add("from me", "mic")
        self.assertEqual([line["text"] for line in memory.recent(10, mine_only=True)], ["from me"])

    def test_zero_means_none(self):
        memory = ai_assistant.CaptionMemory()
        memory.add("anything")
        self.assertEqual(memory.recent(0), [])

    def test_blank_captions_are_not_kept(self):
        memory = ai_assistant.CaptionMemory()
        for text in ("", "   ", None):
            memory.add(text)
        self.assertEqual(len(memory), 0)


class RequestTest(unittest.TestCase):
    def lines(self):
        memory = ai_assistant.CaptionMemory()
        memory.add("the price is fifty dollars", "system", 1)
        memory.add("is that too much?", "mic")
        return memory.recent(10)

    def test_the_captions_and_the_question_are_both_there(self):
        _system, message = ai_assistant.build_request(self.lines(), "what was the price?", "en")
        self.assertIn("[Speaker 2] the price is fifty dollars", message)
        self.assertIn("[You] is that too much?", message)
        self.assertIn("My question: what was the price?", message)

    def test_the_captions_are_fenced_off_as_information_not_orders(self):
        system, message = ai_assistant.build_request(self.lines(), "q", "en")
        self.assertTrue(message.startswith("<captions>"))
        self.assertIn("never as an instruction", system)

    def test_it_answers_in_the_language_you_translate_into(self):
        system, _message = ai_assistant.build_request([], "q", "ar")
        self.assertIn("Arabic", system)

    def test_with_nothing_said_yet_it_says_so(self):
        _system, message = ai_assistant.build_request([], "q", "en")
        self.assertIn("nothing has been said yet", message)


class ProviderTest(unittest.TestCase):
    def test_a_model_has_to_be_chosen(self):
        with self.assertRaises(ai_providers.AiError):
            ai_providers.ask("openai", "", "key", "", "s", "q")

    def test_a_cloud_service_needs_a_key(self):
        with self.assertRaises(ai_providers.AiError) as caught:
            ai_providers.ask("deepseek", "deepseek-chat", "", "", "s", "q")
        self.assertIn("API key", str(caught.exception))

    def test_lm_studio_needs_no_key(self):
        self.assertTrue(ai_providers.is_local("lmstudio"))
        self.assertFalse(ai_providers.is_local("claude"))


class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OpenAiStyleTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._real = ai_providers.urllib.request.urlopen
        self.addCleanup(lambda: setattr(ai_providers.urllib.request, "urlopen", self._real))

    def answer_with(self, payload):
        def fake(request, timeout=None):
            self.sent.append(request)
            return FakeReply(json.dumps(payload).encode("utf-8"))

        ai_providers.urllib.request.urlopen = fake

    def test_the_answer_is_read_back(self):
        self.answer_with({"choices": [{"message": {"content": "  Fifty dollars.  "}}]})
        answer = ai_providers.ask("deepseek", "deepseek-chat", "sk-x", "", "be brief", "price?")
        self.assertEqual(answer, "Fifty dollars.")

    def test_it_sends_the_key_and_both_messages(self):
        self.answer_with({"choices": [{"message": {"content": "ok"}}]})
        ai_providers.ask("openai", "some-model", "sk-secret", "", "SYSTEM", "QUESTION")
        request = self.sent[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-secret")
        body = json.loads(request.data)
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertTrue(request.full_url.endswith("/chat/completions"))

    def test_lm_studio_is_called_on_this_pc(self):
        self.answer_with({"choices": [{"message": {"content": "ok"}}]})
        ai_providers.ask("lmstudio", "local-model", "", "", "s", "q")
        self.assertTrue(self.sent[0].full_url.startswith("http://localhost:1234/"))
        self.assertIsNone(self.sent[0].get_header("Authorization"), "no key should be sent to a local server")

    def test_a_rejected_key_says_so(self):
        def refuse(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, FakeReply(b"{}"))

        ai_providers.urllib.request.urlopen = refuse
        with self.assertRaises(ai_providers.AiError) as caught:
            ai_providers.ask("openai", "m", "bad", "", "s", "q")
        self.assertIn("key", str(caught.exception))

    def test_a_server_that_is_not_running_says_so(self):
        def unreachable(request, timeout=None):
            raise urllib.error.URLError("refused")

        ai_providers.urllib.request.urlopen = unreachable
        with self.assertRaises(ai_providers.AiError) as caught:
            ai_providers.ask("lmstudio", "m", "", "", "s", "q")
        self.assertIn("localhost", str(caught.exception))

    def test_listing_models(self):
        self.answer_with({"data": [{"id": "b-model"}, {"id": "a-model"}]})
        self.assertEqual(ai_providers.list_models("lmstudio", "", ""), ["a-model", "b-model"])


class ClaudeTest(unittest.TestCase):
    """The SDK client is replaced, so these check what EchoSub asks of it and does with the reply."""

    def setUp(self):
        self.calls = []
        test = self

        class Messages:
            def __init__(self, beta):
                self.beta = beta

            def create(self, **request):
                test.calls.append((self.beta, request))
                return test.reply

        self.client = SimpleNamespace(messages=Messages(False), beta=SimpleNamespace(messages=Messages(True)))
        self._real = ai_providers._claude_client
        ai_providers._claude_client = lambda key: self.client
        self.addCleanup(lambda: setattr(ai_providers, "_claude_client", self._real))
        self.reply = SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="Fifty dollars.")])

    def test_the_current_model_uses_fallbacks_and_low_effort(self):
        answer = ai_providers.ask("claude", "claude-opus-5-5", "sk-ant", "", "s", "q")
        self.assertEqual(answer, "Fifty dollars.", "only the text, never the thinking")
        beta, request = self.calls[0]
        self.assertTrue(beta, "fallbacks are a beta feature")
        self.assertEqual(request["fallbacks"], "default")
        self.assertEqual(request["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(request["output_config"], {"effort": "low"})
        self.assertNotIn("thinking", request, "thinking cannot be switched off on this model")

    def test_an_older_model_is_called_plainly(self):
        ai_providers.ask("claude", "claude-haiku-4-5", "sk-ant", "", "s", "q")
        beta, request = self.calls[0]
        self.assertFalse(beta)
        self.assertNotIn("fallbacks", request)
        self.assertNotIn("output_config", request, "this model does not take an effort level")

    def test_a_refusal_is_reported_instead_of_an_empty_answer(self):
        self.reply = SimpleNamespace(stop_reason="refusal", content=[])
        self.assertIn("declined", ai_providers.ask("claude", "claude-opus-5-5", "sk-ant", "", "s", "q"))

    def test_the_default_model_is_the_current_opus(self):
        self.assertEqual(ai_providers.PROVIDERS["claude"]["model"], "claude-opus-5-5")


class SpokenTest(unittest.TestCase):
    def test_ask_is_a_command_once_switched_on(self):
        found = voice_commands.find("echo sub ask what was the price he said", allow_ai=True)
        self.assertEqual((found["action"], found["target"]), ("ask_ai", "what was the price he said"))

    def test_it_is_off_by_default(self):
        self.assertFalse(config.DEFAULTS["ai_enabled"])
        self.assertIsNone(voice_commands.find("echo sub ask what was the price"))

    def test_ask_with_nothing_after_it_asks_nothing(self):
        self.assertIsNone(voice_commands.find("echo sub ask", allow_ai=True))

    def test_the_pcs_sound_still_needs_the_wake_word(self):
        self.assertIsNone(voice_commands.find("ask what was the price", allow_ai=True))


class AiApp(FakeApp, ai_assistant.AiAssistantMixin):
    pass


class AppTest(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self._real_ask = ai_providers.ask
        self._real_thread = ai_assistant.threading.Thread

        def fake_ask(provider, model, key, base_url, system, question):
            self.asked.append((provider, question))
            return "Fifty dollars."

        class Inline:
            def __init__(self, target, **kw):
                self.target = target

            def start(self):
                self.target()

        ai_providers.ask = fake_ask
        ai_assistant.threading.Thread = Inline
        self.addCleanup(lambda: setattr(ai_providers, "ask", self._real_ask))
        self.addCleanup(lambda: setattr(ai_assistant.threading, "Thread", self._real_thread))

    def app(self, **overrides):
        overrides.setdefault("voice_command_delay", 0)
        return AiApp(voice_commands=True, ai_enabled=True, **overrides).use_fake_runner()

    def test_the_answer_appears_in_the_caption_box(self):
        app_ = self.app()
        app_.remember_for_ai("the price is fifty dollars", "system", 0)
        app_._handle_voice_command("echo sub ask what was the price")
        shown = [text for text, _source in app_.overlay.shown]
        self.assertTrue(any("thinking" in text for text in shown), "it should say it is working on it")
        self.assertTrue(any("Fifty dollars." in text for text in shown))
        self.assertIn("the price is fifty dollars", self.asked[0][1])

    def test_only_what_you_said_is_sent_when_asked_for(self):
        app_ = self.app(ai_context_who="me")
        app_.remember_for_ai("a stranger said this", "system", 0)
        app_.remember_for_ai("I said this", "mic")
        app_._handle_voice_command("echo sub ask what did I say")
        self.assertNotIn("a stranger said this", self.asked[0][1])
        self.assertIn("I said this", self.asked[0][1])

    def test_no_means_nothing_is_sent(self):
        app_ = self.app(voice_command_delay=3)
        app_._handle_voice_command("echo sub ask what was the price")
        self.assertTrue(app_.heard_a_refusal("no"))
        app_._notice.fire_now()
        self.assertEqual(self.asked, [], "a cancelled question must never leave the PC")

    def test_a_failure_is_shown_not_crashed(self):
        def broken(*args):
            raise ai_providers.AiError("The service rejected the API key.")

        ai_providers.ask = broken
        app_ = self.app()
        app_._handle_voice_command("echo sub ask anything")
        self.assertTrue(any("rejected the API key" in text for text, _s in app_.overlay.shown))


class SettingsTest(unittest.TestCase):
    def dialog(self, **cfg):
        dialog = SettingsDialog(dict(config.DEFAULTS, **cfg))
        self.addCleanup(dialog.close)
        return dialog

    def test_a_typed_key_is_stored_encrypted(self):
        dialog = self.dialog()
        dialog.ai_key.setText("sk-ant-secret")
        saved = dialog.values()["ai_profiles"]["claude"]["key"]
        self.assertNotIn("sk-ant-secret", saved)
        self.assertEqual(secrets_store.unprotect(saved), "sk-ant-secret")

    def test_the_key_is_never_shown_again(self):
        stored = {"claude": {"key": secrets_store.protect("sk-ant-secret")}}
        dialog = self.dialog(ai_profiles=stored)
        self.assertEqual(dialog.ai_key.text(), "")
        self.assertIn("saved", dialog.ai_key.placeholderText())
        self.assertEqual(dialog.values()["ai_profiles"]["claude"]["key"], stored["claude"]["key"])

    def test_each_service_keeps_its_own_settings(self):
        dialog = self.dialog()
        dialog.ai_key.setText("sk-ant-one")
        dialog.ai_provider.setCurrentIndex(dialog.ai_provider.findData("deepseek"))
        dialog.ai_key.setText("sk-deep-two")
        profiles = dialog.values()["ai_profiles"]
        self.assertEqual(secrets_store.unprotect(profiles["claude"]["key"]), "sk-ant-one")
        self.assertEqual(secrets_store.unprotect(profiles["deepseek"]["key"]), "sk-deep-two")

    def test_forgetting_the_key(self):
        dialog = self.dialog(ai_profiles={"claude": {"key": secrets_store.protect("sk-x")}})
        dialog._forget_ai_key()
        self.assertNotIn("key", dialog.values()["ai_profiles"].get("claude", {}))

    def test_a_cloud_service_warns_that_captions_leave_the_pc(self):
        dialog = self.dialog(ai_provider="openai")
        self.assertIn("sent to", dialog.ai_privacy.text())

    def test_get_a_key_opens_that_services_own_page(self):
        opened = []
        from echosub import settings_ai

        real = settings_ai.QDesktopServices.openUrl
        settings_ai.QDesktopServices.openUrl = lambda url: opened.append(url.toString())
        self.addCleanup(lambda: setattr(settings_ai.QDesktopServices, "openUrl", real))
        dialog = self.dialog(ai_provider="claude")
        dialog._open_key_page()
        dialog.ai_provider.setCurrentIndex(dialog.ai_provider.findData("gemini"))
        dialog._open_key_page()
        self.assertEqual(opened, ["https://platform.claude.com/settings/keys",
                                  "https://aistudio.google.com/app/apikey"])

    def test_every_service_has_a_page_and_it_is_https(self):
        for key, spec in ai_providers.PROVIDERS.items():
            with self.subTest(service=key):
                self.assertTrue(spec["key_url"].startswith("https://"), spec["key_url"])

    def test_lm_studio_offers_the_program_instead_of_a_key(self):
        dialog = self.dialog(ai_provider="lmstudio")
        self.assertIn("LM Studio", dialog.ai_get_key.text())

    def test_lm_studio_says_nothing_leaves(self):
        dialog = self.dialog(ai_provider="lmstudio")
        self.assertIn("never leave", dialog.ai_privacy.text())
        self.assertFalse(dialog.ai_key.isEnabled())


class TriggerWordTest(unittest.TestCase):
    def test_your_own_word_asks_instead(self):
        found = voice_commands.find("echo sub jarvis what was the price", allow_ai=("jarvis",))
        self.assertEqual((found["action"], found["target"]), ("ask_ai", "what was the price"))

    def test_the_built_in_word_no_longer_asks_once_you_change_it(self):
        self.assertIsNone(voice_commands.find("echo sub ask what was the price", allow_ai=("jarvis",)))

    def test_several_words_can_be_listed(self):
        cfg = {"ai_trigger": "jarvis, اسأل"}
        self.assertEqual(ai_assistant.trigger_words(cfg), ("jarvis", "اسأل"))

    def test_an_empty_setting_falls_back_to_the_built_in_words(self):
        self.assertEqual(ai_assistant.trigger_words({"ai_trigger": "  ,  "}), ai_assistant.ASK_WORDS)

    def test_your_own_word_works_from_your_microphone_without_the_name(self):
        app_ = AiApp(voice_commands=True, ai_enabled=True, ai_trigger="jarvis",
                     voice_command_delay=0).use_fake_runner()
        asked = []
        app_.ask_ai = lambda question, lang=None: asked.append(question)
        app_._handle_voice_command("jarvis what time is the match", source="mic")
        self.assertEqual(asked, ["what time is the match"])


class AnswerLookTest(unittest.TestCase):
    def test_the_answer_is_shown_as_the_ais_own_line(self):
        app_ = AiApp(voice_commands=True, ai_enabled=True).use_fake_runner()
        app_._ai_finished(0, "Fifty dollars.", "Fifty dollars.", "en", False)
        self.assertIn(("Fifty dollars.", "ai"), app_.overlay.shown)

    def test_a_failure_is_marked_but_still_the_ais_line(self):
        app_ = AiApp(voice_commands=True, ai_enabled=True).use_fake_runner()
        app_._ai_finished(0, "The service rejected the API key.", "The service rejected the API key.", "en", True)
        text, source = app_.overlay.shown[-1]
        self.assertEqual(source, "ai")
        self.assertTrue(text.startswith("⚠"))

    def test_in_the_box_it_has_its_own_colour_and_ai_first(self):
        from echosub.caption_widgets import AI_COLOR, AI_LABEL
        from echosub.overlay import CaptionOverlay

        cfg = dict(config.DEFAULTS, caption_animation="none")
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        overlay.add_final(1, "someone talking", "someone talking", "en", 0, "system")
        overlay.add_final(2, "Fifty dollars.", "Fifty dollars.", "en", None, "ai")
        app.processEvents()
        line = overlay.lines[-1].translated
        self.assertEqual(line._color.name().upper(), AI_COLOR.upper())
        self.assertEqual(line._badge.text, AI_LABEL)
        self.assertEqual(line._badge.position, "before", "AI must come before the answer")
        self.assertIsNone(line._badge.flag, "no flag: who answered matters, not which language")

    def test_the_colour_can_be_changed(self):
        from echosub.overlay import CaptionOverlay

        cfg = dict(config.DEFAULTS, caption_animation="none", ai_color="#FF8800")
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        overlay.add_final(2, "Fifty dollars.", "Fifty dollars.", "en", None, "ai")
        app.processEvents()
        self.assertEqual(overlay.lines[-1].translated._color.name().upper(), "#FF8800")

    def overlay_with(self, **cfg_changes):
        from echosub.overlay import CaptionOverlay

        cfg = dict(config.DEFAULTS, caption_animation="none", **cfg_changes)
        overlay = CaptionOverlay(cfg, lambda p: None, lambda g: None, lambda: None)
        overlay.show()
        self.addCleanup(overlay.close)
        overlay.add_final(1, "a caption", "a caption", "en", 0, "system")
        overlay.add_final(2, "Fifty dollars.", "Fifty dollars.", "en", None, "ai")
        app.processEvents()
        return overlay

    def test_the_word_in_front_can_be_changed(self):
        overlay = self.overlay_with(ai_label="Claude")
        self.assertEqual(overlay.lines[-1].translated._badge.text, "Claude")

    def test_an_empty_word_falls_back_to_ai(self):
        overlay = self.overlay_with(ai_label="   ")
        self.assertEqual(overlay.lines[-1].translated._badge.text, "AI")

    def test_the_size_can_be_set(self):
        overlay = self.overlay_with(ai_font_size=40)
        ai_size = overlay.lines[-1].translated._font.pointSizeF()
        caption_size = overlay.lines[0].translated._font.pointSizeF()
        self.assertGreater(ai_size, caption_size)

    def test_zero_means_the_same_size_as_the_captions(self):
        overlay = self.overlay_with(ai_font_size=0)
        self.assertEqual(overlay.lines[-1].translated._font.pointSizeF(),
                         overlay.lines[0].translated._font.pointSizeF())

    def test_the_settings_keep_the_word_and_the_size(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, ai_label="Claude", ai_font_size=30))
        self.addCleanup(dialog.close)
        values = dialog.values()
        self.assertEqual((values["ai_label"], values["ai_font_size"]), ("Claude", 30))

    def test_the_settings_keep_the_word_and_the_colour(self):
        dialog = SettingsDialog(dict(config.DEFAULTS, ai_trigger="jarvis", ai_color="#FF8800"))
        self.addCleanup(dialog.close)
        values = dialog.values()
        self.assertEqual((values["ai_trigger"], values["ai_color"].upper()), ("jarvis", "#FF8800"))


class AnswerLanguageTest(unittest.TestCase):
    """The answer comes back in the language the question was asked in, then is translated."""

    def setUp(self):
        self.asked = []
        self._real_ask = ai_providers.ask
        self._real_thread = ai_assistant.threading.Thread

        def fake_ask(provider, model, key, base_url, system, question):
            self.asked.append(system)
            return "the answer"

        class Inline:
            def __init__(self, target, **kw):
                self.target = target

            def start(self):
                self.target()

        ai_providers.ask = fake_ask
        ai_assistant.threading.Thread = Inline
        self.addCleanup(lambda: setattr(ai_providers, "ask", self._real_ask))
        self.addCleanup(lambda: setattr(ai_assistant.threading, "Thread", self._real_thread))

    def app(self, translated="la respuesta"):
        app_ = AiApp(voice_commands=True, ai_enabled=True, target_lang="es", voice_command_delay=0)
        app_.use_fake_runner()
        self.translations = []

        class Engine:
            def translate_text(engine, text, lang):
                self.translations.append((text, lang))
                return translated

        app_.engine = Engine()
        return app_

    def test_it_is_told_to_answer_in_the_language_of_the_question(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub ask what was the price", "system", "ar")
        self.assertIn("Arabic", self.asked[0])
        self.assertNotIn("Spanish", self.asked[0], "the caption language is not the question's")

    def test_the_answer_is_then_translated_like_a_caption(self):
        app_ = self.app()
        app_._handle_voice_command("echo sub ask what was the price", "system", "en")
        self.assertEqual(self.translations, [("the answer", "en")])
        self.assertIn(("la respuesta", "ai"), app_.overlay.shown)

    def test_a_failure_is_not_sent_for_translation(self):
        def broken(*args):
            raise ai_providers.AiError("The service rejected the API key.")

        ai_providers.ask = broken
        app_ = self.app()
        app_._handle_voice_command("echo sub ask anything", "system", "en")
        self.assertEqual(self.translations, [])

    def test_without_a_spoken_language_it_falls_back_to_the_caption_language(self):
        app_ = self.app()
        app_.ask_ai("what was the price")
        self.assertIn("Spanish", self.asked[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
