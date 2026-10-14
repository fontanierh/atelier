# Code contracts and CI review

Atelier uses [spolu/code-contracts](https://github.com/spolu/code-contracts) to record invariants beside
the code they constrain. Every owner is `fontanierh`. Start with the root `CONTRACTS`, scoped directory
files, and [the repository skill](../.agents/skills/code-contracts/SKILL.md).

```sh
npm ci --prefix platform/studio/contracts
uv run atelier contracts check
platform/studio/contracts/node_modules/.bin/cc-check list platform/studio/atelier/build.py
```

The pinned checker requires Node 24.16+ and npm 11.11+. The wrapper checks tracked and nonignored
source files in one parser process without walking generated assets. It validates contract grammar,
duplicate IDs and Atelier's owner policy. It does **not** prove implementation behavior. Python,
TypeScript, Rust and Go declaration contracts are supported upstream; directory contracts also guide
manual and model review of C++, workflows and other file types.

Use a contract for a guarantee a caller or subsystem relies on, rather than narrating the code:

```python
def restore(...):
    """@cc [owner:fontanierh,label:correctness] complete-restoration
    A successful stamp MUST appear only after every restored file passes inventory verification.
    """
```

Contract changes and their implementation belong in the same PR. Keep one directive per declaration
docstring. Do not add notification recipients unless requested. Dust's
[contract guidance](https://github.com/dust-tt/dust/blob/main/CODE-CONTRACTS.md) and
[review workflow](https://github.com/dust-tt/dust/blob/main/.github/workflows/review-bot.yml) informed this setup.

## Review before merging

Before merging, run contract checks and review the findings on the final code. The CI checks
`Code contracts / syntax` and `Code contracts / review` are **advisory**, not required merge gates.
Agents can fix a real issue or resolve a false positive in the PR with a concrete explanation; no
owner permission or repeat model approval is needed to resolve a false positive.

The syntax check runs without secrets on GitHub-hosted CI. The review uses the pinned upstream action with
`gpt-6.1-sol`, reasoning `medium`, through `OPENAI_API_KEY` in GitHub Actions secrets. There is no model
fallback. The bot reviews applicable invariants and posts findings. A successful status means the review
completed for the captured commits, including its advisory finding count; it does not mean zero violations.
Another agent's approval and `atelier lint` remain required. Verify a successful `Studio Python / macOS`
run on the exact final PR head: CI supplies the full-suite result. Locally, run focused tests for changed
behavior; do not repeat the entire suite after successful CI or for documentation-only changes. A full local
run is reserved for diagnosing a specific integration failure or unavailable CI, with the reason recorded.
Native Unreal validation stays on a guarded machine when the change needs it; CI does not allocate render capacity.

The bot starts for ready, same-repository PRs submitted by a writer, and runs again when their head changes.
An existing status on the same head prevents another automatic paid call, including when only the base moves.
Base-only re-reviews need an explicit `r? cc` request. Fork PRs must first be moved to a maintainer-owned
branch for paid review. An authorized writer can comment exactly `r? cc` to request a new review after
reconciling a failure. Do not use GitHub's “Re-run jobs” for a paid operation.

The secret-bearing workflow runs from the trusted base and checks out its controller separately from the
PR. The pinned upstream action supplies the checker and review prompt. PR code is data: the model gets a
read-only sandbox as an unprivileged user, and the job never installs or runs the PR's programs with secrets.
The reviewed base and head must match the requested commits and still be current when the result is posted.
Both upstream's “review published” status and Atelier's commit-bound review status are informational.
The upstream action creates a per-run status that can remain pending after an interruption. Use Atelier's
`Code contracts / review` status and its linked receipt to inspect the completed or uncertain attempt.

The workflow downloads a fixed upstream revision and verifies its action-file SHA-256 before adapting it.
The adapter pins its nested GitHub actions, pins Codex CLI and its API proxy to the same version, and disables
dependency lifecycle scripts and automatic npm caching during the checker install. Its GitHub actions use
Node 24; upgrading `setup-node` must not enable its newer automatic caching default. The upstream review code
and prompt remain unchanged. The pinned Codex action has its own Node 24 setup with automatic cache detection:
all checkouts stay in subdirectories, and a pre-submission check refuses a root `package.json` that could enable
that cache. Revisit the nested action's configuration before changing this workspace layout.
Updating the upstream revision requires reviewing and updating the expected hash and tool pins together.

Every attempt records `atelier.ai.ledger` submission intent and uploads it **before** the provider action.
An always-run step records completion or uncertainty and uploads the final receipt. Hard runner loss may leave
only the submitted artifact; treat that as uncertain. Receipts are retained for 90 days. A repeated workflow
attempt cannot submit another paid request automatically. The persistent commit status prevents resubmission
across runners; the local ledger's exclusive creation protects its path within one run.

## GitHub event policy

GitHub's [default public-repository policy](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
blocks `pull_request_target` from November 2, 2026. This bot needs a trusted base workflow with a provider secret
and permission to post reviews. Keep its controller on `pull_request_target`: changing it to `pull_request` would
let a same-repository PR change the secret-bearing workflow before review.

The reviewed [event policy](../.github/policies/contract-review.json) allows only `pull_request_target` and
`issue_comment`, scoped to `.github/workflows/contract-review.yml`. The workflow still checks the human writer,
same-repository head, draft state and prior paid attempt. Other workflow paths retain their own applicable policies.
The JSON file documents the intended repository setting; GitHub does not apply it just because it is committed.

A repository administrator installs it using the [Actions policies API](https://docs.github.com/en/rest/actions/policies):

```sh
gh api repos/{owner}/{repo}/actions/policies
# Create only if "Contract review events" is absent; otherwise PUT its existing ID.
gh api --method POST repos/{owner}/{repo}/actions/policies --input .github/policies/contract-review.json
gh api repos/{owner}/{repo}/actions/policies/POLICY_ID
```

Check the returned enforcement, exact workflow path and allowed events against the file. Update the policy in
the same change as a workflow rename or trigger change. Do not broaden it to all workflows to suppress a warning.

## Initial rollout

The bot workflow becomes active when it reaches the default branch. Keep the local contract-review rule
during bootstrap. Do not add contract checks to branch protection: they are advisory by design.
Installing the secret does not run a paid review by itself. Native builds and playtest releases retain
their existing coordination and safety requirements.
