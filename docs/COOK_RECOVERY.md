# Recovering interrupted cook certification

**Scope:** the cook-certification examples below belong to the retired Yorimichi V1 generated-content recipe.
They are recovery implementation/reference material, not a V2 migration task or a reason to rerun retired tests.
V2 currently has an explicit `unreal.package` step, not the separate `unreal.cook` recipe shown here; do not assume
these recording/recovery flags are supported by that route. Use the
[V2 package guide](../games/yorimichi_v2/docs/PACKAGE.md) for current packaging and preserve its completed work.
The shared Mac UAT/Zen lifetime behavior described next also applies to the ordinary package launcher.

An opt-in local journal can preserve a successfully guarded cook when certification is interrupted while
hashing its archived app. Recovery repeats certification, then the normal package assembly consumes that
certified cook. It does not run UAT again, touch stamps, restore a native cache or certify gameplay.

Normal Mac `UnrealPackage` builds keep the local Zen service (port 8558) sponsored by the admitted
UAT process for the whole BuildCookRun, including staging after the cook process exits. The launcher
uses the installed `zen attach` client; it never starts or stops a shared server. Health probes and
attach calls run outside the guard polling thread, with bounded HTTP and client timeouts. Readiness
is checked every two seconds on `::1`, matching UAT; a successful attachment is refreshed every
30 seconds and immediately after an observed unhealthy-to-healthy transition.
If staging has begun reading the local Zen store and health checks fail continuously for 60 seconds,
the step fails through normal owned-process cleanup instead of waiting on UAT's long HTTP timeout.
A healthy slow read is allowed to continue. Repeated attach failures also fail explicitly after
60 seconds when no sponsorship has succeeded for the continuously healthy server. A failed refresh
does not discard an established sponsor. `logs/<step>.guard/zen-lifecycle.json` records the admitted
sponsor, health checks and result.
This applies to default and experimental cooking alike; it changes neither engine files nor UAT arguments.

## Legacy recording and certification route

For an explicitly supported generated-content recipe, recording is enabled **before** its original cook,
in its own checkout under normal admission. The following V1 command is historical:

```sh
nice -n 10 uv run atelier build yorimichi unreal.cook --record-cook-recovery
```

The original command prints `cook recovery attempt: ID`. Its private evidence lives under
`build/<game>/cook-attempts/ID/`. Ordinary builds without this flag have no recovery inventory overhead and
cannot be retroactively recovered. Recording currently requires an explicitly supported recipe; it does not
change cook arguments, worker limits, deadlines, guards, capacity admission or default cook mode.
The project and user UBT default XML files must already exist: UAT creates them on first use,
which would change the frozen input set. Recording refuses before deleting an earlier archive if
these defaults are absent; prime them with an ordinary nonrecording cook first. Their bytes remain
part of every recovery check.
Recording supports the bundled default .NET runtime and the default Xcode selection only. It refuses
shell startup hooks (`.unrealrc`, `.autosdk`), command-line injection, SDK/.NET/AutoSDK overrides,
UnrealBuildTool environment configuration overrides and PATH-shadowed selectors. These checks run
before an old archive is removed and again at every input checkpoint; the ordinary nonrecording build
does not acquire these restrictions. Refusals name environment keys without disclosing their values.
An existing absolute `.sdk` directory selected through `SDKROOT` is supported: its exact environment
value, resolved selection and complete SDK bytes join the input proof. A redirected SDK link or changed
SDK content refuses recovery. Empty, relative or missing SDK selectors refuse before removing an archive;
recording never silently unsets `SDKROOT` or substitutes another SDK. Selector links, including ancestor
and chained links, retain their link text and full filesystem identity even when the resolved SDK is
already covered by another inventoried tree.
The opted-in launcher first runs a small Python capture adapter inside the normal charged admission and
both memory guards, then `exec`s the original UAT command in that same PID. Normal guard polling, capacity
heartbeats and the original timeout stay active during capture. There is no second lock or ungated UAT.

Recording conservatively inventories actual Content (including staged Data), prerequisite outputs, source,
configuration, installed engine tools/content/plugin inputs, editor modules and the selected SDK/toolchain.
This includes the complete selected Xcode Contents, both macOS and iPhoneOS SDKs, resolved Metal tools
and their complete toolchain resource owners, the Metal library search paths, selected packaging tools,
and BuildConfiguration XML inputs/absence. One discovery record supplies roots and permitted link owners
within a checkpoint; every later checkpoint discovers them again. Unsupported headless
configuration or escaped links refuse instead of guessing. UAT-written game Binaries/Intermediate remain
outputs; declared source membership follows the existing source/output boundary.
The first inventory may read many GiB; this has no measured speed benefit. Subsequent local input checks use
the existing hash-index implementation with fresh device/inode/mode/size/nanosecond modification/change
identity and complete membership checks. Losing that disposable index causes fresh hashing.
The bundled `dotnet` executable has one narrow identity exception: Unreal's SetupDotnet repeats
`chmod u+x` even when it is already executable. Its change-time alone may differ between checkpoints;
its device, inode, mode, size, modification-time and content hash must still match. Read stability and
hash-index validation still check the full change-time, so permission changes during a read refuse
and changed bytes are rehashed. No other tool, input or archive receives this exception. Archive
certification still hashes the actual app bytes twice. Each input inventory has a 45-minute bound and emits
progress; first review progress after 10 minutes and inspect any stall rather than silently waiting.
Each inventory is limited to 500,000 entries. Fully covered roots are walked once, using actual directory
device/inode ancestry (including case aliases), while all original root declarations stay in the snapshot.
Owned link targets covered by another complete root retain their link identity and use that root's byte
inventory. Missing paths, unsupported links and changed membership still refuse.
Post-UAT and recovery certification remain bounded single-thread
Python file work, as before; coordinate their disk/CPU activity around an owner's quiet benchmark window.
They do not acquire an exclusive native reservation just for hashing. Actual package assembly retains its
separate normal guarded admission. The conservative native-input selection still needs an admitted native
trial; these mocked correctness tests do not claim every installed toolchain's mutable outputs are recoverable.
Environment values are hashed, not written into the journal. The original launch and guard retain an exact
hash of the full, unmodified environment. Recovery compares every build/tool variable, including unknown
keys; a refusal names changed keys without their values. Only this explicit session-bookkeeping set may
change: `TERM_SESSION_ID`, `TERM_PROGRAM_SESSION_ID`, `ITERM_SESSION_ID`, `SSH_AUTH_SOCK`, `SHLVL`,
`OLDPWD`, `PWD`, `_`, `ATELIER_AGENT`, `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, `CODEX_TOOL_CALL_ID`,
`CLAUDE_SESSION_ID`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_CODE_MESSAGING_SOCKET`,
`CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_WORKER_EPOCH`, `CLAUDE_CODE_CHILD_SESSION`,
`CLAUDE_CODE_SESSION_ATTENDED` and `CLAUDECODE`. The actual working
directory is separately pinned, so start recovery from the same checkout directory, including in a new
terminal or agent session. No environment prefix or unknown variable is silently ignored.
Source changes, changed prerequisites, inputs, tools, SDK selection or consumed environment refuse recovery.
Verified named portable products may be restored prerequisites when the current action key and complete
actual byte records match. Manually touched or unproven native prerequisites still refuse.
Some older reuse donors carry inherited `touched` certificates too; the donor path alone is not proof.
In that legacy recording workflow, inspect and rebuild only the selected prerequisites through its ordinary
builder. This does not authorize regenerating V2 committed content:

```sh
uv run atelier build yorimichi STEP... --rebuild-touched --plan --explain
nice -n 10 uv run atelier build yorimichi STEP... --rebuild-touched
```

Use exact step names; prefixes and the default whole-game selection refuse. Only named touched
certificates are replaced; unnamed touched ancestors are left as they were.
Replacement uses normal execution or verified portable-product restoration.
It preserves current proven steps, action keys, caches and normal per-child guards; it never edits the old
certificate into a success. Inspect the downstream plan afterward and coordinate any required imports
before the cook. This is separate from recording/recovery and cannot combine with force or touch.

After an interruption of a supported recorded cook, preserve the evidence and current archive. Recheck Holding, Waiting, actual capacity
mode, charged/uncertain work and the supervisor before the next admitted child. Use the printed ID:

```sh
nice -n 10 uv run atelier build yorimichi unreal.cook --recover-cook ID
# Or certify, then assemble the normal independently guarded download in the same invocation:
nice -n 10 uv run atelier build yorimichi unreal.package --recover-cook ID
```

Replace `ID` with the 32-character attempt UUID. Recovery requires the same checkout and original action
fingerprint, every prerequisite already current and complete, unchanged consumed inputs, and the original
owned archive. The normal builder writes an honest `CookCertificationRecovery` command record with the
attempt identity, without inventing native execution timings. The resulting cook dependency is usable by
ordinary `unreal.package`; a later ordinary package build does not recook an unchanged recovered cook.
Repeating recovery of the same unchanged attempt is supported. Recovery never falls back to UAT on refusal.
Do not combine it with force, touch, planning, experimental cook modes or a heavy-command budget.

The journal has four required parts:

- `launch-request.json` binds the private adapter request and exact original UAT argv/environment identity.
- `prepared.json`: durable pre-UAT source, recipe, prerequisite, native input, tool and launch identities.
- `guarded-success.json`: affirmative returncode0 from the positively waited root and matching aggregate
  terminal receipt, published only after owned cleanup, monitor detachment and successful capacity close.
  Root and watched process guards must exit naturally with status0 before their final receipts are captured;
  a late stop report, failed guard or unsettled guard cannot produce this proof.
- `completed.json`: matching invocation and success proof, completion marker/observation, and the complete
  archive leaf identity before expensive certification hashes begin.

The archive continuity check includes device/inode/type/mode/size/mtime/ctime and internal link targets.
Normal file rewrites or replacement fail even if mtime is restored. This is local filesystem continuity under
exclusive ownership, **not** a cryptographic pre-hash content attestation or a defense against a hostile owner
who can rewrite the journal. Archive links escaping ownership refuse. Keep external writers away; do not
clean, copy over or reuse the archive/report paths before recovery. Failed partial attempts remain evidence.
A crash before durable affirmative completion is written still refuses; that small handoff gap is unavoidable
without a stronger external execution ledger. An interruption during subsequent expensive app hashing can
recover from the completed metadata proof.

UAT text saying success, exit0 in an unbound log, elapsed time, a missing PID, diagnostic execution timings,
stale reused report filenames, failed guards or incomplete cleanup never suffice. In particular, the historical
r4 attempt that printed UAT success but failed aggregate terminal verification has neither this pre-input proof
nor positive guarded completion and **must refuse**. Do not manufacture a journal, edit a stamp, use `--touch`,
or rerun a failed command merely to make existing bytes look certified. Report the refusal and preserve evidence.
