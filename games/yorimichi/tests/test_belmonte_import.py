"""Separate collision hulls should not consume distance-field cook work."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('with_hull', [False, True])
@pytest.mark.parametrize('with_obsolete', [False, True])
def test_import_disables_distance_fields_only_on_separate_physics_hull(tmp_path, with_hull, with_obsolete):
    writes, bindings = [], []
    class Properties:
        def __init__(self, **values): self.values = values
        def get_editor_property(self, key): return self.values.get(key)
        def set_editor_property(self, key, value):
            writes.append((self, key)); self.values[key] = value

    class Mesh(Properties):
        def __init__(self, name):
            super().__init__(static_materials=[None], body_setup=Properties(), vertices=((0, 1, 2),))
            self.name = name
            self.build = dict(distance_field_resolution_scale=1., use_full_precision_u_vs=True,
                              remove_degenerates=False)
        def set_material(self, slot, value):
            bindings.append((self, slot)); self.values['static_materials'][slot] = value
        def get_material(self, slot): return self.values['static_materials'][slot]
        def get_num_triangles(self, lod): return 1
        def get_bounding_box(self):
            return SimpleNamespace(min=SimpleNamespace(x=0, y=-200, z=0), max=SimpleNamespace(x=100, y=0, z=300))

    meshes, changed, saved, tv_imports = {}, [], [], []
    if with_obsolete:
        meshes.update({name: Mesh(name) for name in ('SM_BM_Obsolete', 'SM_BM_Obsolete_Collision')})
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
    entry = dict(sha256='0'*64, name='SM_BM_House', path='glb/House.glb', triangles=1, bounds_m=[[0, 0, 0], [1, 2, 3]])
    if with_hull: entry['collision'] = dict(path='glb/House_hull.glb', sha256='0'*64)
    out = tmp_path / 'belmonte'
    out.mkdir()
    products = tmp_path / 'products/belmonte'
    products.mkdir(parents=True)
    (products / 'geometry.json').write_text(json.dumps(dict(meshes=[entry])))
    (products / 'materials.json').write_text(json.dumps(dict(materials={}, bindings={'SM_BM_House': ['paint']})))
    # The actual native loop must not reopen the placement runtime or broad report.
    (out / 'build-report.json').write_text('unconsumed broad report')
    (out / 'runtime.json').write_text('unconsumed placement runtime')
    assets = SimpleNamespace(make_directory=lambda *_: None,
        list_assets=lambda root, **_: [root+'/'+name+'.'+name for name in meshes],
        does_asset_exist=lambda path: path.rsplit('/', 1)[-1] in meshes,
        find_package_referencers_for_asset=lambda path, **k: [
            '/Game/Belmonte/Meshes/'+name for name, mesh in meshes.items()
            if mesh.get_editor_property('complex_collision_mesh') is meshes[path.rsplit('/', 1)[-1]]],
        delete_asset=lambda path: meshes.pop(path.rsplit('/', 1)[-1], None) is not None,
        load_asset=lambda path: meshes.get(path.rsplit('/', 1)[-1], path), save_loaded_asset=lambda asset, **_: saved.append(asset) or True, delete_directory=lambda *_: None)
    loaded = set()                                   # like the commandlet: no subsystem until its module is loaded
    unreal = SimpleNamespace(StaticMeshEditorSubsystem=object(), load_module=loaded.add,
        get_editor_subsystem=lambda _: editor if 'StaticMeshEditor' in loaded else None,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex-as-simple'), log=lambda *_: None)
    script = Path(__file__).parents[1] / 'unreal/Scripts/import_belmonte.py'
    # Execute the actual import loop without Unreal-only module initialization/material compilation.
    function = next(node for node in ast.parse(script.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')
    namespace = dict(OUT=out, ROOT='/Game/Belmonte', E=assets, unreal=unreal, Path=Path, json=json,
        __file__=str(script), runpy=SimpleNamespace(run_path=lambda path: tv_imports.append(Path(path))),
        parent=lambda: None, textures=lambda _: None, surfaces=lambda *_: None, import_mesh=imported)
    from atelier import native_membership
    from atelier.unreal_mesh_reuse import set_if_changed
    namespace.update(native_membership=native_membership, native_context=lambda _: None, yori=SimpleNamespace(GAME=SimpleNamespace(name='test')),
        atmosphere=SimpleNamespace(__file__=str(script)), ground_grain=SimpleNamespace(__file__=str(script)),
        AssetGroup=lambda *a, **k: SimpleNamespace(matches=lambda _: True), set_if_changed=set_if_changed,
        MeshReuse=lambda *a, **k: SimpleNamespace(donor={}, acquire=lambda name, *a, **k: meshes.get(name), imported=lambda *a: None,
                                                validated=lambda _: None, finish=lambda: None))
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
    namespace['main']()
    assert tv_imports == [script.with_name('racing_tv_material.py')]
    assert not any(name.startswith('SM_BM_Obsolete') for name in meshes)
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

    # A second pass through a verified reuse must validate without mutating native settings/materials.
    writes.clear(); bindings.clear(); changed.clear()
    namespace['main']()
    assert writes == [] and bindings == [] and changed == []

    if with_hull:
        # A compatible existing render mesh can outlive removal of its source
        # hull record. Normal finishing must detach/save it before retirement.
        del entry['collision']
        (products/'geometry.json').write_text(json.dumps(dict(meshes=[entry])))
        namespace['main']()
        assert render.get_editor_property('complex_collision_mesh') is None
        assert 'SM_BM_House_Collision' not in meshes
        assert (render, 'complex_collision_mesh') in writes
