"""Material batching keeps the reimport contract and still builds/dirties the final mesh."""
import copy
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'unreal/Scripts/mesh_materials.py'
spec = importlib.util.spec_from_file_location('mesh_materials', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assign_materials = module.assign_materials


class Slot:
    def __init__(self, index, detached=False):
        self.detached = detached
        self.values = {'material_slot_name': f'slot_{index}',
                       'imported_material_slot_name': f'HDS_surface_{index}',
                       'material_interface': 'old', 'uv_channel_data': {'density': index + .25}}

    def copy(self):
        result = Slot(0, detached=True)
        result.values = copy.deepcopy(self.values)
        return result

    def get_editor_property(self, name):
        return self.values[name]

    def set_editor_property(self, name, value):
        assert self.detached, 'A live Unreal struct wrapper would notify its mesh'
        self.values[name] = value


class Mesh:
    def __init__(self, count):
        self.slots = [Slot(i) for i in range(count)]
        self.array_writes = self.builds = self.physics_refreshes = 0
        self.dirty = False

    @property
    def static_materials(self):
        return self.slots

    @static_materials.setter
    def static_materials(self, slots):
        self.array_writes += 1
        self.slots = slots

    def set_material(self, index, material):
        self.slots[index].values['material_interface'] = material
        for key in ('material_slot_name', 'imported_material_slot_name'):
            if str(self.slots[index].values[key]) in ('', 'None'):
                self.slots[index].values[key] = material
        self.builds += 1
        self.physics_refreshes += 1
        self.dirty = True


class Materials(unittest.TestCase):
    def test_named_slots_keep_all_metadata_and_build_only_the_final_state(self):
        mesh = Mesh(10)
        metadata = [{k: v for k, v in slot.values.items() if k != 'material_interface'} for slot in mesh.slots]
        materials = [f'material_{i}' for i in range(10)]
        assign_materials(mesh, materials)
        self.assertEqual([slot.values['material_interface'] for slot in mesh.slots], materials)
        self.assertEqual([{k: v for k, v in slot.values.items() if k != 'material_interface'} for slot in mesh.slots], metadata)
        self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (1, 1, 1))
        self.assertTrue(mesh.dirty)

    def test_identical_materials_still_dirty_and_refresh_the_package(self):
        mesh = Mesh(1)
        assign_materials(mesh, ['old'])
        self.assertEqual((mesh.builds, mesh.physics_refreshes), (1, 1))
        self.assertTrue(mesh.dirty)

    def test_invalid_assignments_leave_the_mesh_untouched(self):
        for count, materials in [(0, []), (2, ['one']), (2, ['one', None])]:
            with self.subTest(count=count, materials=materials):
                mesh = Mesh(count)
                before = [copy.deepcopy(slot.values) for slot in mesh.slots]
                with self.assertRaises(ValueError):
                    assign_materials(mesh, materials)
                self.assertEqual([slot.values for slot in mesh.slots], before)
                self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (0, 0, 0))
                self.assertFalse(mesh.dirty)

    def test_unnamed_slots_keep_the_native_set_material_name_behavior(self):
        mesh = Mesh(2)
        mesh.slots[0].values['material_slot_name'] = 'None'
        mesh.slots[1].values['imported_material_slot_name'] = ''
        assign_materials(mesh, ['first', 'second'])
        self.assertEqual(mesh.slots[0].values['material_slot_name'], 'first')
        self.assertEqual(mesh.slots[1].values['imported_material_slot_name'], 'second')
        self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (0, 2, 2))


if __name__ == '__main__':
    unittest.main()
