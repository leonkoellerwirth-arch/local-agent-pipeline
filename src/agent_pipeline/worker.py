"""The worker: executes one plan step and returns validated JSON.

Each action has a focused prompt that asks the model for a specific JSON shape.
The response is parsed and validated into a :class:`WorkResult`. If parsing or
validation fails, the worker retries exactly once with the error fed back into
the prompt, then gives up — a bounded, auditable failure rather than a loop.
"""

from __future__ import annotations

from pydantic import ValidationError

from .contracts import Action, PlanStep, Task, WorkResult
from .llm import JSONParseError, LLMClient, StageTrace, parse_json

# Per-action instructions. Each names the exact JSON keys the worker must return
# so the output shape is predictable and cheap to validate.
_ACTION_INSTRUCTIONS: dict[Action, str] = {
    Action.CLASSIFY: (
        "Classify the document. Return JSON with keys: "
        '"label" (one of: report, contract, invoice, other) and '
        '"confidence" (0.0-1.0).'
    ),
    Action.EXTRACT: (
        "Extract key facts from the document. Return JSON with keys: "
        '"fields" (an object of extracted key/value pairs, e.g. parties, dates, '
        'monetary amounts) and "confidence" (0.0-1.0).'
    ),
    Action.SUMMARIZE: (
        "Summarize the document in two or three sentences. Return JSON with keys: "
        '"summary" (string) and "confidence" (0.0-1.0).'
    ),
}


class WorkerError(RuntimeError):
    """Raised when the worker cannot produce a valid result after its retry."""


def _build_prompt(step: PlanStep, task: Task, feedback: str | None) -> str:
    parts = [
        _ACTION_INSTRUCTIONS[step.action],
        "Respond with JSON only, no prose.",
        "",
        "DOCUMENT:",
        task.content,
    ]
    if feedback:
        parts += ["", f"Your previous response was invalid: {feedback}", "Try again."]
    return "\n".join(parts)


def _to_result(step: PlanStep, raw: str) -> WorkResult:
    """Parse and validate raw model text into a WorkResult (raises on failure)."""
    payload = parse_json(raw)
    confidence = payload.pop("confidence", None)
    if confidence is None:
        raise JSONParseError("Response is missing the required 'confidence' key.")
    return WorkResult(
        step_id=step.step_id,
        action=step.action,
        output=payload,
        confidence=float(confidence),
        raw=raw,
    )


class Worker:
    """Runs a single plan step against the worker model."""

    def __init__(self, llm: LLMClient, model: str, max_retries: int = 1) -> None:
        self._llm = llm
        self._model = model
        self._max_retries = max_retries

    def run_step(self, step: PlanStep, task: Task) -> tuple[WorkResult, StageTrace]:
        """Execute ``step`` and return its result plus a trace for the audit log."""
        feedback: str | None = None
        total_latency = 0
        last_prompt = ""
        last_raw = ""

        for _attempt in range(self._max_retries + 1):
            prompt = _build_prompt(step, task, feedback)
            response = self._llm.generate(self._model, prompt, json_mode=True)
            total_latency += response.latency_ms
            last_prompt, last_raw = prompt, response.text
            try:
                result = _to_result(step, response.text)
            except (JSONParseError, ValidationError, ValueError) as exc:
                feedback = str(exc)
                continue
            trace = StageTrace(
                model=self._model,
                prompt=last_prompt,
                output=last_raw,
                latency_ms=total_latency,
            )
            return result, trace

        raise WorkerError(
            f"Step {step.step_id} ({step.action.value}) produced no valid result "
            f"after {self._max_retries + 1} attempts: {feedback}"
        )
