"""Selected Treehouse ownership, source locality and current-before-retirement boundaries."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from atelier import native_membership
from atelier.mesh_geometry import package_inventory

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
import treehouse_surfaces as S  # noqa: E402
from treehouse.atomic_parameters import load  # noqa: E402


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_selected_treehouse_parameters_are_complete_and_original():
    root=GAME/'assets/treehouse/export-parameters'
    recipe=module('treehouse_atomic_recipe',GAME/'treehouse_atomic_build.py')
    assert {path.stem for path in root.glob('*.json')}==set(recipe.TREES+recipe.PROPS)
    for name in recipe.TREES+recipe.PROPS:assert load(root/(name+'.json'))['name']==name
    source=ast.parse((GAME/'world/regions/treehouse/trees.py').read_text())
    specs=next(ast.literal_eval(n.value) for n in source.body if isinstance(n,ast.Assign)
        and any(isinstance(v,ast.Name) and v.id=='SPECS' for v in n.targets))
    assert {name:load(root/(name+'.json'))['args'] for name in recipe.TREES}=={name:list(value) for name,value in specs.items()}


@pytest.mark.parametrize('field,value',[('name','TH_P_../../foreign'),('solid',1),('size',float('nan')),('target',0)])
def test_selected_prop_parameters_refuse_before_geometry(tmp_path,field,value):
    source=json.loads((GAME/'assets/treehouse/export-parameters/TH_P_kamado.json').read_text())
    source[field]=value;path=tmp_path/'TH_P_kamado.json';path.write_text(json.dumps(source))
    with pytest.raises(ValueError):load(path)


def test_cold_treehouse_query_data_and_independent_logical_inputs(tmp_path):
    recipe=module('treehouse_atomic_recipe_graph',GAME/'treehouse_atomic_build.py');ctx=SimpleNamespace(out=tmp_path.resolve())
    trees=recipe.canopy_steps(ctx);props=recipe.prop_steps(ctx);surfaces=recipe.surface_steps(ctx)
    for name,steps,count in (('treehouse_trees',trees,4),('treehouse_props',props,13),('treehouse_surfaces',surfaces,4)):
        planners=[step for step in steps if step.name.startswith('world.'+name+'.geometry.')]
        assert len(planners)==count
        for step in planners:
            assert step.cache and step.commands[0].factory_startup and step.commands[0].threads==3
            assert not any('exports/world.' in str(path) for path in step.inputs)
            if name!='treehouse_surfaces':assert len([path for path in step.inputs if path.parent.name=='export-parameters'])==1
            else:assert step.reads==['treehouse.surface_source.'+step.name.rsplit('.',1)[-1]]
    data=next(step for step in trees if step.name=='world.treehouse_trees.data')
    assert set(data.reads)=={'treehouse.canopy_record.'+name for name in recipe.TREES}
    assert all('.export.' not in str(read) and not str(read).endswith('.atomic') for read in data.reads)
    canonical=next(step for step in surfaces if step.name=='world.treehouse.source_data')
    assert 'treehouse.canopy_dimensions' in canonical.reads and canonical.needs==['world.layout']
    assert {p.name for p in canonical.products}=={'treehouse.surface_metadata',*('treehouse.surface_source.'+parent for parent in S.PARENTS)}


def source_fixture(out):
    root=out/'treehouse';parents={};assets={}
    for parent in S.PARENTS:
        name=parent if parent in ('TH_Frame','TH_Trunks') else parent+'_cell_-1_0'
        folder='structure' if parent=='TH_Structure' else 'dressing' if parent=='TH_Dressing' else parent.removeprefix('TH_').lower()
        path=root/'assets'/folder/(name+'.fbx');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fbx')
        assets[name]=dict(parent=parent,triangles=1,collision_hulls=0,min=[-1,0,0],max=[0,1,1],
            slots=['TH_wood'],used_slots=['TH_wood'],sha256=hashlib.sha256(b'fbx').hexdigest(),
            fbx=str(path.relative_to(root)),uv_channels=['UVMap','Piece1','Piece2','Piece3','Piece4'] if parent in ('TH_Frame','TH_Dressing') else ['UVMap'])
        parents[parent]=[name]
    value=dict(schema=1,complete=True,parents=parents,assets=assets)
    (root/'surfaces.json').write_text(json.dumps(value))
    return value


@pytest.mark.parametrize('bad',['missing','budget','old_parent','uv','duplicate','hull','path','bytes','link'])
def test_complete_surface_sources_refuse_partial_or_foreign_membership(tmp_path,bad):
    value=source_fixture(tmp_path);assert len(S.rows(tmp_path))==4
    key=value['parents']['TH_Structure'][0];row=value['assets'][key]
    if bad=='missing':value['assets'].pop(key)
    if bad=='budget':row['triangles']=32769
    if bad=='old_parent':value['parents']['TH_Structure']=['TH_Structure']
    if bad=='uv':row['uv_channels']=['Piece1']
    if bad=='duplicate':value['parents']['TH_Structure'].append(key)
    if bad=='hull':row['collision_hulls']=1
    if bad=='path':row['fbx']='../foreign.fbx'
    if bad=='bytes':(tmp_path/'treehouse'/row['fbx']).write_bytes(b'changed')
    if bad=='link':
        path=tmp_path/'treehouse'/row['fbx'];path.unlink();path.symlink_to(tmp_path/'foreign')
    (tmp_path/'treehouse/surfaces.json').write_text(json.dumps(value))
    with pytest.raises((ValueError,FileNotFoundError)):S.rows(tmp_path)


def retirement_function():
    file=GAME/'unreal/Scripts/treehouse_atomic_native.py'
    node=next(n for n in ast.parse(file.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='retire')
    scope=dict(package_inventory=package_inventory,native_membership=native_membership,surfaces=S)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(file),'exec'),scope)
    return scope


def test_combined_treehouse_foreign_reference_refuses_before_any_delete_then_repeats(tmp_path):
    source_fixture(tmp_path/'out');rows=S.rows(tmp_path/'out');current=[row['package'] for row in rows]
    content=tmp_path/'Content';old='/Game/Japan/Assets/TH_Structure';other='/Game/Japan/Assets/TH_Dressing'
    owned=set(current)|{old,other};deleted=[];references={other:['/Game/Foreign']}
    for package in owned:
        path=content/(package[6:]+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
    def delete(package):
        deleted.append(package);owned.remove(package);(content/(package[6:]+'.uasset')).unlink();return True
    editor=SimpleNamespace(does_asset_exist=lambda p:p in owned,find_package_referencers_for_asset=lambda p,**kw:references.get(p,[]),delete_asset=delete)
    scope=retirement_function();scope['inventory']=lambda editor:set(owned)
    before=set(owned)
    with pytest.raises(ValueError,match='external references'):scope['retire'](editor,before,current,rows,content)
    assert owned==before and not deleted
    references.clear();assert set(scope['retire'](editor,before,current,rows,content))=={old,other}
    assert owned==set(current) and S.retired_parents_absent(content)
    assert scope['retire'](editor,set(current),current,rows,content)==[]
    assert len(deleted)==2


def test_actual_surface_assembly_publishes_complete_named_five_uv_membership(tmp_path):
    import numpy as np
    from atelier import mesh_ir,export_manifest
    from atelier.atomic_files import atomic_json
    assembly=module('actual_treehouse_file_assembly',GAME/'world/regions/treehouse/assemble_atomic.py')
    out=tmp_path.resolve();positions=np.asarray([[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32)
    matrix=np.eye(4).tolist()
    for parent in S.PARENTS:
        name=parent if parent in ('TH_Frame','TH_Trunks') else parent+'_cell_0_0'
        labels=['UVMap','Piece1','Piece2','Piece3','Piece4'] if parent in ('TH_Frame','TH_Dressing') else ['UVMap']
        piece=dict(positions=positions,normals=np.tile([0,0,1],(3,1)),faces=[[0,1,2]],materials=[0],smooth=[False],
            uvs=[(label,np.zeros((3,2))) for label in labels],colours=[])
        folder=out/'planned_exports/treehouse_surfaces'/parent;folder.mkdir(parents=True)
        payload=mesh_ir.encode(piece,key=name,slots=['TH_wood'],matrix=matrix,options={})
        mesh_ir.write(folder/(name+'.npz'),payload)
        row=dict(name=name,payload=name+'.npz',sha256=hashlib.sha256(payload).hexdigest(),triangles=1,polygons=1,
                 min=[0,0,0],max=[1,1,0],collision_hulls=0,source_faces=[0])
        atomic_json(folder/'plan.json',dict(schema=1,parent=parent,complete=True,triangle_limit=32768,source_triangles=1,
            source_polygons=1,source_collision_hulls=0,slots=['TH_wood'],matrix=matrix,pieces=[row]))
        export=out/'exports/world.treehouse_surfaces.export'/name;export.mkdir(parents=True)
        (export/(name+'.fbx')).write_bytes(b'one verified opaque primary')
        export_manifest.publish_receipt(export,key=name,primary=name+'.fbx',triangles=1,bounds=[[0,0,0],[1,1,0]],
            metadata=dict(geometry_sha256=row['sha256'],slots=['TH_wood'],polygons=1,collision_hulls=0,uv_channels=labels))
    metadata=out/'treehouse-data/surfaces';metadata.mkdir(parents=True)
    for name in ('runtime.json','manifest.json'):atomic_json(metadata/name,dict(source='canonical'))
    old=out/'treehouse/assets/TH_Structure.fbx';old.parent.mkdir(parents=True);old.write_bytes(b'old whole')
    assembly.surfaces(out)
    rows=S.rows(out)
    assert len(rows)==4 and all(row['name'] for row in rows) and not old.exists()
    assert json.loads((out/'treehouse/pieces.json').read_text())['pieces'][0]['name']=='TH_Dressing_cell_0_0'
    before={path:path.stat().st_mtime_ns for path in (out/'treehouse/assets').rglob('*.fbx')}
    assembly.surfaces(out)
    assert {path:path.stat().st_mtime_ns for path in before}==before


def test_host_authority_refuses_native_pass_when_whole_guard_close_is_incomplete(tmp_path,monkeypatch):
    authority=module('treehouse_host_authority',GAME/'tests/native/prepare_treehouse_proof.py')
    monkeypatch.setattr(authority,'revision',lambda root:'a'*40)
    monkeypatch.setattr(authority.subprocess,'check_output',lambda *a,**kw:'')
    path=tmp_path/'input';path.write_bytes(b'bound source')
    manifest=tmp_path/'attestation.json'
    value=dict(schema=1,repo=str(authority.REPO),source_head='a'*40,donor=str(tmp_path),donor_head='a'*40,
        current_source=authority.snapshot([path]),donor_inputs={},archive_files={})
    manifest.write_text(json.dumps(value))
    result=tmp_path/'result.json';result.write_text(json.dumps(dict(complete=True,source_head='a'*40,
        host_attestation_sha256=authority.sha(manifest))))
    guard=tmp_path/'guard';guard.mkdir()
    (guard/'memory-health-tree.json').write_text(json.dumps(dict(state='child_exited',cleanup_complete=True,
        processes=[],late_reporters=dict(unresolved=[]))))
    (guard/'execution-timings.json').write_text(json.dumps(dict(execution_seconds=None)))
    with pytest.raises(ValueError,match='Whole native/guard'):authority.verify(manifest,result,guard,0)
    assert not (tmp_path/'postcheck.json').exists()
    (guard/'execution-timings.json').write_text(json.dumps(dict(execution_seconds=1.)))
    with pytest.raises(ValueError,match='Whole native/guard'):authority.verify(manifest,result,guard,1)
    authority.verify(manifest,result,guard,0)
    assert json.loads((tmp_path/'postcheck.json').read_text())['complete'] is True
    path.write_bytes(b'changed source')
    with pytest.raises(ValueError,match='bytes/stat'):authority.verify(manifest)


def test_guarded_treehouse_proof_uses_frozen_files_without_git_subprocesses():
    source=(GAME/'tests/native/treehouse_atomic_equivalence.py').read_text()
    tree=ast.parse(source)
    assert not any(isinstance(node,ast.Name) and node.id in ('subprocess','revision') for node in ast.walk(tree))
    assert '--attestation-sha256' in source and 'host_attestation_sha256' in source
