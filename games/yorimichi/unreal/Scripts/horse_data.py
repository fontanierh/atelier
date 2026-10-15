"""The horses' import data without Unreal: upright GLB copies for Interchange, and the roster contract.

import_horses.py (in the editor) uses these; the build recipe and the tests use them too. Only the standard library and
atelier.gltf are imported (import yori first, which puts platform/studio on the path): Unreal's Python has no numpy.

roster.json, which UHorseComponent reads from Content/Data/horses, is exactly:

    {"reference_breed": slug, "breed_order": [slug, ...], "fps": int,
     "masters": {"coat" | "hair" | "tack" | "tack_masked": material path},
     "breeds": {slug: {"slug", "name", "mesh", "skeleton": asset path, "mesh_yaw": degrees,
                       "contacts": {"saddle_root": [x, y, z], "seat_z": m, "scale_ratio": float,
                                    "stirrup_L" | "stirrup_R" | "grip_L" | "grip_R": [x, y, z]},
                       "clips": {clip: {"path", "length": s, "loop": bool}},
                       "saddles": {tack id: path}, "reins": {tack id: path}}},
     "tack_sets": [tack id, ...], "coat_masks": {mask: texture path},
     "coat_variants": [{"id", "name", "swatch", "texture"}],
     "hair_colors": [{"id", "label", "primary", "secondary"}], "hair_patterns": [{"id", "label", "mix"}],
     "tints": [{"id", "label", "rgb": [r, g, b]}]}

Contacts are in Yorimichi rider space: metres, +X forward, +Y left, +Z up, origin on the ground between the hooves
(world.horses, assets/horses/build.py). grip_L/R are the rein grips at the Idle clip's first frame.
"""
from array import array
import sys

from atelier.gltf import glb_pack, glb_parts

MESH_YAW = -90.   # glTF faces -Y in Blender (+Z in glTF), which Interchange turns into Unreal +Y; the actor faces +X
CONTACTS = ('saddle_root', 'seat_z', 'scale_ratio', 'stirrup_L', 'stirrup_R', 'grip_L', 'grip_R')
MASTERS = ('coat', 'hair', 'tack', 'tack_masked')
FLOAT, VEC3, VEC4, MAT4 = 5126, 3, 4, 16


def _floats(binary, doc, index, width):
    """(array of the accessor's floats, its byte offset): tightly packed float data only."""
    accessor = doc['accessors'][index]
    view = doc['bufferViews'][accessor['bufferView']]
    if accessor.get('componentType') != FLOAT or view.get('byteStride', 4 * width) != 4 * width:
        raise ValueError(f'accessor {index}: expected packed float data')
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    values = array('f')
    values.frombytes(bytes(binary[start:start + 4 * width * accessor['count']]))
    if sys.byteorder != 'little':
        values.byteswap()
    return values, start


def _store(binary, values, start):
    if sys.byteorder != 'little':
        values = array('f', values); values.byteswap()
    data = values.tobytes()
    binary[start:start + len(data)] = data


def _negated(values):
    return array('f', [-v for v in values])


def upright_glb(data):
    """The horse or tack GLB with its 'Horse' (-90 deg X) and 'Root' (+90 deg X) container nodes and its mesh nodes at
    identity, so Unreal Interchange imports upright meshes and animations. When the mesh nodes carry that rotation,
    their Z-up POSITION, NORMAL and TANGENT data turn by -90 deg about X ((x, y, z) -> (x, z, -y)) and each skin's
    inverse bind matrices are post-multiplied by +90 deg about X. Root's translation turns the same way, and the
    static animation channels of every node set to identity are dropped."""
    doc, binary = glb_parts(data)
    binary = bytearray(binary)
    if any(n.get('rotation') is not None for n in doc.get('nodes', []) if 'mesh' in n or 'skin' in n):
        positions, vec3, vec4 = set(), set(), set()
        for mesh in doc.get('meshes', []):
            for prim in mesh.get('primitives', []):
                attrs = prim.get('attributes', {})
                if 'POSITION' in attrs:
                    vec3.add(attrs['POSITION']); positions.add(attrs['POSITION'])
                if 'NORMAL' in attrs:
                    vec3.add(attrs['NORMAL'])
                if 'TANGENT' in attrs:
                    vec4.add(attrs['TANGENT'])
        for index in sorted(vec3):
            if doc['accessors'][index].get('type') != 'VEC3':
                raise ValueError(f'accessor {index}: expected VEC3')
            values, start = _floats(binary, doc, index, VEC3)
            x, y, z = values[0::3], values[1::3], values[2::3]
            values[1::3], values[2::3] = z, _negated(y)
            _store(binary, values, start)
            if index in positions and len(x):
                ny = values[2::3]
                doc['accessors'][index]['min'] = [min(x), min(z), min(ny)]
                doc['accessors'][index]['max'] = [max(x), max(z), max(ny)]
        for index in sorted(vec4):
            if doc['accessors'][index].get('componentType') == FLOAT and doc['accessors'][index].get('type') == 'VEC4':
                values, start = _floats(binary, doc, index, VEC4)
                y = values[1::4]
                values[1::4], values[2::4] = values[2::4], _negated(y)
                _store(binary, values, start)
        for index in sorted({skin['inverseBindMatrices'] for skin in doc.get('skins', []) if 'inverseBindMatrices' in skin}):
            if doc['accessors'][index].get('type') != 'MAT4':
                raise ValueError(f'accessor {index}: expected MAT4')
            values, start = _floats(binary, doc, index, MAT4)
            for row in range(4):   # column-major: column 1 becomes column 2, column 2 becomes -column 1
                c1 = values[4 + row::16]
                values[4 + row::16], values[8 + row::16] = values[8 + row::16], _negated(c1)
            _store(binary, values, start)

    upright = set()
    for i, node in enumerate(doc.get('nodes', [])):
        if node.get('name') == 'Root':
            t = node.get('translation')
            if t and len(t) == 3:
                node['translation'] = [float(t[0]), float(t[2]), float(-t[1])]
        if node.get('name') in ('Horse', 'Root') or 'mesh' in node or 'skin' in node:
            node['rotation'] = [0., 0., 0., 1.]
            upright.add(i)
    for animation in doc.get('animations', []):
        animation['channels'] = [c for c in animation.get('channels', []) if c.get('target', {}).get('node') not in upright]
    return glb_pack(doc, bytes(binary))


def roster(library, built, masters, coat_masks, coat_variants, breeds):
    """roster.json from the library manifest (assets/horses/manifest.json), world.horses' manifest (its contacts and
    sample rate) and what the import made: `masters` {key: path}, `coat_masks` {mask: texture path}, `coat_variants`
    [{'id', 'name', 'swatch', 'texture'}] and `breeds` {slug: {'mesh', 'skeleton', 'clips', 'saddles', 'reins'}}."""
    return {
        'reference_breed': library['reference_breed'],
        'breed_order': list(library['breeds']),
        'fps': built['fps'],
        'masters': {key: masters[key] for key in MASTERS},
        'breeds': {slug: {
            'slug': slug,
            'name': library['breeds'][slug]['name'],
            'mesh': breeds[slug]['mesh'],
            'skeleton': breeds[slug]['skeleton'],
            'mesh_yaw': MESH_YAW,
            'contacts': {key: built['breeds'][slug]['contacts'][key] for key in CONTACTS},
            'clips': {clip: breeds[slug]['clips'][clip] for clip in library['clips']},
            'saddles': {sid: breeds[slug]['saddles'][sid] for sid in library['tack_sets']},
            'reins': {sid: breeds[slug]['reins'][sid] for sid in library['tack_sets']},
        } for slug in library['breeds']},
        'tack_sets': list(library['tack_sets']),
        'coat_masks': {mask: coat_masks[mask] for mask in library['coat_masks']},
        'coat_variants': [{key: v[key] for key in ('id', 'name', 'swatch', 'texture')} for v in coat_variants],
        'hair_colors': library['hair_colors'],
        'hair_patterns': library['hair_patterns'],
        'tints': library['tints'],
    }


def _point(value):
    return isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value)


def roster_problems(r):
    """What makes `r` differ from the roster contract (the module docstring): an empty list when it matches."""
    problems = []
    def need(ok, what):
        if not ok:
            problems.append(what)
    keys = {'reference_breed', 'breed_order', 'fps', 'masters', 'breeds', 'tack_sets', 'coat_masks', 'coat_variants',
            'hair_colors', 'hair_patterns', 'tints'}
    need(set(r) == keys, f'roster keys {sorted(set(r) ^ keys)}')
    if problems:
        return problems
    need(isinstance(r['fps'], int) and r['fps'] > 0, 'fps')
    need(set(r['masters']) == set(MASTERS) and all(isinstance(p, str) and p for p in r['masters'].values()), 'masters')
    need(r['breed_order'] == list(r['breeds']) and r['reference_breed'] in r['breeds'], 'breed_order/reference_breed')
    tack = r['tack_sets']
    need(bool(tack) and all(isinstance(t, str) for t in tack), 'tack_sets')
    clips = None
    for slug, b in r['breeds'].items():
        need(set(b) == {'slug', 'name', 'mesh', 'skeleton', 'mesh_yaw', 'contacts', 'clips', 'saddles', 'reins'}, f'{slug}: keys')
        if problems:
            return problems
        need(b['slug'] == slug and all(isinstance(b[k], str) and b[k] for k in ('name', 'mesh', 'skeleton')), f'{slug}: names')
        need(isinstance(b['mesh_yaw'], float), f'{slug}: mesh_yaw')
        c = b['contacts']
        need(set(c) == set(CONTACTS), f'{slug}: contacts keys')
        need(all(_point(c.get(k)) for k in ('saddle_root', 'stirrup_L', 'stirrup_R', 'grip_L', 'grip_R'))
             and all(isinstance(c.get(k), (int, float)) for k in ('seat_z', 'scale_ratio')), f'{slug}: contacts values')
        need(all(set(e) == {'path', 'length', 'loop'} and isinstance(e['path'], str) and isinstance(e['loop'], bool)
                 and isinstance(e['length'], (int, float)) and e['length'] > 0 for e in b['clips'].values()), f'{slug}: clips')
        need(clips is None or list(b['clips']) == clips, f'{slug}: clip names')
        clips = list(b['clips'])
        need(list(b['saddles']) == tack and list(b['reins']) == tack, f'{slug}: tack sets')
    need(bool(r['coat_masks']) and all(isinstance(p, str) for p in r['coat_masks'].values()), 'coat_masks')
    need(all(set(v) == {'id', 'name', 'swatch', 'texture'} for v in r['coat_variants']), 'coat_variants')
    need(all(set(v) == {'id', 'label', 'primary', 'secondary'} for v in r['hair_colors']), 'hair_colors')
    need(all(set(v) == {'id', 'label', 'mix'} for v in r['hair_patterns']), 'hair_patterns')
    need(all(set(v) == {'id', 'label', 'rgb'} and _point(v['rgb']) for v in r['tints']), 'tints')
    return problems


def meshes(r):
    """Every skeletal mesh the roster names: each breed's body, saddles and reins."""
    for b in r['breeds'].values():
        yield b['mesh']
        yield from b['saddles'].values()
        yield from b['reins'].values()


def asset_paths(r):
    """Every Unreal asset path the roster names."""
    yield from r['masters'].values()
    yield from r['coat_masks'].values()
    yield from (v['texture'] for v in r['coat_variants'])
    for b in r['breeds'].values():
        yield b['mesh']
        yield b['skeleton']
        yield from (c['path'] for c in b['clips'].values())
        yield from b['saddles'].values()
        yield from b['reins'].values()
