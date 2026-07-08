"""A thin wrapper around Ollama.

Every model call in the pipeline goes through :class:`LLMClient`, so timeouts,
temperature, and the JSON-parsing quirks of local models are handled in exactly
one place. The actual Ollama call is isolated in a ``backend`` callable, which
tests replace with a fake — the suite never needs a running model.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass


class JSONParseError(ValueError):
    """Raised when a model response cannot be coerced into a JSON object."""


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
Backend = Callable[[str, str, bool], str]


def _ollama_backend(host: str, timeout_s: int, temperature: float) -> Backend:
    """Build the real backend. Imported lazily so the module loads without Ollama."""

    def call(model: str, prompt: str, json_mode: bool) -> str:
        import ollama

        client = ollama.Client(host=host, timeout=timeout_s)
        response = client.generate(
            model=model,
            prompt=prompt,
            format="json" if json_mode else "",
            options={"temperature": temperature},
        )
        return response["response"]

    return call


class LLMClient:
    """Issues model calls through a configurable backend."""

    def __init__(self, config: dict, backend: Backend | None = None) -> None:
        self._host = config.get("host", "http://localhost:11434")
        self._timeout_s = int(config.get("timeout_s", 120))
        self._temperature = float(config.get("temperature", 0.0))
        self._backend = backend or _ollama_backend(self._host, self._timeout_s, self._temperature)

    def generate(self, model: str, prompt: str, *, json_mode: bool = False) -> LLMResponse:
        """Call ``model`` with ``prompt`` and time the round-trip."""
        start = time.perf_counter()
        text = self._backend(model, prompt, json_mode)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(text=text, model=model, latency_ms=latency_ms)


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
