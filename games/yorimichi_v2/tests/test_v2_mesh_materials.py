"""Material batching keeps the reimport contract and still builds/dirties the final mesh."""
import ast
import copy
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

path = Path(__file__).resolve().parents[1] / 'unreal/Scripts/mesh_materials.py'
spec = importlib.util.spec_from_file_location('v2_mesh_materials', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assign_materials = module.assign_materials
settings_spec = importlib.util.spec_from_file_location('v2_import_settings', path.with_name('import_settings.py'))
settings_module = importlib.util.module_from_spec(settings_spec)
settings_spec.loader.exec_module(settings_module)


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

    def get_editor_property(self, name):
        assert name == 'static_materials'
        return self.slots

    def get_path_name(self):
        return '/Game/Test/Mesh'


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

    def test_empty_slots_keep_the_importers_no_op(self):
        mesh = Mesh(0)
        assign_materials(mesh, [])
        self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (0, 0, 0))

    def test_invalid_assignments_leave_the_mesh_untouched(self):
        for count, materials in [(2, ['one']), (2, ['one', None])]:
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

    def test_targeted_import_batches_named_slots_and_refuses_missing_material_before_writing(self):
        # Exercise the real importer entry point without launching Unreal or executing its module-level main().
        script = path.with_name('import_asset.py')
        node = next(n for n in ast.parse(script.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == '_apply_mesh_settings')
        loaded = {f'/Game/Material{i}': f'material{i}' for i in range(25)}
        namespace = {'EAL': SimpleNamespace(load_asset=loaded.get), 'assign_materials': assign_materials,
                     'import_settings': settings_module}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(script), 'exec'), namespace)
        apply = namespace['_apply_mesh_settings']
        mesh = Mesh(25)
        apply(mesh, {'slot_materials': list(loaded)})
        self.assertEqual([slot.values['material_interface'] for slot in mesh.slots], list(loaded.values()))
        self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (1, 1, 1))

        mesh = Mesh(25)
        with self.assertRaisesRegex(RuntimeError, 'does not exist'):
            apply(mesh, {'slot_materials': list(loaded)[:-1] + ['/Game/Missing']})
        self.assertEqual([slot.values['material_interface'] for slot in mesh.slots], ['old'] * 25)
        self.assertEqual((mesh.array_writes, mesh.builds, mesh.physics_refreshes), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
