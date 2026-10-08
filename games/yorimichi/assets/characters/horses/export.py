"""Bake the hippodrome's horses and riders (roster.toml) into rigged, animated GLBs for the Unreal import.

The BOTW roster's exporter (../botw/export.py), for a roster of its own: it writes build/yorimichi/horses/glb/<Name>.glb
and build/yorimichi/horses/export.json in the same format, which import_horses.py reads. The horse is assembled first:
its mane and tail (`parts`) are merged onto it like Link's clothing (outfit.py: the part's rig is the horse's own bones
plus the mane and tail chains, which stay at rest), the mane takes its coat's colour, and a `coat` swaps the body and
foot albedos for one of the standard horse's coats. A variant (`shares`) is its owner's skeleton with its own mesh and
textures. Each record also carries the ground speed of every gait role, which the game plays the clips at.
`--only Horse,RiderLink` limits the run; a variant brings its owner with it.
"""
import argparse, io, json, sys, time, tomllib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'botw'))
import bake, library, outfit   # noqa: E402
from export import ground_speed, height, selected, unreal_name   # noqa: E402  (../botw/export.py)
from atelier import paths   # noqa: E402

ROSTER = HERE / 'roster.toml'
OUT = paths.build_dir('yorimichi') / 'horses'
COATS = 'library/horses/Horse/coats'
GAITS = ('walk', 'trot', 'canter', 'run', 'sprint')


def roster():
    manifest = tomllib.loads(ROSTER.read_text())
    return [{'scale': manifest.get('scale', 1.), **character} for character in manifest['character']]


def coats():
    return {coat['id']: coat for coat in json.loads((library.root() / COATS / 'coats.json').read_text())['coats']}


def asset_coat(entry_id):
    """The coat an entry's horse was built with (its asset.json), or None."""
    found = sorted(library.root().glob(f'library/*/{entry_id}/asset.json'))
    return json.loads(found[0].read_text()).get('coat') if found else None


def sources():
    """Every library file the roster reads (the build hashes these)."""
    if not library.available():
        return []
    files = []
    for character in roster():
        item = library.entry(character['id'])
        files += [item['glb'], item['curves']] + [library.garment(g)['glb'] for g in character.get('outfit', [])]
        files += [library.entry(part)['glb'] for part in character.get('parts', [])]
        if character.get('coat'):
            coat = coats()[character['coat']]
            files += [library.root() / COATS / name for name in ('coats.json', coat['body'], coat['foot'])]
        elif character.get('parts'):
            files.append(sorted(library.root().glob(f"library/*/{character['id']}/asset.json"))[0])
    return sorted(set(files))


def _png(image=None, colour=None):
    from PIL import Image
    if image is None:   # a flat swatch: the glTF factor is linear, the texture sRGB
        srgb = [round(255 * (c * 12.92 if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055)) for c in colour[:3]]
        image = Image.new('RGB', (4, 4), tuple(min(255, max(0, v)) for v in srgb))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def _set_texture(gltf, binary, material, png):
    """Point `material`'s base colour at a new embedded PNG (the old image stays unreferenced)."""
    binary.extend(b'\x00' * (-len(binary) % 4))
    gltf['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(png)})
    binary.extend(png)
    gltf.setdefault('images', []).append({'bufferView': len(gltf['bufferViews']) - 1, 'mimeType': 'image/png',
                                          'name': f"{material['name']}_Alb"})
    gltf.setdefault('textures', []).append({'source': len(gltf['images']) - 1})
    pbr = material.setdefault('pbrMetallicRoughness', {})
    pbr['baseColorTexture'] = {'index': len(gltf['textures']) - 1}
    pbr.pop('baseColorFactor', None)


def _accessor(gltf, binary, index):
    accessor = gltf['accessors'][index]
    view = gltf['bufferViews'][accessor['bufferView']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[accessor['type']]
    dtype = {5126: '<f4', 5123: '<u2', 5121: 'u1', 5125: '<u4'}[accessor['componentType']]
    return np.frombuffer(bytes(binary), dtype, accessor['count'] * width,
                         view.get('byteOffset', 0) + accessor.get('byteOffset', 0)).reshape(accessor['count'], width)


def _rigid_to_model(gltf, binary):
    """Rebind the meshes on a rigid skin (identity bind matrices: BOTW's shoes and eyeballs, modelled in their bone's
    space) to the skinned body's skin, in model space. Unreal imports every mesh against one reference pose, and left
    as they are the shoes and eyes float at the horse's feet."""
    def bind(skin):
        return _accessor(gltf, binary, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    rigid = {i for i, skin in enumerate(gltf['skins']) if np.allclose(bind(skin), np.eye(4), atol=1e-5)}
    bound = [i for i in range(len(gltf['skins'])) if i not in rigid]
    if not rigid or not bound:
        return
    main = bound[0]
    slot = {node: k for k, node in enumerate(gltf['skins'][main]['joints'])}
    worlds = np.linalg.inv(bind(gltf['skins'][main]))
    writer = bake.Writer(gltf, binary)
    for node in gltf['nodes']:
        if node.get('skin') not in rigid:
            continue
        joints = gltf['skins'][node['skin']]['joints']
        for primitive in gltf['meshes'][node['mesh']]['primitives']:
            attributes = primitive['attributes']
            index = np.array([slot[joints[j]] for j in range(len(joints))])[_accessor(gltf, binary, attributes['JOINTS_0'])]
            weights = _accessor(gltf, binary, attributes['WEIGHTS_0'])
            matrix = np.einsum('vk,vkij->vij', weights / weights.sum(1, keepdims=True), worlds[index])
            position = _accessor(gltf, binary, attributes['POSITION'])
            attributes['POSITION'] = writer.floats(np.einsum('vij,vj->vi', matrix[:, :3, :3], position) + matrix[:, :3, 3],
                                                   'VEC3', bounds=True)
            if 'NORMAL' in attributes:
                normal = np.einsum('vij,vj->vi', matrix[:, :3, :3], _accessor(gltf, binary, attributes['NORMAL']))
                attributes['NORMAL'] = writer.floats(normal / np.linalg.norm(normal, axis=1, keepdims=True), 'VEC3')
            joint_bytes = np.ascontiguousarray(index, dtype='<u2')
            binary.extend(b'\x00' * (-len(binary) % 4))
            gltf['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': joint_bytes.nbytes})
            binary.extend(joint_bytes.tobytes())
            gltf['accessors'].append({'bufferView': len(gltf['bufferViews']) - 1, 'componentType': 5123,
                                      'count': len(index), 'type': 'VEC4'})
            attributes['JOINTS_0'] = len(gltf['accessors']) - 1
        node['skin'] = main


def assemble(character, item, out):
    """The character's rig: dressed (`outfit`), its parts merged (`parts`), its coat applied, and its rigid meshes (eyes,
    shoes, earrings) moved onto the body's skin. Returns its GLB."""
    from PIL import Image
    rig = item['glb']
    target = out / 'rig' / f"{character['name']}.glb"
    if character.get('outfit'):
        outfit.dress(rig, [library.garment(g) for g in character['outfit']], target)
        rig = target
    if character.get('parts'):
        parts = [{'id': part, 'glb': library.entry(part)['glb'], 'slot': 'part', 'default': False} for part in character['parts']]
        outfit.dress(rig, parts, target)
        rig = target
    gltf, binary = bake.read_glb(rig)
    if character.get('parts'):
        coat = coats()[character['coat']] if character.get('coat') else asset_coat(character['id'])
        for material in gltf['materials']:
            if character.get('coat') and material['name'] in ('Mt_Body', 'Mt_Foot'):
                name = coat['body'] if material['name'] == 'Mt_Body' else coat['foot']
                _set_texture(gltf, binary, material, _png(Image.open(library.root() / COATS / name).convert('RGBA')))
            elif material['name'] in ('Mt_Hair', 'Mt_Tail') and coat:
                _set_texture(gltf, binary, material, _png(colour=coat['mane_base_colour']))
    _rigid_to_model(gltf, binary)
    bake.write_glb(target, gltf, binary)
    return target


def export_one(character, owner, out):
    """Bake one roster character; `owner` is the record of the character whose skeleton and clips a variant uses."""
    started = time.time()
    item = library.entry(character['id'])
    curves = json.loads(item['curves'].read_text())
    target = out / 'glb' / f"{character['name']}.glb"
    rig = assemble(character, item, out)
    if owner is not None:
        summary = bake.bake(rig, item['curves'], target, clips=[])
        if summary['bones'] != owner['bones']:
            raise ValueError(f"{character['name']} does not share {owner['name']}'s skeleton")
        scale = owner['scale']
        record = {'clips': [], 'roles': owner['roles'], 'speeds': owner['speeds'], 'skate': {}, 'board': 1.}
    else:
        scale = float(character.get('scale', 1.))
        clips = selected([clip['name'] for clip in curves['animations']], character.get('clips', 'all'))
        # BOTW's curve clips turn the root (up to 70 degrees a cycle) for the game to turn into the horse's heading. The
        # race steers the horse along the course itself, so they keep only their lean: left in, the horse swung off
        # its line and snapped back on every loop.
        turns = [clip for clip in clips if '_Curve_' in clip]
        summary = bake.bake(rig, item['curves'], target, clips=clips, rename=unreal_name, in_place=True, drive=turns)
        by_source = {clip['name']: clip for clip in curves['animations']}
        speeds = {}
        for role in GAITS:
            if role in character.get('roles', {}):
                speed = ground_speed(curves['skeleton'], by_source[character['roles'][role]], summary['fps'])
                if speed and speed > 0.05:
                    speeds[role] = round(speed * scale, 3)
        roles = {role: unreal_name(clip) for role, clip in character.get('roles', {}).items()}
        record = {'clips': summary['clips'], 'roles': roles, 'speeds': speeds, 'skate': {}, 'board': 1.}
    idle_role = (owner or character).get('roles', {}).get('idle')
    idle = next((clip for clip in curves['animations'] if unreal_name(clip['name']) == idle_role), None)
    return {
        'name': character['name'], 'id': character['id'], 'label': item['name'], 'kind': item['kind'],
        # Relative to the export's folder: a verified reuse clones export.json into another checkout as it is.
        'glb': str(target.relative_to(out)), 'skeleton': owner['name'] if owner else character['name'], 'bones': summary['bones'],
        'fps': summary['fps'], 'scale': scale, 'height': height(target, curves['skeleton'], idle) * scale,
        'coat': character.get('coat', ''), **record, 'seconds': round(time.time() - started, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--only', default='', help='comma-separated roster names')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if not library.available():
        sys.exit(f'no BOTW library in {library.root()} (../botw/README.md says how to fetch it)')
    characters = roster()
    by_name = {character['name']: character for character in characters}
    only = {name for name in args.only.split(',') if name}
    unknown = only - set(by_name)
    if unknown:
        sys.exit(f'not in roster.toml: {sorted(unknown)}')
    if only:
        only |= {by_name[name]['shares'] for name in only if 'shares' in by_name[name]}
        characters = [character for character in characters if character['name'] in only]

    owners = [character for character in characters if 'shares' not in character]
    variants = [character for character in characters if 'shares' in character]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        done = {r['name']: r for r in pool.map(export_one, owners, [None] * len(owners), [OUT] * len(owners))}
        for r in pool.map(export_one, variants, [done[v['shares']] for v in variants], [OUT] * len(variants)):
            done[r['name']] = r

    records = [done[character['name']] for character in characters]
    for r in records:
        print(f"{r['name']:12} {r['label']:22} {len(r['clips']):4} clips  {r['height']:5.2f} m  {r['speeds']}  "
              f"{r['seconds']} s")
    (OUT / 'export.json').write_text(json.dumps({'fps': bake.FPS, 'characters': records}, indent=1))
    print(f'HORSES EXPORT COMPLETE: {len(records)} characters, '
          f"{sum(len(r['clips']) for r in records)} clips -> {OUT / 'export.json'}")


if __name__ == '__main__':
    main()
