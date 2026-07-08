"""The reviewer: an independent check on a worker result.

The reviewer runs on a different model from the worker (so the check is not the
author grading itself) and combines two kinds of judgement:

* **Deterministic heuristics** from ``policy.yaml`` — PII regexes, a contract-value
  threshold, and a minimum-confidence floor. These always fire the same way and
  are cheap to test.
* **The reviewer model** — a second opinion on correctness and risk that the
  heuristics cannot express.

The decision rule is explicit: a model ``reject`` wins; otherwise any fired
policy flag or a model ``escalate`` escalates; otherwise the result passes.
"""

from __future__ import annotations

import json
import re

from .contracts import Decision, Review, Task, WorkResult
from .llm import JSONParseError, LLMClient, StageTrace, parse_json

_PROMPT = """\
You are a reviewer. Judge whether the worker's output is a faithful, complete,
and safe result for the document. Consider correctness and any sensitive data.

Return JSON only: {{"assessment": "pass|escalate|reject", "confidence": 0.0-1.0,
"reasons": ["short reason", ...]}}.

DOCUMENT (excerpt):
{excerpt}

WORKER OUTPUT:
{output}
"""

_AMOUNT_RE = re.compile(r"(?:€|EUR|euro)\s*([\d.,]+)|([\d.,]+)\s*(?:€|EUR|euro)", re.IGNORECASE)


def _parse_amount(token: str) -> float | None:
    """Parse a European- or US-formatted monetary token into a float.

    Treats a separator followed by exactly two trailing digits as the decimal
    point; every other ``.``/``,`` is a thousands separator.
    """
    token = token.strip().strip(".,")
    if not re.search(r"\d", token):
        return None
    decimal = re.search(r"[.,](\d{2})$", token)
    if decimal:
        integer = re.sub(r"[.,]", "", token[: decimal.start()])
        return float(f"{integer}.{decimal.group(1)}") if integer else float(f"0.{decimal.group(1)}")
    return float(re.sub(r"[.,]", "", token))


def _max_amount(text: str) -> float:
    """Return the largest EUR amount found in ``text`` (0.0 if none)."""
    amounts = []
    for match in _AMOUNT_RE.finditer(text):
        parsed = _parse_amount(match.group(1) or match.group(2) or "")
        if parsed is not None:
            amounts.append(parsed)
    return max(amounts, default=0.0)


class Reviewer:
    """Reviews a worker result against policy and a second model."""

    def __init__(self, llm: LLMClient, model: str, policy: dict) -> None:
        self._llm = llm
        self._model = model
        self._min_confidence = float(policy.get("min_confidence", 0.6))
        triggers = policy.get("risk_triggers", {})
        self._pii = {
            name: re.compile(pattern) for name, pattern in triggers.get("pii_patterns", {}).items()
        }
        self._value_threshold = float(triggers.get("contract_value_threshold_eur", float("inf")))

    def review(self, result: WorkResult, task: Task) -> tuple[Review, StageTrace]:
        """Return the review verdict plus a trace for the audit log."""
        flags, reasons = self._heuristics(result, task)
        assessment, model_conf, model_reasons, trace = self._ask_model(result, task)
        reasons.extend(model_reasons)

        if assessment == Decision.REJECT.value:
            decision = Decision.REJECT
        elif flags or assessment == Decision.ESCALATE.value:
            decision = Decision.ESCALATE
        else:
            decision = Decision.PASS

        review = Review(
            step_id=result.step_id,
            decision=decision,
            confidence=model_conf,
            reasons=reasons,
            policy_flags=flags,
        )
        return review, trace

    def _heuristics(self, result: WorkResult, task: Task) -> tuple[list[str], list[str]]:
        """Deterministic policy checks over the document and worker output."""
        haystack = f"{task.content}\n{json.dumps(result.output)}"
        flags: list[str] = []
        reasons: list[str] = []

        for name, pattern in self._pii.items():
            if pattern.search(haystack):
                flags.append(f"pii:{name}")
                reasons.append(f"Possible PII detected ({name}).")

        amount = _max_amount(haystack)
        if amount >= self._value_threshold:
            flags.append("contract_value_exceeds_threshold")
            reasons.append(
                f"Monetary amount {amount:,.0f} EUR is at or above the "
                f"{self._value_threshold:,.0f} EUR threshold."
            )

        if result.confidence < self._min_confidence:
            flags.append("low_confidence")
            reasons.append(
                f"Worker confidence {result.confidence:.2f} is below the "
                f"{self._min_confidence:.2f} floor."
            )

        return flags, reasons

    def _ask_model(
        self, result: WorkResult, task: Task
    ) -> tuple[str, float, list[str], StageTrace]:
        """Query the reviewer model. Defaults to 'escalate' if it cannot be parsed."""
        prompt = _PROMPT.format(excerpt=task.content[:2000], output=result.raw)
        response = self._llm.generate(self._model, prompt, json_mode=True)
        trace = StageTrace(
            model=self._model,
            prompt=prompt,
            output=response.text,
            latency_ms=response.latency_ms,
        )
        try:
            payload = parse_json(response.text)
            assessment = str(payload.get("assessment", "escalate")).strip().lower()
            if assessment not in {d.value for d in Decision}:
                assessment = Decision.ESCALATE.value
            confidence = float(payload.get("confidence", 0.5))
            reasons = [str(r) for r in payload.get("reasons", [])]
        except (JSONParseError, ValueError, TypeError):
            return (
                Decision.ESCALATE.value,
                0.0,
                ["Reviewer response could not be parsed; escalating to be safe."],
                trace,
            )
        return assessment, confidence, reasons, trace
