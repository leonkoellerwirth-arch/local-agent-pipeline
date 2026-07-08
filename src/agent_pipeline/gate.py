"""The human-in-the-loop gate.

When the reviewer escalates, the run pauses here. A human sees the finding, the
reason, and the raw output, then chooses to approve, reject, or edit the result.
Nothing risky reaches the end of the pipeline without this decision — that is
the whole point of the gate.

The prompts are injected so the flow can be driven by a test with canned
answers; there is no hidden dependency on a live terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .contracts import HumanDecision, Review, WorkResult
from .llm import parse_json


@dataclass
class GateOutcome:
    """The human's decision, the (possibly edited) result, and their reason."""

    decision: HumanDecision
    result: WorkResult
    reason: str


class Gate:
    """Presents an escalation to a human and captures their decision."""

    def __init__(
        self,
        console: Console | None = None,
        prompt_choice: Callable[[list[str]], str] | None = None,
        prompt_text: Callable[[str], str] | None = None,
    ) -> None:
        self._console = console or Console()
        self._prompt_choice = prompt_choice or self._default_choice
        self._prompt_text = prompt_text or (lambda label: Prompt.ask(label))

    def _default_choice(self, choices: list[str]) -> str:
        return Prompt.ask("Decision", choices=choices, default=HumanDecision.REJECT.value)

    def request(self, result: WorkResult, review: Review) -> GateOutcome:
        """Show the escalation and return the human's decision."""
        self._render(result, review)
        choice = self._prompt_choice([d.value for d in HumanDecision])
        decision = HumanDecision(choice)

        edited = result
        if decision is HumanDecision.EDIT:
            edited = self._edit(result)

        reason = self._prompt_text("Reason for this decision").strip()
        return GateOutcome(decision=decision, result=edited, reason=reason)

    def _render(self, result: WorkResult, review: Review) -> None:
        flags = ", ".join(review.policy_flags) or "none"
        reasons = "\n".join(f"  • {r}" for r in review.reasons) or "  (none given)"
        body = (
            f"[bold]Step:[/bold] {result.step_id} ({result.action.value})\n"
            f"[bold]Reviewer decision:[/bold] {review.decision.value}\n"
            f"[bold]Policy flags:[/bold] {flags}\n"
            f"[bold]Reasons:[/bold]\n{reasons}\n\n"
            f"[bold]Raw worker output:[/bold]\n{result.raw}"
        )
        self._console.print(Panel(body, title="⚠  Human review required", border_style="yellow"))

    def _edit(self, result: WorkResult) -> WorkResult:
        """Let the human replace the output JSON; keep the original on parse failure."""
        raw = self._prompt_text("New output as JSON (blank to keep original)").strip()
        if not raw:
            return result
        try:
            output = parse_json(raw)
        except ValueError:
            self._console.print("[red]Could not parse JSON; keeping original output.[/red]")
            return result
        return result.model_copy(update={"output": output, "raw": raw})
