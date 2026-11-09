# The donor V2 adopted from

This is historical provenance and a recovery reference for the completed donor build. Normal V2 build/play
uses committed packages and the pinned restricted fetch; it does not rebuild the retired original or run its
disabled tests. Recovered sources are tracked by the V2 asset records and `restricted.originals.json`; see
[the inventory](../INVENTORY.md) for remaining source and object work.

V2's adopted packages (`assets/adopted/`) come from one run of the legacy Yorimichi build at baseline `7eec0f98dd`
with the local fixes in `baseline-7eec0f98dd-fixes.patch` applied (sha256
`7646f3177c45cc11e7d45931e6144d2993c5d7d6116ba1515b33a3c66ab5cb17`). The donor is that baseline plus these fixes,
not the bare baseline. Apply the patch to `7eec0f98dd` with `git apply` to reproduce it.

The fixes are baseline bugs that a cold build on UE 5.8 hit (cold-build paths, module lists, import paths, MessageLog
popups, float bounds) and relaxed triangle-count checks (`games/yorimichi/unreal/Scripts/donor_tris.py`): UE 5.8
removes degenerate triangles that the earlier engine kept. Every mesh whose built count differs is logged as
`V2 DONOR TRIANGLES`; 15 differ, 14 by under 0.2%. The largest, `FY_Superstructure` (18750 of 19070), has exactly
320 zero-area source triangles, the count UE dropped, so no visible geometry was lost.
