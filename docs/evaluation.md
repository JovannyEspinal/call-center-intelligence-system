# Evaluation

This project uses deterministic evaluation checks rather than LLM-as-judge
scoring. The goal is to prove safety, routing, schema completeness, and demo
readiness on persisted outputs.

## Run

After at least one successful analysis has been persisted:

```bash
make eval-demo
```

To evaluate a specific report:

```bash
uv run python scripts/evaluate_demo_outputs.py \
  --database data/calls.db \
  --analysis-id analysis-...
```

## Checks

The harness verifies:

- the report has a successful terminal status;
- report-facing text does not match raw sensitive-value patterns;
- the redacted transcript has enough segments;
- the unknown speaker ratio is under the configured threshold;
- summary fields are present;
- all five QA dimensions are present and the weighted score is valid;
- privacy-event context excerpts do not contain raw sensitive values.

## Scope

The harness intentionally does not grade prose quality or use another LLM as a
judge. Those would add cost and nondeterminism. For this project, deterministic
checks give stronger evidence that the pipeline is safe and demo-ready.
