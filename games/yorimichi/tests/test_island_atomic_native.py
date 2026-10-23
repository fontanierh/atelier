"""Actual native receiver owns miss preparation, current finishing and saved membership."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


def functions():
    tree = ast.parse((GAME / 'unreal/Scripts/import_island_atomic.py').read_text())
    return ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[])


def fixture(*, hit, hulls=0, cooked=True, save=True, precision=False):
    state = dict(removes=0, imports=0, saves=0, hulls=hulls, callback_hulls=None)
    precision_state = {'value': precision}
    settings = SimpleNamespace(get_editor_property=lambda key: precision_state['value'],
        set_editor_property=lambda key, value: precision_state.update(value=value))
    body = SimpleNamespace(get_editor_property=lambda key: 'complex')
    materials = {key: SimpleNamespace(get_path_name=lambda key=key: '/Game/Material/' + key)
                 for key in ('Ground', 'Coast')}
    # UE may compact the unused Coast slot on this one child.
    slot = SimpleNamespace(get_editor_property=lambda key: 'Ground')
    mesh = SimpleNamespace(static_materials=[slot], get_num_triangles=lambda lod: 12,
        get_num_lods=lambda: 1, get_material=lambda i: materials['Ground'],
        get_editor_property=lambda key: body, get_path_name=lambda: '/Game/IslandChild',
        get_bounding_box=lambda: SimpleNamespace(min=SimpleNamespace(x=0., y=-100., z=0.),
                                                max=SimpleNamespace(x=100., y=0., z=0.)))
    def remove(mesh): state['removes'] += 1; state['hulls'] = 0; return True
    editor = SimpleNamespace(get_simple_collision_count=lambda mesh: 0,
        get_convex_collision_count=lambda mesh: state['hulls'], remove_collisions=remove,
        get_lod_build_settings=lambda mesh, lod: settings, set_lod_build_settings=lambda *a: None, get_num_uv_channels=lambda mesh, lod: 1)
    def save_mesh(mesh, dirty_only):
        assert dirty_only is True; state['saves'] += 1; return save
    library = SimpleNamespace(list_assets=lambda *a, **kw: [], load_asset=lambda key: materials[key] if key in materials else mesh,
                              does_asset_exist=lambda path: True, save_loaded_asset=save_mesh)
    unreal = SimpleNamespace(EditorAssetLibrary=library, load_module=lambda module: None,
        StaticMeshEditorSubsystem='editor', get_editor_subsystem=lambda subsystem: editor,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        CitySurfaceValidation=SimpleNamespace(validate_collision=lambda *a: cooked),
        SystemLibrary=SimpleNamespace(execute_console_command=lambda *a: None, collect_garbage=lambda: None),
        log=lambda msg: None)
    groups = dict(Terrain=dict(slots=['Ground', 'Coast'], source_triangles=12,
        pieces=[dict(name='Terrain_cell_0_0', path='piece.fbx', triangles=12, used_slots=['Ground'],
                     uv_channels=['UVMap'], asset='/Game/IslandChild', min=[0., 0., 0.], max=[1., 1., 0.])]))
    def import_mesh(*a, **kw):
        state['imports'] += 1
        if not hit:
            kw['before_import'](); state['callback_hulls'] = state['hulls']
        return mesh
    scope = dict(Path=Path, unreal=unreal, read=lambda root: groups, DESTINATION='/Game/Island',
                 material_paths=lambda parent, slots: {slot: slot for slot in slots},
                 native_bounds=lambda row: ([0., -100., 0.], [100., 0., 0.]))
    exec(compile(functions(), '<actual-island-receiver>', 'exec'), scope)
    scope['owned_packages'] = lambda paths: set(paths)
    scope['import_mesh'] = import_mesh
    scope['precision_state'] = precision_state
    return scope, state


def test_validated_saved_hit_preserves_admission_and_compacted_material_slots():
    scope, state = fixture(hit=True)
    result = scope['receive'](Path('output'))
    assert state == dict(removes=0, imports=1, saves=1, hulls=0, callback_hulls=None)
    assert result['groups']['Terrain'][0]['triangles'] == 12
    assert len(result['groups']['Terrain'][0]['materials']) == 1


def test_actual_miss_resets_old_shapes_before_source_import_only():
    scope, state = fixture(hit=False, hulls=3)
    scope['receive'](Path('output'))
    assert state['callback_hulls'] == 0 and state['removes'] == 1 and state['saves'] == 1


def test_hit_still_receives_current_zero_shape_finishing():
    scope, state = fixture(hit=True, hulls=2)
    scope['receive'](Path('output'))
    assert state['callback_hulls'] is None and state['removes'] == 1


@pytest.mark.parametrize('setting', ['cooked', 'save'])
def test_failed_native_validation_or_save_never_returns_completed_receiving(setting):
    scope, state = fixture(hit=True, **{setting: False})
    with pytest.raises(AssertionError): scope['receive'](Path('output'))
    assert state['saves'] == (1 if setting == 'save' else 0)


def test_map_and_runtime_migration_precede_one_complete_retirement_preflight(tmp_path):
    scope, _ = fixture(hit=True)
    groups = dict(Terrain=[dict(asset='/Game/Current/Terrain')], Sea=[dict(asset='/Game/Current/Sea')])
    received = dict(out=tmp_path, previous={'/Game/Island/Terrain_cell_9_9'}, groups=groups)
    expected = {key: [row['asset'] for row in rows] for key, rows in groups.items()}
    plans = []
    def refuse(editor, replacements):
        plans.append(replacements)
        raise ValueError('Foreign reference preserves the entire old owner')
    scope['native_membership'] = SimpleNamespace(retire_replaced=refuse)
    with pytest.raises(ValueError, match='migrated'):
        scope['retire_after_map'](received, runtime_members={'Terrain': ['/Game/Japan/Terrain']})
    assert not plans
    with pytest.raises(ValueError, match='Foreign reference'):
        scope['retire_after_map'](received, runtime_members=expected)
    assert plans == [{'/Game/Japan/Terrain': ['/Game/Current/Terrain'],
                     '/Game/Japan/Assets/Sea': ['/Game/Current/Sea'],
                     '/Game/Island/Terrain_cell_9_9': ['/Game/Current/Terrain', '/Game/Current/Sea']}]
    assert not (tmp_path / 'terrain/island-import-report.json').exists()


def test_warm_hit_restores_original_legacy_half_precision_uv_policy():
    scope, state = fixture(hit=True, precision=True)
    scope['receive'](Path('output'))
    assert scope['precision_state']['value'] is False
