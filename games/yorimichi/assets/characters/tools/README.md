# Character authoring tools

The tools that made Yorimichi's characters: pose authoring on the rig, clip builders, the sword and skate sets, the
Mixamo retarget, the fox hunter's pose language and checks, the Tripo rig and finger steps, the outfit body swap, and
reference concepts. They are the prototype's tools moved as they were (Blender scripts unless noted); the docs that
explain them are in [../../../docs](../../../docs) (ANIMATION_PRINCIPLES, SKATE, SWORD_COMBAT, MIXAMO_WORKFLOW,
FOX_HUNTER_ANIMATION, TRIPO_P2_ASSET_WORKFLOW, BODY_SWAP_GUIDE, H3_ANIMATION_REFERENCE_WORKFLOW).

## The revision history lives in the archive

Each tool reads earlier revision folders and writes the next one, in the prototype's layout
(`output/imagegen/<character>/<stage>-rNN/`). This repository keeps only each character's current revision
(`../warm-original`, `../fox-hunter`), so the history stays in the prototype repository. Point `YORIMICHI_ARCHIVE` at
a checkout of it before using a tool that reads or writes revisions:

```sh
export YORIMICHI_ARCHIVE=/path/to/the/prototype          # contains output/imagegen/...
blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_skate_clips.py -- ...
python games/yorimichi/assets/characters/tools/promote.py warm-original "$YORIMICHI_ARCHIVE/output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r18"
uv run atelier build yorimichi                            # re-exports and re-imports the promoted character
```

## What is here

| Group | Tools |
|---|---|
| Rig and pose authoring | `warm_rig.py` (FK pose helpers on the 53-bone rig), `warm_clips.py` (the library's pose functions), `outfit` correctives via `warm_outfit_correctives.py` |
| Revisions | `warm_game_revision.py` (author selected actions, protect the rest with signatures), `warm_game_clip_transfer.py` |
| Clip sets | `warm_skate_clips.py` + `warm_skate_review.py` (54 skate clips), `warm_sword_combat_build.py`, `warm_sword_combat_r02.py`, `warm_sword_combat_check.py`, `warm_sword_combat_review.py`, `warm_sword_locomotion.py` (armed copies), `warm_sword_grip.py` |
| Motion capture | `warm_mixamo_test.py`, `warm_mixamo_review.py` |
| Fox hunter | `fox_hunter_animate.py` (pose language, leg solve, contacts), `fox_hunter_clip.py` (self-intersection), `fox_hunter_clipcheck.py`, `fox_hunter_captures.py`, `fox_hunter_animref.py` (H3 references), `fox_hunter_pipeline.py` (staged concepts for Tripo), `add_fox_fingers.py`, `review_fox_rig.py` |
| Tripo | `review_tripo_model.py`, `review_tripo_rig.py`, `add_tripo_fingers.py`, `inspect_tripo_rig.py`; the API client is `atelier.ai.tripo_asset` |
| Outfits | `warm_body_swap_{references,sunburst,fit,assemble,capture,export}.py` |
| Concepts | `warm_back_concepts.py` (its Sunburst edit helper is shared), `spirit_concepts.py` (the spirit roster) |
| Captures | `capture_warm_clip.py`, `capture_warm_revision.py`, `compare_warm_sprint.py` |
| Helpers kept for their functions | `prepare_warm_original_game.py`, `refine_warm_waist_overlap.py`, `validate_warm_idle_dash.py`, `warm_outfit_arm_clearance.py`, `warm_waist_contact.py` (one-off revision scripts whose helpers the live tools import) |

The platform holds the generic pieces: `atelier.ai.tripo_asset` (ledgered Tripo client),
`atelier.review.{contact_sheet,video_reference,export_preview_gltf,review_service}`, `atelier.blender.renderdev`
(Metal setup) and `platform/studio/node` (H3 Max and Seedance through the Vercel AI Gateway).
