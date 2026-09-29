# Momiji Hamlet

A small autumn forest settlement off the existing mountain road: a two-storey
tea house, two cottages, a pottery workshop and a storehouse. Its continuous
2.6 m dirt trail winds through a 70 m forest buffer before revealing the houses;
a short branch loops around the maple and covered well. The original asphalt
road stays clear, with a small wooden waymark beside the entrance. Its arrow-shaped board follows
the trail direction and carries markings on both faces.
Buildings are modeled exteriors with closed doors, not explorable interiors.

The built-in imagegen tool designed the original
[village concept](references/concept.png) and [building sheet](references/buildings.png)
using actual game screenshots as aesthetic references. Exact prompts are saved
alongside those images. Implementation is editable Blender geometry, not a
concept image projected into the game.

## Rebuild

From the repository root, with Blender and Unreal 5.8 installed:

```sh
# JAPAN_PYTHON must provide NumPy and Pillow, as required by the world generator.
JAPAN_PYTHON=/path/to/python3 japan/run.sh village
python3 japan/village/preview.py village-scout --scout --shots overview,entrance,square,workshop,forest
python games/yorimichi/tools/benchmark.py village-walk --view road_walk --route village --seconds 25 --hide-hud
```

`layout.py` integrates the settlement after the original seeded world is generated.
It grades only the local terrace and lanes, clears obstructing foliage, seats
nearby trees, and preserves the original road, player spawn and remote scenery.
`build.py` creates the buildings, covered well, signs, lane and edge walls;
`decorations.py` creates household furniture, planting and leaf litter.

`out/village/Village.blend`, FBXs and Unreal assets are reproducible local output.
The importer checks source, world, heightfield and FBX hashes before updating the
assets. It imports only the village and revised terrain, preserving the existing
level lighting, characters, skating and saved preferences.

The resident system uses existing Wanderer rigs and animations with separate
clothing palettes. These are cosmetic village occupants, with no conversations
or quest AI. Their movement stays beside the houses. Pose evaluation stops when
off screen, and activity pauses at long distance. Cloth hems move through a
small pinned vertex displacement; buildings and collision remain stationary.

## Review and verification

The user requested an independent visual review followed by screenshot-based
imagegen iteration. The first candid review is saved in
[first-independent-review.md](review/first-independent-review.md).

`verify.py` checks authored slopes, asset budgets and unchanged distant scenery.
The overview capture additionally runs live ground traces, capsule sweeps across
the lane width and collision checks against every building. Movement captures
exercise both characters and skating. Captured footage uses fixed 60 Hz
simulation and is not frame-rate evidence; the separate uncapped benchmark
records actual frame times.


The [second independent review](review/second-independent-review.md) guided the
last pass: native understory, seated props, varied pottery, a leafy trellis,
quieter olive roof, and a maple-leaf forest gate. A separate
[screenshot-based Imagegen paintover](references/polish.png) suggested seasonal
path edges, domestic details, a welcoming square and a stronger forest threshold.
Those changes are modeled in the scene; the paintover is a concept reference.

## Secluded forest revision

The built-in Imagegen tool produced [the forest approach](references/forest-approach.png)
and [the well nook](references/well-nook.png), using actual game captures as references.
Their exact prompts are [forest-approach-prompt.txt](references/forest-approach-prompt.txt)
and [well-nook-prompt.txt](references/well-nook-prompt.txt).

The houses now sit 70 m farther into the forest. A narrow dirt trail replaces the
former pale road apron, with the dirt mesh clipped outside the asphalt shoulder.
Terrain-conforming geometry and a broken, earthy colour transition soften its
verges. The well has warm irregular masonry, a wooden shingle canopy, rope and
bucket; the raised rectangular platform and surrounding fence are gone. Smaller
fallen leaves collect under the maple and along edges, with quieter travel lanes.
Forest understory is kept out of the tea-shop terrace and other household aprons.
A main-road exclusion also reserves bush canopy and grass blade width beyond the
asphalt edge; verification checks all newly authored foliage against the baseline.
Leaves share the existing opaque batched mesh and need no per-leaf actors or ticks.

The [independent revision review](review/secluded-village-review.md) guided the
last pass: dirt shoulders, warmer masonry, concentrated leaf drifts and a clearer
arrow on the wooden sign. The previous reviews above describe earlier iterations.

Current measured results and source evidence are in [verification.json](verification.json):
131,103 triangles across 12 meshes; 990 ground probes and capsule sweeps, all five
building fronts and 2,165 tree roots passed. The 587 m spawn-to-village rehearsal
had no falls, a maximum 32.7 cm skating deviation and normal 2.9 m/s running.
The final uncapped 1080p forest/village skate route averaged 75.2 fps on the M3 Pro,
with p95 15.45 ms and 98.8% of frames within 16.67 ms. Preferences were preserved.

![Current forest entrance](review/secluded-roadside.jpg)
![Current well nook](review/secluded-square.jpg)
![Cleared tea-shop terrace](review/secluded-teashop.jpg)
The historical screenshots and film below show the earlier roadside layout.

## Continuous village film

```sh
python3 japan/village/film.py village-rehearsal --rehearse
python3 japan/village/film.py village-journey
python3 japan/village/export_film.py village-journey --zelda-lofi --icloud '/path/to/iCloud Drive/Japan - Forest village'
```

The opt-in director begins at the ordinary player spawn. It supplies real board
steering, pushes and braking, stows the board through its normal animation, then
runs to the tea table, well, cottages, storehouse and pottery workshop. Like normal
gameplay, the tour now uses running by default; Alt remains the deliberate walk control. A camera
rise closes on the village and surrounding forest. The pawn is never teleported
along the route. Pauses and camera movement are authored for this film only.

A sparse rehearsal saves one frame every two seconds while retaining every
simulation sample. The final capture saves every frame as high-quality JPEG,
using Unreal's screenshot callback to avoid PNG compression stalls. Screenshots
are exported to continuous 60 fps H.264/AAC MP4s with chapter markers and a smaller
720p iPhone version. The optional score reuses the Mikel / GameChops Hateno Village
track previously selected for the personal trailer, with credits beside the videos.
Native 1080p rendering is forced only for
the recording; saved preferences are preserved. Movie frame rate is not a game
performance measurement. Capture checks enforce all stages, normal spawn,
continuous pawn movement, successful dismount, frame writes and the aerial rise.

Use `--replace` with `export_film.py --icloud` when intentionally updating an
existing delivery. Both local exports must pass complete decode checks before
replacement starts; each destination is replaced atomically after its staged
copy passes the hash check. Without that flag existing movies are preserved.

Large source frames and movies stay in ignored output directories and iCloud.


The updated full film is **2:27.450**, with 8,847 frames and 587 m of continuous
movement. It begins at the ordinary spawn, follows the forest trail into the
relocated village, visits all five buildings at the normal running pace, and
ends above the village and surrounding forest. The capture had no falls and a
maximum skating deviation of 32.7 cm. The sign, cleared asphalt and tea terrace,
covered well and autumn planting are all present. Export and cloud verification
are recorded in [film-verification.json](film-verification.json).

On iPhone: **Files → iCloud Drive → Japan - Forest village →
Japan - Village journey - iPhone.mp4**. The updated 1080p master is in the same
folder. These replace the earlier movies under the same filenames.

![Updated game footage: closing view](review/secluded-film-birds-eye.jpg)
