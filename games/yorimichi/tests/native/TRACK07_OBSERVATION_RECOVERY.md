# Track07 failed observation recovery

This tooling does not rerun imports or modify the sealed original source, spec,
whole-result, guard, captures, archives or receiving assets. The old whole exit
is **255**, not a native pass. Cleanup remains pending throughout this workflow.
The failure occurred after all 137 capture markers and actor release, at the
fixture's final Library roster assertion. Its expected set omitted exactly four
real `track_material` outputs: `MI_ST_Clock`, `MI_ST_Coach`, `MI_ST_Glass`, and
`MI_ST_Green`. No `MI_ST_*` prefix rule is admitted. `MI_ST_CoachRoof` stays out.

`track_material_roster` requires each admitted local material to have an exact
reported object path, runtime material key and primitive-consumed LOD0 GLB source
witness. The complete Library and prerequisite package sets must agree exactly.
The recovery additionally requires actual captured native slot references to each
of the four material object paths and a matching source/runtime witness.

The parent owns execution and admission. Three separate commands exist:

1. `recover_track_native_observations.py prepare --spec OLD_SPEC --output NEW_PLAN`
   runs on the host outside the queued verifier. It requires the exact sealed
   Track07 spec, clean immutable source `40d5dfed3b057849b6493a2054938152c129ebb6`,
   Git-bound source bytes, and the receiver's actual current compile/module/SDK
   inventory matching the failed observation. It freezes metadata and verifier
   code bytes without parsing raw geometry. Keep its new output outside sealed
   original directories.
2. `validate --plan NEW_PLAN --plan-sha256 SHA --output NEW_DATA_REPORT` runs only
   through the parent's ordinary guarded Python admission/deadline/queue. It
   spawns no subprocess or tool probe. It verifies the frozen inputs, exact
   whole255/empty/actor-cleanup/137 markers, deterministic saved archive bytes,
   actual material slots and every raw record through the unchanged complete
   comparator against itself **as data only**. It prints per-logical progress.
   `--check-current-packages` additionally compares retained archive identities
   against the current receiving files, only in this admitted verifier.
3. `finalize --plan NEW_PLAN --plan-sha256 SHA --data NEW_DATA_REPORT --guard NEW_GUARD
   --whole NEW_WHOLE_RESULT --output NEW_HOST_REPORT` runs after the new caller
   stops, outside admission. It requires the new data verifier's whole0/empty
   guard and repeats host source/native checks. It never treats the old255 guard
   as successful and never cleans up packages.

Every new report says `failed_old_whole: 255`, `observation_validation_only: true`,
`cleanup_pending: true`, with native/full/task acceptance false. Self-consistency
is not an independently executed original/current equivalence proof. The parent
must separately admit any necessary current native observation or bounded cleanup
with exact referencer preflight; this tooling performs neither.
