# Offline park line validator

`validate_park_lines.py` runs the game's existing compiled `GameplaySession` through
`check_skate_feel.Session`. It does not compile a runtime or substitute ballistic calculations for gameplay.
Coordinates are native metres, y up; paths are `[x,z]`. Small CPU trials can run at nice 10 when the coordinator
permits them. Compilation and large native work still require the normal guard.

```sh
nice -n 10 uv run python games/yorimichi/tools/validate_park_lines.py layout.json \
  --binary build/skate-simulation-session-cli/gameplay-session-cli \
  --package build/yorimichi/skate-simulation/package \
  --out build/yorimichi/line-validation
```

`--line ID` selects a line (repeatable); `--speeds 8 12 16` overrides its entry speeds;
`--frames 900` overrides duration at 60 Hz. Every speed gets a fresh process. The binary must match its compiled
build manifest. No binary is built automatically. Use a compatible assembled package and retain its provenance.
Trials stop on reaching the finish in a ground state once the landing recovery window has been observed;
`stop_at_finish: false` requests the entire frame budget. This avoids testing an unintended fall beyond a completed
runout. The frame budget still bounds stalled or unlanded runs.

## Layout schema

The following illustrates the schema; it is **not an accepted park design**.

```json
{
  "lines": [{
    "id": "example-air",
    "path": [[0, 0], [0, 250]],
    "lane_width_m": 80,
    "rideable_width_m": 14,
    "entry_speeds_mps": [12, 16, 20],
    "frames": 900,
    "spawn_s_m": 1,
    "finish_s_m": 110,
    "intended_vert": false,
    "sections": [
      {"id": "kicker", "role": "takeoff", "start_m": 0,
       "profile": {"y": 0, "angle_deg": 0,
                   "parts": [["line", 10], ["arc", 15, 25]]}},
      {"id": "receiver", "role": "landing", "start_m": 35,
       "knots": [[0, 1, -20], [30, -6, -5], [70, -7, 0]]}
    ]
  }]
}
```

Profiles use `additions.profile()` semantics: `line` length is horizontal distance, and `arc` gives radius then
final angle. Explicit knots contain `[distance,height,angle_deg]`, starting at zero with strictly increasing
distance. Heights are absolute within the supplied simulation world. The tool evaluates `additions.hermite()`
and builds a strip along the path; default `mesh_step_m` is 0.25. Section endpoints and authored knots are included
exactly. A gap has no collision unless another explicit section supplies it. The tool adds no hidden catch floor.
Vertical or overhanging surfaces require triangle input. Polyline corners are not automatically smoothed: provide
a sufficiently sampled designed curve. Inspect bent strips for overlaps before treating them as final geometry.

The diagnostic lane defaults to 80 m wide because the unattended rider drifts. Set `rideable_width_m` to the
actual intended corridor: excursions beyond half that width fail even when the diagnostic lane still supports
the rider. This prevents the broad test lane from concealing route failure. The width is uniform along the path.

Spawn is inferred from `spawn_s_m` and collision, or supplied explicitly as `[x,y,z]`. Initial heading follows
the path; initial velocity is horizontal at the requested speed. Thus a low-speed spawn on a downhill start is
not equivalent to having accelerated down an earlier part of the park: include the full approach in the layout.

With no controls, the rider coasts. This is appropriate for straight feature diagnostics. Curved or pump-assisted
routes require authored controller inputs; the tool does not claim that an unsteered coast follows a curve.
Optional `controls` entries specify `start_frame`, `end_frame` (exclusive), `buttons`, `left` and `right`; sticks
are signed integers in [-32767,32767], with `[0,0]` neutral. Later entries override earlier overlapping entries.
Example push input: `{"start_frame":0,"end_frame":90,"buttons":4096}`. Every applied input is saved.
`difficulty` defaults to `normal`; `vert_assist` to 0; optional `feel` is passed unchanged to the Session.

Optional `"follower": {}` enables ground-only path tracking using ordinary left-stick input. It reads the preceding
frame's position/velocity, aims ahead along the path and stays neutral in air/offboard states. It never moves the
rider or alters velocity directly. Scripted buttons/right stick/left.y can accompany it; scripted left.x conflicts
are rejected. Defaults are `lookahead_m: 5`, `lookahead_seconds: 0.45`, `gain: 4`, `max_stick: 0.85`,
`smoothing_seconds: 0.15`, `min_speed_mps: 0.5`; all must be positive and finite, and max stick must be at most 1.
Each report records settings, active/saturated frames and corridor tracking separately. A failed tracking trial
does not establish a geometry defect: tight curves, intersections, sharp corners, low speed and airborne direction
changes can defeat this simple controller. Input traces permit replay. This is not proof of human playability.

## Triangle collision

Instead of `sections`, give `triangles` as `(F,3,3)` arrays, or `mesh` as a relative NPZ path containing
`positions` and indexed `triangles`, or expanded `triangles`. A path is still required for progress and corridor
measurements. `surface_regions` supplies named roles using explicit `faces` indices, or `box_min`/`box_max`
classifying triangle centroids. For example:

```json
"surface_regions": [{"id":"receiver","role":"landing","faces":[20,21,22]}]
```

Untagged surfaces never count as verified transition landings. Later overlapping region definitions take
precedence. Soup must have upward winding on riding faces. This small-job tool limits each world to 100,000
triangles; crop deliberately with sufficient flight, landing and runout context. It never silently decimates.

## Results and acceptance

`report.json` is checkpointed after each trial. `complete` means all requested trials were attempted, not that
they passed. Native failures retain partial traces and count as failures. Exit 0 means every tested entry speed
passes; exit 1 means at least one failed. `passing_tested_speeds_mps` is a sampled set, not a continuous safe range.

Each run saves collision JSON, stderr, and a compact per-frame JSONL trace with position, velocity, state,
controller inputs and surface IDs. Reports include speed sampled every 0.25 s along the path; every observed air;
takeoff speed/angle; horizontal and along-path distance; peak altitude and height above departure; incoming and
outgoing speed; landing slope/mismatch; normal impact-speed estimate; bail/offboard states; and potential bump
losses. Peak height and range come from the published animated root, at frame resolution, not wheel-contact
coordinates or exact subframe contact events.

Defaults can be overridden per line in `acceptance`:

| Key | Default | Meaning |
| --- | ---: | --- |
| `huge_air_m` | 25 | Both horizontal displacement and forward path progress must reach this distance. |
| `min_landing_slope_deg` | 5 | A flat tagged receiver still fails the transition check. |
| `max_landing_mismatch_deg` | 20 | Maximum difference between incoming velocity pitch and directional surface slope. |
| `max_takeoff_angle_deg` | 80 | Unintended near-vertical takeoff threshold. |
| `max_ground_slope_deg` | 85 | Unintended steep supporting surface threshold. |
| `landing_recovery_s` | 0.5 | Required observations after touchdown, with no bail. |
| `bump_loss_mps` | 2 | Excess gravity-corrected ground speed loss over the window. |
| `bump_window_s` | 0.25 | Window of uninterrupted, unbraked ground frames. |
| `gravity_mps2` | 9.81 | Diagnostic energy correction; override if the runtime/feel uses another value. |

A line needs at least one qualifying huge air, all `required_takeoffs` completed (defaults to all `takeoff`
sections), its finish reached, and no bail, corridor exit, sustained unknown ground support or excess speed loss.
Meaningful flights of at least 0.1 s must also have verified safe takeoff/landing/recovery, even if another air
already qualifies. Incomplete flights never pass. `intended_vert` exempts the takeoff/ground steepness limits,
not the landing or survival checks.

The CLI does not expose contact normals or slam impulses. Supporting triangles are **inferred** by a vertical
query from the animated root (up to 0.35 m above, 2 m below); this can be ambiguous at stacked surfaces and seams.
Landing angle compares the last airborne velocity with that inferred plane. Bails/slams are reported through
wipeout/bail/ragdoll/offboard states, not a distinct slam sensor. Bump candidates are unexplained energy losses;
rolling resistance, controls and animation motion can contribute. They are not proof of a collision defect.
These limits remain in each JSON report. No image, rendering-quality or human-playability claim is made.
At a lip, the animated root can pass beyond the surface while the rear wheels still touch it. Departure tagging
therefore uses the latest inferred ground support within 0.15 s; its frame is recorded. All unknown-support frames
remain counted, but only a continuous ground interval longer than 0.15 s fails the general support check. A landing
itself always needs identified support; the tolerance does not turn an unknown touchdown into a pass.

Tests: `uv run pytest games/yorimichi/tests/test_park_line_validator.py -q`. Native trials are explicit and use
the supplied executable/package; ordinary test discovery does not launch them.
