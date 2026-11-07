# Yorimichi V2 visual parity (plan P3.6)

Both games are captured the same way, as a runtime viewport screenshot through each game's live bridge
(`tools/parity/capture_runtime.py`). The donor's scenery exists only at run time, so an editor capture is no
baseline. `tools/parity/compare.py` checks both receipts (revision, map, size, poses, render settings) and scores
each pose.

## Slice result (2026-11-07)

Donor 7eec0f98dd (forward, its desktop launcher), V2 `jim5/yv2-parity-runtime`, 4 poses at
2560x1440, gate `--min-ssim 0.75 --max-mad 0.04`: pass.

| Pose | SSIM | MAD |
|---|---|---|
| coast_start | 0.922 | 0.029 |
| start_road | 0.795 | 0.028 |
| pier_path_top | 0.861 | 0.020 |
| pier_arrival | 0.870 | 0.029 |

The first comparison scored SSIM 0.77–0.86 and MAD 0.065–0.105. It found three V2 defects, each now fixed:

- The coast at `coast_start` was sea. Island cells outside the migrated regions were skipped, so they now belong to
  the environment region (277 terrain and far-hill pieces).
- A migration rerun placed every World Partition actor that was not loaded again. Duplicates appeared and a scene
  patch overwrote a placement edit. The migration now loads every actor before matching stable IDs, and a rerun
  creates nothing.
- Surfaces were 10–34% brighter and bluer, from the sky light only. Measured with the sky light off, the two games
  matched within 2%; with the sun off, V2 was 20–52% brighter. The original's desktop launcher set the forward sky
  light and distance-field settings, which are now the game's own (DECISIONS D09).

Remaining differences are expected:
- the donor's falling leaves are a runtime effect (P4);
- the stall, lantern post, cliff forest and the town beyond the pier belong to regions outside the slice;
- grass and foliage sway in the wind, which keeps SSIM lower on foliage than MAD suggests.

## Route on the same build

`tools/test/route.py` ran twice on this game after the captures. The second run passed: 15.6 m walked at
≥3.5 m/s, a skate top speed of 8.5 m/s with 0.1 cm deck variation, and the lowest sampled fps 59.9 over 20 sampled
frames. The first run failed. Right after the travel to `start_road`, the game ran at about 3 fps for 8 s, through
the start of the walk, then held 60. This is consistent with first-use shader compilation in the uncooked editor
build. It stays open until the packaged slice (P3.5) shows whether a first arrival hitches.
