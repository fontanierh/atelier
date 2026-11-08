"""The start tower's shrine, after the approved Sunburst concept C (assets/craterpark/concepts/editor/
tower-top-shrine-balcony.jpg): a bell pavilion (shoro), stone lanterns, a torii with its shimenawa and red nobori
banners on a balcony behind the deck's back edge (editor_supports.tower builds the balcony and says where each
stands).

Each object is a textured Tripo model in assets/craterpark/shrine/<slug>/<slug>.glb (tools/craterpark_shrine_props.py:
a Sunburst reference sheet, then Tripo P2 image-to-model), fitted here to its size in metres and placed as drawn-only
faces (role coping: no collision, as editor_floor's dressing) with the model's own UVs and one material each; that
material's texture is the model's own (tools/craterpark_textures.py finish writes it out for the Unreal import).
Only numpy and the standard library are used: the GLB is read directly.
"""
from functools import lru_cache
import json
from pathlib import Path
import struct

import numpy as np

from . import dsl

SOURCE = Path(__file__).resolve().parents[4] / 'assets' / 'craterpark' / 'shrine'
# slug: (material, size in metres, what the size measures). The models stand with y up, their front along +x and
# their width along z (Tripo's frame); `width` is the larger plan side.
MODELS = {
    'bell_pavilion': ('material_046', 10.5, 'width'),
    'stone_lantern': ('material_047', 3.4, 'height'),
    'torii': ('material_048', 12.0, 'height'),
    'nobori': ('material_049', 7.0, 'height'),
}
MATERIALS = tuple(m for m, _, _ in MODELS.values())


def path(slug):
    return SOURCE / slug / f'{slug}.glb'


def _parts(data):
    """(JSON document, BIN chunk) of a binary glTF (atelier.gltf.glb_parts, without importing atelier)."""
    magic, version, length = struct.unpack('<4sII', data[:12])
    if magic != b'glTF' or version != 2 or length != len(data):
        raise ValueError('not a glTF 2 binary')
    size, _ = struct.unpack('<I4s', data[12:20])
    doc = json.loads(data[20:20 + size])
    at = 20 + size
    size, _ = struct.unpack('<I4s', data[at:at + 8])
    return doc, data[at + 8:at + 8 + size]


def _accessor(doc, binary, index):
    acc = doc['accessors'][index]
    view = doc['bufferViews'][acc['bufferView']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']]
    dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[acc['componentType']]
    itemsize = np.dtype(dtype).itemsize * width
    stride = view.get('byteStride') or itemsize
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    raw = np.frombuffer(binary, 'u1', count=stride * (acc['count'] - 1) + itemsize, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, (acc['count'], itemsize), (stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(acc['count'], width).squeeze(-1 if width == 1 else None)


@lru_cache(maxsize=None)
def model(slug):
    """(V, N, UV, F) of a shrine model fitted to its size: y up, standing on y = 0, centred on x = z = 0, its front
    along +x. UV as glTF stores it (origin at the image's top left), as the dsl's other UVs (export flips v)."""
    doc, binary = _parts(path(slug).read_bytes())
    if len(doc['nodes']) != 1 or any(k in doc['nodes'][0] for k in ('matrix', 'rotation', 'scale', 'translation')):
        raise ValueError(f'{slug}: expected one untransformed node, as Tripo writes')
    V, N, UV, F = [], [], [], []
    for prim in doc['meshes'][0]['primitives']:
        a = prim['attributes']
        F.append(_accessor(doc, binary, prim['indices']).reshape(-1, 3).astype('i8') + sum(len(v) for v in V))
        V.append(_accessor(doc, binary, a['POSITION']).astype('f8'))
        N.append(_accessor(doc, binary, a['NORMAL']).astype('f8'))
        UV.append(_accessor(doc, binary, a['TEXCOORD_0']).astype('f8'))
    V, N, UV, F = np.concatenate(V), np.concatenate(N), np.concatenate(UV), np.concatenate(F)
    _, size, measure = MODELS[slug]
    lo, hi = V.min(0), V.max(0)
    extent = (hi - lo)[1] if measure == 'height' else max((hi - lo)[0], (hi - lo)[2])
    V = (V - [(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]) * (size / extent)
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return V, N, UV, F


def footprint(slug):
    """(half depth along the front, half width, height) of the fitted model."""
    V = model(slug)[0]
    return float(np.abs(V[:, 0]).max()), float(np.abs(V[:, 2]).max()), float(V[:, 1].max())


def place(slug, at, facing):
    """The model standing at `at` (x, y, z: its base centre), its front toward the plan direction `facing`, as
    (V, F, N, UV, material) in the park's frame (a rotation about y: x -> facing, z -> its left)."""
    V, N, UV, F = model(slug)
    f = np.asarray(facing, 'f8') / np.linalg.norm(facing)
    R = np.array([[f[0], 0., -f[1]], [0., 1., 0.], [f[1], 0., f[0]]])    # columns: where x, y and z go
    return V @ R.T + np.asarray(at, 'f8'), F, N @ R.T, UV, MODELS[slug][0]


def part(placed, feature):
    """A placed model as a drawn-only dsl Mesh part (no collision)."""
    V, F, N, UV, material = placed
    return dsl.Mesh.part(V, F, N=N, UV=UV, role=dsl.COPING, material=material, feature=feature)


def texture(slug):
    """The model's own base colour image (JPEG bytes, as compacted by tools/treehouse_props.py)."""
    doc, binary = _parts(path(slug).read_bytes())
    image = doc['images'][doc['textures'][doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index']]
                          ['source']]
    view = doc['bufferViews'][image['bufferView']]
    return binary[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']]


def available():
    return all(path(slug).is_file() for slug in MODELS)
