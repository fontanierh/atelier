"""Compare every exported native geometry child, including normals, UVs, colours and material indices."""
import array
import hashlib
import json
from pathlib import Path
import struct
import sys
from io_scene_fbx import parse_fbx

folder = Path(sys.argv[sys.argv.index('--') + 1])
def canonical(node):
    def prop(value):
        if isinstance(value, bytes): return ['bytes', value.hex()]
        if isinstance(value, array.array): return [value.typecode, value.tobytes().hex()]
        if isinstance(value, float): return ['float64', struct.pack('<d', value).hex()]
        return value
    return [node.id.decode(), list(node.props_type), [prop(p) for p in node.props],
            [canonical(child) for child in node.elems]]
def geometry(file):
    root, _ = parse_fbx.parse(str(file))
    objects = next(node for node in root.elems if node.id == b'Objects')
    meshes = [node for node in objects.elems if node.id == b'Geometry']
    assert len(meshes) == 1
    children = meshes[0].elems
    assert 1 <= sum(n.id == b'LayerElementUV' for n in children) <= 8
    assert any(n.id == b'LayerElementColor' for n in children)
    return [canonical(node) for node in children]
before, after = geometry(folder/'before.fbx'), geometry(folder/'after.fbx')
assert before == after, 'Native geometry/corner/material data changed'
(folder/'geometry-result.json').write_text(json.dumps(dict(exact=True,
    uv_channels=sum(node[0] == 'LayerElementUV' for node in after),
    sha256=hashlib.sha256(json.dumps(after, separators=(',', ':')).encode()).hexdigest())))
print('INTERCHANGE GEOMETRY EXACT', flush=True)
