# Expected outputs

Local models are not deterministic, so the exact classification labels,
extracted fields, and summary wording will vary between runs and between
models. What is **reproducible** is the pipeline's control flow: which risk
triggers fire and therefore whether a run passes cleanly or is escalated to the
human gate. Those deterministic expectations are captured in the JSON files
here and are exactly what the test suite asserts (with mocked models).

- `sample-report.json` — the benign report: no triggers fire, the reviewer
  passes it, the run completes without human involvement.
- `sample-contract.json` — the draft contract: PII and the contract-value
  threshold fire, the reviewer escalates, and the run pauses at the gate.

## Rendered artifacts

So you can see the payoff without installing Ollama, these are committed too:

- `sample-report.jsonl` / `sample-contract.jsonl` — full audit trails. They are
  hash-chained; verify them with `agent-pipeline audit <file> --verify`.
- `sample-contract-audit.svg` — the `agent-pipeline audit` render of the
  contract trail.
- `sample-contract-gate.svg` — the human-review gate panel.

These were produced by `scripts/render_examples.py`, which drives the real
pipeline with a **mocked** model (the same approach as the test suite). The
policy flags, escalation decision, and hash chain are genuine; only the model's
free-text output is canned, and it is stored only as a hash. Regenerate them
with `python scripts/render_examples.py`.

If you run the examples against a live Ollama model, expect the `flags` and the
escalation behaviour to match; the free-text content (and therefore the content
hashes) will differ.
