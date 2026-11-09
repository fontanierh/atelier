Describe the problem, the resulting behavior and any remaining validation limits.
Visual evidence: `atelier pr-media push <PR number> FILE...`, then paste the printed links here (never commit media to the branch).

Validation:

- `uv run atelier lint`
- `uv run atelier contracts check`; applicable contracts reviewed, findings fixed or false positives explained
- Focused local tests for changed behavior (none needed for documentation-only changes)
- Successful `Studio Python / Linux (macOS deferred)` CI on the exact final PR head; do not duplicate the full suite locally
- Another agent's review and any required guarded native evidence
- Paid review requested with a new `r? cc` comment once code is ready; docs-only PRs are exempt.
  For formatting-only/trivial non-code changes, use the exact-head writer declaration in docs/CODE_CONTRACTS.md.

Contract-bot findings are advisory. An agent may resolve a false positive with an explanation in the PR.
