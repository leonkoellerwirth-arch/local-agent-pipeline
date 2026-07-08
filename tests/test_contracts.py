"""Contracts are the pipeline's guarantees — test that they actually bind."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_pipeline.contracts import (
    Action,
    Actor,
    AuditEvent,
    Decision,
    Plan,
    PlanStep,
    Review,
    Task,
    WorkResult,
)


def test_action_space_is_exactly_three():
    assert {a.value for a in Action} == {"classify", "extract", "summarize"}


def test_plan_step_coerces_action_string():
    step = PlanStep(step_id="s1", action="classify", description="d")
    assert step.action is Action.CLASSIFY


def test_plan_step_rejects_unknown_action():
    with pytest.raises(ValidationError):
        PlanStep(step_id="s1", action="delete", description="d")


def test_plan_capped_at_five_steps():
    steps = [PlanStep(step_id=f"s{i}", action=Action.CLASSIFY, description="d") for i in range(6)]
    with pytest.raises(ValidationError):
        Plan(steps=steps)


def test_work_result_confidence_bounds():
    with pytest.raises(ValidationError):
        WorkResult(step_id="s1", action=Action.CLASSIFY, output={}, confidence=1.5, raw="{}")


def test_review_defaults_are_empty_lists():
    review = Review(step_id="s1", decision=Decision.PASS, confidence=0.9)
    assert review.reasons == []
    assert review.policy_flags == []


def test_audit_event_has_timezone_aware_timestamp():
    event = AuditEvent(run_id="r1", actor=Actor.SYSTEM, action="run_start")
    assert event.timestamp.tzinfo is not None


def test_task_records_source_and_content():
    task = Task(run_id="r1", input_path="a.txt", content="hello")
    assert task.input_path == "a.txt"
    assert task.content == "hello"
