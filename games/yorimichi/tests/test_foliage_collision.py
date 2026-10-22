"""Exercise the real native owner with ordinary Python stubs; no editor is launched."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


class Properties:
    def __init__(self, **values):
        self.values = values

    def get_editor_property(self, key):
        return self.values[key]

    def set_editor_property(self, key, value):
        self.values[key] = value


class Mesh(Properties):
    def __init__(self, mutations):
        super().__init__(body_setup=Properties(collision_trace_flag=None), static_materials=[])
        self.mutations = mutations
        self.primitives, self.convex = 0, 1
        self.lod_count = 4

    def set_num_source_models(self, count):
        self.mutations.append(('reset-lods', self, count))
        self.lod_count = count

    def get_name(self):
        return 'Tree_Test'

    def get_bounding_box(self):
        return SimpleNamespace(min=SimpleNamespace(x=0, y=0, z=0), max=SimpleNamespace(x=100, y=200, z=300))

    def get_num_lods(self):
        return self.lod_count

    def get_num_triangles(self, level):
        return 1


@pytest.fixture
def owner(monkeypatch, tmp_path):
    mutations, logs = [], []
    previous, imported = Mesh(mutations), Mesh(mutations)
    state = SimpleNamespace(previous=previous, imported=imported, mutations=mutations, logs=logs,
                            original_body=imported.values['body_setup'], fail_removal=False,
                            after_lods=lambda mesh: None, reused=False)
    data = dict(bounds=[[0, 0, 0], [1, 2, 3]], triangles=[1], screen_sizes=[1.0], materials=[],
                collision='complex', trunk_collision=[.6, 0, 0, -.25, 0, 0, 2], import_trunk_collision=False)
    manifest = tmp_path / 'foliage/Tree_Test/manifest.json'
    manifest.parent.mkdir(parents=True)
    state.write_manifest = lambda: manifest.write_text(json.dumps(data))
    state.data, state.report = data, tmp_path / 'imports/foliage/Tree_Test.json'
    state.write_manifest()
    interface = tmp_path / 'materials/foliage-interface.json'
    interface.parent.mkdir()
    interface.write_text('{}')

    def remove(mesh):
        mutations.append(('remove', mesh))
        if mesh is imported and state.fail_removal:
            return False
        mesh.primitives, mesh.convex = 0, 0
        # PostEditChange may refresh BodySetup. The owner must apply flags to this fresh object.
        mesh.values['body_setup'] = Properties(collision_trace_flag=None)
        return True

    def import_mesh(*args, **kwargs):
        mutations.append(('admission', imported))
        state.base_predicate = kwargs['reuse_validator']
        reusable = state.reused and kwargs['reuse_validator'](imported)
        if not reusable:
            kwargs['before_import']()
            mutations.append(('import', imported))
            imported.convex = 1
        return imported

    def apply_lods(mesh, *args, **kwargs):
        mutations.append(('lods', mesh))
        state.lod_predicate = kwargs['reuse_validator']
        mesh.lod_count = max(mesh.lod_count, len(data['screen_sizes']))
        state.after_lods(mesh)
        return {}

    def save(mesh, *args):
        mutations.append(('save', mesh))
        return True

    meshes = SimpleNamespace(remove_collisions=remove, get_simple_collision_count=lambda mesh: mesh.primitives,
                             get_convex_collision_count=lambda mesh: mesh.convex,
                             get_collision_complexity=lambda mesh: mesh.values['body_setup'].values['collision_trace_flag'])
    unreal = SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda path: True, load_asset=lambda path: previous,
                                          list_assets=lambda *args, **kwargs: [], save_loaded_asset=save),
        SystemLibrary=SimpleNamespace(execute_console_command=lambda *args: None),
        load_module=lambda name: None, get_editor_subsystem=lambda kind: meshes, StaticMeshEditorSubsystem=object(),
        CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex', CTF_USE_DEFAULT='default'), log=logs.append)
    for name, module in {
        'unreal': unreal, 'yori': SimpleNamespace(OUT=tmp_path, GAME=tmp_path / 'game'),
        'asset_catalog': SimpleNamespace(FOLIAGE=('Tree_Test',)),
        'mesh_import': SimpleNamespace(import_mesh=import_mesh),
        'import_foliage_lods': SimpleNamespace(apply_lods=apply_lods,
                                               crown_path=lambda crown, folder: folder + '/MI_' + crown['slot']),
        'foliage_package_repair': SimpleNamespace(require_valid_or_missing=lambda *args, **kwargs: None),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setenv('ATELIER_FOLIAGE', 'Tree_Test')
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/import_foliage.py'
    spec = importlib.util.spec_from_file_location('fixture_foliage_collision', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state.run = module.main
    return state


@pytest.mark.parametrize('enabled,complexity', [(False, 'complex'), (True, 'default')])
def test_explicit_policy_clears_or_retains_imported_ucx_on_the_final_mesh(owner, enabled, complexity):
    owner.data.update(import_trunk_collision=enabled, collision=complexity)
    owner.write_manifest()
    owner.run()
    removed = [event[1] for event in owner.mutations if event[0] == 'remove']
    assert removed == ([owner.previous] if enabled else [owner.previous, owner.imported])
    body = owner.imported.values['body_setup']
    assert (body is owner.original_body) is enabled
    assert body.values['collision_trace_flag'] == complexity
    if not enabled:
        assert owner.original_body.values['collision_trace_flag'] is None
    report = json.loads(owner.report.read_text())
    assert report['simple_collisions'] == 0 and report['convex_collisions'] == int(enabled)
    assert report['collision'] == complexity
    assert report['import_trunk_collision'] is enabled
    assert ('save', owner.imported) in owner.mutations
    assert any(line.startswith('FOLIAGE IMPORT COMPLETE Tree_Test:') for line in owner.logs)


def assert_uncertified(owner):
    assert not owner.report.exists()
    assert not any(line.startswith('FOLIAGE IMPORT COMPLETE') for line in owner.logs)
    assert ('save', owner.imported) not in owner.mutations


def test_registered_but_unloadable_package_reaches_fresh_import(owner, monkeypatch):
    monkeypatch.setattr(sys.modules['unreal'].EditorAssetLibrary, 'load_asset', lambda path: None)
    owner.run()
    assert ('import', owner.imported) in owner.mutations
    assert ('reset-lods', owner.previous, 1) not in owner.mutations
    assert ('remove', owner.imported) in owner.mutations
    assert owner.report.is_file()


def test_invalid_header_check_precedes_any_existing_asset_load(owner, monkeypatch):
    calls = []
    editor = sys.modules['unreal'].EditorAssetLibrary
    original = editor.does_asset_exist
    monkeypatch.setattr(editor, 'does_asset_exist', lambda path: (calls.append('lookup'), original(path))[1])
    monkeypatch.setitem(owner.run.__globals__, 'require_valid_or_missing', lambda *args, **kwargs: calls.append('check'))
    owner.run()
    assert calls[0] == 'check' and calls[1] == 'lookup'


def test_damage_after_preparation_refuses_without_in_editor_mutation(owner, monkeypatch):
    def refuse(*args):
        raise RuntimeError('Invalid foliage package appeared after pre-editor preparation')
    monkeypatch.setitem(owner.run.__globals__, 'require_valid_or_missing', refuse)
    with pytest.raises(RuntimeError, match='after pre-editor'):
        owner.run()
    assert owner.mutations == []
    assert_uncertified(owner)


@pytest.mark.parametrize('registered', [False, True])
def test_rebuild_applies_the_legacy_lightmap_policy(owner, monkeypatch, registered):
    monkeypatch.setattr(sys.modules['unreal'].EditorAssetLibrary, 'does_asset_exist', lambda path: registered)
    owner.imported.values.update(light_map_resolution=64, light_map_coordinate_index=1)
    owner.run()
    assert owner.imported.values['light_map_resolution'] == 4
    assert owner.imported.values['light_map_coordinate_index'] == 0


def test_failed_fresh_import_of_unloadable_package_stays_uncertified(owner, monkeypatch):
    monkeypatch.setattr(sys.modules['unreal'].EditorAssetLibrary, 'load_asset', lambda path: None)
    def fail_import(*args, **kwargs):
        raise RuntimeError('FBX import failed')
    monkeypatch.setitem(owner.run.__globals__, 'import_mesh', fail_import)
    with pytest.raises(RuntimeError, match='FBX import failed'):
        owner.run()
    assert owner.mutations == []
    assert_uncertified(owner)


def test_failed_final_collision_removal_cannot_certify_the_import(owner):
    owner.fail_removal = True
    with pytest.raises(RuntimeError, match='clear disabled trunk collision'):
        owner.run()
    assert ('remove', owner.imported) in owner.mutations
    assert ('lods', owner.imported) not in owner.mutations
    assert_uncertified(owner)


@pytest.mark.parametrize('invalid', ['missing', None, 0, 1, 'false', [], {}])
def test_missing_or_non_boolean_policy_is_rejected_before_asset_mutation(owner, invalid):
    if invalid == 'missing':
        owner.data.pop('import_trunk_collision')
    else:
        owner.data['import_trunk_collision'] = invalid
    owner.write_manifest()
    with pytest.raises((KeyError, ValueError)):
        owner.run()
    assert owner.mutations == []
    assert_uncertified(owner)


@pytest.mark.parametrize('trunk', [None, []])
def test_enabled_policy_without_authored_trunk_is_rejected_before_asset_mutation(owner, trunk):
    owner.data.update(import_trunk_collision=True, trunk_collision=trunk)
    owner.write_manifest()
    with pytest.raises(ValueError, match='trunk collision policy'):
        owner.run()
    assert owner.mutations == []
    assert_uncertified(owner)


@pytest.mark.parametrize('changed', ['primitives', 'convex', 'flag'])
def test_collision_counts_and_trace_policy_are_checked_after_lod_assembly(owner, changed):
    def alter(mesh):
        if changed == 'flag':
            mesh.values['body_setup'].values['collision_trace_flag'] = 'wrong'
        else:
            setattr(mesh, changed, 1)
    owner.after_lods = alter
    with pytest.raises(AssertionError, match='collision'):
        owner.run()
    assert ('lods', owner.imported) in owner.mutations
    assert_uncertified(owner)


@pytest.mark.parametrize('reused', [False, True])
def test_saved_package_admission_precedes_any_destructive_reset(owner, reused):
    owner.reused = reused
    owner.run()
    assert owner.mutations[0][0] == 'admission'
    resets = [event for event in owner.mutations if event[1] is owner.previous and event[0] in ('reset-lods', 'remove')]
    assert bool(resets) is not reused
    if not reused:
        assert owner.mutations.index(resets[-1]) < next(i for i,e in enumerate(owner.mutations) if e[0] == 'import')
    assert ('lods', owner.imported) in owner.mutations
    assert owner.report.is_file()


def test_reuse_hit_trims_the_previous_longer_lod_chain_before_current_assembly(owner):
    owner.reused = True
    assert owner.imported.get_num_lods() == 4
    assert len(owner.data['screen_sizes']) == 1
    owner.run()
    assert owner.imported.get_num_lods() == 1
    assert json.loads(owner.report.read_text())['triangles'] == [1]
    admission = next(i for i,event in enumerate(owner.mutations) if event[0] == 'admission')
    trim = owner.mutations.index(('reset-lods', owner.imported, 1))
    assembly = owner.mutations.index(('lods', owner.imported))
    assert admission < trim < assembly
    assert ('remove', owner.previous) not in owner.mutations


def test_enabling_authored_trunk_after_a_hull_free_saved_base_requires_raw_import(owner):
    owner.reused = True
    owner.data.update(import_trunk_collision=True, collision='default')
    owner.write_manifest()
    owner.imported.convex = 0
    owner.run()
    assert ('import', owner.imported) in owner.mutations
    assert owner.imported.convex == 1
    assert json.loads(owner.report.read_text())['convex_collisions'] == 1


def test_unchanged_enabled_trunk_keeps_the_admitted_authored_hull(owner):
    owner.reused = True
    owner.data.update(import_trunk_collision=True, collision='default')
    owner.write_manifest()
    owner.run()
    assert ('import', owner.imported) not in owner.mutations
    assert not any(event[0] == 'remove' for event in owner.mutations)
    assert owner.imported.convex == 1


def test_actual_owner_passes_one_policy_to_base_and_lod_sources(owner):
    owner.data.update(import_trunk_collision=True, collision='default')
    owner.write_manifest()
    owner.run()
    assert owner.base_predicate is owner.lod_predicate
    # Source LODs do not own the base's trunk collision and must still be reusable.
    assert owner.lod_predicate(SimpleNamespace(get_name=lambda: 'Tree_Test_LOD1'))


@pytest.mark.parametrize('crowned', [True, False])
def test_reimport_keeps_the_current_crown_material_and_retires_the_rest(owner, monkeypatch, crowned):
    folder = '/Game/Japan/FoliageLODs/Tree_Test'
    lod, crown, stale = (folder + '/Tree_Test_LOD1', folder + '/MI_Tree_Test_Crown', folder + '/Tree_Test_LOD2')
    owner.data.update(screen_sizes=[1.0, .1], triangles=[1, 1])
    if crowned:
        owner.data['crown'] = {'slot': 'Tree_Test_Crown'}
    owner.write_manifest()
    deleted = []
    editor = sys.modules['unreal'].EditorAssetLibrary
    monkeypatch.setattr(editor, 'list_assets', lambda *args, **kwargs: [p + '.' + p.rsplit('/', 1)[1] for p in (lod, crown, stale)],
                        raising=False)
    def delete(asset):
        deleted.append(asset.split('.')[0])
        owner.mutations.append(('delete', asset.split('.')[0]))
        return True
    monkeypatch.setattr(editor, 'delete_asset', delete, raising=False)
    monkeypatch.setattr(editor, 'find_package_referencers_for_asset', lambda asset, load: [], raising=False)
    owner.run()
    assert deleted == ([stale] if crowned else [crown, stale])
    # Retirement follows the validated, saved replacement.
    assert owner.mutations.index(('save', owner.imported)) < owner.mutations.index(('delete', stale))


def test_failed_replacement_retires_nothing(owner, monkeypatch):
    folder = '/Game/Japan/FoliageLODs/Tree_Test'
    deleted = []
    editor = sys.modules['unreal'].EditorAssetLibrary
    monkeypatch.setattr(editor, 'list_assets', lambda *args, **kwargs: [folder + '/MI_Tree_Test_Crown.MI_Tree_Test_Crown'],
                        raising=False)
    monkeypatch.setattr(editor, 'delete_asset', lambda asset: deleted.append(asset) or True, raising=False)
    owner.data['triangles'] = [7]   # the replacement fails validation
    owner.write_manifest()
    with pytest.raises(AssertionError):
        owner.run()
    assert deleted == []


def test_obsolete_package_still_used_elsewhere_is_kept(owner, monkeypatch):
    folder = '/Game/Japan/FoliageLODs/Tree_Test'
    deleted = []
    editor = sys.modules['unreal'].EditorAssetLibrary
    monkeypatch.setattr(editor, 'list_assets', lambda *args, **kwargs: [folder + '/MI_Tree_Test_Crown.MI_Tree_Test_Crown'],
                        raising=False)
    monkeypatch.setattr(editor, 'delete_asset', lambda asset: deleted.append(asset) or True, raising=False)
    monkeypatch.setattr(editor, 'find_package_referencers_for_asset', lambda asset, load: ['/Game/Japan/Other'],
                        raising=False)
    with pytest.raises(RuntimeError, match='still referenced'):
        owner.run()
    assert deleted == []
