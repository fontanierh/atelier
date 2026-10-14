Describe the problem, the resulting behavior and any remaining validation limits.

Validation:

- `uv run atelier lint`
- `uv run atelier contracts check`; applicable contracts reviewed, findings fixed or false positives explained
- `uv run pytest -q` on the final branch
- Another agent's review and any required guarded native evidence

Contract-bot findings are advisory. An agent may resolve a false positive with an explanation in the PR.
