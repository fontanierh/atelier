"""The Belmonte LOD mesh facts: a donor level file's triangles count per node instance, as the donor report and the
saved chain do (tools/migrate/recover.py glb_instanced)."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import recover  # noqa: E402


def glb(path: Path, nodes_for_mesh: list[int], triangles: int) -> Path:
    """A binary glTF with one mesh of `triangles` triangles and a node for each entry of nodes_for_mesh."""
    blob = struct.pack('<' + 'I' * (3 * triangles), *range(3 * triangles))
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': []}],
           'nodes': [{'mesh': m} for m in nodes_for_mesh], 'materials': [{'name': 'M_BT_Test'}],
           'meshes': [{'primitives': [{'attributes': {}, 'indices': 0, 'material': 0}]}],
           'accessors': [{'bufferView': 0, 'componentType': 5125, 'count': 3 * triangles, 'type': 'SCALAR'}],
           'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(blob)}],
           'buffers': [{'byteLength': len(blob)}]}
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(blob), 0x004E4942) + blob
    path.write_bytes(b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body)
    return path


def test_a_mesh_placed_by_several_nodes_counts_once_per_placement(tmp_path):
    triangles, materials = recover.glb_instanced(glb(tmp_path / 'a.glb', [0, 0, 0], 4))
    assert triangles == 12 and materials == ['M_BT_Test']


def test_a_mesh_placed_once_counts_once(tmp_path):
    assert recover.glb_instanced(glb(tmp_path / 'b.glb', [0], 5))[0] == 5
