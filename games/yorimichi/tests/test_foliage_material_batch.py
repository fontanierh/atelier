"""Material replacement preserves the prepared mesh's complete slot layout."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest


class Slot:
    def __init__(self, material, name):
        self.values = dict(material_interface=material, material_slot_name=name,
                           imported_material_slot_name='Imported_' + name,
                           uv_channel_data={'densities': [1., 2., 3., 4.]})

    def copy(self):
        return deepcopy(self)

    def set_editor_property(self, key, value):
        self.values[key] = value


class Mesh:
    def __init__(self, slots):
        self.slots = slots
        self.updates = 0

    def get_editor_property(self, key):
        assert key == 'static_materials'
        return self.slots

    def set_editor_property(self, key, value):
        assert key == 'static_materials'
        self.slots = value
        self.updates += 1

    def get_material(self, index):
        return self.slots[index].values['material_interface']


def binding():
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/build_foliage_system.py'
    function = next(node for node in ast.parse(script.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'bind_variant_materials')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
    return namespace['bind_variant_materials']


def test_many_bindings_preserve_metadata_and_canopy_without_per_slot_mesh_updates():
    originals = [Slot('old_' + str(i), 'slot_' + str(i)) for i in range(80)]
    mesh = Mesh(originals)
    before = deepcopy([slot.values for slot in originals])
    replacements = ['new_' + str(i) for i in range(78)]
    binding()(mesh, replacements)
    assert mesh.updates == 1
    assert [slot.values for slot in originals] == before
    expected = deepcopy(before)
    for slot, material in zip(expected, replacements):
        slot['material_interface'] = material
    assert [slot.values for slot in mesh.slots] == expected


def test_incompatible_material_layout_refuses_without_publishing_changes():
    mesh = Mesh([Slot('old', 'source')])
    before = deepcopy(mesh.slots[0].values)
    with pytest.raises(ValueError, match='material layout'):
        binding()(mesh, ['new'])
    assert mesh.updates == 0 and mesh.slots[0].values == before


def test_editor_no_op_refuses_instead_of_certifying_old_bindings():
    mesh = Mesh([Slot('old', 'source'), Slot('near', 'CanopyNear'), Slot('far', 'CanopyFar')])
    mesh.set_editor_property = lambda key, value: None
    with pytest.raises(ValueError, match='bindings did not apply'):
        binding()(mesh, ['new'])
