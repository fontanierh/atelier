# Decisions

Short records of real deviations from, or choices left open by, [the V2 plan](../../../docs/YORIMICHI_V2_PLAN.md).
Newest last. Each says what was decided, why, and what would reopen it.

## D01 — Baseline identities (P0)

- **Source baseline:** `7eec0f98dd02c9505d3870336717b3edf830be73` (main, 6 November 2026).
- **Reference release:** `yorimichi-macos-2026-10-23-r13`, built at `bd5382b1`, which is `main` at `7f3c0a8f` plus two
  build-system fixes. Its manifest, `package-manifest.json`, `SHA256SUMS` and `verification.json` stay on the GitHub
  release; they are not copied into the repository.
- 114 commits touch `games/yorimichi` or `platform/engine` between `bd5382b1` and the source baseline. V2 ports the
  source baseline. The release is a play reference only: where its behavior and the baseline's differ, the
  inventory row records which one V2 follows.

## D02 — No editable donor project exists; build one once (P0.3)

A search of this machine found no completed editable Yorimichi Unreal project. The checkouts that still have
`games/yorimichi/unreal/Content` hold only small V2 experiments (at most 40 packages). Every earlier full build
was cleaned up. A cooked release cannot be turned back into editable packages.

**Route:** run the original pipeline once, at the source baseline, in a dedicated migration workspace
(`atelier-yv2-donor`, detached at the baseline). Use the normal guarded `atelier build yorimichi` and the machine's
existing verified build cache. That build's `Content` is the donor. V2 copies packages from it, keeping their
`/Game/...` paths, and never edits the donor in place. After copying, V2 no longer needs that workspace; it is kept
only as a recovery reference until P6.

## D03 — Development hosts (P0.5)

- **Primary:** this machine, an Apple-silicon Mac running the pinned Unreal 5.8 (see [TOOLCHAIN.md](TOOLCHAIN.md)).
- **Collaborator ("the brother"):** the tailnet lists one macOS machine for a second account, and a Windows device
  that has been offline for 29 days. The working assumption is a **macOS** collaborator. The Windows route is:
  **Windows workers do code and review only. All Unreal work uses owned workspaces on a supported Mac.** A
  Windows launch/admission adapter is out of scope unless a Windows host is actually assigned.
- **Second machine for C02/C06/P3.4/P6.4/P7.3:** none is reachable from this session. The second Mac is offline,
  and the owner's laptop refuses SSH. These checks stay **blocked**, not substituted. A fresh clone on the same
  machine does not count as a second machine (plan §12, P3 stop rule).

## D04 — Bootstrap binary-content writer (§9)

Until P2-B's claim service passes and adopts or releases every bootstrap lock, the **only** V2 binary-content
writer on all machines is the owner `jim-macbook-5`, in workspace `atelier-yv2`. Other workers may change text
code only. This record is the task record visible to every worker.
