"""Independent fitted prop inputs and complete fail-before-write native file assembly."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from atelier import export_manifest,mesh_ir
from atelier.atomic_files import atomic_json

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
from hidamari.prop_parameters import load
from hidamari.prop_roster import PROPS,TREES,members
from hidamari.assemble_props import assemble


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value


def test_selected_parameters_match_original_fitting_and_lod_policy():
    tools=ast.parse((GAME/'tools/hidamari_props.py').read_text())
    props=next(ast.literal_eval(n.value) for n in tools.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='PROPS' for t in n.targets))
    old=ast.parse((GAME/'world/regions/hidamari/props.py').read_text());scope={}
    assignments=[n for n in old.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id in ('TURN','TARGET','SOLID') for t in n.targets)]
    exec(compile(ast.Module(body=assignments,type_ignores=[]),'legacy fitting policy','exec'),scope)
    scope['TURN']['curve_mirror']=180
    caldera=module('conifer_original_policy',GAME/'world/regions/craterpark/v2/trees.py')
    root=GAME/'assets/hidamari/prop-export-parameters'
    assert {p.stem for p in root.glob('*.json')}==set(members())
    assert {name.removeprefix('HD_P_') for name in PROPS}==set(props)
    for name in PROPS:
        value=load(root/(name+'.json'));slug=value['slug']
        assert (value['size'],value['turn'],value['target'],value['solid'])==(
            props[slug][1],scope['TURN'].get(slug,0.),scope['TARGET'].get(slug,.07),slug in scope['SOLID'])
    for name in TREES:
        for lod in range(4):
            key=name if lod==0 else name+'_LOD'+str(lod);value=load(root/(key+'.json'))
            assert (value['slug'],value['size'],value['crown'])==(
                caldera.TREES[name][0],caldera.TREES[name][2],caldera.TREES[name][3])
            assert value['target']==caldera.TARGET
            assert value['settings']==json.loads(json.dumps({k:getattr(caldera,k) for k in ('LODS','SHELL','BASE','FLOAT')}))


@pytest.mark.parametrize('field,value',[('name','HD_P_../foreign'),('solid',1),('size',float('nan')),
    ('target',0),('parent','HD_P_other'),('lod',True),('settings',{})])
def test_invalid_selected_source_refuses(tmp_path,field,value):
    source=json.loads((GAME/'assets/hidamari/prop-export-parameters/HD_P_postbox.json').read_text())
    source[field]=value;path=tmp_path/'HD_P_postbox.json';path.write_text(json.dumps(source))
    with pytest.raises(ValueError):load(path)


def test_each_logical_source_has_one_parameter_and_committed_glb_without_sibling_exports(tmp_path):
    recipe=module('hidamari_prop_recipe',GAME/'hidamari_prop_build.py')
    steps=recipe.steps(SimpleNamespace(out=tmp_path.resolve()))
    planners=[step for step in steps if step.name.startswith('world.hidamari_props.geometry.')]
    assert len(planners)==48 and len(members())==48
    for step in planners:
        assert step.cache and step.commands[0].threads==3 and step.commands[0].factory_startup
        selected=[p for p in step.inputs if p.parent.name=='prop-export-parameters']
        sources=[p for p in step.inputs if p.suffix=='.glb']
        assert len(selected)==len(sources)==1 and sources[0].is_file()
        assert selected[0].stem==step.name.rsplit('.',1)[-1]
        assert not step.needs and not step.reads
        assert not any('exports/world.' in str(p) or p.name in ('props.py','hidamari_props.py') for p in step.inputs)
        if selected[0].stem.startswith('HD_P_'):
            assert not any(p.name=='prop_lod_geometry.py' for p in step.inputs)
    # A data edit is owned by exactly one source action; common constructors are shared honestly.
    changed=GAME/'assets/hidamari/prop-export-parameters/HD_P_postbox.json'
    assert [step.name for step in planners if changed in step.inputs]==['world.hidamari_props.geometry.HD_P_postbox']


@pytest.mark.parametrize('script',['plan_prop.py','plan_conifer.py'])
def test_plain_script_bootstraps_studio_before_importing_atelier(tmp_path,script):
    # A Blender-like entry has neither the working directory nor Atelier preimported.
    # Refuse an accidental editable-install rescue before the real game bootstrap.
    code='''import importlib.abc,runpy,sys
class RequireBootstrap(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith('atelier') and 'yori' not in sys.modules:
            raise RuntimeError('Atelier imported before world bootstrap')
sys.meta_path.insert(0,RequireBootstrap())
runpy.run_path(sys.argv[1],run_name='bootstrap_check')
assert 'yori' in sys.modules
'''
    result=subprocess.run([sys.executable,'-I','-c',code,str(GAME/'world/regions/hidamari'/script)],
        cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def source_fixture(out):
    for name in members():
        parent=name.split('_LOD')[0];lod=int(name.rsplit('_LOD',1)[1]) if '_LOD' in name else 0
        triangles=4-lod if parent in TREES else 1
        positions=np.array([[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32)
        piece=dict(positions=positions,normals=np.tile([0,0,1],(3*triangles,1)),
            faces=[[0,1,2]]*triangles,materials=[0]*triangles,smooth=[False]*triangles,
            uvs=[('UVMap',np.zeros((3*triangles,2)))],colours=[])
        folder=out/'planned_exports/hidamari_props'/name;folder.mkdir(parents=True)
        payload=mesh_ir.encode(piece,key=name,slots=[parent],matrix=np.eye(4).tolist(),options={})
        mesh_ir.write(folder/(name+'.npz'),payload)
        row=dict(name=name,payload=name+'.npz',sha256=hashlib.sha256(payload).hexdigest(),triangles=triangles,
            polygons=triangles,min=[0,0,0],max=[1,1,0],collision_hulls=0,source_faces=list(range(triangles)))
        atomic_json(folder/'plan.json',dict(schema=1,parent=name,complete=True,triangle_limit=32768,
            source_triangles=triangles,partition='whole',collision_owner=None,source_polygons=triangles,
            source_collision_hulls=0,slots=[parent],matrix=np.eye(4).tolist(),pieces=[row]))
        data=out/'hidamari-prop-data'/name;data.mkdir(parents=True);(data/(parent+'.png')).write_bytes(b'stable texture')
        info=dict(triangles=4 if parent in TREES else 1,boxes=0,gain=1,size=[1,1,1])
        atomic_json(data/'record.json',dict(schema=1,name=name,parent=parent,lod=lod,
            level=[triangles,[1,.25,.1,.04][lod]],info=info,hulls=[]))
        export=out/'exports/world.hidamari_props.export'/name;export.mkdir(parents=True)
        (export/(name+'.fbx')).write_bytes(name.encode())
        export_manifest.publish_receipt(export,key=name,primary=name+'.fbx',triangles=triangles,
            bounds=[[0,0,0],[1,1,0]],metadata=dict(geometry_sha256=row['sha256'],slots=[parent],
                polygons=triangles,collision_hulls=0,uv_channels=['UVMap']))


def test_complete_assembly_preserves_names_lod_policy_and_unchanged_files(tmp_path):
    out=tmp_path.resolve();source_fixture(out);assemble(out)
    root=out/'hidamari/props';data=json.loads((root/'props.json').read_text())
    assert set(data)==set((*PROPS,*TREES))
    assert set(root.glob('*.fbx'))=={root/(name+'.fbx') for name in members()}
    assert data[TREES[0]]['lods']==[[4,1],[3,.25],[2,.1],[1,.04]]
    before={p:p.stat().st_mtime_ns for p in root.glob('*.fbx')};assemble(out)
    assert {p:p.stat().st_mtime_ns for p in before}==before


@pytest.mark.parametrize('bad',['missing','texture','lod','foreign','link','stale_source',
    'directory_png','directory_fbx','directory_json','foreign_empty_directory','source_empty_directory','source_parent_link'])
def test_incomplete_or_foreign_library_refuses_before_first_copy(tmp_path,bad):
    out=tmp_path.resolve();source_fixture(out)
    root=out/'hidamari/props';root.mkdir(parents=True);prior=root/'HD_P_postbox.fbx';prior.write_bytes(b'old owned primary')
    name=TREES[0]+'_LOD2';data=out/'hidamari-prop-data'/name
    if bad=='missing':(out/'exports/world.hidamari_props.export'/name/(name+'.fbx')).unlink()
    if bad=='texture':(data/(TREES[0]+'.png')).write_bytes(b'changed texture')
    if bad=='lod':
        path=data/'record.json';value=json.loads(path.read_text());value['level'][1]=1;atomic_json(path,value)
    if bad=='foreign':(root/'unknown.fbx').write_bytes(b'foreign')
    if bad.startswith('directory_'):
        filename={'directory_png':'HD_P_postbox.png','directory_fbx':'HD_P_phone_booth.fbx','directory_json':'props.json'}[bad]
        (root/filename).mkdir()
    if bad=='foreign_empty_directory':(root/'unknown').mkdir()
    if bad=='source_empty_directory':(data/'unknown').mkdir()
    if bad=='source_parent_link':
        source=out/'hidamari-prop-data';moved=out/'moved-prop-data';source.rename(moved);source.symlink_to(moved,target_is_directory=True)
    if bad=='stale_source':
        path=out/'exports/world.hidamari_props.export'/name/'export.json'
        value=json.loads(path.read_text());value['metadata']['geometry_sha256']='a'*64;atomic_json(path,value)
    if bad=='link':
        path=data/(TREES[0]+'.png');path.unlink();path.symlink_to(prior)
    before={p:p.read_bytes() if p.is_file() else None for p in root.iterdir()}
    with pytest.raises((ValueError,FileNotFoundError)):assemble(out)
    assert {p:p.read_bytes() if p.is_file() else None for p in root.iterdir()}==before
    assert not (out/'hidamari/assembled-props').exists()
