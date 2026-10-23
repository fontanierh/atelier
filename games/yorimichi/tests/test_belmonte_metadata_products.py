"""Scene views and moved runtime/material functions preserve the existing authored behavior."""
import ast
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from atelier.export_manifest import sha

GAME=Path(__file__).resolve().parents[1]
LIBRARY=GAME/'assets/belmonte'
DATA=json.loads((LIBRARY/'source.json').read_text())


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return tuple(importlib.import_module('belmonte.'+key) for key in
                 ('scene_inputs','runtime_layout','material_preparation','prepare_materials'))


def test_separate_scene_views_stop_unconsumed_geometry_sign_and_material_changes(tmp_path,modules):
    views,*_=modules;source=tmp_path/'source.json';source.write_text(json.dumps(DATA));root=tmp_path/'views'
    first=views.publish(source,root)
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.json') if p.name!='inventory.json'}
    changed=deepcopy(DATA);changed['signs'][0]['text']='Edited sign';source.write_text(json.dumps(changed));views.publish(source,root)
    assert (root/'materials.json').stat().st_mtime_ns==before['materials.json'][1]
    assert (root/'planting.json').stat().st_mtime_ns==before['planting.json'][1]
    assert (root/'runtime.json').read_bytes()!=before['runtime.json'][0]
    changed=deepcopy(DATA);changed['meshes'][0]['sha256']='0'*64
    current=views.project(changed)
    assert current['planting']==first['planting'] and current['materials']==first['materials']


@pytest.mark.parametrize('fault',['foreign','link','unrecorded'])
def test_scene_view_preflight_preserves_owned_and_external_bytes(tmp_path,modules,fault):
    views,*_=modules;source=tmp_path/'source.json';source.write_text(json.dumps(DATA));root=tmp_path/'views'
    views.publish(source,root);before=(root/'inventory.json').read_bytes()
    outside=tmp_path/'outside';outside.write_bytes(b'keep')
    if fault=='foreign':(root/'Unexpected').write_bytes(b'keep')
    if fault=='link':(root/'runtime.json').unlink();(root/'runtime.json').symlink_to(outside)
    if fault=='unrecorded':(root/'inventory.json').unlink()
    with pytest.raises(ValueError):views.publish(source,root)
    assert outside.read_bytes()==b'keep'
    if fault!='unrecorded':assert (root/'inventory.json').read_bytes()==before


def test_moved_runtime_declarations_match_complete_original_ast_after_explicit_data_binding(modules):
    _,runtime,*_=modules
    witness=json.loads((GAME/'tests/fixtures/belmonte-runtime-layout-source.json').read_text())
    assert witness['revision']=='283329c07'
    code=ast.parse(Path(runtime.__file__).read_text())
    for name,value in witness['declarations'].items():
        assert hashlib.sha256(value['source'].encode()).hexdigest()==value['sha256']
        old=ast.parse(value['source']).body[0]
        current=deepcopy(next(node for node in code.body if (isinstance(node,ast.FunctionDef) and node.name==name)
            or isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)))
        if name=='osteria_landing':
            current.args.args=[];current.body.insert(1,ast.parse('data = source.manifest()').body[0])
        elif name=='tv_spots':
            current.args.defaults=[ast.Constant(value=None)];current.body.insert(1,ast.parse('data = data or source.manifest()').body[0])
        elif name=='map_zones':
            current.args.args=current.args.args[:1]
            calls=[n for n in ast.walk(current) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='osteria_landing']
            assert len(calls)==1 and ast.unparse(calls[0].args[0])=='data';calls[0].args=[]
        assert ast.dump(current,include_attributes=False)==ast.dump(old,include_attributes=False),name


def test_actual_material_library_matches_original_report_and_every_png_byte(tmp_path,modules):
    views,_,materials,prepared=modules
    witness=json.loads((GAME/'tests/fixtures/belmonte-material-source.json').read_text())
    assert witness['revision']=='283329c07' and hashlib.sha256(witness['source'].encode()).hexdigest()==witness['sha256']
    from belmonte.terrain_palette import TERRAIN_LAYERS
    old=tmp_path/'old';(old/'textures').mkdir(parents=True)
    namespace=dict(hashlib=hashlib,np=np,json=json,Image=Image,OUT=old,
        yori=SimpleNamespace(ASSETS=GAME/'assets'),source=SimpleNamespace(LIBRARY=LIBRARY,sha=sha,TERRAIN_LAYERS=TERRAIN_LAYERS))
    exec(compile(witness['source'],'immutable-original-material-preparation','exec'),namespace)
    expected=namespace['finish_surfaces'](DATA)
    view=tmp_path/'views';source=tmp_path/'source.json';source.write_text(json.dumps(DATA));views.publish(source,view)
    result=prepared.prepare(view/'materials.json',tmp_path/'new',assets=GAME/'assets',library=LIBRARY)
    assert result==expected
    expected_files={p.name:p.read_bytes() for p in (old/'textures').iterdir()}
    assert {p.name:p.read_bytes() for p in (tmp_path/'new/textures').iterdir()}==expected_files
    assert prepared.validate(tmp_path/'new')==expected


def test_direct_source_module_loading_does_not_require_a_prior_region_import(tmp_path):
    script="""import importlib.util,sys
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('isolated_source',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert len(module.manifest()['meshes'])==288
assert len(module.TERRAIN_LAYERS)==4
"""
    result=subprocess.run([sys.executable,'-I','-c',script,str(GAME/'world/regions/belmonte/source.py')],
        cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def small_material_view(tmp_path,count=1):
    selected={};textures={};used=set()
    for key,value in DATA['materials'].items():
        texture=value['textures'].get('BaseColor') or value['textures'].get('DryColor')
        if not texture or 'terrain_' in key or texture in used:continue
        used.add(texture);selected[key]=value;textures[texture]=DATA['textures'][texture]
        if len(selected)==count:break
    path=tmp_path/'materials.json'
    path.write_text(json.dumps(dict(schema=1,view='materials',data=dict(materials=selected,textures=textures))))
    return path


@pytest.mark.parametrize('fault',['foreign','link','stale_source'])
def test_material_preflight_and_source_failure_preserve_existing_library(tmp_path,modules,fault):
    *_,prepared=modules;view=small_material_view(tmp_path);root=tmp_path/'library'
    prepared.prepare(view,root,assets=GAME/'assets',library=LIBRARY)
    before=(root/'materials.json').read_bytes();outside=tmp_path/'outside';outside.write_bytes(b'keep')
    if fault=='foreign':(root/'textures/Foreign.png').write_bytes(b'keep')
    if fault=='link':
        path=next((root/'textures').iterdir());path.unlink();path.symlink_to(outside)
    if fault=='stale_source':
        data=json.loads(view.read_text());next(iter(data['data']['textures'].values()))['sha256']='0'*64
        view.write_text(json.dumps(data))
    with pytest.raises((ValueError,AssertionError)):
        prepared.prepare(view,root,assets=GAME/'assets',library=LIBRARY)
    assert outside.read_bytes()==b'keep' and (root/'materials.json').read_bytes()==before
    if fault=='foreign':assert (root/'textures/Foreign.png').read_bytes()==b'keep'


def test_material_removal_retires_only_previously_owned_unused_image(tmp_path,modules):
    *_,prepared=modules;view=small_material_view(tmp_path,count=2);root=tmp_path/'library'
    first=prepared.prepare(view,root,assets=GAME/'assets',library=LIBRARY)
    old={row['texture'] for row in first.values()};assert len(old)==2
    view=small_material_view(tmp_path,count=1)
    second=prepared.prepare(view,root,assets=GAME/'assets',library=LIBRARY)
    current={row['texture'] for row in second.values()}
    assert {path.name for path in (root/'textures').iterdir()}==current
    assert len(old-current)==1 and not (root/prepared.JOURNAL).exists()
    assert prepared.validate(root)==second


def test_runtime_groups_preserve_original_full_scene_and_parent_material_groups(modules):
    from belmonte.runtime_groups import groups
    witness=json.loads((GAME/'tests/fixtures/belmonte-runtime-groups-source.json').read_text())
    assert witness['revision']=='283329c07'
    assert hashlib.sha256(witness['source'].encode()).hexdigest()==witness['sha256']
    meshes=deepcopy(DATA['meshes'])
    materials={key:dict(name='MI_'+str(index)) for index,key in enumerate(DATA['materials'])}
    by_asset={row['source_asset']:[(row,list(range(len(row['slots']))),True)] for row in meshes}
    # These two compact children share retained slots but keep distinct authored
    # parent groups, matching the original parent cull/material policy.
    parent=next(row for row in meshes if len(row['slots'])>1)
    child=dict(parent,name=parent['name']+'_PieceWitness',parent_material_slots=[0,1],parent_bounds_m=parent['bounds_m'])
    meshes.append(child);by_asset[parent['source_asset']]=[(child,[0],False)]
    extra=[dict(name='SM_BM_NorthApron',bounds_m=[[-1.,-1.,0.],[1.,1.,0.]])]
    meshes.extend(extra)
    original_materials=deepcopy(materials)
    namespace=dict(data=DATA,materials=original_materials,by_asset=by_asset,meshes=meshes,extra=extra,np=np)
    exec(compile(witness['source'],'immutable-original-runtime-groups','exec'),namespace)
    actual=groups(DATA,materials,by_asset,meshes,extra)
    assert actual==namespace['groups'] and materials==original_materials
    current=ast.parse(__import__('inspect').getsource(groups)).body[0]
    assert ast.dump(ast.Module(body=current.body[:-1],type_ignores=[]),include_attributes=False)==ast.dump(ast.parse(witness['source']),include_attributes=False)
