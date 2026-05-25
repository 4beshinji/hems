# HEMS Eval Artifacts

`infra/eval/` contains local model evaluation tooling and a small tracked benchmark history.

Tracked files under `infra/eval/results/*.jsonl`, `infra/eval/results/_progress.json`, and
`infra/eval/eval.log` are retained intentionally as historical evaluation artifacts. They are not runtime
state for the HEMS services.

If a future run should replace this history, update the files deliberately in the same change as the model
or scenario update being evaluated. If eval output becomes too large or machine-specific, move it to an
ignored output directory in a separate repository-hygiene change.
