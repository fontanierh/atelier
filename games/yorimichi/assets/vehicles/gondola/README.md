# Gondola ropeway

The aerial cable car between Hidamari, Belmonte, the Crater Park rim and the crater floor. It is modelled in the
style of the gondola concepts (`gondola_cabin.jpg`, `gondola_tower_pylon.jpg`, `gondola_valley_station.jpg`,
`gondola_rim_station.jpg`, `gondola_crater_floor_station.jpg`). The concepts set the look. The structure is designed
for riding and walking. All lines are monocable detachable gondola (MDG) lines, and every line runs both ways.

The kit builds route-independent geometry: the cabin, a parametric tower and three station shells. The normal
Yorimichi build also fits and imports three working lines, their foundations and ground access, as described under
World integration below.

## Build and review

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.safety.guarded --report build/yorimichi/gondola/logs/build \
  --timeout 1500 --small 3 --purpose 'gondola model build' -- \
  $B --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/gondola/build.py
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.safety.guarded --report build/yorimichi/gondola/logs/render \
  --timeout 1500 --small 3 --purpose 'gondola review render' -- \
  $B --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/gondola/render.py
uv run python games/yorimichi/assets/vehicles/gondola/compare.py CONCEPT_DIR   # folder with the gondola_*.jpg concepts
uv run python games/yorimichi/assets/vehicles/gondola/walk.py
```

- [`build.py`](build.py) writes into `build/yorimichi/gondola/`:
  - one FBX per mesh, plus one UCX collision FBX per piece, under `assets/`;
  - a `.blend` per piece;
  - `layout_<piece>.json`, the walk layouts;
  - `textures/`, the procedural timber maps;
  - `manifest.json`, written on a full run only.

  `$GONDOLA_PIECES` limits a run to some of `cabin,towers,valley,rim,crater`. Setting `$GONDOLA_SOFT_FAIL` turns the
  failure exit into a report, for review renders.
- [`render.py`](render.py) renders the matched views and close-ups into `review/`, including
  `<station>_bullwheel.png` (the bullwheel bay from the deck) and `<station>_eave.png` (a roof eave with its post and
  brackets) for each station. `$GONDOLA_VIEWS` limits a run to some of `cabin,towers,valley,rim,crater`. The grip
  diagrams are labelled orthographic views with thin leader lines:
  - `cabin_grip_end_view.png`, looking along the rope, with a reference length of the station rail under the wheels;
  - `cabin_grip_section_view.png`, a cut across the rope through the housing: rope, jaws, pivot pin, wheel axes;
  - `station_mouth_side.png` and `station_mouth_section.png`, at the valley mouth: one grip still on the line (jaws
    closed on the rope) and one inside on the rail (rope dropped 0.15 m clear of the jaws).
- [`compare.py`](compare.py) writes:
  - `compare_<concept>.png`, with the concept on the left and the model on the right in matched framing;
  - `overlay_<concept>.png`, a 50% blend;
  - `edges_<concept>.png`, the concept's strong edges over the render;
  - `closeup_*.png`.
- [`walk.py`](walk.py) runs without Blender. It writes `review/walk_report.json` and the top-down layouts
  `review/walk_{cabin,valley,rim,crater}.png`.
- [`fitcam.py`](fitcam.py) fits cameras to picked correspondences (Levenberg-Marquardt) and writes
  [`cameras.json`](cameras.json): the cabin views, and the valley and crater-floor station views (structural anchors:
  roof apexes and eave corners, post feet, the bullwheel centre; fixed 30 mm lens, zero roll), so that the overlays
  compare structure and the fit residual measures the remaining difference. The tower and rim views are framed by
  eye: their layout does not trace the paintings.
- [`params.py`](params.py) holds the parameters. [`rope.py`](rope.py) is the rope path. [`textures.py`](textures.py)
  makes the timber textures. [`solid.py`](solid.py) is the closed-mesh core and holds the audits.

## Parameters

Overrides come from a JSON file named by `$GONDOLA_PARAMS`, and the build records the values it used in
`manifest.json`.

| Parameter | Default | What it moves |
| --- | --- | --- |
| `gauge` | 6.0 m | distance between the two rope tracks; bullwheel rope diameter; tower crossarm |
| `rope_radius` | 0.045 m | 90 mm haul rope (six strands); jaw, sheave and bullwheel groove radii; clearances |
| `hanger_length` | 1.45 m | rope axis to the cabin roof deck; grip-to-floor 3.75 m; rope height at the platforms 3.77 m |
| `tower_heights` | 10, 13, 16, 20, 24, 28 m | one tower model per height (saddle height above the foundation datum) |
| `berth_x`, `pit_depth`, `berth_floor_step` | 3.4 m, 0.28 m, 0.02 m | berth position, cabin channel depth, sill step |

`manifest.json` records the attachment points for every piece:

- **Cabin:** grip point, jaw groove, running wheels, door frame, sill and leaves.
- **Towers:** rope saddles and sheave trains, crossarm, foundation datum and allowed ground relief, guy anchors, ladder.
- **Stations:**
  - rope exits and the station rope height;
  - the bullwheel;
  - the running rail;
  - berths: cabin grip, door centre and platform edge;
  - the pit;
  - access edges.

## Mechanism (MDG)

The model uses one rope path for everything. `rope.py`'s `RopePath` is the single source of `rope_point(s)` and
`rope_tangent(s)`. The rope meshes and every cabin placement use its `grip_frame(s)` (x along the tangent, z up, door
side outward):

- review spans;
- tower passes (`over_tower`);
- the station loop (`station_loop`).

**Grip.** A clamp housing about 0.45 m long and 0.30 m tall straddles the rope: a top body over two bolted,
chamfered side plates, with the rope running between them. Inside, a fixed jaw (inner side) and a movable jaw (outer,
door side) close on the rope from above. Their grooves are arcs of the rope radius about the rope axis, ending at the
axis height. Below the rope the housing is open, so the tower sheaves and the bullwheel run under the rope. Also on
the grip:

- two running wheels (0.32 m, grooved tyres), one at each end of the housing on the outer side, 0.30 m outboard of
  the rope axis, each on its own stub axle carried by a bolted arm from the side plate. Their centres are 0.16 m above
  the rope axis, so their treads come down to rope-axis height and the station rail runs under them, beside the rope
  and clear of it. They roll on that rail once the jaws open, and touch nothing on the line;
- a pivot: a lug under the outer side plate and a pin across the rope (along y), 0.13 m below the rope axis and
  0.185 m outboard of it;
- the hanger, a chamfered rectangular post from a bolted base plate on the roof. It rises nearly vertically, has one
  dogleg 40% of the way up and ends in a round boss on the pivot pin, beside the rope, never across it.

**Hanging plumb.** Only the grip (`GD_CabinGrip`) takes the rope's frame. The hanger, the body and the doors hang
from the pivot pin: `rope.hang_frame` gives them the grip's heading turned level, with world up and no pitch or roll,
and keeps the pivot point shared. On every grade the cabin floor stays level and the hanger stays vertical, while the
grip pitches about the pin. `cabin.pose` builds this two-frame placement; the build, the stations and the renders all
use it.

The load path is rope → jaws → grip body → hanger → cabin.

**Groove check.** The build measures the distance from the rope axis to the jaw groove at every placement:

- a level rope;
- a 40% grade;
- a sagging span;
- 49 positions over each tower sheave train;
- the station mouths.

It fails if any point is off the rope radius by more than 2 mm. The current maximum is 0.2 mm.

**Stations.** The haul rope drops 0.15 m inside the mouth (`station_loop`), away from the opened grips, and runs
round the bullwheel at that height. The detached grips roll on a running rail whose top is at the wheels' bottom. The
rail is hung from an overhead frame on the inside of the loop: posts in the pit, a spine and crossarms over the grips,
and drop plates outside the wheel path. The cabin is checked round the whole loop:

- the running wheels against everything but the rail;
- the rest of the cabin against everything including the rail;
- the jaws against the rope everywhere except the 1.8 m attach zone inside the mouth.

**Rope clearance.** `solid.rope_clearance` samples the rope centreline every 2 cm within 3 m of the grip, in each
mesh's own frame. It measures the nearest-surface distance to the cabin, hanger and grip, and casts a ray along each
sample segment so that any crossing counts as 0. The jaws and the clamp body over them are left out, because they
close on the rope. The build fails below the rope radius plus 0.05 m. The poses checked are:

- spans: level, 40% and 75% grades (the steepest, as the crater-floor line), and a sagging span, in both directions;
- every tower pass;
- every station loop position, including the dropped rope round the bullwheel.

The manifest records the minimum distance and where it occurs (`rope_clearance`).

**Contact categories.** The report keeps the rope's intentional contacts apart from clearance to unrelated hardware:

| Category | Parts | Rule |
| --- | --- | --- |
| intentional contact | each grip jaw half (tag `jaw`; 2 per grip) | seated: the rope radius from the rope axis, within 2 mm either way, at every pose; in a station's attach zone, where the rope ramps down off the opening jaws, no jaw may cut into the rope |
| intentional contact | the clamp body over the jaws (tag `clamp`) | beside the rope by design: must not cut into it |
| intentional contact | each tower sheave (tag `sheave`; 4 per rope) | seated, as for the jaws |
| intentional contact | the bullwheel rim (tag `bullwheel groove`; 1 per rope) | seated, as for the jaws |
| clearance to unrelated hardware | everything else on the cabin, towers and stations (the bullwheel's lower flange included) | at least the rope radius plus 0.05 m (0.095 m for the 90 mm rope) |

The intentional contacts are gated part by part (`checks.part_verdicts`), so one seated sheave cannot carry a train
whose other sheaves are off the rope, and each rope must meet the expected number of each part. The distance is
signed: a ray-parity test (three skew rays vote) marks a rope axis inside a part, so an axis buried one radius deep
reads minus the radius and fails. Each row in the manifest names its category, the minimum and where it occurs, with
each part's least and greatest signed distance over the poses.

**Station loop margin.** At every loop position (every 0.2 m), the cabin body keeps at least
`checks.STATION_LOOP_MARGIN` (0.10 m) from the station structure: posts, headers, walls, railings, the rail frame and
the bullwheel's machinery. As on the towers, the check places the cabin body's bounding prism grown by the margin on
every side (the top too, for the headers) and fails on any station triangle inside it. The manifest reports the
minimum, bracketed to 5 mm by bisection on the margin (`cabin_loop/body_margin`). The platform, its painted steel
edge strip and the pit are the boarding interface: the door-to-edge gap (0.05 to 0.12 m, now 0.10 m) and the sill are
gated in the walk audit. The stone walls that carry the pit channel through the rim and crater mouths are structure,
inside the margin: the channel there is `Station.MOUTH_WIDEN` (0.05 m) wider each side than the pit. The running gear (hanger and grip)
works against the rail, the rope and the bullwheel by design, and fails on any other contact.

## Gates and thresholds

`build.py` exits non-zero when any gate fails, and lists every failure (`FAIL ...`) and records them in
`manifest.json`. `$GONDOLA_SOFT_FAIL=1` keeps the exit code at 0 so that a review render can run on a failing build;
the manifest then records `soft_fail: true`. `walk.py` run on its own exits 1 when the walk audit fails.

The gates: closed meshes (open, misoriented or degenerate), coplanar overlaps, seats, cabin contacts with towers and
stations, the jaw groove, both rope contact categories, the cabin hanging level, the grip's wheels and pivot clear of
the rope, convex collision proxies, collision under every walkable slab, triangle budgets, and on a full run the walk audit.

Every threshold is a named constant. [`checks.py`](checks.py) holds the decisions as plain Python, so the build and
the fast tests run the same rules. `games/yorimichi/tests/test_gondola_docs.py` asserts that this table matches the
code:

| Constant | Value | Gate |
| --- | --- | --- |
| `checks.ROPE_CLEARANCE` | 0.05 m | unrelated hardware to the rope surface |
| `checks.CONTACT_TOL` | 0.002 m | intentional contact and jaw groove, either side of the rope radius |
| `checks.FLOOR_TILT_TOL_DEG` | 0.01 deg | cabin floor from level |
| `checks.BUDGET['cabin']` | 15000 triangles | cabin |
| `checks.BUDGET['tower']` | 8000 triangles | each tower height |
| `checks.BUDGET['station']` | 60000 triangles | each station |
| `walk.RADIUS` | 0.22 m | player capsule radius |
| `walk.STEP` | 0.3 m | step limit |
| `walk.HEAD` | 2.0 m | headroom |
| `walk.MIN_WIDTH` | 0.9 m | route clear width and stair width |
| `walk.RISER_MAX` | 0.3 m | stair riser |
| `walk.TREAD_MIN` | 0.25 m | stair tread |
| `checks.STATION_LOOP_MARGIN` | 0.1 m | cabin body to station structure round the loop |
| `checks.FLOOR_SAMPLE` | 0.25 m | grid step of the floor-support check: every walkable slab sample stands on a collision hull |
| `checks.FLOOR_TOL` | 0.05 m | a floor-support sample this near a hull's plan edge counts as supported |
| `checks.FLOOR_Z_TOL` | 0.01 m | a hull supports a slab only where its top is this near the slab's walking height |
| `walk.BOARDING_GAP_MIN` | 0.05 m | berth: door sill to platform edge, least |
| `walk.BOARDING_GAP_MAX` | 0.12 m | berth: door sill to platform edge, most |
| `walk.SILL_MIN` | 0.0 m | berth: sill above the platform, least |
| `walk.SILL_MAX` | 0.03 m | berth: sill above the platform, most |
| `stations.ROPE_DROP` | 0.15 m | station rope below the grip line (jaws open) |
| `stations.ATTACH_ZONE` | 1.8 m | attach zone inside the mouth |

The fast tests (`games/yorimichi/tests/test_gondola_*.py`) need no Blender. They exercise the rope path and the
sagging span, the tower pass, the station loop, the plumb hang, the grip clearances and the contact classification,
and include fixtures that must fail: a hanger 0.05 m from the rope, a jaw contact 3 mm off the rope radius, a tilted
cabin floor, one sheave of a train dropped off the rope, one jaw half lifted off it, a rope axis buried a radius deep
in a part, a sheave missing from the train, a cabin body 0.05 m from a post, and a boarding gap or sill out of range.

## Mesh rules

Every part is a closed solid with outward normals. The build fails on:

- an open or misoriented edge, or a degenerate face;
- coplanar same-facing overlaps between parts (z-fighting);
- a fitting that floats or sinks beyond its declared embedding: ray seats with five probes, 15 mm apart;
- a cabin touching a tower or a station;
- a triangle-budget overrun: cabin 15k, tower 8k, station 60k.

Timber surfaces carry procedural textures, `textures.py`:

- 1 m tiles;
- UVs in metres along each part's grain;
- planks 10 cm wide (walls) and 12.5 cm wide (decks), with dark seams, staggered butt joints and matte roughness that
  varies slightly.

## Walkability

`walk.py` uses the same proxies that the build exports as UCX hulls:

- a 0.22 m capsule;
- 0.30 m step limit;
- 2.0 m headroom;
- 0.9 m minimum clear width;
- stairs: risers at most 0.30 m, treads at least 0.25 m, at least 0.9 m wide;
- the cabin door at least 0.9 m wide and 2.0 m high.

It reports route bottlenecks, pinch points, trapping pockets and slivers, and the stair riser and tread checks. A
disconnected or narrow route, a pinch on a route, a trapping pocket, a stair or door under the rules, or a berth door
outside its gate (the door's clear width centred on the door), a boarding gap outside 0.05 to 0.12 m or a sill
outside 0 to 0.03 m above the platform fails the audit. Slivers and off-route notches are listed but do not fail it. Each
station is checked with a cabin in each berth with its doors open, so the boarding routes run from the access through
the gate into the cabin.

## Contracts

- **closed-visible-geometry** and **pieces-meet-by-construction:** see Mesh rules.
- **ground-is-the-rendered-surface:** world placement queries the final exported terrain with explicit region ownership
  and resolves the North Trail overlay for walking contact. Complete foundation, footing and access footprints must
  be covered. Every access-floor triangle is checked against the owned ground, including landings and fitted joins.
- **walkable-routes-traversable:** the kit's raster walk audit checks both berths. The committed
  `scenarios/gondola_roundtrip_live.py` additionally drives the imported access, boarding and alighting routes at both
  ends of each line, rides both directions and refuses a stall, a lost rider or a tilted cabin.
- **one-implementation-per-mechanism:** `solid.py` adapts the shared `world/solid_mesh.py` builder and audits while
  preserving the kit's geometry, tags and timber grain. The rope path, grip frame and groove check use `rope.py`.
  Runtime riders share `FTransportRiders` with the ferry and train.

## World integration (B4)

The normal dependency graph prepares and imports the complete network:

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi
```

- **Routes:** L1 joins Hidamari to the southeast rim; L2 joins Belmonte to the northwest rim; L3 joins the crater
  floor to its separate southeast rim station. Regional placement records supply the station mouths and tower
  locations; `world/regions/gondola/site.py` fits six stations and ten towers to the final world. Foundations use
  timber posts and braces with individual stone feet. Access stairs terminate on the existing walking surface.
- **Required preparation:** the graph builds all canonical kit pieces, extracts source-bound final ground, fits
  foundations and access, exports all rope detail levels, then writes runtime data. It refuses stale or missing
  inputs, incomplete footprints, failed closure, coplanar overlaps, unsupported fittings and triangle overruns.
- **Ramps and jumps:** placement leaves the riding geometry unchanged. Complete triangle bounds include the moving
  cabin length and sag; the floor-to-rim line must stay at least 15 m above riding and jump geometry. Cabin-to-ground
  clearance must be at least 6 m outside the station approaches. Approach and access checks remain separate.
- **Actual fitted contact:** both travel directions use the fitted rope profile. The near rope is reduced only
  within its remaining 2 mm jaw budget. The build reads the exported FBX back, preserves its imported world
  transform, models float32 centimetre storage, and checks all 114 groove samples at every directed audit pose.
  The resulting axis displacement also reduces the hardware-clearance bound, which must remain at least 0.095 m.
  More distant rope meshes have explicit minimum viewing distances.
- **Runtime and import:** preflight verifies the current kit, ground, site proofs and every generated file before
  Unreal asset mutation. Cabins and physical doors follow a shared deterministic clock; cabin floors stay level
  while the grips follow the rope. The service owns boarding membership, map stops, corridor vegetation clearing
  and state-driven transport audio. Late snapshot application does not replay historical sound cues.
- **Game evidence:** the round-trip scenario exercises ordinary walking and the production clock. Native runtime
  tests, physical traversal captures and any unrun real-peer or listening checks are recorded with their exact
  revisions in the implementation PR; geometric preparation alone does not establish physical traversal.

The collision is in this kit: every piece (the cabin, each tower, each station's walkable parts) exports its UCX
convex hulls, and the build fails on a proxy that is not convex, or on a walkable slab (platform, plaza, boardwalk,
viewing bulge, stair landing) with any part not standing on a collision hull at its own walking height, within 1 cm
(`checks.floor_support_failures`).

## Asset library

Everything here is procedural Python plus Markdown and JSON. Under `games/yorimichi/assets`, only `.glb`, `.npz`,
`.blend`, `.png` and `.jpg` files need `source-library.json` entries, so nothing is registered. The textures and
models are build outputs under `build/`.
