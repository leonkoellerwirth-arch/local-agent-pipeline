"""Reviewer heuristics and the human gate — the governance-critical paths."""

from __future__ import annotations

import io

from rich.console import Console

from agent_pipeline.contracts import Action, Decision, HumanDecision, Review, Task, WorkResult
from agent_pipeline.gate import Gate
from agent_pipeline.llm import LLMClient
from agent_pipeline.reviewer import Reviewer, _max_amount, _parse_amount
from conftest import ScriptedBackend, make_llm

CONTRACT = (
    "Total contract value is EUR 150,000. Contact billing@example-contractor.test. "
    "IBAN: DE89 3704 0044 0532 0130 00."
)
BENIGN = "A short internal note with no sensitive data and no monetary amounts."


def _task(content: str) -> Task:
    return Task(run_id="r1", input_path="x.txt", content=content)


def _result(confidence: float = 0.9) -> WorkResult:
    return WorkResult(
        step_id="s1", action=Action.EXTRACT, output={"ok": True}, confidence=confidence, raw="{}"
    )


def _reviewer(policy_cfg: dict, assessment: str = "pass") -> Reviewer:
    backend = ScriptedBackend(reviewer_assessment=assessment)
    return Reviewer(make_llm(backend), "reviewer-model", policy_cfg)


# --- amount parsing -------------------------------------------------------
def test_parse_amount_european_and_us_formats():
    assert _parse_amount("150,000") == 150000.0
    assert _parse_amount("1.500.000") == 1500000.0
    assert _parse_amount("1.250.000,00") == 1250000.0
    assert _parse_amount("150,000.50") == 150000.5


def test_max_amount_picks_largest_eur_value():
    assert _max_amount("fees of EUR 37,500 and total EUR 150,000") == 150000.0
    assert _max_amount("no money here") == 0.0


# --- reviewer heuristics --------------------------------------------------
def test_contract_triggers_pii_and_value_flags(policy_cfg):
    review, _ = _reviewer(policy_cfg).review(_result(), _task(CONTRACT))
    assert "pii:email" in review.policy_flags
    assert "pii:iban" in review.policy_flags
    assert "contract_value_exceeds_threshold" in review.policy_flags
    assert review.decision is Decision.ESCALATE


def test_benign_document_passes(policy_cfg):
    review, _ = _reviewer(policy_cfg, assessment="pass").review(_result(), _task(BENIGN))
    assert review.policy_flags == []
    assert review.decision is Decision.PASS


def test_low_confidence_escalates_even_when_clean(policy_cfg):
    review, _ = _reviewer(policy_cfg).review(_result(confidence=0.2), _task(BENIGN))
    assert "low_confidence" in review.policy_flags
    assert review.decision is Decision.ESCALATE


def test_model_reject_overrides_clean_heuristics(policy_cfg):
    review, _ = _reviewer(policy_cfg, assessment="reject").review(_result(), _task(BENIGN))
    assert review.decision is Decision.REJECT


def test_unparseable_reviewer_response_escalates(policy_cfg):
    # A backend that never returns valid JSON: the reviewer must fail safe.
    llm = LLMClient({"host": "unused"}, backend=lambda model, prompt, json_mode: "garbage")
    reviewer = Reviewer(llm, "m", policy_cfg)
    review, _ = reviewer.review(_result(), _task(BENIGN))
    assert review.decision is Decision.ESCALATE


# --- gate -----------------------------------------------------------------
def _gate(choice: str, text: str = "because") -> Gate:
    console = Console(file=io.StringIO(), force_terminal=False)
    return Gate(
        console=console, prompt_choice=lambda choices: choice, prompt_text=lambda label: text
    )


def _review() -> Review:
    return Review(
        step_id="s1", decision=Decision.ESCALATE, confidence=0.5, policy_flags=["pii:email"]
    )


def test_gate_approve_keeps_result():
    outcome = _gate("approve").request(_result(), _review())
    assert outcome.decision is HumanDecision.APPROVE
    assert outcome.result.output == {"ok": True}
    assert outcome.reason == "because"


def test_gate_reject():
    outcome = _gate("reject").request(_result(), _review())
    assert outcome.decision is HumanDecision.REJECT


def test_gate_edit_replaces_output():
    console = Console(file=io.StringIO())
    texts = iter(['{"ok": false, "edited": true}', "human correction"])
    gate = Gate(
        console=console,
        prompt_choice=lambda choices: "edit",
        prompt_text=lambda label: next(texts),
    )
    outcome = gate.request(_result(), _review())
    assert outcome.decision is HumanDecision.EDIT
    assert outcome.result.output == {"ok": False, "edited": True}


def test_gate_edit_keeps_original_on_bad_json():
    console = Console(file=io.StringIO())
    texts = iter(["not json", "reason"])
    gate = Gate(
        console=console,
        prompt_choice=lambda choices: "edit",
        prompt_text=lambda label: next(texts),
    )
    outcome = gate.request(_result(), _review())
    assert outcome.result.output == {"ok": True}
