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

If you run the examples against a live Ollama model, expect the `flags` and the
escalation behaviour below to match; the free-text content will differ.
