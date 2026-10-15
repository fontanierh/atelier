# Crater Park editor

The owner's park editor. It runs on the build Mac and is published on the tailnet only, at `/parkeditor/`.

To start it (it survives until the Mac restarts), run `zsh serve_editor.sh`. That starts `server.py` on 127.0.0.1:8914 and adds the `tailscale serve` path.

## This folder in the repository

- **Live copy.** The owner's live editor runs from its own folder on the build Mac, with its live `park.json`. This folder is the reviewed copy of that editor's code.
  - `tools/ship_craterpark_editor.py` refreshes the code here from the live folder whenever it ships a design.
  - It never touches the live folder.
- **`pieces.js`** is a link to the pinned compiler `world/regions/craterpark/v2/editor/pieces.cjs`, so the editor and the game build mesh with the same code.
- **`designs/`** holds shipped designs. `craterpark-rev72.json` is the orange-line park.
- **`data/`** is the crater terrain the editor draws and cuts.
- **Running this copy.** Copy a design to `park.json` and run `python3 server.py 8914`. `park.json`, `versions/`, `snapshots/` and the logs are ignored by git.
- **`import_v4.py`** was a one-time converter from the v4 design. It is not kept here.

## Files

| File | Purpose |
|---|---|
| `park.json` | **The park as the owner edits it. This is the source of truth for building.** It saves automatically after every change. |
| `versions/` | Snapshots: one at least every 5 minutes while editing, plus each named version. |
| `index.html`, `app.js` | The editor UI: three.js view, picking, dragging, inspector, lines, problems, profile. |
| `pieces.js` | Piece geometry, meshing and ride physics. It has no DOM dependency, so `node` can run it for tests. |
| `server.py` | Static files plus the save API. A save with a stale `base_rev` returns 409 instead of overwriting. |
| `export_terrain.py` | Writes `data/` for the crater: 2 m inner grids (natural, and natural plus the v4 funnel dig) and the 5 m surroundings. |

## park.json schema (`craterpark-editor/1`)

### Frame

- Units are native metres. Plan coordinates are `x` and `z`; `y` is up. World altitude = `y + 680`.
- `heading` is in degrees, measured from +x toward +z. A positive `turn` is a right turn for the rider.
- Slopes are in degrees; negative means downhill.

### Top level

- `rev` and `saved_at`
- `terrain`: `"dug"` or `"natural"`
- `lines`: `[{id, name, color, role}]`
- `pieces`: the list described below

### Piece fields

`{id, type, name, line, attach, next[], x, y, z, heading, slope, params{}, start?}`

- **`attach`** is the id of the piece whose end this piece starts from. Its pose then follows that piece's exit pose. In that case `x/y/z/heading/slope` are kept up to date as derived values.
- **`next`** lists where the rider goes after this piece. A branch has several entries.
  - If the target's `attach` points back to this piece, the path is continuous.
  - Otherwise it is a flight (from a `kicker`) or a gap the checker flags.
- **`start`** (or `type: "rollin"`) marks where a line begins.

### Piece types

Defaults for every parameter are in `pieces.js` (`TYPES`).

- **`run`**: a runway, turn, vert corner, half bowl or flared mouth.
  - `corner` (optional boolean) is an import tag on vert-corner runs. It is information only: the editor derives corner behaviour from `turn` and wall height, and compilers should accept and ignore it.
  - `len` is the plan length. `turn` (°) gives a constant plan curvature.
  - `slope` is the target slope. It eases in from the incoming slope with vertical radius `vR`. `ease_end` and `end_slope` add an ease at the end.
  - `width` is the floor width; `width_end` is optional, for a flare.
  - `wl`/`wr` = `{h, R}` are curved walls. A wall goes vertical above `R`. `deck` is the coping deck width.
  - A turn of at least 45° whose outer wall is 5 m or taller counts as a vert corner in the physics.
- **`rollin`**: `drop`, `steep_deg`, `crest_R`, `foot_R`, `out_deg`, `run`, `width`, walls. It starts level at its pose.
- **`jump`**: a kicker, a gap and a receiver in one piece. It is the same profile as the `v4/check.py` gap.
  - Kicker: `run_in`, `kick_R`, `lip_deg`, `lip_len`.
  - Gap: `open`, plus `drop` (knuckle below the lip).
  - Receiver from a level knuckle: `knuckle_R` → `−land_deg`, then `land_len`, then `out_R` → `mid_deg`, then `mid_len`, then `out_R` → `end_deg`, then `out_len`.
  - Widths: `width` and `land_width`. `rail` adds a rainbow rail over the gap.
  - `template` names a proven module (med15/20/25/30, mega42/55). It is cleared when the shape is edited.
- **`kicker`**: a standalone kicker. The rider flies to the pieces in `next`.
- **`landing`**: `deck_len` (a flat knuckle deck), then the receiver as in `jump`.
- **`qp`**: a face-on quarter pipe: `approach`, `h`, `R`, `deck`, `width`. The rider comes back out heading the other way.
- **`bowl`**: `outline` is the coping line in local metres, rotated by `heading` about `x/z`. The other fields are `wall_h`, `wall_R` and `deck`. `y` is the floor. A line that reaches a bowl ends there.
- **`deck`**: a platform: `len` along the heading, `width`, `thick`. With `solid`, it goes down to the ground (the tower).
- **`rail`**: a rainbow rail: `len` and `rise`.

## Physics in the editor

This is the same model as `v4/check.py`:
- the ground drag table, the turn loss and the 3.4 m/s vert-corner loss;
- riders start at 1, 4 and 8 m/s;
- flight with lift, measured past the knuckle, with impact normal to the slope.

It reports stalls, short or hard landings, overshoots, vert corners outside 14–21 m/s, gaps between pieces that aren't connected, dead ends, pieces below the ground, and pieces no roll-in reaches.

After a failure, the line is followed on with an assumed speed so that later problems are still listed. Those are marked "(after an earlier problem)".

Supports are deliberately ignored for now (owner, 2026-10-15).

**Walls on jumps.** `jump`, `kicker` and `landing` take optional `wl`, `wr` and `deck` like a run. A key left unset means "the walls of the piece before": layout passes the parent's end section in `pose.walls` (from `exit.walls`). The walls run up the kicker to the lip and along the whole landing.

**Ground cuts.** `carveGround()` in `pieces.js` applies them to the terrain grid:
- Every bowl removes the ground inside its coping line, plus 1 m, down to 3 m below its floor.
- A ridable piece with `params.dig` cuts a trench: flat under the floor, 1.5 m wider than the floor on each side, with 45° sides.

**Shaped platforms.** A `deck` with `params.outline` (local `[u, v]` points, rotated by heading about the piece position, like a bowl) is that polygon extruded down by `thick`. A point may carry two more values, `[u, v, top, under]`: its top and underside heights relative to `y`. The top is then triangulated through those heights, so an infill meets each neighbour's deck and underside exactly. The U-turn infill uses this. Joints carry straight on: a run starts at the width and walls of the piece before; a run before a tight turn eases its inner wall down to the turn's trimmed start; and a joint with no step is drawn without end faces. A run's `wall_blend` (default 12 m) eases its walls from the piece before. On the inside of a tight turn, the inner wall and deck are trimmed so they never reach the turn centre.

**Walls and vert.** A wall `{h, R}` taller than its radius goes vertical above it (h − R of vert); runway walls are 4 m on a 3.5 m radius, so every runway has half a metre of vert to carve, pump and pop out of. `level: true` on a run's wall keeps its coping at the start height while the floor drops (the wall grows). A flow bowl's `exit_wl` / `exit_wr` set the walls its exit neck hands to the next runway (else the entry walls carry through).

**Vert landings.** A pool bowl's `params.ext = {at: [u, v], half, blend, h, R}` raises a stretch of its wall: full height and radius for `half` metres either side of the outline point nearest `at`, easing back to the bowl's own wall over `blend` metres. Prado has one where the orange line's last run (which ends in a 35° kick) lands into it: a 16 m wall on a 30 m radius, so the rider lands on its steep face and drops into the bowl. A run whose end slopes up into a pool bowl is flown into it by the simulation, like a kicker. Jumps can land into vert too: `land_deg` up to 80°, and a `mid_deg` steeper than the landing makes the receiver steepen again, following the fall (g6 lands on a 44° face that steepens to 52°).

**Bowl floors and spines.** A pool bowl's `params.deep = {from: [u, v], to: [u, v], depth}` sinks its floor by `depth`, easing in from `from` to `to` (smoothstep) and full depth beyond; the walls grow by the depth so the coping stays level. `params.spines = [{a: [u, v], b: [u, v], h, R}]` adds spines: two transitions back to back along a–b (local, like the outline), with a 0.6 m flat coping top and rounded ends. Prado's pockets are 2 m deeper than the rest, with the v4 transfer spine between them (crest level with the rim, R 11.6, 0.6 m vert).

**Cut ground.** `dig` cuts the crater away around a piece: under the floor, just below each deck top out past the deck edge, then a 40° bank up to the ground.

## Shipping to the game

In the atelier worktree on `claude/crater-park-editor`:

```sh
uv run python games/yorimichi/tools/ship_craterpark_editor.py --lines L1 --build
```

This freezes this folder as `../ship/rev<N>`, pins `pieces.js` into the repository, checks that the game's bridge
meshes the park, and runs the guarded game build with only the given lines (L1 is orange). Package and publish the
playtest after that as usual. See `games/yorimichi/docs/CRATERPARK.md`, "Editor parks".
