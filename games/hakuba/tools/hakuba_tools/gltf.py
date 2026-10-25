"""Reading, editing and writing binary glTF (.glb) files.

Edits change the JSON and record new bytes for buffer views; `write` packs only what is still referenced, so removed
accessors and replaced images leave nothing behind in the file.
"""
import json
import struct
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image

MAGIC, VERSION = b'glTF', 2
JSON_CHUNK, BIN_CHUNK = b'JSON', b'BIN\0'


@dataclass
class Glb:
    json: dict
    bin: bytes
    replaced: dict[int, bytes] = field(default_factory=dict)   # buffer view -> its new bytes

    def view(self, index):
        if index in self.replaced:
            return self.replaced[index]
        view = self.json['bufferViews'][index]
        start = view.get('byteOffset', 0)
        return self.bin[start:start + view['byteLength']]


def read(path):
    data = Path(path).read_bytes()
    magic, version, _ = struct.unpack_from('<4sII', data)
    if magic != MAGIC or version != VERSION:
        raise ValueError(f'{path}: not a glTF 2 binary')
    chunks, offset = {}, 12
    while offset < len(data):
        length, kind = struct.unpack_from('<I4s', data, offset)
        chunks[kind] = data[offset + 8:offset + 8 + length]
        offset += 8 + length
    return Glb(json.loads(chunks[JSON_CHUNK]), chunks.get(BIN_CHUNK, b''))


def write(glb, path):
    gltf, data = _repack(glb)
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<I4s', len(text), JSON_CHUNK) + text
    if data:
        data += b'\0' * (-len(data) % 4)
        body += struct.pack('<I4s', len(data), BIN_CHUNK) + data
    Path(path).write_bytes(struct.pack('<4sII', MAGIC, VERSION, 12 + len(body)) + body)


def scene_height(glb):
    """The height of the meshes in their bind pose, from their primitives' position bounds."""
    accessors = glb.json['accessors']
    bounds = [accessors[p['attributes']['POSITION']] for m in glb.json['meshes'] for p in m['primitives']]
    return max(a['max'][1] for a in bounds) - min(a['min'][1] for a in bounds)


def scale_to_height(glb, height):
    """Scales every root node of the default scene so the meshes stand `height` tall."""
    factor = height / scene_height(glb)
    scene = glb.json['scenes'][glb.json.get('scene', 0)]
    for index in scene['nodes']:
        node = glb.json['nodes'][index]
        node['scale'] = [s * factor for s in node.get('scale', [1, 1, 1])]
        if 'translation' in node:
            node['translation'] = [t * factor for t in node['translation']]


def remove_morph_targets(glb):
    for mesh in glb.json['meshes']:
        mesh.pop('weights', None)
        mesh.get('extras', {}).pop('targetNames', None)
        for primitive in mesh['primitives']:
            primitive.pop('targets', None)
    for node in glb.json['nodes']:
        node.pop('weights', None)


def resize_images(glb, size):
    """Shrinks every embedded image larger than `size` pixels on a side, keeping its format."""
    for image in glb.json.get('images', []):
        picture = Image.open(BytesIO(glb.view(image['bufferView'])))
        if max(picture.size) <= size:
            continue
        picture.thumbnail((size, size), Image.Resampling.LANCZOS)
        out = BytesIO()
        picture.save(out, format=picture.format, optimize=True)
        glb.replaced[image['bufferView']] = out.getvalue()


def _accessor_refs(gltf):
    """Every (holder, key) whose value is an accessor index."""
    for mesh in gltf.get('meshes', []):
        for primitive in mesh['primitives']:
            yield from ((primitive['attributes'], name) for name in primitive['attributes'])
            if 'indices' in primitive:
                yield primitive, 'indices'
            for target in primitive.get('targets', []):
                yield from ((target, name) for name in target)
    for skin in gltf.get('skins', []):
        if 'inverseBindMatrices' in skin:
            yield skin, 'inverseBindMatrices'
    for animation in gltf.get('animations', []):
        for sampler in animation['samplers']:
            yield sampler, 'input'
            yield sampler, 'output'


def _repack(glb):
    """The JSON without unreferenced accessors and buffer views, and one fresh buffer holding the rest."""
    gltf = json.loads(json.dumps(glb.json))
    refs = list(_accessor_refs(gltf))
    kept = sorted({holder[key] for holder, key in refs})
    if any('sparse' in gltf['accessors'][i] for i in kept):
        raise NotImplementedError('sparse accessors')
    accessor_map = {old: new for new, old in enumerate(kept)}
    for holder, key in refs:
        holder[key] = accessor_map[holder[key]]
    gltf['accessors'] = [gltf['accessors'][i] for i in kept]

    holders = [a for a in gltf['accessors'] if 'bufferView' in a] + [i for i in gltf.get('images', []) if 'bufferView' in i]
    views, data, view_map = [], bytearray(), {}
    for old in sorted({h['bufferView'] for h in holders}):
        data += b'\0' * (-len(data) % 4)
        chunk = glb.view(old)
        view = {k: v for k, v in gltf['bufferViews'][old].items() if k != 'byteOffset'}
        view.update(buffer=0, byteOffset=len(data), byteLength=len(chunk))
        view_map[old] = len(views)
        views.append(view)
        data += chunk
    for holder in holders:
        holder['bufferView'] = view_map[holder['bufferView']]
    gltf['bufferViews'] = views
    gltf['buffers'] = [{'byteLength': len(data)}] if data else []
    return gltf, bytes(data)
