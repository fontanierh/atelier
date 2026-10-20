"""Separate collision hulls should not consume distance-field cook work."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('with_hull', [False, True])
def test_import_disables_distance_fields_only_on_separate_physics_hull(tmp_path, with_hull):
    class Properties:
        def __init__(self, **values): self.values = values
        def get_editor_property(self, key): return self.values[key]
        def set_editor_property(self, key, value): self.values[key] = value

    class Mesh(Properties):
        def __init__(self, name):
            super().__init__(static_materials=[None], body_setup=Properties(), vertices=((0, 1, 2),))
            self.name = name
            self.build = dict(distance_field_resolution_scale=1., use_full_precision_u_vs=True,
                              remove_degenerates=False)
        def set_material(self, slot, value): self.values['static_materials'][slot] = value
        def get_num_triangles(self, lod): return 1
        def get_bounding_box(self):
            return SimpleNamespace(min=SimpleNamespace(x=0, y=-200, z=0), max=SimpleNamespace(x=100, y=0, z=300))

    meshes, changed, saved, tv_imports = {}, [], [], []
    def imported(path, name):
        meshes[name] = Mesh(name)
        return meshes[name]

    def get_settings(mesh, lod):
        assert lod == 0
        return Properties(**mesh.build)  # A copied UE struct must be committed back to the right mesh.

    def set_settings(mesh, lod, settings):
        assert lod == 0
        changed.append(mesh.name)
        mesh.build = dict(settings.values)

    editor = SimpleNamespace(get_lod_build_settings=get_settings, set_lod_build_settings=set_settings)
    entry = dict(name='SM_BM_House', path='glb/House.glb', triangles=1, bounds_m=[[0, 0, 0], [1, 2, 3]])
    if with_hull: entry['collision'] = dict(path='glb/House_hull.glb')
    (tmp_path / 'build-report.json').write_text(json.dumps(dict(meshes=[entry])))
    (tmp_path / 'runtime.json').write_text(json.dumps(dict(groups=[dict(plant=False,
        asset='/Game/Belmonte/Meshes/SM_BM_House.SM_BM_House', materials=['paint'])])))
    assets = SimpleNamespace(make_directory=lambda *_: None, does_asset_exist=lambda *_: False,
        load_asset=lambda path: path, save_loaded_asset=saved.append, delete_directory=lambda *_: None)
    loaded = set()                                   # like the commandlet: no subsystem until its module is loaded
    unreal = SimpleNamespace(StaticMeshEditorSubsystem=object(), load_module=loaded.add,
        get_editor_subsystem=lambda _: editor if 'StaticMeshEditor' in loaded else None,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex-as-simple'), log=lambda *_: None)
    script = Path(__file__).parents[1] / 'unreal/Scripts/import_belmonte.py'
    # Execute the actual import loop without Unreal-only module initialization/material compilation.
    function = next(node for node in ast.parse(script.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')
    namespace = dict(OUT=tmp_path, ROOT='/Game/Belmonte', E=assets, unreal=unreal, Path=Path, json=json,
        __file__=str(script), runpy=SimpleNamespace(run_path=lambda path: tv_imports.append(Path(path))),
        parent=lambda: None, textures=lambda _: None, surfaces=lambda *_: None, import_mesh=imported)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
    namespace['main']()
    assert tv_imports == [script.with_name('racing_tv_material.py')]
    render = meshes['SM_BM_House']
    assert render.build == dict(distance_field_resolution_scale=1., use_full_precision_u_vs=True,
                                remove_degenerates=False)
    assert render.values['body_setup'].values == dict(collision_trace_flag='complex-as-simple', double_sided_geometry=True)
    assert render.values['vertices'] == ((0, 1, 2),)
    assert changed == (['SM_BM_House_Collision'] if with_hull else [])
    if with_hull:
        hull = meshes['SM_BM_House_Collision']
        assert render.values['complex_collision_mesh'] is hull and hull in saved
        assert hull.build == dict(distance_field_resolution_scale=0., use_full_precision_u_vs=True,
                                   remove_degenerates=False)
        assert hull.values['vertices'] == ((0, 1, 2),) and hull.values['body_setup'].values == {}
