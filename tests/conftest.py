"""Shared test fixtures.

The whole point of the suite is that it runs without Ollama. ``ScriptedBackend``
stands in for the model: it inspects the prompt to tell which stage is calling
and returns canned JSON, so planner, worker, and reviewer can be exercised
end-to-end deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_pipeline.llm import LLMClient

_ROOT = Path(__file__).resolve().parents[1]


class ScriptedBackend:
    """A fake LLM backend. Routes by markers in each stage's prompt."""

    def __init__(
        self,
        *,
        plan_actions: tuple[str, ...] = ("classify", "extract", "summarize"),
        worker_confidence: float = 0.9,
        reviewer_assessment: str = "pass",
        reviewer_confidence: float = 0.9,
        worker_bad_first: bool = False,
        worker_bad_forever: bool = False,
    ) -> None:
        self.plan_actions = plan_actions
        self.worker_confidence = worker_confidence
        self.reviewer_assessment = reviewer_assessment
        self.reviewer_confidence = reviewer_confidence
        self.worker_bad_first = worker_bad_first
        self.worker_bad_forever = worker_bad_forever
        self.calls: list[str] = []
        self._worker_calls = 0

    def __call__(self, model: str, prompt: str, json_mode: bool) -> str:
        if "You plan how to process" in prompt:
            self.calls.append("plan")
            steps = [{"action": a, "description": f"do {a}"} for a in self.plan_actions]
            return json.dumps({"steps": steps})

        if "You are a reviewer" in prompt:
            self.calls.append("review")
            return json.dumps(
                {
                    "assessment": self.reviewer_assessment,
                    "confidence": self.reviewer_confidence,
                    "reasons": ["scripted review"],
                }
            )

        # Otherwise it is a worker call.
        self.calls.append("work")
        self._worker_calls += 1
        if self.worker_bad_forever or (self.worker_bad_first and self._worker_calls == 1):
            return "not json at all"
        return self._worker_payload(prompt)

    def _worker_payload(self, prompt: str) -> str:
        conf = self.worker_confidence
        if "Classify the document" in prompt:
            return json.dumps({"label": "report", "confidence": conf})
        if "Extract key facts" in prompt:
            return json.dumps({"fields": {"title": "Sample"}, "confidence": conf})
        return json.dumps({"summary": "A short summary.", "confidence": conf})


def make_llm(backend: ScriptedBackend) -> LLMClient:
    """Build an LLMClient wired to a scripted backend."""
    return LLMClient({"host": "unused", "timeout_s": 1, "temperature": 0.0}, backend=backend)


@pytest.fixture
def pipeline_cfg() -> dict:
    return yaml.safe_load((_ROOT / "config" / "pipeline.yaml").read_text())


@pytest.fixture
def policy_cfg() -> dict:
    return yaml.safe_load((_ROOT / "config" / "policy.yaml").read_text())
