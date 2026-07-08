"""The planner: turns a task into a short, typed plan.

The planner asks the model for up to five steps, then enforces the action-space
whitelist from ``policy.yaml`` itself. Any step naming an action outside the
whitelist is discarded and reported, so the planner can never smuggle an
unapproved capability into the run. This is the action-space limiting the
briefing calls for, made visible.
"""

from __future__ import annotations

from .contracts import Action, Plan, PlanStep, Task
from .llm import LLMClient, StageTrace, parse_json

_MAX_STEPS = 5

_PROMPT = """\
You plan how to process a document. Produce at most {max_steps} steps.
Each step must use exactly one of these actions: {actions}.

Return JSON only, with this shape:
{{"steps": [{{"action": "<action>", "description": "<why this step>"}}]}}

DOCUMENT:
{content}
"""


class Planner:
    """Generates and validates a plan for a task."""

    def __init__(self, llm: LLMClient, model: str, action_space: list[str]) -> None:
        self._llm = llm
        self._model = model
        # Only actions that are both in the policy whitelist and known to the
        # contract enum are admissible.
        self._allowed = {a for a in action_space if a in Action._value2member_map_}

    def make_plan(self, task: Task) -> tuple[Plan, list[str], StageTrace]:
        """Return the validated plan, the discarded action names, and a trace."""
        prompt = _PROMPT.format(
            max_steps=_MAX_STEPS,
            actions=", ".join(sorted(self._allowed)),
            content=task.content,
        )
        response = self._llm.generate(self._model, prompt, json_mode=True)
        trace = StageTrace(
            model=self._model,
            prompt=prompt,
            output=response.text,
            latency_ms=response.latency_ms,
        )

        steps, discarded = self._validate(parse_json(response.text))
        return Plan(steps=steps), discarded, trace

    def _validate(self, payload: dict) -> tuple[list[PlanStep], list[str]]:
        """Keep whitelisted steps (up to the cap); collect the rest as discarded."""
        steps: list[PlanStep] = []
        discarded: list[str] = []
        for raw in payload.get("steps", []):
            action = str(raw.get("action", "")).strip().lower()
            if action in self._allowed:
                if len(steps) < _MAX_STEPS:
                    steps.append(
                        PlanStep(
                            step_id=f"s{len(steps) + 1}",
                            action=Action(action),
                            description=str(raw.get("description", "")).strip(),
                        )
                    )
            else:
                discarded.append(action or "<empty>")
        return steps, discarded
