# Claims: global task and scope ownership bound to Git LFS locks

One small service is the authority for who may write which protected content across machines. It records
principals (agents and humans), opaque machine IDs, workspaces, tasks and their claims, and keeps an
append-only event history. It is not a scheduler, a chat channel or a replacement for local admission.

- **Exactly one writer.** A claim holds scopes (`region/north/harbour`, `asset/prop/bench-01`,
  `shared/material/M_Sea`, `boundary/north+south`), exact paths and path prefixes. Parent and child scopes
  overlap; siblings coexist. A prefix covers files whose names do not exist yet. A region claim does not own
  a shared scope: claim that separately.
- **LFS locks are necessary, not sufficient.** LFS knows an account, not which agent using it may write.
  Ownership comes from the claim; the lock is verified (path, owner, ID) on the remote before the claim is active.
- **Fail closed.** If the service, the LFS server or Git cannot be asked, nothing becomes active and protected
  checks fail. Unprotected text changes still pass.
- **No release without merge or cancel.** A push does not release; neither does an expired heartbeat
  (it only marks the owner unreachable). Recovery is an explicit coordinator operation that records who and why.

## Grant sequence

1. `request` atomically reserves the items as **pending** after checking overlap and the base revision
   against the target branch (refused if a claimed or read path changed since the base: update first).
2. For each LFS path the client records an intent (the service snapshots the remote locks on that path),
   runs `git lfs lock --json` with **its own** credentials and reports the result.
3. `activate` verifies every lock on the remote and the base again; only then is the claim **active**.
4. On failure the attempt is aborted: only locks this attempt proved it created are unlocked. A lock whose
   result is unknown stays **uncertain** and keeps the reservation until `reconcile` proves whose it is
   (a lock ID absent from the intent snapshot and owned by the claimant was created by the attempt) or a
   coordinator resolves it. A pre-existing lock is never unlocked because its account matches.

After every start the service is **reconciling** and refuses grants and protected checks until `reconcile`
has compared every recorded lock with the remote.

## Invocations

These are the commands exercised by `platform/harness/tests/test_claims.py` (CLI and Python API) and the
opt-in `test_claims_lfs_integration.py`.

**Service host** (one process; the SQLite database stays on this host, never on a shared folder; back it up):

```sh
# The token file must be private (chmod 600) and is never committed. ATELIER_CLAIMS_TOKEN also works.
uv run atelier claims --token-file ~/.config/atelier/claims.token serve \
  --db ~/.local/state/atelier-claims/claims.sqlite \
  --git-repo ~/claims-service/repo --git-remote origin \
  --lfs-repo ~/claims-service/repo \
  --bind 127.0.0.1 --port 8840 --coordinator lead
```

`--git-repo` is a clone of the shared repository on the service host (heads come from `git ls-remote`, then a
fetch). `--lfs-repo` verifies with `git lfs locks --json` in that clone; `--lfs-url URL` instead calls the LFS
locking API directly, with `ATELIER_CLAIMS_LFS_AUTH` as its `Authorization` header. Bind a private-network
address to serve other machines; keep addresses out of the repository.

**Every client** sets `ATELIER_CLAIMS_URL` (default `http://127.0.0.1:8840`), the token, and its principal
(`--actor`, `ATELIER_CLAIMS_ACTOR` or `ATELIER_AGENT`):

```sh
atelier claims reconcile                                    # after every service start
atelier claims register-principal agent-a --kind agent --git-account <lfs-lock-owner-name>
atelier claims register-machine m-7f3a                      # opaque ID, never a hostname
atelier claims register-workspace agent-a-ws --machine m-7f3a
atelier claims heartbeat agent-a-ws
atelier claims task create T42 --title "Bench mesh" --workspace agent-a-ws --target main \
  --branch agent-a/bench --base "$(git rev-parse origin/main)" --reads Content/Shared/
atelier claims request --task T42 --workspace agent-a-ws \
  --scope asset/prop/bench-01 --lock-path Content/Props/Bench01.uasset --acquire
atelier claims request --task T43 --workspace agent-a-ws \
  --scope region/north/harbour --prefix Content/__ExternalActors__/North/Harbour/ --acquire
atelier claims extend 7 --lock-path Content/__ExternalActors__/North/Harbour/NewActor.uasset --acquire
atelier claims acquire 7                                    # retry locking + activation of a pending claim
atelier claims show 7
atelier claims check --task T42 --paths Content/Props/Bench01.uasset
atelier claims check --task T42 --staged                    # reads git diff --cached --name-status
atelier claims check --task T42 --range origin/main...HEAD --stage publish
atelier claims task push T42 --revision "$(git rev-parse HEAD)"          # evidence only: no release
atelier claims task push T42 --revision "$(git rev-parse HEAD)" --failed --detail "LFS upload failed"
atelier claims premerge --task T42                          # re-verifies locks live, checks origin/main...HEAD
atelier claims task merged T42 --revision <merged-commit>   # verified reachable from main, then unlocks
atelier claims cancel 7 --disposition preserved --note "kept on branch agent-a/bench"
atelier claims unlock 7                                     # retry unlocking after a failure
atelier claims events --after 120                           # durable polling cursor
atelier claims status
```

**Coordinator** (configured with `serve --coordinator NAME`):

```sh
atelier claims --actor lead recover 7 --action transfer --to-workspace agent-b-ws \
  --old-writer-stopped --preserved "branch agent-a/bench at <commit>" --reason "agent-a crashed"
atelier claims --actor lead recover 7 --action release --old-writer-stopped --preserved "<where>" --reason "..."
atelier claims --actor lead recover 7 --action resolve --path Content/Props/Bench01.uasset \
  --decision adopt --lock-id 123 --reason "bootstrap writer's lock adopted into this claim"
```

## Checks and hooks

`check` lists the changed files (with `--staged` or `--range`, including deletions and both sides of renames)
and finds protected ones: files with the Git LFS `lockable` attribute in `.gitattributes`, plus globs from
`--protect` or `git config --add atelier.claims.protect 'Content/**'`. Each protected path must be covered by
an **active** claim of the task. `--stage publish` (pre-push, pre-merge) also requires exact paths, with a
verified LFS lock for lockable files: add new files found under a prefix with `extend` first.

`atelier claims use-task T42` sets this checkout's task. The repository's `.githooks/pre-commit` and
`pre-push` then call `hooks/pre-commit` and `hooks/pre-push` here; checkouts without a task are unaffected.
Hooks are cooperative and bypassable (`--no-verify`); they are not a security boundary. Protect `main` and run
`atelier claims premerge` on the integration path as the final check.

The bearer token admits a team member; the `actor` field names the principal. Like the hooks, this protects
cooperative workers from mistakes rather than from someone holding the token.
