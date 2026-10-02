"""Bake the roster's BOTW characters (roster.toml) into rigged, animated GLBs for the Unreal import.

Reads the local library (library.py) and writes build/yorimichi/botw/glb/<Name>.glb and build/yorimichi/botw/export.json:
for each character its file, the character whose skeleton it uses, its clips (Unreal-safe names, frames, loop flag),
its roles, its game scale, its height and walk and run speeds at that scale, its skate bone map and board size. A
character with an `outfit` (Link) is dressed first (outfit.py) and its clips are baked on the dressed body. Clips are
baked in place (the game moves the character); each keeps the ground travel it had as `travel`, which gives the
speeds, or the planted ankles do when a clip never moved.
`--only Bokoblin,Moblin` limits the run; a variant brings its owner with it.
"""
import argparse, json, re, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bake, library, outfit   # noqa: E402
from atelier import paths   # noqa: E402

OUT = paths.build_dir('yorimichi') / 'botw'
FEET = ('Ankle_L', 'Ankle_R')


def unreal_name(clip):
    return re.sub(r'[^A-Za-z0-9_]+', '_', clip).strip('_')


def selected(names, wanted):
    if wanted == 'all':
        return list(names)
    out = []
    for item in wanted:
        if item.startswith('re:'):
            out += [name for name in names if re.search(item[3:], name) and name not in out]
        elif item not in out:
            out.append(item)
    return out


def height(glb, skeleton, idle):
    """Standing height in metres: the highest joint of the idle pose's first frame, plus how far the bind-pose mesh
    rises above its highest joint (BOTW rigs bind in a tall T-pose; most of them stand hunched)."""
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


def export_one(character, owner):
    """Bake one roster character; `owner` is the character whose skeleton and clips a variant uses."""
    started = time.time()
    item = library.entry(character['id'])
    curves = json.loads(item['curves'].read_text())
    target = OUT / 'glb' / f"{character['name']}.glb"
    if owner is not None:
        bones = [bone['name'] for bone in curves['skeleton']]
        if bones != owner['bones']:
            raise ValueError(f"{character['name']} does not share {owner['name']}'s skeleton")
        summary = bake.bake(item['glb'], item['curves'], target, clips=[])
        scale = owner['scale']
        record = {'clips': [], 'roles': owner['roles'], 'speeds': owner['speeds'], 'skate': owner['skate'],
                  'board': owner['board']}
    else:
        scale = float(character.get('scale', 1.))
        clips = selected([clip['name'] for clip in curves['animations']], character.get('clips', 'all'))
        rig = item['glb']
        if character.get('outfit'):
            rig = OUT / 'rig' / f"{character['name']}.glb"
            outfit.dress(item['glb'], [library.garment(g) for g in character['outfit']], rig)
        summary = bake.bake(rig, item['curves'], target, clips=clips, rename=unreal_name, in_place=True)
        names = [clip['name'] for clip in summary['clips']]
        if len(set(names)) != len(names):
            raise ValueError(f"{character['name']}: clip names collide once made Unreal-safe")
        roles = {role: unreal_name(clip) for role, clip in character.get('roles', {}).items()}
        by_source = {clip['name']: clip for clip in curves['animations']}
        speeds = {}
        for role in ('walk', 'run'):
            if role in character.get('roles', {}):
                speed = ground_speed(curves['skeleton'], by_source[character['roles'][role]], summary['fps'])
                if speed and speed > 0.05:
                    speeds[role] = speed * scale
        skate = character.get('skate', {})
        missing = sorted(bone for bone in skate.values() if bone and bone not in summary['bones'])
        if missing:
            raise ValueError(f"{character['name']}: skate bones not in the skeleton: {missing}")
        record = {'clips': summary['clips'], 'roles': roles, 'speeds': speeds, 'skate': skate,
                  'board': float(character.get('board', 1.))}
    idle_role = (owner or character).get('roles', {}).get('idle')
    idle = next((clip for clip in curves['animations'] if clip['name'] == idle_role), None)
    return {
        'name': character['name'], 'id': character['id'], 'label': item['name'], 'kind': item['kind'],
        'glb': str(target), 'skeleton': owner['name'] if owner else character['name'], 'bones': summary['bones'],
        'fps': summary['fps'], 'scale': scale, 'height': height(target, curves['skeleton'], idle) * scale, **record,
        'seconds': round(time.time() - started, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--only', default='', help='comma-separated roster names')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not library.available():
        sys.exit(f'no BOTW library in {library.root()} (README.md says how to fetch it)')
    manifest = library.roster()
    roster = [{'scale': manifest.get('scale', 1.), **character} for character in manifest['character']]
    by_name = {character['name']: character for character in roster}
    only = {name for name in args.only.split(',') if name}
    unknown = only - set(by_name)
    if unknown:
        sys.exit(f'not in roster.toml: {sorted(unknown)}')
    if only:
        only |= {by_name[name]['shares'] for name in only if 'shares' in by_name[name]}
        roster = [character for character in roster if character['name'] in only]

    owners = [character for character in roster if 'shares' not in character]
    variants = [character for character in roster if 'shares' in character]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        done = {record['name']: record for record in pool.map(export_one, owners, [None] * len(owners))}
        for record in pool.map(export_one, variants, [done[v['shares']] for v in variants]):
            done[record['name']] = record

    characters = [done[character['name']] for character in roster]
    for record in characters:
        print(f"{record['name']:15} {record['label']:28} {len(record['clips']):4} clips  {record['height']:5.2f} m  "
              f"{record['speeds']}  {record['seconds']} s")
    (OUT / 'export.json').write_text(json.dumps({'fps': bake.FPS, 'characters': characters}, indent=1))
    print(f'BOTW EXPORT COMPLETE: {len(characters)} characters, '
          f"{sum(len(c['clips']) for c in characters)} clips -> {OUT / 'export.json'}")


if __name__ == '__main__':
    main()
