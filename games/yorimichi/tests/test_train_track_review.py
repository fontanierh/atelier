"""Diagnostics consume the strict assembled railway library without reconstructing source geometry."""
import ast
import json
from pathlib import Path
import struct
import sys

import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
from train import track_review_source as S  # noqa: E402


def library(tmp_path):
    from atelier import export_assembly
    from atelier.export_manifest import publish_receipt
    from atelier.gltf import glb_pack
    key = 'SM_TK_Sleeper_LOD0'
    vertices = struct.pack('<9f', 0., 0., 0., 1., 0., 0., 0., 1., 0.)
    normals = struct.pack('<9f', 0., 0., 1., 0., 0., 1., 0., 0., 1.)
    binary = vertices + normals + struct.pack('<3H', 0, 1, 2)
    doc = dict(asset=dict(version='2.0'), scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, NORMAL=1), indices=2, material=0)])],
        materials=[dict(name='Wood')], buffers=[dict(byteLength=len(binary))],
        bufferViews=[dict(buffer=0, byteOffset=0, byteLength=36), dict(buffer=0, byteOffset=36, byteLength=36),
                     dict(buffer=0, byteOffset=72, byteLength=6)],
        accessors=[dict(bufferView=0, componentType=5126, count=3, type='VEC3'),
                   dict(bufferView=1, componentType=5126, count=3, type='VEC3'),
                   dict(bufferView=2, componentType=5123, count=3, type='SCALAR')])
    root = tmp_path / 'belmonte-track'; product = tmp_path / 'export'; product.mkdir()
    (product / (key + '.glb')).write_bytes(glb_pack(doc, binary))
    publish_receipt(product, key=key, primary=key + '.glb', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]])
    export_assembly.assemble([export_assembly.Item(key, product)], root / 'atomic/meshes')
    path = root / 'atomic/track.json'
    path.write_text(json.dumps(dict(meshes=dict(SM_TK_Sleeper=dict(lods=['atomic/meshes/' + key + '.glb'])))))
    return root, path


def test_reader_accepts_exact_current_assembly_and_rejects_legacy_alias(tmp_path):
    root, path = library(tmp_path)
    folder, doc = S.read(path)
    assert folder == root and doc['meshes']['SM_TK_Sleeper']['lods'] == ['atomic/meshes/SM_TK_Sleeper_LOD0.glb']
    legacy = root / 'track.json'; legacy.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match='atomic'): S.read(legacy)
    value = json.loads(path.read_text()); value['meshes']['SM_TK_Sleeper']['lods'][0] = '../unowned.glb'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Escaping'): S.read(path)


def test_reader_refuses_missing_corrupt_and_foreign_current_primaries(tmp_path):
    root, path = library(tmp_path)
    primary = root / 'atomic/meshes/SM_TK_Sleeper_LOD0.glb'; original = primary.read_bytes()
    primary.write_bytes(original + b'changed')
    with pytest.raises(ValueError, match='Changed'): S.read(path)
    primary.write_bytes(original)
    (primary.parent / 'foreign.glb').write_bytes(b'foreign')
    with pytest.raises(ValueError, match='Foreign'): S.read(path)


def test_every_published_piece_origin_and_grouped_instance_frame_is_retained():
    doc = dict(chunks=[dict(name='Chunk', origin=[1, 2, 3])], banks=[dict(name='Bank', origin=[4, 5, 6])],
        tunnels=[dict(lining=[dict(name='Lining', origin=[7, 8, 9])])],
        viaducts=[dict(pieces=[dict(name='Viaduct', origin=[10, 11, 12])])],
        station=dict(pieces=[dict(name='Station', origin=[13, 14, 15])]),
        overbridge=dict(name='Bridge', origin=[16, 17, 18]),
        instances=dict(Sleeper={'chunk': [[1, 2, 3, 45, -1]]}, Buffer=[[4, 5, 6, 90, 1]]))
    assert S.origins(doc) == dict(Chunk=[1, 2, 3], Bank=[4, 5, 6], Lining=[7, 8, 9],
                                 Viaduct=[10, 11, 12], Station=[13, 14, 15], Bridge=[16, 17, 18])
    assert S.instances(doc, 'Sleeper') == [[1, 2, 3, 45, -1]]
    assert S.instances(doc, 'Buffer') == [[4, 5, 6, 90, 1]]


@pytest.mark.parametrize('script', ['track_render.py', 'station_render.py'])
def test_review_consumers_do_not_call_legacy_geometry_constructors_or_exporters(script):
    tree = ast.parse((GAME / 'world/train' / script).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not [node for node in calls if isinstance(node.func, ast.Attribute)
                and node.func.attr in ('layout', 'to_object', 'materials', 'export_glb', 'merged')]
    assert any(isinstance(node.func, ast.Name) and node.func.id == 'Library' for node in calls)


def test_diagnostic_instances_share_imported_data_and_apply_published_frame(tmp_path, monkeypatch):
    import math
    import numpy as np
    from types import SimpleNamespace
    root, source = library(tmp_path)
    objects = []; imported = []
    class Object:
        def __init__(self, label, data=None):
            self.name = label; self.data = data; self.type = 'MESH' if data is not None else 'EMPTY'
            self.parent = None; self.hide_render = False; self.hidden = False
        def copy(self): return Object(self.name + '_copy', self.data)
        def hide_set(self, hidden): self.hidden = hidden
    class Objects:
        def __iter__(self): return iter(objects)
        def new(self, label, data):
            obj = Object(label, data); objects.append(obj); return obj
        def link(self, obj):
            if obj not in objects: objects.append(obj)
    collection = Objects()
    def import_glb(filepath):
        imported.append(filepath); collection.new('Source', object())
    class Matrix:
        @staticmethod
        def Translation(position):
            matrix = np.eye(4); matrix[:3, 3] = position; return matrix
        @staticmethod
        def Rotation(angle, width, axis):
            c, s = math.cos(angle), math.sin(angle)
            return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        @staticmethod
        def Diagonal(values): return np.diag(values)
    monkeypatch.setitem(sys.modules, 'bpy', SimpleNamespace(data=SimpleNamespace(objects=collection),
        context=SimpleNamespace(scene=SimpleNamespace(collection=SimpleNamespace(objects=collection))),
        ops=SimpleNamespace(import_scene=SimpleNamespace(gltf=import_glb))))
    monkeypatch.setitem(sys.modules, 'mathutils', SimpleNamespace(Matrix=Matrix))
    reader = S.Library(source)
    first = reader.place('SM_TK_Sleeper', [[2, 3, 4, 90, -1]])
    second = reader.place('SM_TK_Sleeper', [[5, 6, 7, 0, 2]])
    assert len(imported) == 1 and len(first) == len(second) == 1
    assert first[0].data is second[0].data is reader.templates['SM_TK_Sleeper'][0].data
    assert reader.templates['SM_TK_Sleeper'][0].hidden and reader.templates['SM_TK_Sleeper'][0].hide_render
    assert not first[0].hidden and not first[0].hide_render
    assert np.array_equal(first[0].parent.matrix_world[:3, 3], [2, 3, 4])
    assert np.array_equal(second[0].parent.matrix_world @ [0, 1, 0, 1], [5, 8, 7, 1])
    assert np.array_equal(first[0].parent.matrix_world @ [0, 1, 0, 1], [3, 3, 4, 1])
