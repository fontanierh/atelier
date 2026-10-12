# Nox: a character built through generation, inspection and repair

Nox is the first Yorimichi character made from separate head and body generations, inspired by
[Charakuru's workflow](CHARAKURU_WORKFLOW.md). His approved assembly is
[`assets/characters/nox/Nox.glb`](../assets/characters/nox/Nox.glb): one rig, a head with its own
4K atlas and a body with another. The face, ears, earring, hairstyle, chain and original cuff are retained.
The watch trial was abandoned because its band could not fit the cuff cleanly; the current character has no watch.

This is our practical recipe and case study. The Charakuru document records the upstream kit unchanged.
We used its separate-part idea, then kept the supplied Tripo body rig, projected texture repairs onto its
existing UVs and built our own review tool. We did not perform the kit's VRM export, base-body weight transfer
or every segmentation and per-group Smart UV step. The game target is Unreal, not VRM.

## Build and play from a clone

No paid generation, account login, model download or personal asset cache is needed to build Nox.
His GLB, embedded atlases, current reference images, prompts and source checksums are committed.
Follow the [main build instructions](../../../README.md#quick-start) to install Unreal and Blender first.

```sh
uv sync
uv run python games/yorimichi/tools/verify_asset_library.py
uv run atelier build yorimichi
uv run atelier play yorimichi -- -rider=Nox
```

For a checkout whose world is already built:

```sh
uv run atelier build yorimichi unreal.nox_adventure unreal.nox_bike data.network
```

`characters.nox` exports the approved mesh. `characters.nox_adventure` retargets every merged movement,
action and donor gesture. `characters.nox_bike` authors every bike action on his skeleton.
The three `unreal.nox*` steps import their results. The character menu and `-rider=Nox` both select him.
The menu refuses him until his merged definition and move record are built.

Skating retargets the shared library onto the character's humanoid bones in the live animation graph.
It includes mounts, pushes, tricks, transitions, bails and recoveries; creating a second copy of those
shared simulation clips per character would not be the runtime the game actually uses.
Ordinary interaction, sitting, waving, double jumping, sword actions, crouching, swimming, climbing and
gliding come from the merged set and its nine donor clips. Bike actions use the procedural bike authoring recipe.

## 1. Choose an identity and a readable design

Start with concepts at the game's normal screen size. Nox grew out of a trap-inspired young adult idea:
a quiet, serious expression, black locs, a short oversized black bomber, a violet shirt motif and loose
washed charcoal jeans. His face can carry more detail than Cairo or Modori while the silhouette and painted
materials still fit their world. The design is an original character, not a scan or asserted likeness of a musician.

The first outfit was too wholesome. We selected the second fit, reduced photographic detail and kept the
large readable forms. Approve a front design before drawing orthographic views; otherwise eight images can
be internally consistent versions of an unwanted character.

Use **GPT Image 2.5 Sunburst**, `gpt-image-2.5-sunburst`, `quality=high`, through the repository client and
`atelier.ai.ledger`. Each generated image records its model, exact prompt and input hashes alongside it.
An uncertain paid request is inspected before retrying.

## 2. Make eight references, then repair individual views

The committed [reference folder](../assets/characters/nox/references) contains four head views and four body views.
Each part's front is the authority for the three edits that follow. They are 1024 × 1024 PNGs with real transparency,
not contact sheets, mirrored profiles or screenshots of a checkerboard.

- **Head:** neutral face, ears and all hair, including the low ends. No neck, shoulders, hood or collar.
- **Body:** headless neck-down T-pose, arms level, straight elbows and wrists, palms down, straight legs and a bare neck plug.
- **Directions:** `left` shows the anatomical left side, nose/chest/toes pointing left on screen;
  `right` shows the anatomical right side pointing right. Preserve one-sided details such as the earring and knee tear.
- **Registration:** match crown, eyes, chin and lowest hair tip within the head set; match neck top, shoulders,
  hands, hems and soles within the body set. Head and body image scale need not be equal.

Our corrections were specific: turn the rear ears correctly and hide them under the hair; confine the violet motif
to the shirt, with plain bomber panels; remove the generated watch and necklaces from all body views.
Those small repeated accessories produced artifacts in the body reconstruction. The right-hand ring stayed.
We drew the chain separately as a flat transparent decal. Separate watch references were also tried, but the
watch and its fitting experiments are archived rather than shipped.

## 3. Generate and choose the head and body separately

In Tripo Studio, use four-view **multiview**, not batch-image input. Charakuru recommends Smart Mesh **P2.0,
25,000 quads, four candidates per part**. Check those settings explicitly: Studio remembers prior values.
A requested quad budget and the final triangulated mesh count are different measurements.

Download each chosen model with its textures before further operations. We received an initial head, then a
better head v2, and a separately rigged and UV'd body. The source receipts record their archive hashes; previous
models stay in the ignored archive. Only the final assembled GLB is the game's model source.

Nox's accepted authoring meshes contain 52,963 body triangles and 23,305 head/hair triangles, 76,268 in total.
The body had 26,939 vertices and the head 12,003 before interchange seam splits. GLB/FBX import can split vertices
at UV or normal seams, so a runtime vertex count need not equal that authoring count. Each part has a 4K atlas.
Inspect all sides and the underside before accepting: frontal beauty alone missed our rear scalp and chin errors.

## 4. Paint the hidden face without rebuilding the hair

The fringe looked good but hid part of the face during texture generation. We generated an **unobstructed face
painting**, retaining identity, expression, projection and registration. That is a painting reference for the
existing mesh, not another bald-head Tripo generation. The head and all its hair remain one reconstruction.

We used the Pixel Match projection code from
[Bingeljell/image-to-3dlab](https://github.com/Bingeljell/image-to-3dlab), pinned to
`7793fd3622bab7d3fd4526ba02433244d5bf02e2`. The inspected projection module and its Apache-2.0 licence are
[committed here](../tools/pixel_match). We adapted it to a calibrated orthographic face-only projection:

1. Export the actual head positions, triangles, normals, UV corners and labelled loose components.
2. Match the face painting to an orthographic render using eye, nose, mouth and chin landmarks.
3. Rasterize UV triangles to find the 3D point behind each texel, then project that point into the painting.
4. Blend the sampled original pixels with confidence from face region, facing angle and visible depth.
   Label the face separately from the foreground fringe so the face surface can receive the unobstructed painting.
5. Protect hair, rear scalp, ears, earring and other UV islands. If protected and painted UVs overlap, protection wins.
6. Grow paint only into empty gutters, with a four-texel exclusion around protected islands.
7. Save the confidence, protected and changed-texel masks. Assert that no protected texel changed, then render again.

Pixel Match transfers pixels according to the mesh and camera; it does not repair malformed ears or invent the
missing surface. This process also avoids regenerating the UV layout, body weights or mesh every time a face needs work.
The unobstructed painting, its exact prompt and provenance are in the current reference folder.

## 5. Repair ears, hair paint and the underside separately

The ears still needed a Sunburst cleanup guided by renders of the actual ear, preserving the earring. Those
clean paintings were projected back onto their ear regions, then inspected in the full head viewer.
Later feedback found a skin-coloured patch on a loc and skin visible through the hair at the back.
We repainted the labelled hair surface and rear scalp in matching dark tones.

The first scalp mask also blackened the underside of the chin. We restored the chin and jaw to skin colour and
restricted dark paint to the scalp behind the hair. Inspect **under** as well as front, sides and back.
Paint by semantic surface and UV coverage, not a broad height or texture rectangle alone.

The current GLB contains the accepted face, repaired ears and earring, dark hair and rear scalp, and skin-coloured
chin. Its source checksum is recorded in `source-manifest.json`; the library verifier checks it from a clone.

## 6. Assemble onto the supplied body rig

Keep the rigged body's UVs and weights. Fit the head uniformly to the neck plug and check both profile and front;
image framing is not a physical scale. Our source fit used a head scale of approximately `0.2545664` and a
`0.02`-unit neck overlap, before the whole character was scaled to 1.78 m for the game.

The face, skull and earring are rigidly attached to the body's head bone. The neck remains weighted by the body's
original rig. There is one armature for both meshes, not two separately animated rigs. The head can be a separate
material section without being a separate gameplay character.

The source retains the original 65 Mixamo bones and its 180 additional hair bones. The Unreal exporter adds a floor
root, renames the humanoid contract bones, preserves all weighted auxiliaries and explicitly declares their neutral
parent-following pose to the shared retargeter. It exports a fresh transformed copy; it never overwrites the source.
Check head tilts and turns, neck overlap, feet on the floor and facing before importing animation.

## 7. Project the chain onto the garment atlas

A flat RGBA chain painting avoids asking Tripo to build tiny links. Use the body camera and mesh, not an arbitrary
UV paste: rasterize visible cloth texels, project into the decal, alpha blend and protect unrelated garment surfaces.
That keeps the pendant and links at the right place on the front of the hoodie.

Our first projection left dirty chain ends where they met the collar. Fade and occlude those ends under the collar,
accounting for the cloth's slope and rejecting grazing surfaces. The accepted paint used a sloped collar boundary
`z = 0.825 + 0.28 × abs(x)` in source units, `0.0015` feathering and a normal-facing fade from `0.18` to `0.45`.
Those values are Nox-specific calibration, not a general rule for another model.

The current body atlas contains the accepted chain. There is no chain mesh or watch object in the playable asset.
A decal follows the existing skinning but cannot dangle independently; choose actual accessory geometry if independent
motion or silhouette is required.

## 8. Collect precise clipping feedback in a bespoke tool

The [character review tool](../tools/character_review.py) grew out of screenshots that showed two locs intersecting
and chain ends that were hard to describe. It is now reusable with any GLB and has its Three.js dependencies committed.

```sh
uv run python games/yorimichi/tools/character_review.py \
  --model games/yorimichi/assets/characters/nox/Nox.glb \
  --hair games/yorimichi/assets/characters/nox/hair-preview.json
```

Open `http://127.0.0.1:8899/`. Drag or swipe to rotate, pinch/scroll to zoom, inspect front/back/underside/collar,
and choose texture, lighting or wireframe. **Mark clipping** pauses the current motion. Tap the faulty surface,
undo misplaced marks and **Save marks**. The JSON captures the exact model hash, mesh, triangle, model-space point,
camera, target and every bone rotation. The agent can reproduce the pose rather than guess from a crop.

Saves go to `build/yorimichi/character-review/feedback/`, never into source folders. Automated checks have their own
latest file and cannot overwrite the operator's latest marks. Timestamped saves, captures, failed fits and previous
models remain in the ignored workspace/archive. Commit the approved correction, not the review session's whole history.
The server binds loopback and serves only the chosen model and viewer files; private remote viewing is configured
outside the public repository.

For our marked loc pair, a shape-preserving root rotation of 16° on one strand cleared the pair without new neighbor
intersections. The earlier attempt bent the tips locally and looked messy. Always compare neighbouring locks and the
hood as well as the marked pair, preserve the silhouette and validate the whole repaired strand.

## 9. Rig and inspect all the locs

The first motion attempt moved only tips; another moved the avatar but produced no visible hair deformation.
The accepted rig covers **all 66 locks**: 48 longer chains with three joints and 18 shorter chains with two,
180 hair bones total. Roots blend to the head and proximal joints, with normalized weights along each strand.
The body's original UVs and weights stay intact. Dense geometry alone does not make secondary motion work.

The optional browser demo uses restrained, damped quaternion springs at proximal and middle joints, root-acceleration
lag and a measured garment envelope. It checks skinned surface probes and body triangles and reduces lag toward the
clear neutral pose as a strand approaches the hood. A lock close to the hood has less available movement than one
with free space. It is a **neutral-pose browser prototype**, not proof of animated garment collision in Unreal.

Measure deformation in head-relative coordinates, at upper, middle and tip surface points. Bone angles or a moving
camera are insufficient evidence. We compared renders with the same avatar transform and camera and checked the
marked pair and whole hair against the body at sampled poses. Export/reimport also checked that the weights and
180 hair bones survived GLB and FBX.

## 10. Validate the real game and retain one current source

Generate all merged and donor clips, author all bike actions, import the character, compile and select Nox in the
game. Check footsteps, crouch, dash, roll, jump/double jump, sword carrying and attacks, paraglider, swimming,
climbing, gestures, sitting, bike contacts and skating mounts/tricks/bails/recoveries. Use the actual runtime graph
for skating. A static T-pose, a successful FBX import or a browser sway demo alone does not prove playability.

Use matched fixtures to diagnose a failure before changing shared movement code. Nox's direct swim-to-shore route
caught the cabin's moored rowboat; an open-water waypoint kept the same shore-exit assertion and total deadline.
For the bike comparison, align the **bike's** world origin after mounting, since different bodies finish the mount
a few centimetres apart. Preserve the original failed receipts, input sequence and contact thresholds.

Validate collision against the animated skin as well as the bones. Nox's rounded boots needed denser fitted hulls:
`GetSkateCollisionHullDirections()` requests 1024 for Nox, with the existing default of 256 for other riders.
The cache and active reuse include this resolution. With `skate.RideSkinCheck 1`, the native skate state reports
`skin`, `skin_bone`, `skin_vertex`, `skin_point` and `skin_weights`; save the worst event and its bone pose.
The four street/grass ride-and-recovery checks kept their 2 cm limit; Nox's worst measured contact was 1.9 cm.

Report results by their actual scope. Nox passed all 39 merged-move checks and all four skating ride/bail sites.
The aligned bike circuit passed 25 of 27 checks; Cairo reproduced the remaining sprint-speed and ramp-wheel
failures. Those remain shared physics issues, not a passing bike suite. Hair springs are still a browser prototype.

Run the source-library verifier, repository lint and the full Python suite. Record native validation and screenshots
in the review workspace, then request another agent's PR review. Generated Unreal Content, exported FBXs and captures
stay ignored. The committed GLB with embedded textures is sufficient to regenerate the game imports; paid generation
is an optional authoring step, never a build dependency.
