"""Measure self-intersection of the fox hunter's clips on the deformed mesh (see fox_hunter_clip.py).

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_clipcheck.py -- --rev animation-r03 [--only Run,Kick] [--step 2]
Writes <rev>/clipcheck.json and prints one line per clip: per pair, worst pierced-edge count @ frame / frames
with any piercing / deepest inside vertex; then how far each hand stays on its own side of the chest (negative =
crossed the midline).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, json, sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fox_hunter_clip import Checker, summarize, line

ap = argparse.ArgumentParser()
ap.add_argument('--rev', default='animation-r03')
ap.add_argument('--only', default='')
ap.add_argument('--step', type=int, default=1)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
# ROOT (the archive) comes from _archive
OUT = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13' / a.rev
bpy.ops.wm.open_mainfile(filepath=str(OUT / f'FoxHunter-Anim-{a.rev.split("-")[-1]}.blend'))
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = next(o for o in sc.objects if o.type == 'MESH' and o.vertex_groups)
m = json.loads((OUT / 'manifest.json').read_text())
only = [s for s in a.only.split(',') if s]
ck = Checker(body, arm)
dg = bpy.context.evaluated_depsgraph_get()
for tr in arm.animation_data.nla_tracks: tr.mute = True
report = {}
for name, info in m['clips'].items():
    if only and name not in only: continue
    arm.animation_data.action = bpy.data.actions[info['action']]
    frames = []
    for f in range(0, info['frames'] + 1, a.step):
        sc.frame_set(f); bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get(); frames.append((f, ck.frame(dg)))
    arm.animation_data.action = None
    report[name] = summarize(frames); print(line(name, report[name]))
(OUT / 'clipcheck.json').write_text(json.dumps(dict(step=a.step, clips=report), indent=2) + '\n')
print('CLIPCHECK OK')
