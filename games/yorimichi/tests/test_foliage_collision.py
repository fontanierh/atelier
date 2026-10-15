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

    def set_num_source_models(self, count):
        self.mutations.append(('reset-lods', self, count))

    def get_name(self):
        return 'Tree_Test'

    def get_bounding_box(self):
        return SimpleNamespace(min=SimpleNamespace(x=0, y=0, z=0), max=SimpleNamespace(x=100, y=200, z=300))

    def get_num_lods(self):
        return 1

    def get_num_triangles(self, level):
        return 1


@pytest.fixture
def owner(monkeypatch, tmp_path):
    mutations, logs = [], []
    previous, imported = Mesh(mutations), Mesh(mutations)
    state = SimpleNamespace(previous=previous, imported=imported, mutations=mutations, logs=logs,
                            original_body=imported.values['body_setup'], fail_removal=False,
                            after_lods=lambda mesh: None)
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
        mutations.append(('import', imported))
        return imported

    def apply_lods(mesh, *args, **kwargs):
        mutations.append(('lods', mesh))
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
        'unreal': unreal, 'yori': SimpleNamespace(OUT=tmp_path),
        'asset_catalog': SimpleNamespace(FOLIAGE=('Tree_Test',)),
        'mesh_import': SimpleNamespace(import_mesh=import_mesh),
        'import_foliage_lods': SimpleNamespace(apply_lods=apply_lods),
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
