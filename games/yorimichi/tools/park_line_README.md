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
the rider. This prevents the broad test lane from concealing route failure. For an actual wider room or receiver,
`corridor_zones: [{"start_s_m": 200, "end_s_m": 250, "width_m": 30}]` overrides the authored width only on that
interval. Zones must be finite, positive, disjoint and inside the route. Derive them from the built surfaces;
the tool validates metadata and observed tracking, not whether a supplied width matches the source mesh.
`max_corridor_excess_m` reports the greatest excursion beyond the applicable half-width.

Spawn is inferred from `spawn_s_m` and collision, or supplied explicitly as `[x,y,z]`. Initial heading follows
the path; initial velocity is horizontal at the requested speed. Thus a low-speed spawn on a downhill start is
not equivalent to having accelerated down an earlier part of the park: include the full approach in the layout.

The follower, finish detection and final measurements track station continuously at 60 Hz. Each observation
projects only within `max(3 m, 3 * speed / 60)` of the preceding station, seeded from the declared spawn where
available. This prevents a plan crossing or stacked run from snapping progress onto a different leg. Airborne
frames update progress while keeping steering neutral. A shortcut outside that local route remains a corridor
failure; tracking does not correct the rider's pose or change collision.

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

`landing_normal_speed_mps` uses the final airborne velocity. The additional
`landing_normal_speed_peak_3frames_mps` uses the largest absolute normal component in the last three airborne
frames against the same inferred landing plane; this helps reveal velocity already reduced before the state
changes to ground. It is diagnostic, not a contact impulse or a universal impact limit, and does not alter the
ordinary gap verdict. Both are unknown when landing support is unknown.

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

For a line with several gaps, optional `required_airs` declares the takeoff/receiver pairs **in riding order**:

```json
"required_airs": [
  {"id":"hero", "takeoff":"kicker1", "landing":"receiver1",
   "knuckle_s_m":80, "knuckle_y_m":-6, "landing_end_s_m":115,
   "min_air_m":25, "min_knuckle_margin_m":3},
  {"id":"secondary", "takeoff":"kicker2", "landing":"receiver2",
   "knuckle_s_m":160, "knuckle_y_m":-12, "landing_end_s_m":185,
   "min_knuckle_margin_m":3}
]
```

Each pair needs its own completed safe flight, the exact named receiver, and a touchdown between the knuckle
plus the required margin and `landing_end_s_m` (the intended slope's end, excluding later runout). IDs and takeoff
names must be unique. Section/region names must exist with the appropriate roles. `min_air_m`,
`min_knuckle_margin_m`, and optional `min_takeoff_speed_mps` default to zero and must be finite and nonnegative.
The explicit pair can satisfy its `required_takeoffs` entry with a shorter secondary air, but the whole route
still needs at least one huge air and all previous safety checks. Use `min_air_m: 25` on the designated hero.
Unpaired required takeoffs retain the original huge-air rule. A wrong receiver, missing gap, repeated departure
from a declared takeoff, or gaps ridden out of order fails even if another air succeeds.

`gap_checks` reports each pair's verdict, linked air index and along-route touchdown margin. Air records include
takeoff/landing stations and `safe_landing_pass` (all flight safety checks, excluding the global huge-air distance).
When `knuckle_y_m` is supplied, vertical clearance is interpolated from observed root positions crossing that
station during the flight. It is informational, not wheel clearance or an exact contact measurement; absent
height or no observed crossing returns null. All thresholds apply to every speed in that line spec. For a margin
required only at 1 m/s, use separate copies of the same full-route spec for that speed and for the 4/8 m/s cases,
with explicit margins. Each trial still runs the complete route continuously, without resetting at gaps.

For intentional air-outs returning to the same quarter pipe, declare that region explicitly:

```json
"required_vert_returns": [
  {"id":"elbow-air-out", "surface":"elbow_qp", "coping_y_m":7,
   "max_normal_speed_mps":5}
]
```

The named surface must have role `vert` or `transition`. The requirement uses globally nearest **3D** collision
at the last grounded departure and at return, never a nearest search restricted to the desired wall. Default
maximum root-to-collision distances are 0.75 m at departure and 0.25 m at return; optional
`max_departure_distance_m`/`max_contact_distance_m` may not exceed 1 m/0.5 m. It needs an apex at least 0.5 m above
`coping_y_m` (`min_apex_above_coping_m`), the same named wall at return, and a non-flat return face under the
existing minimum slope rule. IDs and surface names must be unique. All bounds must be positive and finite.

For this declared return only, the peak absolute normal component of the last three airborne velocities replaces
the directional slope/mismatch criterion. The `max_normal_speed_mps` bound is **required**, at most 7 m/s,
and also capped by the route's normal-impact bound. It is not calibrated
automatically from surviving runs. It remains an estimate against an inferred face, not measured contact speed
or impulse; nearby seams, animation offsets and early wheel contact limit its precision. The normal return speed,
distance, face, apex and method are retained in the air's `vert_return` report. No bail and the existing recovery
duration are still required; vert recovery must remain in riding-ground states. Missing, distant, flat-deck,
wrong-wall and hard returns fail. Ordinary gap landings retain their original slope/mismatch checks.

Only explicitly declared wall regions get the intentional-vert steepness exemption. `vert_checks` requires an
observed successful air-out from every declared region by default. A route can explicitly set
`require_air: false` for a wall that can be carved at lower speed: without a flight it needs nearby grounded
contact on that named wall at least 15 degrees steep. Any observed flight still needs the full same-wall return,
apex, impact and recovery checks; this option cannot turn a failed flight into a passing carve. The separate
wall-only diagnostic always requires its air-out. A vert return
never supplies the route's required hero air, even if it travels 25 m horizontally. Default
`validation_mode: "route"` retains that hero requirement. A **separate wall-only diagnostic** may set
`validation_mode: "vert_return"`: it must declare a wall return and cannot declare `required_airs`; it omits only
the hero-air requirement. Finish, corridor, unknown support, ground-loss and bailout checks remain active.
The report records its mode: a passing wall diagnostic is not evidence that the complete park route passes.

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
