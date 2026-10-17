# Suzu, the bell-ringer

The old woman who rings Hidamari's hours. She has not missed an hour in fifty years, and she will tell anyone who
listens that the spirits never come while the hours are being struck. In the lore's pile of rumours about why the
spirits stay out of the towns, hers is the one that is true
([LORE.md](../../../docs/LORE.md#why-they-stay-out-of-cities)).

She is a stylised non-player villager in Cairo's graphic language, not a mover: someone who stands at the clock
hall, rings the bell, talks and walks a slow round. The model, rig and clips are entirely procedural: `build.py`
makes them in Blender, and nothing but the painted design sheet is a binary source.

## The references

[`references/sheet.jpg`](references/sheet.jpg) is a single painted model sheet: four labelled views (front, right
profile, back, three-quarter), two face close-ups, a bell-and-rope close-up, the bun from behind and a colour
palette. It was painted by **GPT Image 2.5 Sunburst** (`gpt-image-2.5-sunburst`, `quality=high`, 1536×1024) through
`atelier.ai.images` and recorded before the call by `atelier.ai.ledger`:

| File | Contents |
| --- | --- |
| `references/sheet.jpg` | the sheet, as it is used by the model |
| `references/sheet.prompt.txt` | the complete prompt |
| `references/sheet.provenance.json` | model, quality, size, endpoint, input hashes, output hash and usage |

The reference images sent with the prompt were Cairo's front T-pose and three-quarter renders (made from
`../cairo/Cairo-Game-r18.blend` by `../tools/sword_trainer_refs.py`) for the finish and the villager's sheet for
the layout. To paint another take:

```sh
uv run python games/yorimichi/assets/characters/tools/bell_ringer_concepts.py          # paints what is missing
uv run python games/yorimichi/assets/characters/tools/bell_ringer_concepts.py --dry-run # the prompts only
```

The full-size original stays outside the repository, in
`build/yorimichi/characters/bell-ringer/references/originals/sheet.png`.

## Build and review

```sh
uv run atelier build yorimichi characters.bell_ringer
```

`characters.bell_ringer` runs `build.py -- --animations --export --no-render` into `build/yorimichi/bell-ringer/`:
the disposable `Suzu.blend` (with the design sheet packed inside), the body FBX and one FBX per clip, the manifests
and `build.json` with the source and artifact hashes. For geometry studies:

```sh
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/bell-ringer/build.py -- \
  --study NAME --engine CYCLES --views front,side,back,three_quarter,face,head_back
```

A study writes to `build/yorimichi/bell-ringer/studies/NAME/` and refuses `--export`, so it cannot overwrite the
production export. `review.py` puts the study's orthographic views beside the same crops of the sheet, at one
height, for a direct comparison:

```sh
uv run python games/yorimichi/assets/characters/bell-ringer/review.py --study NAME
```

## The model

- **Proportions** measured from the sheet's front and profile figures at 2.76 mm to the pixel: 1.40 m to the top
  of the hair, a little over four heads, a round pear-shaped body, short legs and a gentle forward settle of the
  head. The sole sits at 0 and the obi spans z 0.69–0.79.
- **About 11,500 triangles**, one opaque vertex-colour material (`Suzu_Palette`), no textures, no strand or cloth
  micro-geometry. The sheet's soft painterly finish is carried by smooth shading, a three-tone palette and broad
  sculpted planes; her material keeps less emission than the villager's (0.18 instead of 0.30) so the silver hair
  and cream collar keep the sheet's shading.
- **33 bones**: the compact spine and limbs, eyes, four fingers and a thumb per hand, and three secondary bodies:
  the bun, the hand bell on its cord, and the folded cloth tucked into the obi. Not the humanoid contract: she is
  not playable and does not play the merged move set, so she keeps the villager's smaller rig.
- **16 clips at 60 Hz**: Idle, Walk, Jog, CrouchIdle, CrouchWalk, JumpStart, JumpRise, Fall, Land, Interact, Wave,
  SitDown, SitIdle, StandUp, TurnLeft, TurnRight. Walk 0.62 m/s and jog 1.15 m/s with a short, flat stride; turns
  take 0.95 s; the bun, bell and cloth carry baked secondary motion.
- **Design**: silver-white hair parted at the crown, gathered past the ears into a low round bun bound with a dark
  cord and pinned with a dark wooden comb; a padded deep-indigo haori with cream lining turned back at the cuffs,
  a broad cream collar crossed in a kimono V; a muted vermilion obi; a deeper indigo apron-front skirt over baggy
  charcoal trousers gathered at the ankle; white tabi and dark wooden geta; a twisted straw bell rope over her
  right shoulder, across the chest and back and knotted at her left hip, with a dull-gold bell-metal hand bell
  hanging from it.

### What the sheet drew, and what the model keeps

The sheet is a painting, and the model is a game mesh built from primitives. It follows the sheet's proportions,
palette, silhouette, costume construction and feature placement; the low-poly edges, the soft vertex-colour shading
and the simplified rope twist and comb are deliberate choices so the character reads at game-camera distance and
costs no texture memory. The face keeps Cairo's dark pill eyes without whites, the small nose, the soft smile and
the grey brows; the close-ups are the place to judge the face, the full-body views the silhouette.

## Files

| File | Contents |
| --- | --- |
| `build.py` | the Blender entry point: model, rig, clips, export, study renders |
| `suzu_mesh.py` | head and face, haori, collar, sleeves, obi, hip cloth, trousers, rope, bell, hands |
| `suzu_hair.py` | crown, parted fringe, side locks, nape bun, comb |
| `suzu_foot.py` | tabi socks and geta on the shared sole footprint |
| `suzu_shapes.py` | the eye pill, the twisted rope and the faceted ball |
| `suzu_rig.py` | the 33-bone compact rig and its secondary bodies |
| `suzu_motion.py` | her clips and accessory motion over the villager kit's contact solver |
| `pipeline.py` | source and artifact hashes, written to `build.json` |
| `review.py` | the sheet-against-renders comparison sheet |
| `references/` | the painted model sheet, its prompt and its ledger record |
| `character.toml` | her identity, rig, build command and Unreal folder |

The shared clip builder, contact solver, rig, head and hair primitives come from the villager's kit
(`../wanderer/kit/`); her sources are hashed into `build.json` beside her own, so a change to the kit invalidates
her build too. Her Unreal folder is `/Game/BellRinger`; bringing her into a level is a separate import step, not
part of this asset build.
