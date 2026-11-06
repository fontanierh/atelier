# Yorimichi V2 collaboration tests (plan §13)

One row per test: the revision it ran at, the workspaces and commands, and the evidence. A failed test stays
listed until its fix and rerun are linked. "Blocked" names the missing prerequisite (DECISIONS D03: no second
machine is reachable from this one, so the two-machine rows wait for a collaborator's machine).

| Test | Status | Revision | Evidence |
| --- | --- | --- | --- |
| C01 one machine, three agents | not run | | needs the slice content (P3) |
| C02 two machines, four workers | blocked | | D03: no second machine |
| C03 human editor workflow | not run | | needs the slice content (P3) |
| C04 handoff | not run | | needs the first targeted import |
| C05 warm no-op | pass (test map) | e56b885da9 | warm check + compile: up to date in 1 s, no authoring step; `editor.run` with `Scripts/open_close.py` opened TestMinimal in 27 s, dirty packages after open: none; `git status` unchanged before and after. Rerun on the slice map. |
| C06 clean second-machine checkout | partial | e56b885da9 | LFS round trip on this machine: a fresh `--depth 1` clone (227 s) holds pointers, and the check reports NOT_HYDRATED for all 7 files with the pull to run; `git lfs pull` skipped everything until `git lfs install --local` (now in the README and the check's hint); then the pull took 1 s, `check.py --full` passed with 7 files hashed, and the map is byte-identical. Compile, open and package on a second machine are blocked (D03). |
| C07 same-asset requests | unit + real LFS | PR #732 | `test_claims.py` (different/same account), `test_claims_lfs_integration.py` against the GitHub LFS API |
| C08 same-region new actors | unit | PR #732 | region scopes in `test_claims.py`; save validation refuses another region's actor (`test_save_validate.py`) |
| C09 stale base | unit + real LFS | PR #732 | `stale_base` refusal in `test_claims.py` and the integration test |
| C10 service unreachable | unit | PR #732 | fail-closed and partial-acquisition cases in `test_claims.py` |
| C11 crash and restart | unit | PR #732 | restart/reconcile cases in `test_claims.py` |
| C12 import crash | unit | | `test_import_run.py` journal restore cases |
| C13 delete/rename/move | unit | | `test_changeset.py` |
| C14 undeclared shared scope | unit | | `test_changeset.py` out-of-scope write |
| C15 missing payload, stale source, corrupt output | pass (test map; stale source in unit tests) | f1d2b1529a | on the real test map in a clean clone: one flipped byte in `TestMinimal.umap` → OUTPUT_CHANGED, a deleted HLOD layer → MISSING, an actor package restored to its LFS pointer → NOT_HYDRATED with the exact pull; exit 1, nothing regenerated, and after restoring, `check.py --full` passes with 7 files hashed. The hint for a changed or lost editor package now says to restore unless the change is a claimed edit (recording it would have stamped corrupt bytes as current). SOURCE_CHANGED: `test_content_check.py`, real import pending. |
| C16 two live sessions plus stale record | partial pass (native) | PR #733 (merged) | unit: `test_live_sessions.py` with two fake bridges. Native, two `atelier play yorimichi_v2 --profile test` launches: each got its own session record and loopback port (26874, 26981); game A's bridge answered and `atelier live --session ID py -` ran inside it (PID 42089); with two records and no `--session` the CLI refused ("pass --session ID"); after stopping game A its session was refused ("no live session"), and `--prune` removed the stale records. Found and fixed on the way: the bridge started only once a player pawn was ready, so a map without world data never listened; `AJapanGameMode::BeginPlay` now starts it. Not yet shown: both games answering at once, and screenshots. Game B waited in the capacity queue the whole 20 minutes while the donor build held the CPU (admission working, not bypassed); rerun once the donor is done. |
| C17 pushed, not merged | unit | PR #732 | claims release only on merge or cancel |
| C18 push or LFS upload fails | partial pass | f1d2b1529a | in a scratch clone with `.githooks`, a commit carrying a new LFS package was pushed with LFS pointed at an unreachable endpoint: `git lfs pre-push` failed the batch upload ("connection refused"), the push exited 1, `git ls-remote` shows the branch never reached origin, and the commit and the 4 KB local package stayed. Claim retention on failure is the claims service rule (release only on merge or cancel, PR #732). Not yet run: the retry that reconciles before pushing again (needs a sandbox remote, not the public repository). |
| C19 shared definition update | not run | | needs adopted content |
| C20 cancel a guarded build | pass (test map) | f1d2b1529a | a guarded `editor.run` holding the editor (`Scripts/hold.py`) was cancelled with SIGTERM 16 s in: the build reported "BUILD INTERRUPTED during editor.run; completed steps stay published", its editor child (UnrealEditor-Cmd) was gone within 1 s, the hold script never finished, another owner's running build (the donor, same machine) kept its PID and kept running, and `git status` was unchanged. The next guarded editor run was admitted at once. |

Unit rows prove the logic; each still needs its run on the slice (plan §13: "a simulation of lock logic does not
replace actual LFS/server integration tests").
