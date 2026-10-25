"""Project the actual adventure export (adventure/export.py) into narrow GLB views and FileSet members.

The export Item is export.json with glb/Reference.glb and the committed equipment GLBs (sword, glider). ``project``
writes one group's members, each <piece>.json carrying exactly what its owner consumes:
- ``clips``: per Reference clip, a GLB view with that one animation (skin, nodes and mesh, no images) and its export
  entry (frames, loop, travel) at the export rate;
- ``images``: each embedded glTF image of Reference and the equipment, as <Owner>_<image> bytes;
- ``materials``: each glTF material as <Owner>_<material>: masked (alphaMode is not OPAQUE, Interchange's
  masked parent), its base colour and emissive image pieces, emissive factor and alpha cutoff.
``views`` writes the fixed owners' sources: Reference.glb without animations or images, the sword as a static
view (bake.static), the glider without its animation or images and its one clip as a one-animation view.
Each view keeps only the accessors and buffer views it references. ``select`` unpacks one member.
"""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')
TEXTURES = ('baseColorTexture', 'metallicRoughnessTexture')


def _bake(path):
    spec = importlib.util.spec_from_file_location('adventure_bake_view', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate adventure export field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite adventure export value')))


def _piece(*parts):
    name = re.sub(r'[^A-Za-z0-9_]+', '_', '_'.join(parts)).strip('_')
    if not NAME.fullmatch(name):
        raise ValueError('Adventure member has no canonical name: ' + '_'.join(parts))
    return name


def compact(gltf, binary, *, animations=(), images=False):
    """A view of (gltf, binary) with only the given animations, images when asked, and the accessors and buffer
    views those and the meshes and skins reference, repacked."""
    view = deepcopy(gltf)
    view['animations'] = [deepcopy(gltf['animations'][i]) for i in animations]
    if not view['animations']:
        view.pop('animations')
    if not images:
        for key in ('images', 'textures', 'samplers'):
            view.pop(key, None)
        for material in view.get('materials', ()):
            for key in ('normalTexture', 'occlusionTexture', 'emissiveTexture'):
                material.pop(key, None)
            for key in TEXTURES:
                material.get('pbrMetallicRoughness', {}).pop(key, None)
    accessors = set()
    for mesh in view.get('meshes', ()):
        for primitive in mesh['primitives']:
            accessors.update(primitive['attributes'].values())
            if 'indices' in primitive:
                accessors.add(primitive['indices'])
            for target in primitive.get('targets', ()):
                accessors.update(target.values())
    for skin in view.get('skins', ()):
        if 'inverseBindMatrices' in skin:
            accessors.add(skin['inverseBindMatrices'])
    for animation in view.get('animations', ()):
        for sampler in animation['samplers']:
            accessors.update((sampler['input'], sampler['output']))
    views = {gltf['accessors'][a]['bufferView'] for a in accessors if 'bufferView' in gltf['accessors'][a]}
    views |= {image['bufferView'] for image in view.get('images', ()) if 'bufferView' in image}
    packed, view_map = bytearray(), {}
    new_views = []
    for index in sorted(views):
        old = gltf['bufferViews'][index]
        packed += b'\x00' * (-len(packed) % 4)
        start = old.get('byteOffset', 0)
        new = {key: value for key, value in old.items() if key not in ('byteOffset', 'buffer')}
        new.update(buffer=0, byteOffset=len(packed))
        packed += binary[start:start + old['byteLength']]
        view_map[index] = len(new_views); new_views.append(new)
    accessor_map, new_accessors = {}, []
    for index in sorted(accessors):
        accessor = deepcopy(gltf['accessors'][index])
        if 'bufferView' in accessor:
            accessor['bufferView'] = view_map[accessor['bufferView']]
        accessor_map[index] = len(new_accessors); new_accessors.append(accessor)
    for mesh in view.get('meshes', ()):
        for primitive in mesh['primitives']:
            primitive['attributes'] = {k: accessor_map[v] for k, v in primitive['attributes'].items()}
            if 'indices' in primitive:
                primitive['indices'] = accessor_map[primitive['indices']]
            primitive['targets'] = [{k: accessor_map[v] for k, v in t.items()} for t in primitive.get('targets', ())]
            if not primitive['targets']:
                primitive.pop('targets')
    for skin in view.get('skins', ()):
        if 'inverseBindMatrices' in skin:
            skin['inverseBindMatrices'] = accessor_map[skin['inverseBindMatrices']]
    for animation in view.get('animations', ()):
        for sampler in animation['samplers']:
            sampler['input'], sampler['output'] = accessor_map[sampler['input']], accessor_map[sampler['output']]
    for image in view.get('images', ()):
        if 'bufferView' in image:
            image['bufferView'] = view_map[image['bufferView']]
    view['bufferViews'], view['accessors'] = new_views, new_accessors
    return view, packed


def _glb(bake, gltf, binary):
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / 'view.glb'
        bake.write_glb(path, gltf, binary)
        return path.read_bytes()


def _source(root, relative):
    path = Path(root) / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError('Adventure export GLB is absent or aliased: ' + str(relative))
    return path


def reference(export):
    """The export's one character, Reference, the motion reference with the committed sword and glider."""
    config = _json(export)
    characters = config.get('characters')
    if not isinstance(characters, list) or len(characters) != 1 or characters[0].get('name') != 'Reference':
        raise ValueError('Adventure export is not exactly the Reference rig')
    character = characters[0]
    if character.get('skeleton') != 'Reference' or set(character['moves']['equipment']) != {'sword', 'glider'}:
        raise ValueError('Adventure export differs from the committed Reference roster (sword, glider)')
    if 'clip' in character['moves']['equipment']['sword'] or 'clip' not in character['moves']['equipment']['glider']:
        raise ValueError('Adventure equipment differs: the sword is a prop, the glider is skinned with one clip')
    return config, character


def members(export, glb, bake_script):
    """{kind: {piece: member value}} for every group, after the whole Item checks."""
    bake = _bake(bake_script)
    config, character = reference(export)
    out = Path(glb).parent
    owners = {'Reference': character['glb'], **{f'Reference{slot.capitalize()}': item['glb']
                                                 for slot, item in character['moves']['equipment'].items()}}
    loaded = {owner: bake.read_glb(_source(out, relative)) for owner, relative in owners.items()}
    gltf, binary = loaded['Reference']
    by_name = {a.get('name'): i for i, a in enumerate(gltf.get('animations', ()))}
    if len(by_name) != len(gltf.get('animations', ())):
        raise ValueError('Reference.glb repeats an animation name')
    result = {'clips': {}, 'images': {}, 'materials': {}}
    for clip in character['clips']:
        name = clip['name']
        if not NAME.fullmatch(name) or name not in by_name or type(clip['frames']) is not int or clip['frames'] <= 0:
            raise ValueError('Reference clip differs from Reference.glb: ' + str(name))
        data = _glb(bake, *compact(gltf, binary, animations=(by_name[name],)))
        result['clips'][name] = {'name': name, 'frames': clip['frames'], 'fps': config['fps'], 'loop': clip['loop'],
                                 'travel': clip['travel'], 'glb': data}
    if set(by_name) != {clip['name'] for clip in character['clips']}:
        raise ValueError('Reference.glb carries clips the export does not list')
    for owner, (data, chunk) in loaded.items():
        pieces = {}
        for index, image in enumerate(data.get('images', ())):
            if 'bufferView' not in image or image.get('mimeType') not in ('image/png', 'image/jpeg'):
                raise ValueError(f'{owner}: image {index} is not an embedded PNG/JPEG')
            piece = _piece(owner, image.get('name') or f'image{index}')
            if piece in result['images']:
                raise ValueError('Aliased adventure image: ' + piece)
            view = data['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            result['images'][piece] = {'name': piece, 'mime': image['mimeType'],
                                       'image': bytes(chunk[start:start + view['byteLength']])}
            pieces[index] = piece
        def image_of(reference):
            if reference is None:
                return None
            return pieces[data['textures'][reference['index']]['source']]
        for index, material in enumerate(data.get('materials', ())):
            piece = _piece(owner, material.get('name') or f'material{index}')
            if piece in result['materials']:
                raise ValueError('Aliased adventure material: ' + piece)
            pbr = material.get('pbrMetallicRoughness', {})
            result['materials'][piece] = {
                'name': piece, 'owner': owner, 'slot': material.get('name') or f'material{index}',
                'masked': material.get('alphaMode', 'OPAQUE') != 'OPAQUE',
                'base': image_of(pbr.get('baseColorTexture')), 'emissive': image_of(material.get('emissiveTexture')),
                'emissive_factor': list(material.get('emissiveFactor', [0., 0., 0.])),
                'alpha_cutoff': material.get('alphaCutoff', .5)}
    return result, loaded, bake


def _encode(value):
    encoded = {key: (base64.b64encode(item).decode('ascii') if isinstance(item, bytes) else item) for key, item in value.items()}
    blob = next((value[key] for key in ('glb', 'image') if key in value), None)
    if blob is not None:
        encoded['sha256'] = hashlib.sha256(blob).hexdigest()
    return json.dumps(encoded, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def project(export=None, glb=None, bake_script=None, output=None, kind=None):
    """@cc [owner:fontanierh,label:correctness] actual-reference-export-members
    Membership MUST come from the complete declared adventure export Item: the
    one Reference rig and its committed sword and glider. Every listed clip MUST
    be exactly one Reference.glb animation, and images and materials come from
    the actual GLB JSON. Each member carries only its owner's narrow view; no
    speculative member, generated scan or native work.
    """
    rows = members(export, glb, bake_script)[0]
    if kind not in rows:
        raise ValueError('Unknown Reference projection kind')
    if output.exists():
        raise ValueError('Reference member output must be fresh')
    output.mkdir(parents=True)
    for piece, value in rows[kind].items():
        (output / (piece + '.json')).write_text(_encode(value))


def views(export=None, glb=None, bake_script=None, output=None, glider_clip=None):
    """The fixed owners' GLB views, each with an export receipt beside it in its own folder."""
    _, loaded, bake = members(export, glb, bake_script)
    _, character = reference(export)
    clip = character['moves']['equipment']['glider']['clip']
    if clip != glider_clip:
        raise ValueError('The exported glider clip differs from the committed moves.toml one')
    glider, chunk = loaded['ReferenceGlider']
    names = [a.get('name') for a in glider.get('animations', ())]
    if len(names) != 1:
        raise ValueError('The glider GLB must carry exactly its one clip')
    with tempfile.TemporaryDirectory() as scratch:
        sword = Path(scratch) / 'sword.glb'
        bake.static(_source(Path(glb).parent, character['moves']['equipment']['sword']['glb']), sword)
        sword_view = _glb(bake, *compact(*bake.read_glb(sword)))
    # A raw glTF animation import names its one animation by its destination: the committed clip name.
    clip_view, clip_chunk = compact(glider, chunk, animations=(0,))
    clip_view['animations'][0]['name'] = clip
    written = {'Reference': _glb(bake, *compact(*loaded['Reference'])), 'ReferenceSword': sword_view,
               'ReferenceGlider': _glb(bake, *compact(glider, chunk)),
               f'ReferenceGlider_{clip}': _glb(bake, clip_view, clip_chunk)}
    if output.exists():
        raise ValueError('Reference views output must be fresh')
    for name, data in written.items():
        folder = output / name
        folder.mkdir(parents=True)
        (folder / (name + '.glb')).write_bytes(data)
        (folder / 'export.json').write_text(json.dumps({'primary': name + '.glb', 'sha256': hashlib.sha256(data).hexdigest()},
                                                       sort_keys=True) + '\n')


def select(selected=None, destination=None, metadata=None, piece=None):
    """Unpack exactly the engine-selected member: its bytes (a GLB view with its export receipt, or an image) in
    member/, and its own metadata in meta/meta.json."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists() or metadata.exists()):
        raise ValueError('Reference selected member must be one fresh regular <piece>.json')
    member = _json(found[0])
    if member.get('name') != piece:
        raise ValueError('Reference selected member differs from its piece')
    meta = {key: value for key, value in member.items() if key not in ('glb', 'image', 'sha256')}
    for key, suffix in (('glb', '.glb'), ('image', None)):
        if key in member:
            data = base64.b64decode(member[key], validate=True)
            if hashlib.sha256(data).hexdigest() != member['sha256']:
                raise ValueError('Reference selected member bytes differ from their checksum')
            destination.mkdir(parents=True)
            name = piece + (suffix or ('.png' if member['mime'] == 'image/png' else '.jpg'))
            (destination / name).write_bytes(data)
            (destination / 'export.json').write_text(json.dumps({'primary': name, 'sha256': member['sha256']}, sort_keys=True) + '\n')
    metadata.mkdir(parents=True)
    (metadata / 'meta.json').write_text(json.dumps(meta, sort_keys=True) + '\n')
