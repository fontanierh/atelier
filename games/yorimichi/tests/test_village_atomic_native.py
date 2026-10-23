"""Original Village material graphs and native simple/complex roles survive the split."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]
SCRIPT = GAME / 'unreal/Scripts/import_village_atomic.py'


def native(*, hit=True, hulls=0, expected=0, ground=False, save=True):
    state = dict(hulls=hulls, resets=0, raw=0, saves=0, trace='simple', cooked_policy=None)
    material = object()
    settings = SimpleNamespace(get_editor_property=lambda name: True)
    def set_body(key, value): state['trace'] = value
    body = SimpleNamespace(get_editor_property=lambda name: state['trace'], set_editor_property=set_body)
    slot = SimpleNamespace(get_editor_property=lambda name: 'VillagePalette')
    key = 'Village_Ground' if ground else 'Village_Planting'
    mesh = SimpleNamespace(get_path_name=lambda: '/Game/Atomic/' + key, get_num_triangles=lambda lod: 12,
        get_num_lods=lambda: 1, static_materials=[slot], get_material=lambda i: material,
        get_editor_property=lambda prop: body,
        get_bounding_box=lambda: SimpleNamespace(min=SimpleNamespace(x=0., y=0., z=0.), max=SimpleNamespace(x=1., y=1., z=1.)))
    def remove(mesh): state['resets'] += 1; state['hulls'] = 0; return True
    editor = SimpleNamespace(get_simple_collision_count=lambda mesh: 0, get_convex_collision_count=lambda mesh: state['hulls'],
        remove_collisions=remove, get_lod_build_settings=lambda *a: settings, get_num_uv_channels=lambda *a: 1)
    def save_mesh(mesh, dirty): assert dirty; state['saves'] += 1; return save
    library = SimpleNamespace(list_assets=lambda *a, **kw: [], load_asset=lambda path: material if path == 'material' else mesh,
        does_asset_exist=lambda path: True, save_loaded_asset=save_mesh)
    def cooked(mesh, triangles, source_policy): state['cooked_policy'] = source_policy; return True
    unreal = SimpleNamespace(EditorAssetLibrary=library, load_module=lambda *a: None,
        StaticMeshEditorSubsystem='editor', get_editor_subsystem=lambda *a: editor,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_SIMPLE_AND_COMPLEX='simple', CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        CitySurfaceValidation=SimpleNamespace(validate_collision=cooked), log=lambda *a: None,
        SystemLibrary=SimpleNamespace(execute_console_command=lambda *a: None, collect_garbage=lambda: None))
    row = dict(name=key, triangles=12, collision_hulls=expected, uv_channels=['UVMap'])
    groups = {key: dict(collision='complex_as_simple' if ground else 'simple_and_complex', source_triangles=12, pieces=[row])}
    def import_mesh(*a, **kw):
        if not hit or not kw['reuse_validator'](mesh):
            kw['before_import'](); state['raw'] += 1; state['hulls'] = expected
        return mesh
    scope = dict(Path=Path, unreal=unreal, read=lambda root: groups, MATERIAL='material', DESTINATION='/Game/Atomic',
        import_mesh=import_mesh, collision_matches=lambda *a: state['hulls'] == expected,
        native_bounds=lambda row: ([0., 0., 0.], [1., 1., 1.]))
    tree = ast.parse(SCRIPT.read_text())
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]), str(SCRIPT), 'exec'), scope)
    scope['inventory'] = lambda paths: set(paths)
    return scope, state


def test_zero_hull_planting_hit_keeps_original_nonblocking_simple_query_role():
    scope, state = native()
    scope['receive'](Path('output'))
    assert state == dict(hulls=0, resets=0, raw=0, saves=1, trace='simple', cooked_policy=True)


def test_ground_hit_keeps_complex_surface_and_does_not_reimport():
    scope, state = native(ground=True)
    scope['receive'](Path('output'))
    assert state['trace'] == 'complex' and state['cooked_policy'] is False and not state['raw']


def test_stale_saved_hulls_force_actual_miss_reset_before_import():
    scope, state = native(hulls=3, expected=2)
    scope['receive'](Path('output'))
    assert state['resets'] == state['raw'] == 1 and state['hulls'] == 2


def test_false_current_save_refuses_receiving_completion():
    scope, state = native(save=False)
    with pytest.raises(AssertionError, match='native save failed'): scope['receive'](Path('output'))


def test_original_material_and_resident_graphs_change_only_checked_save_result():
    old = ast.parse((GAME / 'tests/fixtures/village-native-predecessor-283329c07.txt').read_text())
    current = ast.parse((GAME / 'unreal/Scripts/import_village.py').read_text())
    for key in ('material', 'resident_material'):
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == key)
        b = next(n for n in current.body if isinstance(n, ast.FunctionDef) and n.name == key)
        for index, node in enumerate(b.body):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Call) and isinstance(node.test.func, ast.Attribute) and node.test.func.attr == 'save_loaded_asset':
                b.body[index] = ast.Expr(value=node.test)
        if key == 'resident_material': b.body.pop()  # New checked owner exposes its successfully saved material.
        assert ast.dump(a) == ast.dump(b), key


def test_village_owner_never_recreates_combined_island_terrain():
    tree = ast.parse((GAME / 'unreal/Scripts/import_village.py').read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    assert 'terrain.fbx' not in ast.unparse(main) and '/Game/Japan/Terrain' not in ast.unparse(main)
    assert 'receive(ROOT)' in ast.unparse(main) and 'retire(received, runtime_members=members)' in ast.unparse(main)
