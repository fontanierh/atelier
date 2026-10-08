"""Cairo on horseback: the hippodrome riders' clips (Link's BOTW riding clips, RiderLink in roster.toml) retargeted onto
Cairo with his BOTW move set's retarget (../cairo/botw.py), so the player races and rides as himself.

    blender -b --python games/yorimichi/assets/characters/horses/cairo_rider.py

Reads RiderLink's baked clips (build/yorimichi/horses/glb/RiderLink.glb and export.json, from export.py), Link's bone
map (build/yorimichi/botw/export.json) and Cairo's source (export_unreal.prepare). Writes build/yorimichi/horses/cairo/:
fbx/A_<Clip>.fbx on Cairo's skeleton at 30 fps, and export.json with the clips, the roles and per clip the retarget's
checks. A riding clip's root is the horse's saddle: Cairo's hips sit above it as Link's do, at the ratio of their hip
heights, and his legs, far from the ground, take the shape of Link's round the horse.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cairo_botw', HERE.parent / 'cairo' / 'botw.py')
retarget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retarget)
import yori   # noqa: E402  (on the path through cairo/export_unreal.py)

HORSES = yori.OUT / 'horses'
OUT = HORSES / 'cairo'
RIDER = 'RiderLink'


def main():
    rider = next(c for c in json.loads((HORSES / 'export.json').read_text())['characters'] if c['name'] == RIDER)
    link = next(c for c in json.loads((retarget.LINK / 'export.json').read_text())['characters'] if c['name'] == 'Link')
    module, _ = retarget.character('cairo')
    prepared = module.prepare(module.SOURCE)
    scene, arm = prepared.scene, prepared.arm
    scene.render.fps, scene.render.fps_base = retarget.FPS, 1
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bone_map = {**(rider['skate'] or link['skate']), 'root': '', 'spine_mid': '', 'pelvis': 'Waist'}
    missing = sorted(b.name for b in arm.data.bones if b.name not in bone_map)
    assert not missing, ('Cairo bones without a Link bone', missing)
    solver = retarget.Retarget(retarget.Glb(HORSES / rider['glb']), arm, bone_map)
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    clips = {}
    for clip in rider['clips']:
        checks = retarget.export_clip(scene, arm, OUT, clip['name'], clip['frames'], solver, module, retarget.FPS)
        clips[clip['name']] = {'frames': clip['frames'], 'duration': round(clip['frames'] / retarget.FPS, 4),
                               'loop': clip['loop'], 'fps': retarget.FPS, **checks}
    report = {'character': 'cairo', 'rider': RIDER, 'glb': rider['glb'], 'source': prepared.native.name,
              'source_sha256': prepared.record['native_sha256'], 'fps': retarget.FPS,
              'body': round(float(solver.body), 4), 'roles': rider['roles'], 'speeds': rider['speeds'], 'clips': clips}
    (OUT / 'export.json').write_text(json.dumps(report, indent=1) + '\n')
    print(f'CAIRO RIDER EXPORT COMPLETE: {len(clips)} clips, body {solver.body:.3f}', flush=True)


if __name__ == '__main__':
    main()
