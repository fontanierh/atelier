# Passenger ferry

The old-school passenger ferry between Yorimichi's harbour towns, modelled after the approved concept C
(`ferry_oldschool_c.jpg`). It is about 80 m long, with a long white hull, a raked bow and an elegant sheer. A blue
boot-top and a gold rope moulding run along the hull. The forward deckhouse is a low varnished timber house with a
rounded (superellipse) front and a continuous band of tall windows. Above it, a shorter, narrower wheelhouse with a
rounded front sits well back, with a narrow white deck walk and rail round it. Its railed roof carries a brass
searchlight and bell. The midship house is white, with varnished, white-framed window bays set in raised white portals
between white pilasters. One fat, faceted cream funnel tapers to a black top band and a smaller black inner stack.
Short, fat brass bell-mouth cowl ventilators stand round it on white drums; their mouths are dark warm brass inside.
Slim, pointed clinker-built lifeboats in golden-brown varnish hang in bays framed by white pillars. Each has a
pronounced sheer, a dark gunwale cap and a cream canvas cover tented over a ridge line, with its skirt draped below
the gunwale and lashed down. Each boat hangs from blocks and falls in tall gold radial davits that stand on the boat
deck at its ends. The boats stay inside the hull's beam, clear of the house and with headroom over the main-deck
walk below them. There is a foremast with a
crosstree and a brass lantern on a forward platform, and an aft mast, both with a few fine tarred stays. A canvas
canopy covers the stern deck. A stockless anchor sits in a recessed, white-lipped hawse pocket on each bow.

The normal build prepares and imports the ship and both terminals, stages the timetable, and opens the audited
Hidamari quay access. One ferry shuttles between Hidamari and Brinecove from the shared server clock.

## Build and review

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.safety.guarded --report build/yorimichi/ferry/logs/build \
  --timeout 900 --small 3 --purpose 'ferry model build' -- \
  $B --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/ferry/build.py
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.safety.guarded --report build/yorimichi/ferry/logs/render \
  --timeout 900 --small 3 --purpose 'ferry review render' -- \
  $B --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/ferry/render.py
uv run python games/yorimichi/assets/vehicles/ferry/compare.py
```

- [`build.py`](build.py) writes `FY_Hull`, `FY_Superstructure`, `FY_Funnel`, `FY_Lifeboats`, `FY_Rails`, `FY_Masts` and
  `FY_Fittings` as FBX files under `build/yorimichi/ferry/assets/`. It also writes `ferry.blend` and `manifest.json`
  (triangle counts, bounds, decks and boarding openings).
- [`render.py`](render.py) renders three views into `build/yorimichi/ferry/review/`: the concept's camera, which was
  fitted to the concept's hull lines, an orthographic side elevation and a top view.
- [`compare.py`](compare.py) writes `compare_*.png` with the concept on the left and the render on the right. It also
  writes a 50% overlay of the matched view and close-ups, `closeup_*.png`, which crop the concept and the render to
  the same framing: both rigging areas, the funnel and ventilators, the lifeboats and the bow anchor. A side-view
  stair close-up compares the previous side elevation with the current one.
- `build.py` also writes `assets/FY_Collision.fbx` and `deck_layout.json`, and runs a deck audit (see below).
- [`walk.py`](walk.py) runs without Blender (`uv run python games/yorimichi/assets/vehicles/ferry/walk.py`). It reads
  `deck_layout.json` and writes `review/walk_report.json` and a top-down layout per deck, `review/walk_*.png`.

## Model

- Units are metres. +X is the bow, z is up and the waterline is at z = 0.
- The ship is 80.1 m long, 12.0 m across the swung-out lifeboats and has a 2.6 m draft; the masthead is 24 m above
  the water. There are about 89k triangles in all: the hull 22.9k, superstructure 19.1k, rails 16.3k, lifeboats
  19.6k, fittings 8.5k, masts and rigging 2.1k and funnel 0.3k. The collision file holds 920 convex hulls.
- Materials: `FY_WhitePaint`, `FY_BootTopBlue`, `FY_GoldMoulding`, `FY_VarnishedTimber`, `FY_DeckTimber`,
  `FY_CreamFunnel`, `FY_Black`, `FY_Brass`, `FY_Canvas`, `FY_Glass`, `FY_DarkIron`, `FY_Lifebuoy`, `FY_BoatTimber` and
  `FY_TarredRope`, `FY_CowlThroat`, `FY_AnchorBronze`, `FY_HawseRecess`, `FY_BoatTimberDark`, `FY_BoatGunwale` and
  `FY_BoatCover`.
- Ship and terminals build on the shared closed-solid builder, [`world/solid_mesh.py`](../../../world/solid_mesh.py)
  (prisms, lofts, boxes, beams, tubes, lathes, tori and `to_object`); the kit keeps only its materials.
- Every part is a closed solid. Roofs, decks, canopies and covers have thickness. The build fails on any open edge
  and flips any part whose normals face inward. The hawse pockets are cut into the closed hull with an exact
  boolean, so the shell stays closed.
- The hull lines and the positions of the superstructure come from a pinhole camera fitted to the concept's hull
  edge, rope moulding and boot-top. The upper decks follow the sheer, as they do in the painting.
- Rigging follows the painting: a forestay pair from the lamp platform to the foredeck, and three shrouds on each
  side of the foremast (one from the masthead crosstree, two from the lamp platform). The shrouds set up on the
  monkey island inside its rail. The aft mast has two shrouds on each side to the boat deck. The landing points
  were solved so that each stay matches its painted line in the concept camera. Stays are 2 cm tarred rope (1.6 cm
  on the aft mast), with brass turnbuckles and eye plates at the deck ends and brass bands at the mast fittings.
- In game, the stays are about a pixel wide at normal viewing distances and will alias. Keep them in a separate
  LOD section: draw them with temporal AA, or as camera-facing ribbons whose opacity fades with distance (about
  1 px minimum width), and cull them from about 150 m.
- Walkable decks:
  - the main deck all round the hull, with rails;
  - the boat deck, reached by the companionway stair, with a narrow walk round the wheelhouse;
  - the open stern deck under the canopy (the canopy stops at x = -24.6 to give the stair headroom). Benches line its
    sides, and a white seat-locker with a timber top fills the narrow stern tip and carries the stern lantern;
  - the monkey island on the wheelhouse roof, reached by a ladder. The ladder is climb-only: it has a gate in the
    roof rail and side rails that stand above the roof.
- Companionway: a straight fore-and-aft flight on the starboard side of the centreline (y -1.7 to -0.7, 1.0 m wide).
  It climbs from the stern deck to the boat deck's aft edge. Its treads are solid and closed, with stringers and
  handrails on both sides. The top lands through a gated opening in the boat-deck rail. `manifest.json` records its
  risers, rise, tread, angle, foot and top.
- Deck audit: every deck fitting registers seat points. Fittings with a footprint register each corner of the
  footprint, and bench legs register both feet. The build ray-casts each seat onto the deck-bearing meshes and fails
  if there is a gap over 1 cm or a penetration beyond the fitting's declared embedding. It also fails if a lifeboat
  touches the ship. On the sloping sheer, flat-based fittings (windlass, capstan, bollards, vent box, lockers, lamp
  pedestals and monkey-island fittings) stand on deck-following plinths, so no edge floats. The build also fails if
  any fitting triangle meets a rail triangle. The result is in `manifest.json` under `deck_audit`.
- Collision: `FY_Collision.fbx` holds one `UCX_FY_Collision_###` convex hull per deck, house and obstacle proxy. It
  also holds a tiny placeholder render mesh, `FY_Collision`, which should be hidden or deleted after import. The
  same proxies drive the walk analysis.
- Walkability, for a player capsule of radius 0.22 m and half-height 0.755 m: `walk.py` rasterises the proxies
  that fall in the capsule's body band and measures clearance with an exact distance transform. It reports the
  narrowest point of every required route against a 0.9 m minimum (0.6 m for short, isolated pinches). It also
  reports any free pocket that the capsule cannot sweep, headroom per stair tread, and the stair and landing
  dimensions. In the layout images, walkable area is green, the capsule-dilated margins of obstacles are pink,
  pinches are annotated with their width, and the boarding openings are marked.
- Boarding: there is a 2.2 m opening in the main-deck rail amidships on both sides, centred at x = 15.2, in front of
  the deckhouse's white-framed side door. It has brass gate posts and a landing plate. The gangway lands on the deck
  edge there. `manifest.json` records its centre, width and outward direction.

## Terminals

[`terminals/`](terminals/) holds the berths and the terminal kits for Hidamari and Brinecove. Like the ship, they are
placed by the production ferry service. The normal recipe runs these audited preparations in order:

1. [`world_probe.py`](terminals/world_probe.py) (Blender, `-- WORLD_BUILD`) exports the real geometry around both
   berths from a built world: the ground (HD_Terrain and the far hills; the Brinecove ground tiles) and every solid the
   game places there (Hidamari's harbour mesh and every `city.json` instance at its position, yaw and scale, including
   the moored HD_Boat workboats; every Brinecove `runtime.json` group at each transform, read back from Unreal's frame).
   It writes `world_<harbour>.npz` with the sha256 of every file it read.
2. [`site.py`](terminals/site.py) runs without Blender. It sweeps the ship's full outline (half-width plus 0.4 m) and
   its underwater footprint along the authored arrival and departure manoeuvres (ahead, crab, berth, pivot, glide)
   against those exported triangles:
   - Structure rule: the outline keeps 4 m from every exported solid and from land while manoeuvring
     (`STRUCTURE_CLEARANCE`). Only on the berthing crab, onto or off the fenders, may the berth's own structure (the
     terminal deck and the exported solids inside the berth zone) come closer, and the outline must never touch it.
     Everything outside the berth zone keeps 4 m, alongside too.
   - Keel rule: the exported seabed under the underwater footprint stays at or below −3.3 m (0.5 m keel clearance plus
     0.2 m margin). A swept cell with no exported ground counts as grounding.
   - It also measures the walk levels the kits stand on from the exported surfaces (Hidamari quay coping and
     promenade, Brinecove pier deck) and records the probes' and its own code's sha256 in `site.json`.
   - Hidamari: berth at (855, −145), bow west, on a jetty off the quay. The ship arrives north along x 872, pivots at
     (872, −190), glides to the stand-off line and crabs onto the fenders; it leaves in reverse. Nearest exported solid
     while moving: an HD_Boat workboat at 4.49 m. Seabed under the keel: −3.32 m at worst.
   - Brinecove: berth along the west pier's west face (local (−251.2, 10), bow north). The ship runs north 4 m west of
     the berth line, east of the rowboat moored at (−270, −145), glides 9 m west at y −95 to pass west of the rowboat
     moored at (−250, −40), and crabs 13 m east onto the fenders. It leaves by crabbing 40 m west, pivoting 180° and
     running 260 m south. Nearest exported solid while moving: 5.0 m. Seabed under the keel: −3.92 m at worst.
3. [`build.py`](terminals/build.py) (Blender) refuses a `site.json` whose recorded inputs changed or whose sweep
   failed, builds the kits and writes `terminals.blend`, FBX render meshes and `FT_HD_Collision.fbx` /
   `FT_BC_Collision.fbx` (one `UCX_` convex hull per deck, stair flight (as a ramp), landing, brow, rail run, post,
   bench and wall; a tiny placeholder render mesh to hide or delete after import):
   - Hidamari: `FT_HD_Jetty` (piles, deck, black fenders hung 5 cm off the hull), `FT_HD_Stage` (a two-level timber
     boarding stage: the ship's gate is at 6.94 m, 4.5 m above the quay coping, so a stair of 19 equal risers climbs to
     a gallery at sill height under a kawara roof), `FT_HD_Brow`, `FT_HD_WaitingHouse` (its door
     steps down to the quay in equal risers of at most 0.2 m, from the quay level `site.py` measures at the door) and
     `FT_HD_Timetable` (on the quay west of the jetty root, at its measured level; east of the root is the canal
     mouth).
   - Brinecove: `FT_BC_Landing` (a framed timber stage at sill height, closed underneath, with a 7-riser stair down to
     the pier deck), `FT_BC_Brow`, `FT_BC_Pavilion`, `FT_BC_TicketHut`, `FT_BC_Fenders` (piles standing off the pier
     edge on chocks, tyres 5 cm off the hull) and `FT_BC_Props`.
   - Brow: 1.9 m wide, so it passes between the ship's brass gate posts (inner faces 1.04 m off the gate centre). Its
     body stops 3 cm outside the hull side and rises to a steel lip that rests 3 mm above the ship's level landing
     plate, 0.55 m inboard. At the gates the ship's covering board stops and the landing plate runs out to the hull
     edge.
   - Audits, each failing the build: closed meshes; ship against terminal in 3D, with ship C's meshes at the berth
     pose (no terminal triangle may meet a ship triangle; the fender and brow gaps are reported); and a ray-cast walk
     from inside the waiting house (Hidamari: out of its door, along the quay clear of the canal wall's railing at x 840)
     or from the pier (Brinecove), over the brow onto the ship's deck ([`walkcheck.py`](terminals/walkcheck.py), plain Python),
     on the exported world's own surfaces near the route and the ship itself. For a 0.22 m player capsule: step at
     most 0.25 m, headroom at least 2.1 m, width at least 0.9 m, at least 0.22 m clear on each side of the route
     line, a floor everywhere, and nothing across the way at knee, waist or head height on the line or 0.22 m to
     either side. World geometry that B3 must remove is recorded by `site.py` in `site.json` (`world_cuts`: a plan
     band, an x span and a base height, so posts go with their rail); the walk leaves it out, and `manifest.json`
     reports what it removed under `world_cuts_pending`. Today that is Hidamari's quay timber rail and its posts
     across the jetty root (x 831.8–847.8).
   - Seat and coplanar audits ([`world/solid_mesh.py`](../../../world/solid_mesh.py)), also failing the build. Every
     fitting (posts, footings, props, bench legs, plant pots) registers its base points, and every gable infill
     registers points along its sloped edges. Each base is ray-cast onto the kit and the exported ground near it: down
     for feet, which must stand at most 1 cm off what carries them and no deeper than their declared embedding, and up
     for gable infills, which must reach the roof underside within 2 mm, one ray per point so the slope cannot hide a
     gap. No two parts may have same-facing coplanar faces that overlap (they z-fight).
   - A carried-by audit covers everything the seats do not (roofs, trusses, rafters, hung tyres, lanterns): each kit
     mesh is split into loose islands, islands touching within 1 cm (or intersecting) are joined into contact groups,
     and every group must reach the exported world under the whole kit (less the world cuts). The ship never carries a
     terminal part. Each uncarried group is reported with its size, its kit source lines and the nearest gap.
   - Before its own audits, the build runs `audit_fixtures()`, fourteen known cases: a floating, sunk and unsupported
     foot, a short gable infill under a sloped roof, two slabs sharing a top face, a part in the air, two parts 2 cm
     short of the ground and a part resting only on the ship must fail, and their fixed forms must pass. The results
     are in `manifest.json` (`seats`, `coplanar`, `carried`, `audit_fixtures`).
4. [`render.py`](terminals/render.py) renders the kits with ship C at each berth (`TERMINAL_VIEWS=a,b` renders a
   subset), and [`compare.py`](terminals/compare.py) puts them beside the v2 concepts.

`walk.py` (the ship's decks) also gates: it exits 1 on a route that does not connect or narrows below 0.6 m, a pinch
under 0.9 m that is not isolated, a trapping pocket, stair headroom under 2.0 m, an unseated fitting or a lifeboat
overlap. `tests/test_ferry_site.py` covers the sweep, the rasterising, the berth-zone rule, input binding, the brow
fit and the walk verdicts on small fixtures, without Blender or a world build.

## In the game

`atelier build yorimichi` includes `world.ferry_ship`, `world.ferry_probes`, `world.ferry_site`,
`world.ferry_terminals`, `world.hidamari_ferry_cut`, `world.ferry_service` and `unreal.ferry`.
The source-bound manifests refuse failed audits, changed exports and stale source code. Harbour and
open-water manoeuvres use the same swept full-hull and underwater rules. The sea sweep uses bounded,
overlapping tiles; missing seabed fails rather than being treated as deep water.

Each harbour owns its berth, manoeuvres and terminal assembly in `world/regions/<region>/ferry_terminal.py`.
The terminal kit supplies the shared building pieces. Hidamari's own `ferry_cut.py` opens the recorded
rail/post span while preserving the remainder of its harbour. Hidamari's normal importer owns the final
harbour package and always selects the validated cut mesh, preserving its materials and collision policy.
A targeted world reimport therefore retains the terminal opening.

`world/regions/ferry/service.py` writes one shuttle's timetable, with stationary boarding windows.
The runtime follows those samples from the shared server clock. Brass boarding gates close away from
the dock; gangway collision moves with the gangway. Walk onto the deck to ride it, and walk off at the
other harbour. The arrival boards and the ferry sounds follow that same clock and state.
Map destinations lead to the terminal approach without changing the timetable: wait when the ship is away.

`FTransportRiders` supplies the moving-base, capsule-response and camera-lag mechanism shared with the
Belmonte train. The ferry retains ordinary world collision and third-person view; the train retains its
own admission, seats and passenger camera. Alighting restores the captured state and clears the vehicle identity.
Fine masts and stays cull at 150 m.

For bounded native checks, `ferry.Go hidamari` / `ferry.Go brinecove` selects the next docking window when
nobody is aboard. `ferry.TimeScale` changes the diagnostic clock speed. Live helpers expose the state,
audited walking points, ship-local points and sound loops (`FerryState`, `FerryPoint`, `FerryLoops`).
Native automation tests under `Yorimichi.Ferry` cover interpolation, wrap, boarding windows, invalid
line data and shared rider cleanup. [Integration validation](https://github.com/fontanierh/atelier/pull/494)
records guarded, revision-bound ordinary walking over both harbour routes in both directions,
both sea voyages and moving-deck walking at `bb28064b`, plus companionway ascent/descent at `b2dc033a`.
The production geometry and native binaries are identical across those two revisions. Arrival/departure
horns, brow/fender events and engine-loop state were recorded; this is event evidence, not a listening-quality
assessment. Actual two-process and late-join play was not run because the existing compound worker refused
its available-memory prerequisite before either game launched. Native remote-membership regression
coverage is separate from that reduced real-peer coverage.
