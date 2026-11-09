"""Binary glTF subsets of a mesh, with the standard library only.

`read_glb` reads a GLB into plain lists, `triangles` yields its triangles in one fixed order, and `write_subset` writes
chosen triangles back as a GLB that keeps every vertex position, normal and UV unchanged. A triangle is named by its
ordinal in that order, so a set of ordinals (tools/content/carve.py) is enough to reproduce the same bytes.
"""
from __future__ import annotations

import json
import struct
from collections import defaultdict
from pathlib import Path


def read_glb(path: Path) -> dict:
    """{'materials': [name], 'prims': [{'material': int, 'positions': [(x,y,z)], 'indices': [int]}]} of a binary glTF."""
    return parse_glb(Path(path).read_bytes(), str(path))


def parse_glb(data: bytes, where: str = 'glb') -> dict:
    if data[:4] != b'glTF':
        raise ValueError(f'{where}: not a binary glTF (an LFS pointer?)')
    json_len = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + json_len])
    bin_start = 20 + json_len + 8
    blob = data[bin_start:]
    sizes = {5126: ('f', 4), 5123: ('H', 2), 5125: ('I', 4), 5121: ('B', 1)}
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}

    def accessor(index):
        acc = doc['accessors'][index]
        view = doc['bufferViews'][acc['bufferView']]
        fmt, size = sizes[acc['componentType']]
        n = width[acc['type']]
        start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = view.get('byteStride') or size * n
        out = []
        for i in range(acc['count']):
            out.append(struct.unpack_from('<' + fmt * n, blob, start + i * stride))
        return out

    prims = []
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            pos = accessor(prim['attributes']['POSITION'])
            idx = [v[0] for v in accessor(prim['indices'])] if 'indices' in prim else list(range(len(pos)))
            extra = {k: accessor(prim['attributes'][k]) for k in ('NORMAL', 'TEXCOORD_0') if k in prim['attributes']}
            prims.append({'material': prim.get('material', -1), 'positions': pos, 'indices': idx, **extra})
    return {'materials': [m.get('name', '') for m in doc.get('materials', [])], 'prims': prims,
            'material_docs': doc.get('materials', [])}


def triangles(model: dict):
    """Yield (material name, (p0, p1, p2)) for every triangle, in the order write_subset and merge_models count them."""
    for prim in model['prims']:
        name = model['materials'][prim['material']] if prim['material'] >= 0 else ''
        pos, idx = prim['positions'], prim['indices']
        for i in range(0, len(idx) - 2, 3):
            yield name, (pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]])


def write_subset(model: dict, members, path: Path) -> list[str]:
    """Write the subset to `path` (its file stem names the glTF node) and return the used material names."""
    data, used = subset_glb(model, members, Path(path).stem)
    Path(path).write_bytes(data)
    return used


def subset_glb(model: dict, members, name: str) -> tuple[bytes, list[str]]:
    """The binary glTF of the triangles with these ordinals (the order `triangles` yields them), as bytes, and its used
    material names. Every source vertex position, normal and UV is kept unchanged. The material list is the used
    materials in first-use order (what the Unreal import turns into slots). Vertices are not shared between triangles."""
    chosen = set(members)
    refs, n = [], 0
    for pi, prim in enumerate(model['prims']):
        for k in range(0, len(prim['indices']) - 2, 3):
            if n in chosen:
                refs.append((pi, k))
            n += 1
    blob, views, accessors, primitives = b'', [], [], []

    def add(values, fmt, ctype, kind, minmax=False):
        nonlocal blob
        data = b''.join(struct.pack('<' + fmt * len(v), *v) for v in values)
        data += b'\0' * (-len(data) % 4)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data)})
        acc = {'bufferView': len(views) - 1, 'componentType': ctype, 'count': len(values), 'type': kind}
        if minmax and values:
            acc['min'] = [min(v[i] for v in values) for i in range(3)]
            acc['max'] = [max(v[i] for v in values) for i in range(3)]
        accessors.append(acc)
        blob += data
        return len(accessors) - 1

    by_prim: dict = defaultdict(list)
    for pi, k in refs:
        by_prim[pi].append(k)
    used: list[int] = []        # source material indices in first-use order
    docs = model.get('material_docs') or [{'name': m} for m in model['materials']]
    for pi in sorted(by_prim):
        prim = model['prims'][pi]
        order = [prim['indices'][k + j] for k in by_prim[pi] for j in range(3)]
        attrs = {'POSITION': add([prim['positions'][i] for i in order], 'f', 5126, 'VEC3', True)}
        if 'NORMAL' in prim:
            attrs['NORMAL'] = add([prim['NORMAL'][i] for i in order], 'f', 5126, 'VEC3')
        if 'TEXCOORD_0' in prim:
            attrs['TEXCOORD_0'] = add([prim['TEXCOORD_0'][i] for i in order], 'f', 5126, 'VEC2')
        index = add([(i,) for i in range(len(order))], 'I', 5125, 'SCALAR')
        if prim['material'] not in used:
            used.append(prim['material'])
        primitives.append({'attributes': attrs, 'indices': index, 'material': used.index(prim['material'])})
    doc = {'asset': {'version': '2.0', 'generator': 'brinecove_split'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'mesh': 0, 'name': name}], 'meshes': [{'name': name, 'primitives': primitives}],
           'materials': [docs[m] for m in used],
           'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(blob)}]}
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(blob), 0x004E4942) + blob
    return b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body, [model['materials'][m] for m in used]
