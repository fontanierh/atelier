"""Export the assembled body swap as GLB (all 24 clips as actions) next to the blend.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_body_swap_export.py
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, sys
from pathlib import Path
import bpy
# ROOT (the archive) comes from _archive
import os
SWAP_DIR = os.environ.get('BODY_SWAP_DIR', 'body-swap-r01')
SWAP_STEM = os.environ.get('BODY_SWAP_STEM', 'WarmOriginal-BodySwap-r01')
HEADLESS = bool(os.environ.get('BODY_SWAP_HEADLESS'))
SWAP = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12' / SWAP_DIR
STEM = SWAP_STEM
bpy.ops.wm.open_mainfile(filepath=str(SWAP / f'assembled/{STEM}.blend'))
s = bpy.context.scene
for o in s.objects:
    o.select_set(o.type in ('MESH', 'ARMATURE') and not o.hide_render and not o.name.startswith('Review floor'))
bpy.ops.export_scene.gltf(filepath=str(SWAP / f'assembled/{STEM}.glb'), export_format='GLB', use_selection=True,
                          export_animations=True, export_animation_mode='ACTIONS', export_frame_range=False,
                          export_apply=True, export_skins=True, export_materials='EXPORT', export_image_format='AUTO')
print('EXPORTED', (SWAP / f'assembled/{STEM}.glb').stat().st_size)
