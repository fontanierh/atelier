# Normal course caller

This draft connects the existing course output to build-v2. The accepted target is
`atelier build yorimichi data.stage.racing_courses`; its existing runtime consumer reads
`Content/Data/racing/belmonte_courses.json`. Normal command routing is pending the real
C5c constructor/Q3 and installer/reader ownership gates. The initial helper binary
currently supports distribution identity only and refuses execution.

`games/yorimichi/build_v2.py` returns a fresh declaration without asset reads or writes.
The leaf uses `py_data/1` and `JsonData`, the full course/scene/GLB inputs and the explicit
shared validator code closure. `stage_courses.run(context)` calls the same full course
preflight as v1, including six-lane surface support, before requesting an output path.
It writes the original validated bytes; JSON whitespace, line endings and formatting
are preserved. Its byte/path/normalized-mode contract makes no source-mtime promise.
All still-v1 staging keeps its existing `copy2` behavior.

`controller::ControllerRequest::parse` validates bounded strict control data and the
supported fixed JSON data contract. `controller::prepare` reuses A4, explicit source
capture and the frozen Python worker implementation. `prepared.plan()` creates no
cache, root, lease, job or checkout files. Without a genuine readonly store accessor,
it reports `unknown_readonly_store_unavailable`; this is neither a hit nor a miss.

The Python distribution adapter captures only `controller-sources.json` and its named
Rust/config/Cargo closure. This digest is helper freshness metadata, distinct from A3
unit keys. `ControllerSource.materialize` emits captured bytes into a new private root.
`write_control` and `read_control` exchange bounded private exclusive files; no ambient
environment values belong in requests or reports. Planning never bootstraps a helper.
`ensure_controller` performs visible guarded incremental bootstrap from that frozen
closure with locked Cargo and three jobs. It publishes a source-versioned independent
binary only after unchanged-source and embedded distribution-identity checks. A stale
binary is never a fallback. Complete normal execution is still being wired.

The first normal proof must compare the full output against an unchanged v1 byte
oracle, then exercise an identical warm build and a valid course edit between stopped
builds. If only a pinned original `copy2` operation is available, evidence must label
that bounded source-derived oracle rather than claim a completed v1 data.stage or game
build. A formatting change changes the copied output bytes; it is not output cutoff.
A code-only change with identical output can demonstrate cutoff only with an actual
selected downstream consumer. No timing or full-game performance claim follows from
the portable preparation and body tests.

Runtime success, scheduler/A7 observations and final root/release/cancellation outcomes
remain separate. Missing or partial finalization evidence is unknown, not success.
Current must remain usable without opening the cache, and a partial selected B4 session
must commit without a complete-declaration pruning roster. A6 mid-build edits and full
game/native reader integration remain pending; MAC1 native validation is deferred.
