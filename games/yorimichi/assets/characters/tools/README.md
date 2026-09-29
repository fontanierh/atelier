# Character authoring tools

The tools that made Yorimichi's characters: pose authoring on the rig, clip builders, the sword and skate sets, the
Mixamo retarget, the fox hunter's pose language and checks, the Tripo rig and finger steps, the outfit body swap, and
reference concepts. They are the prototype's tools moved as they were (Blender scripts unless noted); the docs that
explain them are in [../../../docs](../../../docs) (ANIMATION_PRINCIPLES, SKATE, SWORD_COMBAT, MIXAMO_WORKFLOW,
FOX_HUNTER_ANIMATION, TRIPO_P2_ASSET_WORKFLOW, BODY_SWAP_GUIDE, H3_ANIMATION_REFERENCE_WORKFLOW).

## The revision history lives in the archive

Each tool reads earlier revision folders and writes the next one, in the prototype's layout
(`output/imagegen/<character>/<stage>-rNN/`). This repository keeps only each character's current revision
(`../cairo`, `../fox-hunter`), so the history stays in the prototype repository. Point `YORIMICHI_ARCHIVE` at
a checkout of it before using a tool that reads or writes revisions:

```sh
export YORIMICHI_ARCHIVE=/path/to/the/prototype          # contains output/imagegen/...
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_skate_clips.py -- ...
python games/yorimichi/assets/characters/tools/promote.py cairo "$YORIMICHI_ARCHIVE/output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r18"
uv run atelier build yorimichi                            # re-exports and re-imports the promoted character
```

## What is here

| Group | Tools |
|---|---|
| Rig and pose authoring | `cairo_rig.py` (FK pose helpers on the 53-bone rig), `cairo_clips.py` (the library's pose functions), `outfit` correctives via `cairo_outfit_correctives.py` |
| Revisions | `cairo_game_revision.py` (author selected actions, protect the rest with signatures), `cairo_game_clip_transfer.py` |
| Clip sets | `cairo_skate_clips.py` + `cairo_skate_review.py` (54 skate clips), `cairo_sword_combat_build.py`, `cairo_sword_combat_r02.py`, `cairo_sword_combat_check.py`, `cairo_sword_combat_review.py`, `cairo_sword_locomotion.py` (armed copies), `cairo_sword_grip.py` |
| Motion capture | `cairo_mixamo_test.py` (retarget), `cairo_mixamo_clearance.py` + `cairo_mixamo_clearance_check.py` (head clearance), `cairo_mixamo_review.py`; the route is in [MIXAMO_WORKFLOW](../../../docs/MIXAMO_WORKFLOW.md) |
| Fox hunter | `fox_hunter_animate.py` (pose language, leg solve, contacts), `fox_hunter_clip.py` (self-intersection), `fox_hunter_clipcheck.py`, `fox_hunter_captures.py`, `fox_hunter_animref.py` (H3 references), `fox_hunter_pipeline.py` (staged concepts for Tripo), `add_fox_fingers.py`, `review_fox_rig.py` |
| Tripo | `review_tripo_model.py`, `review_tripo_rig.py`, `add_tripo_fingers.py`, `inspect_tripo_rig.py`; the API client is `atelier.ai.tripo_asset` |
| Outfits | `cairo_body_swap_{references,sunburst,fit,assemble,capture,export,check}.py`; outfit specs in `../cairo/outfits/` |
| Concepts | `cairo_back_concepts.py` (its Sunburst edit helper is shared), `spirit_concepts.py` (the spirit roster) |
| Captures | `capture_cairo_clip.py`, `capture_cairo_revision.py`, `compare_cairo_sprint.py` |
| Helpers kept for their functions | `prepare_cairo_game.py`, `refine_cairo_waist_overlap.py`, `validate_cairo_idle_dash.py`, `cairo_outfit_arm_clearance.py`, `cairo_waist_contact.py` (one-off revision scripts whose helpers the live tools import) |

The platform holds the generic pieces: `atelier.ai.tripo_asset` (ledgered Tripo client),
`atelier.review.{contact_sheet,video_reference,export_preview_gltf,review_service}`, `atelier.blender.renderdev`
(Metal setup) and `platform/studio/node` (H3 Max and Seedance through the Vercel AI Gateway).
