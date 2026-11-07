# Yorimichi V2 visual parity (plan P3.6)

Both games are captured the same way, as a runtime viewport screenshot through each game's live bridge
(`tools/parity/capture_runtime.py`). The donor's scenery exists only at run time, so an editor capture is no
baseline. `tools/parity/compare.py` checks both receipts and scores each pose. A receipt must name the revision its
game was proven to launch from: the live session's launch commit for V2; for the donor, which has no session record,
HEAD of the checkout whose project the process on its live port runs, unmoved since that process started.

**What this comparison proves.** It compares lighting, terrain and the scenery the slice has already migrated (W00
environment, W01 start, W04 pier approach). It does not prove the whole view matches the original. Two of the four
cameras stand outside the migrated regions, and their missing landmarks are listed below. A whole-image score passes
with those landmarks absent, so it closes none of them.

## Slice result (2026-11-07)

Donor 7eec0f98dd (forward, through its desktop launcher). That checkout is dirty: 31 local edits to its export and
import scripts and its hippodrome and skate park sources, made for the one-time donor export. None touch C++, config
or packages. V2 main aea8c3c860 (clean), with the C01 edits merged. 4 poses at 2560x1440, both receipts carrying their
proven launch revision; gate `--min-ssim 0.75 --max-mad 0.04`: pass.

| Pose | Camera (cm) | In migrated regions | SSIM | MAD |
|---|---|---|---|---|
| coast_start | -23600, 16000 | no: south of W01 (y > 12800), west of W04 | 0.910 | 0.031 |
| start_road | -24830, 10000 | W01 | 0.790 | 0.038 |
| pier_path_top | -15421, 8680 | W01 | 0.878 | 0.018 |
| pier_arrival | -200, 36200 | no: north of W04 (y > 25600) | 0.868 | 0.031 |

The earlier pass (V2 b563d5d3f1, dirty) predates the receipts' launch proof, and `compare.py` now refuses it.

### Missing landmarks and where they belong

| Seen from | Missing in V2 | Belongs to | Status |
|---|---|---|---|
| coast_start | the food stall, the paper-lantern post and the sign beside the coast path | the coast south of W01, not yet a region | open: about 60 m south of the spawn (-25526, 9951, on the W01 road), off the start route, which runs east along the road to the pier path |
| coast_start | the cliff forest on the headland across the bay | the headland, not yet a region | open (backdrop) |
| pier_arrival | the forested hillside above the beach, behind the pier | the slope north of W04, not yet a region | **open**: it frames the pier arrival, the route's end |
| pier_arrival | the town on the far shore (top left) | the town regions | open (backdrop) |
| all | falling leaves | the leaf effect (P4) | open, P4 |
| start_road | the donor's view shows its fox (the donor's pawn is not hidden) | capture difference, not scenery | none |

Foliage and grass sway in the wind, which keeps SSIM lower on foliage than MAD suggests.

### Defects the first comparison found (fixed)

The first comparison scored SSIM 0.77–0.86 and MAD 0.065–0.105. It found three V2 defects:

- The coast at `coast_start` was sea. Island cells outside the migrated regions were skipped, so they now belong to
  the environment region (277 terrain and far-hill pieces).
- A migration rerun placed every World Partition actor that was not loaded again. Duplicates appeared and a scene
  patch overwrote a placement edit. The migration now loads every actor before matching stable IDs, and a rerun
  creates nothing.
- Surfaces were 10–34% brighter and bluer, from the sky light only. Measured with the sky light off, the two games
  matched within 2%; with the sun off, V2 was 20–52% brighter. The original's desktop launcher set the forward sky
  light and distance-field settings, which are now the game's own (DECISIONS D09).

## Route on the same build

`tools/test/route.py` ran twice on the aea8c3c860 game, after the captures. The second run passed: 15.5 m walked at
≥3.5 m/s, a skate top speed of 8.5 m/s with 0.0 cm deck variation, and the lowest sampled fps 59.9 over 20 sampled
frames. The first run failed at a lowest sampled 3.1 fps, as on the earlier build. The capture had already visited
`start_road`, so this is not only first use of that place. It stays open until the packaged slice (P3.5) shows whether
a first arrival hitches.
