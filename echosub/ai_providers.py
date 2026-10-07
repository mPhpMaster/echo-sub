# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Asking an AI model a question, through whichever service the user chose.

Claude is called through Anthropic's own SDK. ChatGPT, Gemini, DeepSeek and LM Studio all speak
the same OpenAI-style "chat completions" format, so one small HTTP call serves the four of them,
with only the address and the key differing.

Nothing here runs unless the user asks a question; see `ai_assistant.py` for when that is.
"""
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT = 60
MAX_TOKENS = 16000

PROVIDERS = {
    "claude": {"title": "Claude (Anthropic)", "kind": "anthropic", "base_url": "",
               "model": "claude-opus-5-5", "local": False},
    "openai": {"title": "ChatGPT (OpenAI)", "kind": "openai", "base_url": "https://api.openai.com/v1",
               "model": "", "local": False},
    "gemini": {"title": "Gemini (Google)", "kind": "openai",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "", "local": False},
    "deepseek": {"title": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com/v1",
                 "model": "deepseek-chat", "local": False},
    "lmstudio": {"title": "LM Studio (on this PC)", "kind": "openai", "base_url": "http://localhost:1234/v1",
                 "model": "", "local": True},
}

# Claude models that accept an effort level, and those that can hand a declined request to another
# model on the server. Anything not listed is called plainly, so an older model still works.
EFFORT_MODELS = {"claude-fable-5-1", "claude-fable-5", "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8",
                 "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6"}
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AiError(Exception):
    """Something the user can act on: a missing key, a wrong address, a service that said no."""


def is_local(provider):
    return bool(PROVIDERS.get(provider, {}).get("local"))


def ask(provider, model, key, base_url, system, question):
    """The model's answer to `question`, given `system` as its instructions."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise AiError(f"Unknown AI service: {provider}")
    model = (model or spec["model"] or "").strip()
    if not model:
        raise AiError("Choose a model in Settings → AI first (Load models lists them).")
    if not spec["local"] and not key:
        raise AiError(f"{spec['title']} needs an API key in Settings → AI.")
    if spec["kind"] == "anthropic":
        return _ask_claude(model, key, system, question)
    return _ask_openai_style(base_url or spec["base_url"], model, key, system, question)


def list_models(provider, key, base_url):
    """The model names this service offers, so the user picks a real one rather than typing a guess."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise AiError(f"Unknown AI service: {provider}")
    if spec["kind"] == "anthropic":
        anthropic = _anthropic()
        try:
            return sorted(model.id for model in _claude_client(key).models.list())
        except anthropic.AuthenticationError as e:
            raise AiError("Claude rejected the API key.") from e
        except anthropic.APIConnectionError as e:
            raise AiError("Could not reach Anthropic — check the internet connection.") from e
        except anthropic.APIStatusError as e:
            raise AiError(f"Anthropic answered with an error ({e.status_code}).") from e
    data = _request("GET", (base_url or spec["base_url"]).rstrip("/") + "/models", key)
    return sorted(str(item.get("id")) for item in data.get("data", []) if item.get("id"))


# ---- Claude -----------------------------------------------------------------

def _anthropic():
    import anthropic  # imported on first use, so the app starts without it when AI is off

    return anthropic


def _claude_client(key):
    return _anthropic().Anthropic(api_key=key, timeout=TIMEOUT, max_retries=1)


def _ask_claude(model, key, system, question):
    anthropic = _anthropic()
    client = _claude_client(key)
    request = {"model": model, "max_tokens": MAX_TOKENS, "system": system,
               "messages": [{"role": "user", "content": question}]}
    if model in EFFORT_MODELS:
        # A short answer read off a caption box: low effort keeps the wait short.
        request["output_config"] = {"effort": "low"}
    try:
        if model in FALLBACK_MODELS:
            # If a safety check declines, the request is re-run on Anthropic's chosen fallback model.
            response = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default", **request)
        else:
            response = client.messages.create(**request)
    except anthropic.AuthenticationError as e:
        raise AiError("Claude rejected the API key.") from e
    except anthropic.PermissionDeniedError as e:
        raise AiError("This API key may not use that model.") from e
    except anthropic.NotFoundError as e:
        raise AiError(f"Claude does not know a model called {model}.") from e
    except anthropic.RateLimitError as e:
        raise AiError("Claude is rate-limiting this key; try again in a moment.") from e
    except anthropic.BadRequestError as e:
        raise AiError(f"Claude could not take that request: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AiError("Could not reach Anthropic — check the internet connection.") from e
    except anthropic.APIStatusError as e:
        raise AiError(f"Anthropic answered with an error ({e.status_code}); try again later.") from e
    if response.stop_reason == "refusal":
        return "(Claude declined to answer this.)"
    text = " ".join(block.text for block in response.content if block.type == "text").strip()
    return text or "(No answer came back.)"


# ---- the OpenAI-style services ----------------------------------------------

def _request(method, url, key, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        if e.code in (401, 403):
            raise AiError("The service rejected the API key.") from e
        if e.code == 404:
            raise AiError("Nothing answered at that address, or the model does not exist.") from e
        if e.code == 429:
            raise AiError("The service is rate-limiting this key; try again in a moment.") from e
        raise AiError(f"The service answered with an error ({e.code}). {detail}".strip()) from e
    except urllib.error.URLError as e:
        raise AiError(f"Could not reach {url.split('/')[2]} — is it running, and is the address right?") from e
    except (TimeoutError, OSError) as e:
        raise AiError("The service took too long to answer.") from e
    except ValueError as e:
        raise AiError("The service sent back something that was not an answer.") from e


def _ask_openai_style(base_url, model, key, system, question):
    data = _request("POST", base_url.rstrip("/") + "/chat/completions", key, {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
    })
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise AiError("The service sent back something that was not an answer.") from e
    return (text or "").strip() or "(No answer came back.)"
