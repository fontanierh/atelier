"""Exercise the real LOD owner with package bytes and dirtying setters modelled."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def owner(monkeypatch, tmp_path):
    material = object()
    calls = []

    class Mesh:
        def __init__(self, name):
            self.name, self.material, self.dirty = name, material, False
            self.file = tmp_path / (name + '.uasset')
            self.file.write_bytes(b'unchanged package')
            self.saves, self.fail_save, self.reject_binding = 0, False, False

        def get_name(self):
            return self.name

        def get_path_name(self):
            return '/Game/Owned/' + self.name

        def get_bounding_box(self):
            return SimpleNamespace(min=SimpleNamespace(x=0, y=0, z=0),
                                   max=SimpleNamespace(x=100, y=100, z=100))

        def get_editor_property(self, key):
            assert key == 'static_materials'
            return [SimpleNamespace(get_editor_property=lambda key: 'Bark')]

        def get_material(self, index):
            return self.material

        def set_material(self, index, value):
            calls.append(('material', self.name))
            self.dirty = True  # UE setters dirty even if the value is identical.
            if not self.reject_binding:
                self.material = value

    target, source = Mesh('Tree'), Mesh('Tree_LOD1')

    def save(mesh, only_if_is_dirty=True):
        calls.append(('save', mesh.name, only_if_is_dirty))
        if mesh.fail_save:
            return False
        if mesh.dirty or not only_if_is_dirty:
            mesh.saves += 1
            mesh.file.write_bytes(b'saved package ' + str(mesh.saves).encode())
            mesh.dirty = False
        return True

    def assemble(mesh, level, donor, source_level, reuse_slots):
        calls.append(('assemble', level))
        mesh.dirty = True
        return level

    editor = SimpleNamespace(load_asset=lambda path: material, save_loaded_asset=save)
    meshes = SimpleNamespace(get_number_verts=lambda mesh, level: 10,
                             set_lod_from_static_mesh=assemble,
                             set_lod_screen_sizes=lambda *args: True)
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(EditorAssetLibrary=editor))
    monkeypatch.setitem(sys.modules, 'yori', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'foliage_material', SimpleNamespace(supports_lod_blend=lambda _: True))
    monkeypatch.setitem(sys.modules, 'mesh_import', SimpleNamespace(import_mesh=lambda *args, **kwargs: source))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    path = Path(__file__).resolve().parents[1] / 'unreal/Scripts/import_foliage_lods.py'
    spec = importlib.util.spec_from_file_location('lod_package_owner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    validations = []
    monkeypatch.setattr(module, 'verify_lods', lambda *args, **kwargs: validations.append(True) or {'valid': True})

    def run():
        return module.apply_lods(target, {'screen_sizes': [1., .1]}, tmp_path, meshes,
                                 seed=tmp_path / 'seed.fbx', folder='/Game/Owned')

    return SimpleNamespace(run=run, source=source, target=target, calls=calls, material=material,
                           validations=validations, editor=editor)


def test_reused_lod_source_keeps_package_bytes_on_repeated_owner_finishing(owner):
    before = owner.source.file.read_bytes()
    for _ in range(2):
        assert owner.run() == {'valid': True}
    assert owner.source.file.read_bytes() == before
    assert owner.source.saves == 0
    assert not any(call[0] == 'material' for call in owner.calls)
    assert owner.calls.count(('assemble', 1)) == 2
    assert len(owner.validations) == 2
    assert owner.target.saves == 2  # Required target LOD assembly still runs.


def test_changed_material_is_applied_and_saved_once(owner):
    owner.source.material = object()
    owner.run()
    assert owner.source.material is owner.material
    assert owner.source.saves == 1
    changed = owner.source.file.read_bytes()
    owner.run()
    assert owner.source.file.read_bytes() == changed
    assert owner.source.saves == 1


def test_already_dirty_source_is_saved_even_with_unchanged_material(owner):
    owner.source.dirty = True
    owner.run()
    assert owner.source.saves == 1


def test_failed_source_save_refuses_target_assembly(owner):
    owner.source.fail_save = True
    with pytest.raises(RuntimeError, match='Could not save owned LOD'):
        owner.run()
    assert not any(call[0] == 'assemble' for call in owner.calls)
    assert not owner.validations


def test_failed_material_binding_cannot_be_certified(owner):
    owner.source.material, owner.source.reject_binding = object(), True
    with pytest.raises(RuntimeError, match='material binding did not persist'):
        owner.run()
    assert owner.source.saves == 0
    assert not owner.validations


def test_missing_current_material_cannot_be_certified(owner):
    owner.editor.load_asset = lambda _: None
    with pytest.raises(RuntimeError, match='LOD material missing'):
        owner.run()
    assert owner.source.saves == 0
    assert not owner.validations
