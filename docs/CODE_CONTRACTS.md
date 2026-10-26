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
Owner notifications about edited contracts render as `cc @owner`; upstream ignores their body, which may be empty.
They count as comments, not violations; violation comments must contain an explanation.
Another agent's approval and `atelier lint` remain required. Verify a successful `Studio Python / Linux
(macOS deferred)` run on the exact final PR head (for a PR that changes only `games/hakuba/`, the `Hakuba`
workflow instead): this aggregate check fails unless `quality` and the two
Linux test shards (studio, games) pass. The macOS-only board job and the macOS render hosts are deferred to
final validation (owner 2026-10-23), so this check does not cover the darwin board server, macOS T0/T1a, APFS,
the sandbox or libproc. CI supplies the full-suite result, with per-group test lists and timings. Locally, run focused tests
for changed behavior; do not repeat the entire suite after successful CI or for documentation-only changes. A full local
run is reserved for diagnosing a specific integration failure or unavailable CI, with the reason recorded.
Native Unreal validation stays on a guarded machine when the change needs it; CI does not allocate render capacity.

## Requesting a paid review

Paid review is **manual only**: an authorized repository writer account posts a new PR comment
containing exactly `r? cc` when an open, same-repository code PR is ready (not a draft). Agents must request it for every
ready code PR. Batch intermediate edits before requesting; opening, pushing, reopening or marking a PR
ready never starts a paid call. After substantive changes to reviewed code, explicitly request another
review of the ready revision. A resolved false positive or wording-only edit does not require another call.
Do not edit an existing comment to trigger review, and do not use GitHub's “Re-run jobs” for a paid operation.
Reconcile a failed or uncertain attempt before requesting another; each new request can incur a charge.
Fork PRs must first move to a maintainer-owned branch for paid review.

**Exemptions:** documentation-only, formatting-only and trivial non-code PRs need neither a paid request
nor a missing-request warning. The lightweight reminder recognizes `.md` and `.rst` files, and PNG/JPEG/WebP/GIF
files under `docs/`, automatically. Both sides of a rename must qualify, and the API's complete changed-file
count must match. Unknown files, configuration and dependency changes are not automatically exempt.
For a formatting-only or other trivial non-code change outside that set, a writer posts:

```text
cc: exempt FULL_HEAD_SHA
Explain concretely why this revision does not change behavior.
```

Use the full current head SHA. This declaration expires on the next push, so it cannot silently exempt new
code. Whitespace alone is not proof of unchanged behavior (Python indentation can change execution).
Never declare behavior changes trivial. Independent peer review, contract checks and exact-head Python CI
still apply to exempt PRs.

A separate, metadata-only workflow maintains one **Paid review** PR comment. It warns on ready code PRs
without a recorded paid review on that head or an applicable exemption. It updates on PR and comment
changes, makes no provider call and has no provider secret. Only the current head's
`Code contracts / review` status proves the request was accepted; arbitrary or edited request comments
do not clear the warning. Acceptance is not review completion or approval.
A new head without that status warns again: batch intermediate edits before requesting on the ready code,
or declare an exact-head trivial exemption when appropriate. The paid workflow refreshes the notice after
accepting a request; a reminder failure cannot block the paid review. A request made while draft must be
posted again once ready. Check the status and receipt for the exact reviewed commits. The notice is advisory
and never a required merge check. Existing pre-migration review statuses count, avoiding duplicate charges.

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
attempt cannot submit another paid request automatically. Only a newly created writer request comment may
start a fresh workflow submission; the local ledger's exclusive creation protects its path within one run.
Automatic PR events cannot submit a paid call.

## Token usage and spend

The trusted workflow captures the pinned Codex CLI's `--json` stream while preserving its final review
output and exit status. Only validated numeric `turn.completed.usage` counters enter the final ledger:
input, cached input, output, and reasoning output where reported. Model/tool text is not copied into the
receipt. An interrupted stream retains any observed usage as partial; absent counters are unknown, not zero.
The action and CLI versions remain pinned, the model remains unprivileged/read-only, and there is no paid retry.

Each run's **Paid contract review** job summary shows the counters and a standard list-price estimate.
The final `contract-review-final-RUN_ID` artifact retains that information with the exact model, pricing
date/source, assumptions, run ID and reviewed SHAs. Download the receipts you want to total:

```sh
gh run download RUN_ID -n contract-review-final-RUN_ID -D receipts/RUN_ID
uv run python -m atelier.ai.usage summary receipts/*/ledger.json
```

The command reads only supplied local files, makes no provider calls, and counts a submitted/final CI
receipt pair once by run ID. Its totals include priced-operation coverage, unknown-cost counts and partial
usage. It is a total of the supplied receipts, not a claim that the entire account or history is covered.
Old receipts cannot yield exact tokens that were never retained; downloading them will show unknown cost.
Do not rerun a paid review to reconstruct missing usage.

The initial rate snapshot is [GPT-6.1 Sol standard pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
checked 2026-10-16: $2 input, $0.10 cached input and $10 output per million tokens. Cached input is included
in input, and reasoning is included in output; neither is charged twice. The estimate assumes short-context
standard rates and excludes cache-write surcharges, regional premiums, taxes and account discounts.
CLI aggregate counters do not establish every request's context tier, service tier or cache-write billing,
so this is explicitly an estimate, not an exact invoice. A turn may contain multiple provider requests;
its combined input count alone cannot select the long-context rate for those requests. The receipt's
pricing assumptions retain these limits. See [the CLI event format](https://learn.chatgpt.com/docs/non-interactive-mode).

The same summary accepts existing image provenance and Tripo job receipts. `atelier.ai.images.paint` already
retains provider token usage, and Tripo job receipts retain `credits_consumed` when supplied by the provider.
Those counters/credits are totaled separately; image USD prices and a Tripo credit-to-currency conversion
are not guessed. Unknown prices remain visible. Identical copied receipts and Tripo task IDs count once.

## GitHub event policy

The paid workflow runs only on `issue_comment`, whose controller comes from the default branch. Never
change it to `pull_request`: PR code must not control a secret-bearing review job. The lightweight reminder
uses `pull_request_target` and `issue_comment`, checks out only its trusted base controller and reads GitHub
metadata; it never checks out or runs PR programs and has no provider credentials.

The reviewed [paid event policy](../.github/policies/contract-review.json) allows only `issue_comment`,
scoped to `.github/workflows/contract-review.yml`. The separate
[reminder policy](../.github/policies/contract-review-notice.json) allows `pull_request_target` and
`issue_comment` only for `.github/workflows/contract-review-notice.yml`. The paid workflow still checks the
human writer, same-repository head, draft state and prior workflow attempt.
The JSON file documents the intended repository setting; GitHub does not apply it just because it is committed.

A repository administrator installs it using the [Actions policies API](https://docs.github.com/en/rest/actions/policies):

```sh
gh api repos/{owner}/{repo}/actions/policies
# For each policy, create only if its name is absent; otherwise PUT its existing ID.
gh api --method POST repos/{owner}/{repo}/actions/policies --input .github/policies/contract-review.json
gh api --method POST repos/{owner}/{repo}/actions/policies --input .github/policies/contract-review-notice.json
gh api repos/{owner}/{repo}/actions/policies/POLICY_ID
```

Check the returned enforcement, exact workflow path and allowed events against the file. Update the policy in
the same change as a workflow rename or trigger change. Do not broaden it to all workflows to suppress a warning.

## Initial rollout

The bot workflow becomes active when it reaches the default branch. Keep the local contract-review rule
during bootstrap. Do not add contract checks to branch protection: they are advisory by design.
Installing the secret does not run a paid review by itself. Native builds and playtest releases retain
their existing coordination and safety requirements.
