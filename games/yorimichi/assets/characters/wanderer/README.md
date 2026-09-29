> Wanderer is an NPC only. The yellow kid is the player character. Keep his hat
> for village life; any future authored skating sequence must remove and stow
> it before he climbs the ramp. No Wanderer skating sequence is enabled now.

# Wanderer V2

The playable Wanderer now follows Yellow Boy's proportions and graphic style:
large simple face, broad angular hair, tied topknot, short moss haori, rust scarf,
cropped trousers and slim shoes with thin, flush soles. A single belt pouch and
faceted straw hat preserve his traveller identity. Yellow Boy's mesh is unchanged.

![Wanderer V2 in the game](review/game-front.jpg)

## Imagegen references

The built-in imagegen tool produced the [model sheet](references/design-sheet.png),
[walking, running and action sheet](references/motion-sheet.png), and
[skateboard motion sheet](references/skate-sheet.png). Its inputs included the
original Yellow Boy reference and unretouched screenshots of both game characters.
Exact prompts are saved alongside those sheets as `*-prompt.txt`. Orthographic,
face, clothing and shoe crops are recorded in [crops.json](references/crops.json).

The sheets guide silhouettes, gesture and outfit construction. Their approximate
contact drawings are not motion capture: the actual animation uses constrained
foot contacts, continuous stride recovery and modest ollie knee flexion.

## Source and assets

- `wanderer_mesh.py`, `wanderer_hair.py`: editable metre-scale procedural geometry.
- `wanderer_rig.py`: 34-bone compact rig, independent head, scarf tails, pouch and hat.
- `wanderer_motion.py`: 21 clips at 60 Hz; quieter arms and shorter recovery than
  Yellow Boy. Walk 0.90 m/s, jog 1.80 m/s, default run 3.00 m/s, crouch 0.50 m/s.
- `accessories.py`: baked secondary motion, shared by foot and skateboard clips.
- `../cape_boy/animate.py`: shared contact solver; its defaults retain Yellow Boy's
  original poses. Geometry primitives and shoe contact conventions are also shared.
- `../../out/wanderer`: disposable `.blend`, FBXs, manifests and review renders.

The body has about 3,800 triangles and a single opaque vertex-colour material.
There are no cloth grain textures, woven straw microgeometry or fine hair strands.
Unreal uses `/Game/Wanderer/V2` for the new mesh, skeleton and base clips, and
`/Game/Skateboard/WandererV2` for its 18 regular/goofy skating clips. The existing
`/Game/Wanderer/DA_Wanderer` selection asset points to the new content. The previous
80-bone model is retained under `../../character` for historical comparison.

The skateboard importer derives ankle clearance from the rider's bind pose rather
than retaining the old tall character's offset. The shorter capsule and camera
framing match the new proportions. Both stances, repeated pushes and ollies remain
supported. The new rig uses the previously approved compact-rider ollie curves.

## Rebuild and import

Run from the repository root. Do not run Blender and Unreal rendering jobs together.

```sh
blender -b --threads 6 --python-exit-code 1 --python japan/characters/wanderer/build.py -- --animations --export --no-render
blender -b japan/out/wanderer/Wanderer.blend --threads 6 --python-exit-code 1 --python japan/characters/wanderer/review.py
# Refresh Yellow Boy when the shared solver source changes.
blender -b --threads 6 --python-exit-code 1 --python japan/characters/cape_boy/build.py -- --animations --export --no-render
blender -b --threads 6 --python-exit-code 1 --python japan/items/skateboard/build.py -- --render
japan/run.sh build
P="$PWD/japan/unreal/JapanProto"
E="/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd"
for SCRIPT in import_wanderer.py import_cape_boy.py import_skateboard.py; do
  "$E" "$P/JapanProto.uproject" -run=pythonscript "-script=$P/Scripts/$SCRIPT" -unattended -nop4 -nosplash -stdout
done
japan/run.sh play wanderer
```

For geometry studies, use `build.py -- --study NAME --views front,side,back,face,head_profile`.
Studies cannot overwrite production exports. Production imports verify source and
artifact hashes. Rebuilding either rider requires rebuilding its skating clips.

## Review

```sh
python3 japan/characters/cape_boy/locomotion_qa.py NAME --character wanderer
python3 japan/items/skateboard/stance_qa.py NAME --character wanderer
python3 japan/items/skateboard/qa.py NAME --character cape_boy
python3 japan/benchmark.py NAME --character wanderer --view skate --seconds 25 --hide-hud
python3 japan/characters/wanderer/preview.py SESSION
python3 japan/characters/wanderer/preview.py SESSION --encode-only
```

The Blender review checks every frame for normalized weights, joint continuity,
finite transforms, looping seams, and sole height/velocity during ground support.
Runtime checks use actual final poses and controls. `verification.json` records
completed checks and visual review. Preview captures use fixed 60 Hz simulation;
they are not evidence of real-time frame rate. The optional 720p60 phone edit is
a silent H.264/AAC MP4 and receives a complete decode and frame-count check. Native assets and movies stay in
ignored output directories; references, source and compact verification are tracked.

Completed verification for this pass: all 21 base clips and 18 skate clips per
rider pass baked contact, joint and loop checks. Both characters pass live gait
and skating checks; Wanderer also passes the actual stance-menu change and saved
goofy reload. All 1,720 authored Yellow Boy poses and accessory samples are
numerically identical to the preceding version. The revised Wanderer run peaks
at 39 cm/s of vertical pelvis motion, down from the original reach-correction pulse.

The separate 1080p skate benchmark measured 72.3 median / 71.4 average fps, with
17.29 ms at the 95th percentile. This is not a locked-60 guarantee. The 21-second
phone preview and three reference sheets are uploaded to iCloud Drive under
`Japan - Wanderer redesign`. The game is stopped; physical iPhone playback was
not tested on the device.
