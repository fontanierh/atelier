"""Brinecove meshes keep full-precision UVs, so faces far from the origin keep their texture detail.

Op410 review: Builder.face box-projects UVs in world metres, ~72 tiles at the grand stair and up to ~650 at the
region's edge. Unreal's default half-precision UVs step by 1/16 of a tile at 72, so every 14 cm stair nosing collapsed
to a single texel row and showed as streaks along each step edge.
"""
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from brinecove import modules as M  # noqa: E402
from brinecove.geom import Builder  # noqa: E402


def test_half_precision_uvs_flatten_the_grand_stair_nosings():
    """The measured failure: a nosing's 14 cm top face spans 0.044 in v around 72 (y / 3.2 m), and half precision
    steps by 0.0625 there: each nosing's texture is either squashed to a single texel row or stretched by 43%."""
    b = Builder('stair')
    M.terrace_stair(b, *M.TERRACE_STAIRS[0], cheek=1.0)
    _, steps = M.terrace_stair_plan(M.TERRACE_STAIRS[0][0])
    tops = []
    for f, mat in zip(b.faces, b.mats):
        pts = [b.verts[i] for i in f]
        ys = [p[1] for p in pts]
        if mat == 'stone' and len({round(p[2], 6) for p in pts}) == 1 and abs(max(ys) - min(ys) - 0.14) < 1e-6:
            tops.append(np.array([b.uvs[i][1] for i in f]))
    assert len(tops) == 2 * len(steps)                     # each nosing's top and bottom
    for v in tops:
        assert np.ptp(v) > 0.04                            # full precision keeps 14 cm of texture
        half = np.ptp(v.astype(np.float16).astype(np.float64))
        assert abs(half - np.ptp(v)) > 0.3 * np.ptp(v)    # half precision: none keeps its texture span within 30%
    assert sum(np.ptp(v.astype(np.float16)) == 0 for v in tops) > len(tops) // 4  # many sample one texel row


def run_import(tmp_path, meshes, *, role_transport=True):
    """Execute import_brinecove.main with Unreal faked; returns the build settings each mesh ends with."""
    class Properties:
        def __init__(self, **values): self.values = values
        def get_editor_property(self, key): return self.values[key]
        def set_editor_property(self, key, value): self.values[key] = value

    class Mesh(Properties):
        def __init__(self, entry):
            super().__init__(static_materials=[Properties(material_slot_name=key) for key in entry['slots']],
                             materials=[None]*len(entry['slots']),body_setup=Properties())
            self.build = dict(use_full_precision_u_vs=False, remove_degenerates=True)
            self.entry = entry
        def set_material(self, slot, value): self.values['materials'][slot] = value
        def get_num_triangles(self, lod): return self.entry['triangles']
        def get_bounding_box(self):
            (x0, y0, z0), (x1, y1, z1) = self.entry['bounds_m']
            return SimpleNamespace(min=SimpleNamespace(x=x0 * 100, y=-y1 * 100, z=z0 * 100),
                                   max=SimpleNamespace(x=x1 * 100, y=-y0 * 100, z=z1 * 100))

    built = {}
    def imported(path, name):
        built[name] = Mesh(next(e for e in meshes if e['name'] == name))
        return built[name]

    def get_settings(mesh, lod):
        assert lod == 0
        return Properties(**mesh.build)  # a copied UE struct must be committed back to its mesh

    def set_settings(mesh, lod, settings):
        assert lod == 0
        mesh.build = dict(settings.values)

    materials = {'stone': dict(name='MI_BC_stone', kind='opaque'), 'leaf': dict(name='MI_BC_leaf', kind='masked'),
                 'terrain': dict(name='MI_BC_terrain', kind='terrain')}
    (tmp_path / 'build-report.json').write_text(json.dumps(dict(meshes=meshes, materials=materials)))
    editor = SimpleNamespace(get_lod_build_settings=get_settings, set_lod_build_settings=set_settings)
    loaded = set()                                   # like the commandlet: no subsystem until its module is loaded
    def stamp_roles(mesh):
        assert 'YorimichiImport' in loaded
        if mesh.entry.get('foliage_roles') and role_transport:
            for slot in mesh.values['static_materials']:
                slot.set_editor_property('material_slot_name','FoliageRoles_'+slot.get_editor_property('material_slot_name'))
        return True
    unreal = SimpleNamespace(StaticMeshEditorSubsystem=object(), load_module=loaded.add,
        YorimichiFoliageBuilder=SimpleNamespace(stamp_source_roles=stamp_roles),
        get_editor_subsystem=lambda _: editor if 'StaticMeshEditor' in loaded else None,
        CollisionTraceFlag=SimpleNamespace(CTF_USE_COMPLEX_AS_SIMPLE='complex-as-simple'), log=lambda *_: None)
    assets = SimpleNamespace(make_directory=lambda *_: None, does_asset_exist=lambda *_: False,
        load_asset=lambda path: path, save_loaded_asset=lambda *_: None, delete_directory=lambda *_: None)
    script = GAME / 'unreal/Scripts/import_brinecove.py'
    wanted = {'main', 'keep_full_precision_uvs'}
    functions = [node for node in ast.parse(script.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {f.name for f in functions} == wanted
    namespace = dict(OUT=tmp_path, ROOT='/Game/Brinecove', E=assets, unreal=unreal, json=json,
        surfaces=lambda *_: None, textures=lambda _: None, import_mesh=imported, generate_lods=lambda _: None)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(script), 'exec'), namespace)
    namespace['main']()
    return {name: mesh.build for name, mesh in built.items()}


def test_every_uv_textured_brinecove_mesh_imports_full_precision_uvs(tmp_path):
    box = [[0, 0, 0], [1, 1, 1]]
    meshes = [dict(name='SM_BC_TownUpper_4_4', path='glb/a.glb', slots=['stone', 'leaf'], triangles=10, bounds_m=box,
                   collision=True),
              dict(name='SM_BC_Ground_3_3', path='glb/b.glb', slots=['terrain', 'stone'], triangles=10, bounds_m=box,
                   collision=True),
              dict(name='SM_BC_Rocks_9_9', path='glb/c.glb', slots=['terrain'], triangles=10, bounds_m=box,
                   collision=True),
              dict(name='SM_BC_Plant_Palm0', path='glb/d.glb', slots=['leaf'], triangles=10, bounds_m=box,
                   collision=False, lods=True)]
    builds = run_import(tmp_path, meshes)
    assert builds['SM_BC_TownUpper_4_4'] == dict(use_full_precision_u_vs=True, remove_degenerates=True)
    assert builds['SM_BC_Ground_3_3']['use_full_precision_u_vs']        # its paving samples world-metre UVs
    assert not builds['SM_BC_Rocks_9_9']['use_full_precision_u_vs']     # world-position material only
    assert not builds['SM_BC_Plant_Palm0']['use_full_precision_u_vs']   # atlas cells within 0-1


def test_source_import_refuses_roles_lost_by_interchange(tmp_path):
    meshes=[dict(name='SM_BC_Plant',path='glb/a.glb',slots=['leaf'],triangles=10,
                 bounds_m=[[0,0,0],[1,1,1]],collision=False,foliage_roles=True)]
    with pytest.raises(AssertionError,match='foliage UV5 lost across source import'):
        run_import(tmp_path,meshes,role_transport=False)
    assert run_import(tmp_path,meshes)['SM_BC_Plant']['use_full_precision_u_vs']
