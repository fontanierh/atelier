"""Project the assembled hippodrome region (regions/hippodrome/atomic.assemble) into its structures' painted maps.

The region Item is glb/<child>.glb with hippodrome.json and build-report.json. Each exported child whose report
material is not one of import_hippodrome's own SURFACES is a Tripo structure piece: the original imported its glTF
material and painted base-colour map with it and restyled that instance onto M_HD_Structure. ``project`` writes one
member per such child, <child>.json: its glTF material name and the base-colour image bytes. ``select`` unpacks one.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct

NAME = re.compile('[A-Za-z][A-Za-z0-9_]*\\Z')


def _json(path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ValueError('Duplicate hippodrome field')
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)


def _regular(path):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError('Hippodrome region file is absent or aliased: ' + str(path))
    return path


def _glb(data):
    if len(data) < 20 or data[:4] != b'glTF' or struct.unpack_from('<II', data, 4) != (2, len(data)):
        raise ValueError('not a complete GLB2')
    size, kind = struct.unpack_from('<I4s', data, 12)
    document = json.loads(data[20:20 + size])
    if kind != b'JSON':
        raise ValueError('first GLB chunk is not JSON')
    offset = 20 + size
    binary = b''
    if offset < len(data):
        length, kind = struct.unpack_from('<I4s', data, offset)
        if kind != b'BIN\x00':
            raise ValueError('second GLB chunk is not BIN')
        binary = data[offset + 8:offset + 8 + length]
    return document, binary


def paint(data):
    """(material name, image bytes, mime) of the single material's base-colour map."""
    document, binary = _glb(data)
    materials = document.get('materials') or []
    if len(materials) != 1:
        raise ValueError('A structure piece has exactly one glTF material')
    texture = ((materials[0].get('pbrMetallicRoughness') or {}).get('baseColorTexture') or {}).get('index')
    if type(texture) is not int:
        raise ValueError('A structure material has no painted base-colour map')
    image = document['images'][document['textures'][texture]['source']]
    if 'bufferView' not in image or image.get('mimeType') not in ('image/png', 'image/jpeg'):
        raise ValueError('A structure map must be an embedded PNG or JPEG')
    view = document['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    return materials[0].get('name', ''), binary[start:start + view['byteLength']], image['mimeType']


def members(region, surfaces):
    """{child: member} for every structure child of the complete assembled region."""
    region = Path(region)
    data, report = _json(_regular(region / 'hippodrome.json')), _json(_regular(region / 'build-report.json'))
    names = [entry['name'] for entry in data['meshes']]
    if sorted(names) != sorted(report['meshes']) or len(set(names)) != len(names):
        raise ValueError('Hippodrome venue data and build report differ')
    result = {}
    for name in names:
        expected = report['meshes'][name]
        if not NAME.fullmatch(name):
            raise ValueError('Noncanonical hippodrome mesh name: ' + name)
        payload = _regular(region / 'glb' / f'{name}.glb').read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected['sha256']:
            raise ValueError('stale region build: ' + name)
        if expected['material'] in surfaces:
            continue
        material, image, mime = paint(payload)
        result[name] = {'name': name, 'material': material, 'mime': mime, 'image': image}
    return result


def project(region=None, surfaces=None, output=None):
    """@cc [owner:fontanierh,label:correctness] hippodrome-structure-paint-members
    Membership MUST come from the complete declared assembled region: every child
    whose report material is not an original SURFACES key, checked against the
    report checksum, with exactly its one material's embedded base-colour map. No
    speculative member, scan beyond the declared region or native work.
    """
    rows = members(region, surfaces)
    if output.exists():
        raise ValueError('Hippodrome member output must be fresh')
    output.mkdir(parents=True)
    for piece, value in rows.items():
        encoded = {**value, 'image': base64.b64encode(value['image']).decode('ascii'),
                   'sha256': hashlib.sha256(value['image']).hexdigest()}
        (output / (piece + '.json')).write_text(json.dumps(encoded, sort_keys=True, separators=(',', ':')) + '\n')


def select(selected=None, destination=None, piece=None):
    """Unpack exactly the engine-selected member: its map and export receipt in member/."""
    found = sorted(Path(selected).iterdir()) if Path(selected).is_dir() else []
    if (len(found) != 1 or found[0].name != piece + '.json' or found[0].is_symlink() or not found[0].is_file()
            or destination.exists()):
        raise ValueError('Hippodrome selected member must be one fresh regular <piece>.json')
    member = _json(found[0])
    data = base64.b64decode(member['image'], validate=True)
    if member.get('name') != piece or hashlib.sha256(data).hexdigest() != member['sha256']:
        raise ValueError('Hippodrome selected member differs from its piece or checksum')
    destination.mkdir(parents=True)
    name = piece + ('.png' if member['mime'] == 'image/png' else '.jpg')
    (destination / name).write_bytes(data)
    (destination / 'export.json').write_text(json.dumps({'primary': name, 'sha256': member['sha256']}, sort_keys=True) + '\n')
