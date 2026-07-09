"""Provider routing: model refs, key resolution, and per-provider HTTP shape.

No network: the HTTP layer (`_post_json`) is monkeypatched, so these tests
exercise request building and response parsing offline.
"""

from __future__ import annotations

import os

import pytest

from agent_pipeline import llm as llm_mod
from agent_pipeline.cli import _load_dotenv
from agent_pipeline.llm import (
    LLMClient,
    LLMError,
    _post_json,
    _safe_url,
    parse_model_ref,
    resolve_api_key,
)


# --- model refs -----------------------------------------------------------
@pytest.mark.parametrize(
    "ref,expected",
    [
        ("llama3.2", ("ollama", "llama3.2")),
        ("llama3.1:8b", ("ollama", "llama3.1:8b")),  # ollama tag colon is not a provider
        ("ollama:llama3.1:8b", ("ollama", "llama3.1:8b")),
        ("openai:gpt-4o", ("openai", "gpt-4o")),
        ("gemini:gemini-1.5-pro", ("gemini", "gemini-1.5-pro")),
        ("claude:claude-sonnet-4-5", ("claude", "claude-sonnet-4-5")),
    ],
)
def test_parse_model_ref(ref, expected):
    assert parse_model_ref(ref) == expected


# --- key resolution -------------------------------------------------------
def test_resolve_api_key_prefers_standard_name(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "std")
    assert resolve_api_key("openai") == "std"


def test_resolve_api_key_accepts_alias(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_KEY", "alias")
    assert resolve_api_key("claude") == "alias"


def test_resolve_api_key_missing_raises(monkeypatch):
    for name in ("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMError, match="No API key for 'gemini'"):
        resolve_api_key("gemini")


# --- dispatch + response parsing (HTTP mocked) ----------------------------
@pytest.fixture
def capture_post(monkeypatch):
    calls: dict = {}

    def fake_post(url, headers, payload, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["payload"] = payload
        return calls["response"]

    monkeypatch.setattr(llm_mod, "_post_json", fake_post)
    return calls


def test_openai_dispatch(monkeypatch, capture_post):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    capture_post["response"] = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    result = LLMClient({}).generate("openai:gpt-4o", "hi", json_mode=True)
    assert result.text == '{"ok": true}'
    assert result.model == "openai:gpt-4o"
    assert "api.openai.com" in capture_post["url"]
    assert capture_post["payload"]["response_format"] == {"type": "json_object"}
    assert capture_post["headers"]["Authorization"] == "Bearer k"


def test_gemini_dispatch(monkeypatch, capture_post):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    capture_post["response"] = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    result = LLMClient({}).generate("gemini:gemini-1.5-pro", "hi", json_mode=True)
    assert result.text == "hello"
    assert "generativelanguage.googleapis.com" in capture_post["url"]
    assert capture_post["payload"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_key_goes_in_header_not_url(monkeypatch, capture_post):
    # Regression: the key must never appear in the request URL (it used to be a
    # ?key= query param, which leaks through error messages).
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    capture_post["response"] = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
    LLMClient({}).generate("gemini:gemini-1.5-pro", "hi")
    assert "super-secret" not in capture_post["url"]
    assert "key=" not in capture_post["url"]
    assert capture_post["headers"]["x-goog-api-key"] == "super-secret"


def test_claude_dispatch(monkeypatch, capture_post):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    capture_post["response"] = {"content": [{"text": "reviewed"}]}
    result = LLMClient({}).generate("claude:claude-sonnet-4-5", "hi")
    assert result.text == "reviewed"
    assert "api.anthropic.com" in capture_post["url"]
    assert capture_post["headers"]["x-api-key"] == "k"


def test_ollama_dispatch_needs_no_key(capture_post):
    capture_post["response"] = {"response": "local answer"}
    client = LLMClient({"host": "http://localhost:11434"})
    result = client.generate("llama3.2", "hi", json_mode=True)
    assert result.text == "local answer"
    assert capture_post["url"].endswith("/api/generate")
    assert capture_post["payload"]["format"] == "json"


def test_unexpected_response_raises(monkeypatch, capture_post):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    capture_post["response"] = {"error": "quota"}
    with pytest.raises(LLMError, match="Unexpected OpenAI response"):
        LLMClient({}).generate("openai:gpt-4o", "hi")


def test_injected_backend_bypasses_providers():
    # No key set, no network: an injected backend serves every provider ref.
    client = LLMClient({}, backend=lambda model, prompt, jm: "canned")
    assert client.generate("openai:gpt-4o", "hi").text == "canned"


# --- error redaction ------------------------------------------------------
def test_safe_url_strips_query_string():
    url = "https://example.com/v1/models/x:generateContent?key=SECRET&alt=json"
    assert _safe_url(url) == "https://example.com/v1/models/x:generateContent"


def test_post_json_error_message_redacts_query_secrets(monkeypatch):
    # If a key ever rides in the URL, transport errors must not echo it back.
    import urllib.error

    def boom(*_a, **_k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
    url = "https://example.com/v1beta/models/x:generateContent?key=leaked-secret"
    with pytest.raises(LLMError) as exc:
        _post_json(url, {}, {"a": 1}, timeout=1)
    assert "leaked-secret" not in str(exc.value)
    assert "key=" not in str(exc.value)


# --- .env loading ---------------------------------------------------------
def test_load_dotenv_sets_and_respects_existing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "already-set")
    env = tmp_path / ".env"
    env.write_text('OPENAI_API_KEY="from-file"\n# comment\nGEMINI_API_KEY=ignored\n')
    _load_dotenv(env)
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    assert os.environ["GEMINI_API_KEY"] == "already-set"  # real env wins
