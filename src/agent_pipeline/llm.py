"""A thin, multi-provider wrapper for model calls.

Every model call in the pipeline goes through :class:`LLMClient`, so timeouts,
temperature, provider routing, and the JSON-parsing quirks of local models are
handled in exactly one place.

Models are addressed as ``provider:model``. Without a prefix the provider is
``ollama`` (local), so ``llama3.2`` and ``llama3.1:8b`` both mean Ollama. Prefix
with ``openai:``, ``gemini:``, or ``claude:`` to route a role to an external
provider for stronger review — the API key is read from the environment (see
``.env.example``). Local is the default; external providers are opt-in and only
used when you name them.

Cloud providers are called over plain HTTP (`urllib`, standard library) — no
provider SDKs are pulled in. Tests inject a fake ``backend`` and never touch the
network.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

KNOWN_PROVIDERS = ("ollama", "openai", "gemini", "claude")

# Which environment variables hold each provider's API key. The first that is
# set wins; both the provider-standard name and a short alias are accepted.
PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY", "OPEN_AI_KEY"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_KEY"),
}


class JSONParseError(ValueError):
    """Raised when a model response cannot be coerced into a JSON object."""


class LLMError(RuntimeError):
    """Raised on a provider, transport, or configuration failure."""


@dataclass(frozen=True)
class LLMResponse:
    """The result of one model call."""

    text: str
    model: str
    latency_ms: int


@dataclass(frozen=True)
class StageTrace:
    """Everything a stage did that the audit log needs to record.

    Stages return this alongside their domain object so the orchestrator can
    hash the prompt and output without knowing how the stage produced them.
    """

    model: str
    prompt: str
    output: str
    latency_ms: int


# A backend takes (model, prompt, json_mode) and returns the raw model text.
# Injecting one bypasses provider routing entirely; the test suite uses this.
Backend = Callable[[str, str, bool], str]


def parse_model_ref(ref: str) -> tuple[str, str]:
    """Split ``provider:model`` into its parts, defaulting to the ``ollama`` provider.

    Only the known provider prefixes are treated as providers, so an Ollama tag
    such as ``llama3.1:8b`` is left intact as a model name.
    """
    prefix, sep, rest = ref.partition(":")
    if sep and prefix in KNOWN_PROVIDERS:
        return prefix, rest
    return "ollama", ref


def resolve_api_key(provider: str) -> str:
    """Return the API key for ``provider`` from the environment, or raise."""
    names = PROVIDER_ENV_VARS[provider]
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise LLMError(
        f"No API key for '{provider}'. Set one of {', '.join(names)} "
        f"(e.g. in a .env file). See .env.example."
    )


def _safe_url(url: str) -> str:
    """Return ``url`` without its query string.

    Some providers (Gemini's REST endpoint) accept the API key as a query
    parameter. Dropping the query before a URL ever reaches an error message,
    log line, or traceback keeps that secret from leaking. Keys should still be
    sent as headers where possible; this is defence in depth, not the primary
    guard.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _post_json(url: str, headers: dict[str, str], payload: dict, timeout: int) -> dict:
    """POST ``payload`` as JSON and return the decoded JSON response."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed https provider endpoints
        url, data=data, method="POST", headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise LLMError(f"HTTP {exc.code} from {_safe_url(url)}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LLMError(f"Could not reach {_safe_url(url)}: {exc}") from exc


def _call_ollama(host: str, timeout: int, temp: float, model: str, prompt: str, jm: bool) -> str:
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temp},
    }
    if jm:
        payload["format"] = "json"
    data = _post_json(f"{host.rstrip('/')}/api/generate", {}, payload, timeout)
    return data.get("response", "")


def _call_openai(timeout: int, temp: float, model: str, prompt: str, jm: bool) -> str:
    payload: dict = {
        "model": model,
        "temperature": temp,
        "messages": [{"role": "user", "content": prompt}],
    }
    if jm:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {resolve_api_key('openai')}"}
    data = _post_json("https://api.openai.com/v1/chat/completions", headers, payload, timeout)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected OpenAI response: {data}") from exc


def _call_gemini(timeout: int, temp: float, model: str, prompt: str, jm: bool) -> str:
    generation: dict = {"temperature": temp}
    if jm:
        generation["responseMimeType"] = "application/json"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation}
    # Send the key as a header, never in the URL, so it cannot leak into an
    # error message, log line, or traceback via the request URL.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": resolve_api_key("gemini")}
    data = _post_json(url, headers, payload, timeout)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Gemini response: {data}") from exc


def _call_claude(
    timeout: int, temp: float, max_tokens: int, model: str, prompt: str, jm: bool
) -> str:
    # Anthropic has no JSON response mode; the prompts already demand JSON only.
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temp,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"x-api-key": resolve_api_key("claude"), "anthropic-version": "2023-06-01"}
    data = _post_json("https://api.anthropic.com/v1/messages", headers, payload, timeout)
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Anthropic response: {data}") from exc


class LLMClient:
    """Routes model calls to the right provider (or a single injected backend)."""

    def __init__(self, config: dict, backend: Backend | None = None) -> None:
        self._host = config.get("host", "http://localhost:11434")
        self._timeout_s = int(config.get("timeout_s", 120))
        self._temperature = float(config.get("temperature", 0.0))
        self._max_tokens = int(config.get("max_tokens", 1024))
        self._backend = backend

    def generate(self, model: str, prompt: str, *, json_mode: bool = False) -> LLMResponse:
        """Call ``model`` (a ``provider:model`` ref) with ``prompt`` and time the round-trip."""
        start = time.perf_counter()
        if self._backend is not None:
            text = self._backend(model, prompt, json_mode)
        else:
            provider, name = parse_model_ref(model)
            text = self._dispatch(provider, name, prompt, json_mode)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(text=text, model=model, latency_ms=latency_ms)

    def _dispatch(self, provider: str, model: str, prompt: str, json_mode: bool) -> str:
        if provider == "ollama":
            return _call_ollama(
                self._host, self._timeout_s, self._temperature, model, prompt, json_mode
            )
        if provider == "openai":
            return _call_openai(self._timeout_s, self._temperature, model, prompt, json_mode)
        if provider == "gemini":
            return _call_gemini(self._timeout_s, self._temperature, model, prompt, json_mode)
        if provider == "claude":
            return _call_claude(
                self._timeout_s, self._temperature, self._max_tokens, model, prompt, json_mode
            )
        raise LLMError(f"Unknown provider '{provider}'. Known: {', '.join(KNOWN_PROVIDERS)}.")


def parse_json(text: str) -> dict:
    """Extract a JSON object from model text.

    Local models wrap JSON in prose or code fences more often than they should,
    so we try a direct parse first, then fall back to the first balanced
    ``{...}`` span. Raises :class:`JSONParseError` if neither yields an object.
    """
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError as exc:
            raise JSONParseError(f"Found a JSON-like span but could not parse it: {exc}") from exc

    raise JSONParseError("No JSON object found in model response.")
