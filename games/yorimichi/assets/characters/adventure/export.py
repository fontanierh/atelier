"""Bake the merged move set on a neutral reference rig, plus the sword and paraglider.

The reference has no character surfaces or player definition. It supplies bind transforms and motion
samples for retargeting onto Cairo, Modori and Kaede. Outputs stay in build/yorimichi/adventure/.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bake, library, moves  # noqa: E402
from atelier import paths  # noqa: E402

OUT = paths.build_dir('yorimichi') / 'adventure'
FEET = ('Ankle_L', 'Ankle_R')


def unreal_name(clip):
    return re.sub(r'[^A-Za-z0-9_]+', '_', clip).strip('_')


def height(glb, skeleton, idle):
    """Standing height in metres: the highest joint of the idle pose's first frame, plus how far the bind-pose mesh
    rises above its highest joint (Adventure rigs bind in a tall T-pose; most of them stand hunched)."""
    gltf, _ = bake.read_glb(glb)
    top = max(gltf['accessors'][primitive['attributes']['POSITION']]['max'][1]
              for mesh in gltf['meshes'] for primitive in mesh['primitives'])
    bind = bake.sample_clip(skeleton, {'bones': []}, np.zeros(1))[:, 0, 1, 3].max()
    if idle is None:
        return round(top, 3)
    pose = bake.sample_clip(skeleton, idle, np.zeros(1))[:, 0, 1, 3].max()
    return round(pose + max(0.0, top - bind), 3)


def ground_speed(skeleton, clip, fps):
    """Ground speed (m/s) of a locomotion loop: the root's forward travel when the clip moves the character, otherwise
    how fast a planted ankle slides backwards under the in-place body."""
    frames = np.arange(int(clip['frames']) + 1, dtype=np.float64)
    worlds = bake.sample_clip(skeleton, clip, frames)
    travel = bake.ground_travel(skeleton, worlds)
    if np.linalg.norm(travel[-1]) > 0.05:
        return round(float(np.linalg.norm(travel[-1])) * fps / max(1, int(clip['frames'])), 3)
    names = [bone['name'] for bone in skeleton]
    if not all(foot in names for foot in FEET):
        return None
    speeds = []
    for foot in FEET:
        track = worlds[names.index(foot), :, :3, 3]
        y, z = track[:, 1], track[:, 2]
        planted = y <= y.min() + 0.15 * (y.max() - y.min())
        both = planted[1:] & planted[:-1]
        if both.sum() >= 2:
            speeds.append(float(np.median(-(z[1:] - z[:-1])[both])) * fps)
    return round(float(np.mean(speeds)), 3) if speeds else None


def main():
    if not library.available():
        sys.exit(f'no merged motion source in {library.root()}')
    manifest = library.roster()
    character = manifest['character'][0]
    scale = float(manifest.get('scale', 1.))
    item = library.entry(character['id'])
    curves = json.loads(item['curves'].read_text())
    spec = moves.load(HERE / character['moves'])
    clips = list(dict.fromkeys([*character['clips'], *moves.clips(spec)]))
    strip, drive = moves.modes(spec)
    target = OUT / 'glb' / 'Reference.glb'
    summary = bake.bake(item['glb'], item['curves'], target, clips=clips, rename=unreal_name,
                        in_place=True, strip=strip, drive=drive,
                        progress=lambda name, count, frames: print(f'Motion {count}/{len(clips)}: {name}, {frames} frames baked', flush=True))
    by_source = {clip['name']: clip for clip in curves['animations']}
    roles = {role: unreal_name(clip) for role, clip in character['roles'].items()}
    speeds = {role: ground_speed(curves['skeleton'], by_source[clip], summary['fps']) * scale
              for role, clip in character['roles'].items() if role in ('walk', 'run')}
    idle = by_source[character['roles']['idle']]
    record = {'name': 'Reference', 'id': 'reference', 'label': 'Motion reference', 'kind': 'motion',
              'glb': str(target.relative_to(OUT)), 'skeleton': 'Reference', 'bones': summary['bones'],
              'fps': summary['fps'], 'scale': scale, 'height': height(target, curves['skeleton'], idle) * scale,
              'clips': summary['clips'], 'roles': roles, 'speeds': speeds, 'skate': character['skate']}
    record['moves'] = moves.record(spec, curves, summary, scale, OUT / 'glb', unreal_name,
                                  lambda clip: ground_speed(curves['skeleton'], clip, summary['fps']))
    (OUT / 'export.json').write_text(json.dumps({'fps': bake.FPS, 'characters': [record]}, indent=1) + '\n')
    print(f"ADVENTURE EXPORT COMPLETE: {len(record['clips'])} motion clips, sword and paraglider -> {OUT}", flush=True)


if __name__ == '__main__':
    main()
