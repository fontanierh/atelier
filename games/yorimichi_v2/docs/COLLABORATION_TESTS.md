# Yorimichi V2 collaboration tests (plan §13)

One row per test: the revision it ran at, the workspaces and commands, and the evidence. A failed test stays
listed until its fix and rerun are linked. "Blocked" names the missing prerequisite (DECISIONS D03: no second
machine is reachable from this one, so the two-machine rows wait for a collaborator's machine).

| Test | Status | Revision | Evidence |
| --- | --- | --- | --- |
| C01 one machine, three agents | harness (no Unreal) | | `tests/test_collaboration_harness.py`: three agents in their own Git worktrees, each under a disjoint fake claim (asset, editor-owned material, region), write through import, the build's editor guard and save validation, and land on main in sequence with no conflict, a clean change-set report and a clean content check after each merge; writes outside a claim, a new actor before its lock, D04 inside a claimed checkout and a stray committed edit are refused. Rerun on the slice with real claims and Unreal. |
| C02 two machines, four workers | blocked | | D03: no second machine |
| C03 human editor workflow | not run | | needs the slice content (P3) |
| C04 handoff | harness (no Unreal) | | `tests/test_collaboration_harness.py`: agent A imports under a claim and commits, the coordinator transfers the claim to B, who continues A's branch; A's next import is refused before any write and B's result lands with a clean report and content check. Rerun with the real `recover --action transfer` and LFS locks. |
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
| C19 shared definition update | harness (no Unreal) | | `tests/test_collaboration_harness.py`: a claimed save of a shared material makes the check report exactly its direct `input_dependencies` dependents STALE_IMPORT and the import plan add the transitive one, nothing else; two dependent owners reimport under their own claims and main checks clean, with unrelated records and packages byte-identical. Rerun on adopted content. |
| C20 cancel a guarded build | pass (test map) | f1d2b1529a | a guarded `editor.run` holding the editor (`Scripts/hold.py`) was cancelled with SIGTERM 16 s in: the build reported "BUILD INTERRUPTED during editor.run; completed steps stay published", its editor child (UnrealEditor-Cmd) was gone within 1 s, the hold script never finished, another owner's running build (the donor, same machine) kept its PID and kept running, and `git status` was unchanged. The next guarded editor run was admitted at once. |
| C21 claimed new actors after D04 closes | pass (native, one machine) | main fa63a342cd plus the claims change of PR #739, in a scratch branch | Unit: `tests/test_d04.py`. Native run with Unreal and the real claims service and GitHub LFS locks, recorded under "C21 native run" below. |

Unit rows prove the logic; each still needs its run on the slice (plan §13: "a simulation of lock logic does not
replace actual LFS/server integration tests").

## P3 targeted edits on the slice (plan P3 step 2)

These are measured on the reference Mac, with a warm editor build. Each edit is guarded and admitted. Each was
checked with `git status`: nothing outside its write set changed.

| Edit | Command | Wall time | Written |
|---|---|---|---|
| Mesh import: `prop/lantern` from its committed FBX (`assets/props/lantern/src/Lantern.fbx`) | `tools/import/run.py prop/lantern` | 30 s (editor 28.5 s) | `Japan/Assets/Lantern.uasset` and its record. Import data keeps only the repo-relative source path |
| Same import again, unchanged | same | 1 s, no Unreal | nothing |
| Actor placement: one `w01-start` lantern patch moved 30 cm east | `editor.run` with `Scripts/move_actor.py` | 31 s (editor 29.9 s) | that actor's OFPA package; then `save_validate.py region/w01-start` (1 changed) |
| C++ feature: `UYorimichiLive::Travel` (the game's travel, which leaves swim/ride states) | the `unreal.compile` build step | 27 s incremental | the editor module binaries (not committed) |

These first edits ran as the D04 bootstrap writer. The claimed versions belong to C01, C03 and C21.

`tools/test/route.py` passed again after the C++ edit, now starting through `Travel` (falling, then walking).
At that point, the running slice game's static scenery was all saved: 510 `V2ScenePatch` and 9 `StaticMeshActor`
OFPA actors, and `JapanWorld` spawned no meshes. Feature actors are still spawned at runtime: the `SkatePark`
(the skate pier, from `skatepark/park.json`, 20 mesh components), 3 `SwordTrainer`s and the `FoxHunter`. They
become saved, placed actors with the gameplay features in P4.

The first real import found that `import.<id>` was no valid build step name (`/` is not allowed). Import steps are
now named `import.` plus the ID with `.` for `/` (`records.import_step`), and a collision fails the build.

## C21 native run

This ran on 2026-11-07 in a scratch branch with `governance.toml` `closed = true`. The local claims service
backed the run, and the locks were real GitHub LFS locks. Agent `jim5-c21` held task C21-T1, with scope
`region/test-minimal` and locks on the TestMinimal map and its 4 existing actors. With region/test-minimal as its
own environment, the migration placed the whole island's scenery: 1015 scene patches in 1025 new OFPA packages.

| Step | Result |
|---|---|
| The bootstrap writer without `--claim` | refused in 0 s, before the editor |
| Claimed migration (`tools/migrate/run.py region/test-minimal --environment region/test-minimal --claim C21-T1`) | rc 0 in 200 s (editor 190 s, including binding). All 1025 created files were bound with `claims extend --lock-path … --acquire`; 1032 locks were verified on GitHub (`git lfs locks`); `claims: ok (1025 changed paths, stage publish)`; the region record was written (1025 changed) |
| A second agent (`jim5-c21b`, task C21-T2) requests `region/test-minimal` | refused: `overlap` |
| The same agent, holding `region/w01-start`, migrates test-minimal with `--claim C21-T2` | refused in 0 s, before the editor: no claim whose scopes cover region/test-minimal |
| Cleanup | both claims cancelled as discarded; their locks released through the LFS API |

The first attempt failed after the editor finished. Binding locked the 1025 paths one at a time with `git lfs
lock` (about 0.6 locks/s). Activation then verified each of 507 locks with its own remote listing and passed the
client's 30 s timeout. The cleanup removed every created file and left no unbound write behind, as designed;
the leftover locks were released afterwards.

PR #739 made three changes:
- Clients lock through the LFS locking API with the checkout's git credential.
- Up to 8 paths are locked at once.
- A claim with more than 20 locks is verified against one listing.

The rerun locked at about 8 locks/s. Concurrent `git lfs lock/unlock` commands corrupt git-lfs's per-repository
lock cache (`lockcache.db: gob: bad data`), so the command-line fallback locks one path at a time.
