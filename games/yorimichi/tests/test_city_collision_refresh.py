"""Exercise the actual city owner around saved zero-hull and authored-hull imports."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]
SCRIPT = GAME/'unreal/Scripts/import_city_surface_tiles.py'


@pytest.fixture
def owner(monkeypatch):
    library = SimpleNamespace(does_asset_exist=lambda path: True, load_asset=lambda path: mesh)
    mesh = SimpleNamespace(simple=0, convex=1)
    unreal = SimpleNamespace(EditorAssetLibrary=library)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'mesh_import', SimpleNamespace(import_mesh=lambda *a, **k: None))
    monkeypatch.syspath_prepend(str(GAME))
    monkeypatch.syspath_prepend(str(GAME/'world'))
    spec = importlib.util.spec_from_file_location('city_collision_owner_test', SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    removed = []
    def remove(target):
        removed.append(target)
        target.simple = target.convex = 0
        return True
    editor = SimpleNamespace(get_simple_collision_count=lambda mesh:mesh.simple,
                             get_convex_collision_count=lambda mesh:mesh.convex,
                             remove_collisions=remove)
    return SimpleNamespace(module=module, unreal=unreal, mesh=mesh, editor=editor, removed=removed)


@pytest.mark.parametrize('hit', [False, True])
def test_real_owner_passes_miss_reset_then_finishes_empty_hulls_even_on_hit(owner, monkeypatch, tmp_path, hit):
    p = owner
    # Execute the actual production main through the first saved tile. Stop at
    # its save after the unchanged source/cooked gates have run successfully.
    module = p.module
    name = 'HD_Square_cell_5_1_Piece01'
    folder = tmp_path/'city_surface_tiles/v1_128m/HD_Square'; folder.mkdir(parents=True)
    source = folder/(name+'.fbx'); source.write_bytes(b'current hull-free FBX')
    tile = dict(name=name,sha256=module.hashlib.sha256(source.read_bytes()).hexdigest(),
                triangles=1,collision_hulls=0,min=[0,0,0],max=[1,1,1])
    row = dict(tiles=[tile],source_material_slots=['HDS_stone'],source_collision_hulls=51,
               source_triangles=1,source_bounds=tile,source_collision_vertices=[[[0,0,0]]]*51)
    (folder.parent/'manifest.json').write_text(json.dumps({'sources':{'HD_Square':row}}))
    monkeypatch.setenv('CITY_SURFACE_TILES_TAG','v1_128m')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module,'production_groups',lambda manifest:{'HD_Square':[]})
    monkeypatch.setattr(module,'owned_tiles',lambda *a:{})
    monkeypatch.setattr(module,'protected_files',lambda *a:{})
    monkeypatch.setattr(module.yori,'GAME',tmp_path)
    material = object()
    library = p.unreal.EditorAssetLibrary
    library.list_assets=lambda *a,**k:[]
    library.load_asset=lambda path: p.mesh if path.endswith(name) else material
    events = []
    def raw_import(path, destination, actual_name, *, fresh_slots, before_import):
        assert actual_name==name and Path(path)==source and fresh_slots
        events.append('admission')
        if not hit:
            before_import()
            assert p.mesh.convex==0  # Legacy FBX with no UCX otherwise leaves the old hull.
            events.append('raw-source')
        return p.mesh
    monkeypatch.setattr(module,'import_mesh',raw_import)
    p.mesh.static_materials=[SimpleNamespace(get_editor_property=lambda key:'HDS_stone')]
    p.mesh.get_material=lambda index:material
    p.mesh.get_num_triangles=lambda lod:1
    p.mesh.get_bounding_box=lambda:SimpleNamespace(min=SimpleNamespace(x=0,y=-100,z=0),
                                                  max=SimpleNamespace(x=100,y=0,z=100))
    settings=SimpleNamespace(get_editor_property=lambda key:True)
    p.editor.get_lod_build_settings=lambda *a:settings
    body=SimpleNamespace(get_editor_property=lambda key:'desired',set_editor_property=lambda *a:None)
    p.mesh.get_editor_property=lambda key:body
    p.unreal.load_module=lambda name:None
    p.unreal.StaticMeshEditorSubsystem=object
    p.unreal.get_editor_subsystem=lambda cls:p.editor
    p.unreal.SystemLibrary=SimpleNamespace(execute_console_command=lambda *a:None)
    p.unreal.CollisionTraceFlag=SimpleNamespace(CTF_USE_SIMPLE_AND_COMPLEX='desired',CTF_USE_COMPLEX_AS_SIMPLE='other')
    assert_gate = []
    monkeypatch.setattr(module,'collision_matches',lambda mesh,*a:assert_gate.append('exact-hulls') or mesh.convex==mesh.simple==0)
    def cooked(mesh,count,hulls):
        assert count==1 and hulls and mesh.convex==mesh.simple==0
        assert_gate.append('cooked-complex')
        return True
    p.unreal.CitySurfaceValidation=SimpleNamespace(validate_collision=cooked)
    class SavedBoundary(Exception): pass
    def save(mesh, only_dirty):
        assert assert_gate==['exact-hulls','cooked-complex'] and only_dirty
        raise SavedBoundary()
    library.save_loaded_asset=save
    with pytest.raises(SavedBoundary):module.main()
    assert events==(['admission'] if hit else ['admission','raw-source'])
    assert len(p.removed)==1 and p.mesh.convex==0


def test_positive_owner_is_reset_before_import_not_after_fifty_one_authored_hulls(owner):
    p = owner
    p.module.prepare_collision_import('/Game/Owned','Mesh',p.editor)
    assert p.mesh.convex==0 and len(p.removed)==1
    # Model the real engine's append/dedup collision import, rather than replacing
    # the list silently. Reset must precede this source pass.
    p.mesh.convex += 51
    p.module.finish_empty_collision(p.mesh, {'name':'Mesh','collision_hulls':51}, p.editor)
    assert p.mesh.convex==51 and len(p.removed)==1


def test_failed_reset_cannot_reach_source_import_or_publish(owner):
    p = owner
    p.editor.remove_collisions=lambda mesh:False
    with pytest.raises(AssertionError, match='reset failed'):
        p.module.prepare_collision_import('/Game/Owned','Mesh',p.editor)
    assert p.mesh.convex==1


def test_city_importer_uses_the_shared_miss_hook_not_an_unrelated_seed_wrapper():
    tree=ast.parse(SCRIPT.read_text())
    imports=[node.module for node in tree.body if isinstance(node,ast.ImportFrom)]
    assert 'mesh_import' in imports and 'import_village' not in imports
