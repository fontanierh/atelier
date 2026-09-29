# Zeppelin link — woodland ↔ Hidamari

Status: implemented, visually checked in Unreal, and tested through the streamed touch controls in both directions.

Extend the trail west of the hidden woodland lake to a small air station. A shared zeppelin service connects this clearing to Hidamari's station district in both directions.

## V2 requirements

- Fully **open passenger deck**: shallow wooden hull, perimeter railings, simple benches, helm and hinged boarding gate. No enclosed cabin, windows, windshield, roof or canopy.
- No diagonal ropes or lines between propellers and deck. **Two pods total**, one per side, attach directly to the envelope with short rigid brackets. Four independent vertical struts support the deck from the envelope keel.
- **Animate the propellers in the build**: separate blade meshes, correctly aligned hub pivots, slow docked rotation, smooth acceleration on departure and deceleration on arrival. The runtime rotates separate blade meshes around their hub pivots.
- Ground the city reference in actual game captures. The first concept's immediately adjacent lake and bridge were inaccurate and must not guide placement.

## Review images

- [Open-deck zeppelin and boarding sheet](../../../output/imagegen/zeppelin/v2/01-open-deck-final.png)
- [Revised woodland stop](../../../output/imagegen/zeppelin/v2/02-woodland.png)
- [Hidamari concept from the actual site](../../../output/imagegen/zeppelin/v2/03-hidamari-grounded.png)
- [Actual matching ground view](site-stills/hidamari-site-ground.png)
- [Actual district overview](site-stills/hidamari-site-overview.png)
- [Actual view toward the dry plot](site-stills/hidamari-site-east.png)

Earlier images in `output/imagegen/zeppelin/` remain historical v1 concepts. The intermediate v2 `01-open-deck.png` retained an extra near-side propeller and closed boarding gate; `01-open-deck-final.png` corrects those details and governs the station variants. Do not build from the superseded closed-cabin references.

The user flagged the **front panel as buggy**. It is not a geometry blueprint. The side and boarding panels govern the implementation: one motor per side, four independent supports, a coherent rounded envelope and an open deck.

## Locations checked in the game

Coordinates are Blender metres: X east, Y north, Z up. Both modules are now installed at these shared layout origins.

- **Woodland: (-205, 230)**, about 115 m west of the lake centre; terrain graded to 70.4 m. Continue from the cabin around the southern shore, then west through the woods. Preserve the cabin, water and islet. Use a low supported pier on gentle terrain.
- **Hidamari: (1273, 308)**, east/northeast of the existing station at (1185, 290). The new candidate is on dry grass **east of the X=1240 road**. The initial candidate (1245, 320) was too close to the road; shift the footprint east. Terrain at the new centre is 34.29 m, with about 2.34 m variation across sampled opposite corners. Proper local grading and foundations are required. Keep the existing station, forecourt, road and crossing intact.
- The park pond is centred at **(1030, 284)**, about **244 m west** of the revised candidate. It appears in the upper left of the aerial still, beyond the station block and roads. The new terminal is not on its shore. No new pond or bridge is proposed.

Checks used `hidamari/layout.py`, `out/hidamari/city.json`, terrain samples and three fresh native screenshots. Generated concepts propose additions to those views; they are not screenshots of built content. The implemented footprints use local grading, ground-sampled foundations and explicit foliage clearance.

## Visual and interaction brief

Retain the cream-and-sage envelope, gold sunrise mark, clean rounded/faceted silhouette and cedar deck. Initial envelope target: about 26 m long and 8 m across. The old 7 m closed-cabin specification is superseded; reconcile open-deck proportions and character clearance against the revised sheet.

The woodland station retains its tiled timber ticket hut and leaf-strewn trail. Hidamari uses the same vocabulary with a modest paved forecourt connected to the actual streets. Both share a clearly accessible side boarding gate and short gangway with closely matched floor heights.

**Use → board → close gate/retract gangway → propeller acceleration/lift-off → scenic flight → dock → reconnect gangway/open gate → disembark.** Reverse the same flow for the return trip. A call bell can avoid stranding a player who reaches the opposite terminal by map travel. Gentle airborne rise and banking and boarding animation accompany the rotating propellers. No player piloting system is proposed.

## Implementation

- `japan/zeppelin/layout.py` owns both stations, ship/entry/safe datums, the southern-shore woodland trail and terrain/foliage clearance. The lake, cabin, rock islet and existing city roads remain intact.
- `japan/zeppelin/build.py` exports the envelope/deck, motor pods, propeller, gate, gangway, two stations and trail. Approximately 43k triangles in eight meshes. Fittings and stations reuse the village material; the fabric has one additional material slot with continuous sun-driven shading and distance haze. The actual sun direction updates this material when lighting settings change.
- `AZeppelinService` owns a single shared ship and a state machine: docked → boarding → takeoff → cruise → landing → disembarkation. The passenger walks across the gangway, stows equipment, rides with the ship and receives normal movement again on the platform. Independent propellers spool up and down. Gates close and gangways retract before departure.
- The opposite terminal can call an empty ship. Use during flight skips to safe docking; map travel or Back to spawn cancels passenger control cleanly. Camera look remains available during travel. Idle dock gates stay closed until boarding begins, while the docked deck has real floor collision. A player who jumps onto the deck can also board from there.
- Both terminals are in the desktop and iPhone destination list. On the platform, the phone Use button becomes **Fly**, **Call ship**, or **Skip flight**. The flight is a passenger ride, with a 28-second cruise plus departure/arrival.

## Flight view and ride speed

The passenger camera pulls well back once the ship lifts off, so the landscape reads during the cruise:
the arm scales with the player's own camera-distance preference (`StoredArm*11`, clamped to 4200-7000 cm)
and the boom rises with it. It returns to the player's setting on disembarking.

The ride speed is the passenger's to choose, stepping through **0.5x, 0.75x, 1x, 1.5x, 2x and 3x** around
the authored 28 second cruise. It scales takeoff, cruise and landing alike, the propellers spin to match,
and the choice persists between flights. Boarding and disembarking keep their authored pace.

- Phone: **Slower** and **Faster** sit either side of the Use button for the whole ride, from boarding to
  arrival. The Faster button shows the current setting, and the status line and hint carry it too.
- Desktop: `[` and `]`. Gamepad: the left and right shoulder buttons.
- The page sends `{yorimichi:1,action:'flightSpeed',delta:-1|1}`; the game answers with `flightSpeed` in
  its telemetry. Only the current passenger can change it.

![Cruise at 3x](flight-controls/flight-3x.png)

## Flight-control regression checks

Departure framing now runs once when boarding transitions to takeoff, independently of the flight
speed or frame duration. Camera look remains under passenger control after that transition.

`node japan/streaming/zeppelin-smoke.mjs` performs full flights at all six supported speeds,
starts at 3x, verifies that the return trip retains that selection, checks both speed limits,
and changes speed in flight. It checks the actual streamed camera angles and touch look,
arrival support, calling, skipping, cancellation, and restored jump/skate controls. Its deadline
includes a whole 0.5x flight plus boarding/disembarkation. Speed steps wait for acknowledged
telemetry, without retrying a press that could overshoot the requested value.

September 10 validation: all 27 live checks passed, covering nine rides including a full journey at
each speed. Measured flight time ranged from 77.03 seconds at 0.5x to 12.75 seconds at 3x;
1,619 airborne telemetry samples had a median of 60 FPS. The saved settings checksum stayed
unchanged. This run used the stream's Metal debug-label fix (see the streaming memory report).

## Rebuild

The generated FBX, world JSON and Unreal assets follow the repository policy of remaining in ignored output directories. From an existing pre-zeppelin lake build:

```sh
# Use a Python environment containing NumPy and Pillow.
PYTHONPATH=japan python3 -m zeppelin.layout
blender -b --threads 2 --python-exit-code 1 --python japan/zeppelin/build.py
blender -b --threads 2 --python-exit-code 1 --python japan/build_terrain.py
HIDAMARI_ASSETS=HD_Terrain blender -b --threads 2 --python-exit-code 1 --python japan/hidamari/build.py
python3 japan/tools/build_map.py
# Stop the stream before any native import/review. Keep one Unreal process running.
# Import with Scripts/import_zeppelin.py, then compile JapanProtoEditor.
python3 japan/streaming/run.py build-web
```

The targeted layout command saves a pre-zeppelin baseline under `out/zeppelin/source` and always regenerates from it. A full `gen_world.py` run invokes the zeppelin integration after the lake. To rebuild meshes alone, set `ZEPPELIN_ASSETS_ONLY=1` during the importer invocation.

## QA

- `japan/tests/test_zeppelin.py`: lake/cabin route clearance, unchanged lake bed and city roads, boarding floor datums, exactly one copy per terminal, and the generated rotor sweep.
- `japan/zeppelin/qa.py <fresh-folder> 0|1`: thirteen native views around each station plus sixteen real visibility/pawn collision probes across stairs, landing, gangway and ticket-hut veranda.
- `node japan/streaming/zeppelin-smoke.mjs`: real streamed touch controls, both complete journeys, independent propeller motion, call, skip, spawn cancellation, restored jump and skateboard.
- `node japan/streaming/zeppelin-smoke.mjs --trail`: actual walk from the lake to the woodland station, then up the steps.
- `node japan/streaming/zeppelin-smoke.mjs --release`: boarding from the skateboard, automatic stowing, a complete flight, city steps and the pedestrian connection to the existing street.
- `zeppelin/check_rotors.py`: tests the actual mesh at 720 angles per rotor and proves continuous clearance using the swept cylinder, including angles between samples. The 3.3 m diameter blades clear every part of the hull by at least 31.9 cm. The two centres are 6 m either side of the centreline; rigid mounts connect them to the envelope. The build runs this check automatically.

The first native pass caught bevelled plank/apron seams causing poor floor normals. Continuous walkable surfaces fixed all sixteen forest probes. Visual review also corrected unsupported flower heads, lantern mounts, roof posts and an emblem cutting through the curved envelope.

Native views and ground checks passed at both stations, with settings unchanged. The touch test passed both full journeys, call/skip/cancel and restored jump/skate controls. The woodland route completed with zero falling samples. The final two flights recorded 59.6–60 FPS across 445 samples; this is a local streamed run, not a guarantee for every phone connection. Final camera, propeller, material and gameplay evidence is recorded in [review/qa.json](review/qa.json). Keep the existing 10 GiB process guard active for native captures and the stream.

## Generation

All v2 concepts use **GPT Image 2.5 Sunburst**, via the imagegen skill's bundled CLI with explicit `--model gpt-image-2.5-sunburst --quality high`. [Prompts, source images and hashes](../../../output/imagegen/zeppelin/v2/provenance.json) are saved alongside the images. Preserve historical provenance. The user approved v2 before implementation.
