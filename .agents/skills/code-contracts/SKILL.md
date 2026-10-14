---
name: code-contracts
description: Discover, maintain and verify Atelier code contracts when changing or reviewing code.
---

# Code contracts in Atelier

Use the [upstream specification and skill](https://github.com/spolu/code-contracts/blob/main/skills/code-contracts/SKILL.md)
for contract grammar and verification. Atelier pins its checker in `platform/studio/contracts`.

Before changing code, read applicable ancestor `CONTRACTS` files and the contracts attached to the
changed declarations. Follow relevant callees and callers when the change relies on their guarantees.
Use `platform/studio/contracts/node_modules/.bin/cc-check list path/to/source.py:42` for discovery.

Write a contract for a concrete invariant or material assumption. Put a shared rule in the narrowest
applicable `CONTRACTS` file; put a local rule in its declaration docstring. One directive per docstring.
Always use `owner:fontanierh`. Do not add notification recipients without an explicit request.

When behavior changes intentionally, update its contract in the same change. Do not weaken a contract
to conceal a defect. Backfill a missing contract when a change depends on an important implicit guarantee.

Run `uv run atelier contracts check` after edits. It checks syntax and owners only. Semantic review must
compare the final diff with the applicable contracts, including data flow and relevant callers. Report
specific violations with evidence and a concrete fix; do not claim the checker proves the prose true.
For C++ and other languages unsupported by `cc-check`, read directory contracts and review the code directly.

Before merging, follow [the contract and CI guide](../../../docs/CODE_CONTRACTS.md), check contracts,
obtain another agent's approval, and run the required local checks. Bot findings are advisory:
fix real defects and resolve false positives in the PR with a specific explanation. Contract CI
is not a required merge gate, and an agent may resolve a false positive without asking the owner.
