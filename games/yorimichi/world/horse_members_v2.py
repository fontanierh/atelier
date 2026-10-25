"""Project one breed's actual horse sources (world.horses' turns/<slug>.glb, the committed tack GLBs) into narrow GLB
views and FileSet members for Scripts/import_horses.py's native owners.

Each source is first made upright exactly as import_horses.upright does (horse_data.upright_glb). Owners are the breed
body SK_Horse_<Breed> and its tack <Part>_<sid> (Saddle, Reins per committed tack set). ``project`` writes one group's
members, each <piece>.json carrying exactly what its owner consumes:
- ``clips``: per committed clip (the library's and horse_data.GENERATED_CLIPS), matched to its body animation by
  import_horses.match_clip, a GLB view with only that animation renamed to the clip (the raw import's destination);
- ``images``: each embedded glTF image of the body and tack, as <Owner>_<image> bytes;
- ``materials``: each glTF material as <Owner>_<material>: its restyle_instance role (coat, hair, tack), masked
  (alphaMode is not OPAQUE), its base-colour image piece and alpha cutoff.
``views`` writes the fixed owners' sources: the body and each tack GLB without animations or images. Each view keeps
only the accessors and buffer views it references. ``select`` is reference_members_v2.select.
"""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re

NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')
PARTS = ('Saddle', 'Reins')
HERE = Path(__file__).resolve().parent


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


_reference = _module(HERE / 'reference_members_v2.py', 'horse_reference_members')
compact, select = _reference.compact, _reference.select


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate horse source field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite horse source value')))


def piece(*parts):
    """The member name of an owner's glTF material or image (an image name's .png/.jpg suffix dropped)."""
    name = re.sub(r'\.(png|jpe?g)\Z', '', '_'.join(parts), flags=re.I)
    name = re.sub(r'[^A-Za-z0-9_]+', '_', name).strip('_')
    if not NAME.fullmatch(name):
        raise ValueError('Horse member has no canonical name: ' + '_'.join(parts))
    return name


def match_clip(names, clip):
    """import_horses.match_clip over animation names: exact, horse<clip>, horse_<clip>, else one unique suffix."""
    for name in names:
        if name in (clip, f'horse{clip}', f'horse_{clip}'):
            return name
    matches = [name for name in names if name.endswith(clip)]
    return matches[0] if len(matches) == 1 else None


def role(name):
    """import_horses.restyle_instance's master for a glTF material: Coat, Mane/Tail (hair), else tack."""
    return 'coat' if name == 'Coat' else 'hair' if name in ('Mane', 'Tail') else 'tack'


def _source(path):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError('Horse source GLB is absent or aliased: ' + str(path))
    return path


def owners(library, slug, body, assets):
    """{owner: source GLB} for one breed: its body and every committed tack set's saddle and reins."""
    library = _json(library)
    if slug not in library['breeds']:
        raise ValueError('Unknown horse breed: ' + slug)
    name = library['breeds'][slug]['name']
    result = {f'SK_Horse_{name}': _source(body)}
    for sid in library['tack_sets']:
        for part in PARTS:
            result[f'{part}_{sid}'] = _source(Path(assets) / 'tack' / f'{part}_{sid}.glb')
    return library, name, result


def members(library, slug, body, assets, horse_data):
    """{kind: {piece: member value}} for one breed, after every source checks; and the upright sources."""
    data = _module(horse_data, 'horse_members_data')
    from atelier.gltf import glb_pack, glb_parts
    library, name, sources = owners(library, slug, body, assets)
    loaded = {owner: glb_parts(data.upright_glb(path.read_bytes())) for owner, path in sources.items()}
    gltf, binary = loaded[f'SK_Horse_{name}']
    animations = [a.get('name') for a in gltf.get('animations', ())]
    if len(set(animations)) != len(animations) or any(not isinstance(a, str) for a in animations):
        raise ValueError(f'{name}: body animations are unnamed or repeated')
    roster = {**library['clips'], **data.GENERATED_CLIPS}
    result = {'clips': {}, 'images': {}, 'materials': {}}
    used = set()
    for clip, entry in roster.items():
        found = match_clip(animations, clip)
        if not NAME.fullmatch(clip) or found is None or found in used:
            raise ValueError(f'{name}: missing horse clip {clip}')
        used.add(found)
        view, chunk = compact(gltf, binary, animations=(animations.index(found),))
        view['animations'][0]['name'] = clip   # a raw glTF animation import is named by its destination
        result['clips'][clip] = {'name': clip, 'loop': bool(entry['loop']), 'glb': glb_pack(view, chunk)}
    if used != set(animations):
        raise ValueError(f'{name}: body carries clips the library does not list: {sorted(set(animations) - used)}')
    for owner, (doc, chunk) in loaded.items():
        if owner != f'SK_Horse_{name}' and doc.get('animations'):
            raise ValueError(f'{owner}: tack carries animations')
        pieces = {}
        for index, image in enumerate(doc.get('images', ())):
            if 'bufferView' not in image or image.get('mimeType') not in ('image/png', 'image/jpeg'):
                raise ValueError(f'{owner}: image {index} is not an embedded PNG/JPEG')
            key = piece(owner, image.get('name') or f'image{index}')
            if key in result['images']:
                raise ValueError('Aliased horse image: ' + key)
            view = doc['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            result['images'][key] = {'name': key, 'mime': image['mimeType'], 'image': bytes(chunk[start:start + view['byteLength']])}
            pieces[index] = key
        if not doc.get('materials'):
            raise ValueError(f'{owner}: a mesh imported without material instances')
        for index, material in enumerate(doc['materials']):
            slot = material.get('name') or f'material{index}'
            key = piece(owner, slot)
            base = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if key in result['materials']:
                raise ValueError('Aliased horse material: ' + key)
            if base is None:
                raise ValueError(f'{key}: no base-colour texture imported from its GLB')
            result['materials'][key] = {'name': key, 'owner': owner, 'slot': slot, 'role': role(slot),
                                        'masked': material.get('alphaMode', 'OPAQUE') != 'OPAQUE',
                                        'base': pieces[doc['textures'][base['index']]['source']],
                                        'alpha_cutoff': material.get('alphaCutoff', .5)}
    return result, loaded


def _encode(value):
    encoded = {key: (base64.b64encode(item).decode('ascii') if isinstance(item, bytes) else item) for key, item in value.items()}
    blob = next((value[key] for key in ('glb', 'image') if key in value), None)
    if blob is not None:
        encoded['sha256'] = hashlib.sha256(blob).hexdigest()
    return json.dumps(encoded, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def project(library=None, slug=None, body=None, assets=None, horse_data=None, output=None, kind=None):
    """@cc [owner:fontanierh,label:correctness] actual-horse-source-members
    Membership MUST come from the breed's actual world.horses body GLB and its
    committed tack GLBs, each made upright as the original does. Every committed
    clip MUST match exactly one body animation and no other may remain; images
    and materials come from the actual GLB JSON, each material keeping its base
    colour image. Each member carries only its owner's narrow view; no speculative
    member, generated scan or native work.
    """
    rows = members(library, slug, body, assets, horse_data)[0]
    if kind not in rows:
        raise ValueError('Unknown horse projection kind')
    if output.exists():
        raise ValueError('Horse member output must be fresh')
    output.mkdir(parents=True)
    for key, value in rows[kind].items():
        (output / (key + '.json')).write_text(_encode(value))


def views(library=None, slug=None, body=None, assets=None, horse_data=None, output=None):
    """The fixed owners' GLB views (the body and each tack, no animations or images), each with an export receipt."""
    from atelier.gltf import glb_pack
    _, loaded = members(library, slug, body, assets, horse_data)
    if output.exists():
        raise ValueError('Horse views output must be fresh')
    for owner, (doc, chunk) in loaded.items():
        data = glb_pack(*compact(doc, chunk))
        folder = output / owner
        folder.mkdir(parents=True)
        (folder / (owner + '.glb')).write_bytes(data)
        (folder / 'export.json').write_text(json.dumps({'primary': owner + '.glb', 'sha256': hashlib.sha256(data).hexdigest()},
                                                       sort_keys=True) + '\n')


__all__ = ['members', 'project', 'views', 'select', 'piece', 'match_clip', 'role', 'owners']
