"""Run the actual native finishing loop with controlled engine readbacks and failures."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import hashlib
import json

import pytest

SCRIPT = Path(__file__).parents[1] / 'unreal/Scripts/import_skatepark.py'


def function(name, namespace):
    tree = ast.parse(SCRIPT.read_text())
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCRIPT), 'exec'), namespace)
    return namespace[name]


class Properties:
    def __init__(self, **properties):
        self.properties = properties
        self.writes = []

    def get_editor_property(self, name):
        return self.properties[name]

    def set_editor_property(self, name, value):
        self.writes.append(name)
        self.properties[name] = value


def finishing(damage=None):
    tree = ast.parse(SCRIPT.read_text())
    loop = next(node for node in tree.body if isinstance(node, ast.For)
                and isinstance(node.target, ast.Name) and node.target.id == 'entry')
    code = compile(ast.Module(body=[loop], type_ignores=[]), str(SCRIPT), 'exec')
    names = ['SM_SkatePier_Piece' + c * 16 for c in ('a', 'b')]
    surface = object()
    meshes, imports, saves, bounds, report = {}, [], [], [], {'park': {}}
    for name in names:
        slot = Properties(imported_material_slot_name='Pier_concrete', material_interface=surface)
        body = Properties(collision_trace_flag='complex')
        mesh = Properties(static_materials=[slot], allow_cpu_access=True, body_setup=body,
                          complex_collision_mesh=None, lod_for_collision=0)
        mesh.get_num_triangles = lambda lod: 2
        meshes[name] = mesh
    if damage == 'stale-settings':
        meshes[names[0]].properties.update(allow_cpu_access=False, complex_collision_mesh=object(), lod_for_collision=2)
        meshes[names[0]].properties['body_setup'].properties['collision_trace_flag'] = 'default'
    elif damage == 'triangles':
        meshes[names[0]].get_num_triangles = lambda lod: 3
    elif damage == 'materials':
        meshes[names[0]].properties['static_materials'][0].properties['imported_material_slot_name'] = 'Foreign'

    def load(path, root, name, **options):
        imports.append((path.name, root, options))
        return meshes[name]

    def save(mesh):
        saves.append(mesh)
        return damage != 'save'

    def axes(name, mesh, expected):
        bounds.append(name)
        assert damage != 'bounds', 'native bounds differ'
        return [0, 0, 0], [100, 100, 100]

    namespace = dict(park={'meshes': [dict(name=name, asset='/Game/SkatePark/' + name, blocks=True) for name in names]},
                     receive=load, current_geometry=lambda mesh: mesh.get_num_triangles(0)==2, OUT=Path('/unused-build-root'), surfaces={'Pier_concrete': surface},
                     E=SimpleNamespace(save_loaded_asset=save), pieces=SimpleNamespace(TRIANGLE_LIMIT=32768),
                     unreal=SimpleNamespace(CitySurfaceValidation=SimpleNamespace(validate_collision=lambda *args: damage != 'cooked-collision'), CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex',
                                                                              CTF_USE_SIMPLE_AS_COMPLEX='simple')),
                     build={'material_slots': {name: ['Pier_concrete'] for name in names},
                            'meshes': {name: {'triangles': 2} for name in names}},
                     check_axes=axes, report=report)
    return code, namespace, meshes, imports, saves, bounds, report


def test_warm_native_pieces_keep_current_bindings_and_never_import_the_retired_whole_parent():
    code, namespace, meshes, imports, saves, bounds, report = finishing()
    exec(code, namespace)
    assert set(report['park']) == set(meshes) == set(bounds)
    assert len(saves) == len(meshes)
    assert all(options == {'fresh_slots': True} for _, _, options in imports)
    assert all(name != 'SM_SkatePier.fbx' for name, _, _ in imports)
    assert all(not mesh.writes and not mesh.properties['body_setup'].writes for mesh in meshes.values())


def test_current_piece_collision_is_its_own_lod_zero_and_cooked_cpu_access_is_restored():
    code, namespace, meshes, *_ = finishing('stale-settings')
    exec(code, namespace)
    mesh = next(iter(meshes.values()))
    assert mesh.get_editor_property('complex_collision_mesh') is None
    assert mesh.get_editor_property('lod_for_collision') == 0
    assert mesh.get_editor_property('allow_cpu_access') is True
    assert mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag') == 'complex'


@pytest.mark.parametrize('damage', ['triangles', 'materials', 'save', 'bounds', 'cooked-collision'])
def test_native_piece_refusal_stops_before_the_next_import_or_a_complete_report(damage):
    code, namespace, _, imports, _, _, report = finishing(damage)
    with pytest.raises(AssertionError):
        exec(code, namespace)
    assert len(imports) == 1
    assert report['park'] == {}


def test_failed_warm_texture_save_refuses_even_when_old_package_exists(tmp_path):
    textures = tmp_path / 'textures'; textures.mkdir(); file = textures / 'concrete-albedo.png'
    file.write_bytes(b'current texture source')
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    texture = Properties()
    namespace = dict(OUT=tmp_path, owned_textures=set(), sha=sha,
                     E=SimpleNamespace(load_asset=lambda path: texture, does_asset_exist=lambda path: True,
                                       get_metadata_tag=lambda *args: sha(file), save_loaded_asset=lambda value: False),
                     unreal=SimpleNamespace(TextureCompressionSettings=SimpleNamespace(TC_NORMALMAP=1, TC_DEFAULT=2)))
    with pytest.raises(AssertionError, match='texture save failed'):
        function('texture', namespace)(file.name, 'T_Pier_concrete_albedo', 'albedo')


def test_failed_warm_material_save_refuses_even_when_old_package_exists(tmp_path):
    textures = tmp_path / 'textures'; textures.mkdir()
    (textures / 'textures.json').write_text(json.dumps({'steel': {'maps': {'albedo': 'steel.png'}, 'metallic': 1.}}))
    editing = MagicMock(); editing.connect_material_expressions.return_value = True
    editing.connect_material_property.return_value = True
    namespace = dict(OUT=tmp_path, json=json, unreal=MagicMock(), MEL=editing,
                     texture=lambda *args: object(),
                     E=SimpleNamespace(load_asset=lambda path: MagicMock(), does_asset_exist=lambda path: True,
                                       save_loaded_asset=lambda value: False))
    with pytest.raises(AssertionError, match='material save failed'):
        function('materials', namespace)()
