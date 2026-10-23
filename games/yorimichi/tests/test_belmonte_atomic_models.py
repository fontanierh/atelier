"""Committed models become lossless source data before independent atomic exports."""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import encoded_glb
from atelier.gltf import glb_pack,glb_parts
from atelier.build import Python,check_modules

GAME=Path(__file__).resolve().parents[1]
LIBRARY=GAME/'assets/belmonte'
SOURCE=json.loads((LIBRARY/'source.json').read_text())
STATIC=[row for row in SOURCE['meshes'] if not row['name'].startswith(('SM_BM_BT_Terrain_','SM_BM_North'))]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    monkeypatch.syspath_prepend(str(GAME/'world'))
    return tuple(importlib.import_module('belmonte.'+key) for key in ('model_sources','plan_model'))


def test_actual_catalogue_projects_each_geometry_without_placements_or_siblings(tmp_path,modules):
    definitions,_=modules
    source=tmp_path/'catalogue.json';source.write_text(json.dumps(SOURCE))
    root=tmp_path/'definitions';definitions.publish(source,root)
    assert len(list(root.glob('SM_BM_*.json')))==288
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('SM_BM_*.json')}
    changed=deepcopy(SOURCE);changed['placements'][0]['transform']['translation_cm'][0]+=1
    source.write_text(json.dumps(changed));definitions.publish(source,root)
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('SM_BM_*.json')}
    selected=changed['meshes'][0];selected['bounds_m'][0][0]-=1
    source.write_text(json.dumps(changed));definitions.publish(source,root)
    modified=[p.stem for p in root.glob('SM_BM_*.json') if p.read_bytes()!=before[p.name][0]]
    assert modified==[selected['name']]
    assert all(p.stat().st_mtime_ns==before[p.name][1] for p in root.glob('SM_BM_*.json') if p.stem!=selected['name'])


@pytest.mark.parametrize('fault',['alias','foreign','link','changed_retirement'])
def test_definition_preflight_refuses_before_any_owned_or_external_write(tmp_path,modules,fault):
    definitions,_=modules;value=dict(meshes=deepcopy(STATIC[:2]))
    source=tmp_path/'catalogue.json';source.write_text(json.dumps(value));root=tmp_path/'definitions'
    definitions.publish(source,root);before=(root/'inventory.json').read_bytes()
    outside=tmp_path/'external';outside.write_bytes(b'preserve')
    if fault=='alias':value['meshes'].append(deepcopy(value['meshes'][0]))
    if fault=='foreign':(root/'Foreign.json').write_bytes(b'preserve')
    if fault=='link':
        p=root/(value['meshes'][0]['name']+'.json');p.unlink();p.symlink_to(outside)
    if fault=='changed_retirement':
        removed=value['meshes'].pop();(root/(removed['name']+'.json')).write_text('{}')
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError):definitions.publish(source,root)
    assert outside.read_bytes()==b'preserve' and (root/'inventory.json').read_bytes()==before


EXAMPLES=[next(row for row in STATIC if row['triangles']<1000 and row.get('collision')),
          *[row for row in STATIC if row['triangles']>32768]]


@pytest.mark.parametrize('entry',EXAMPLES,ids=lambda row:row['name'])
def test_actual_small_and_all_large_static_models_preserve_source_and_hull_bytes(tmp_path,modules,entry):
    definitions,planner=modules
    definition=tmp_path/(entry['name']+'.json')
    definition.write_text(json.dumps(definitions.project(dict(meshes=[entry]))[entry['name']]))
    root=tmp_path/'plan'
    value=planner.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(LIBRARY),'--output',str(root)])
    renders=[row for row in value['pieces'] if row['role']=='render']
    assert sum(row['triangles'] for row in renders)==entry['triangles']
    assert max(row['triangles'] for row in value['pieces'])<=32768
    assert sum(bool(encoded_glb.read(root/row['payload'])[0]['metadata']['entry'].get('collision')) for row in renders)==bool(entry.get('collision'))
    if entry['triangles']<=32768:
        assert len(renders)==1
        assert encoded_glb.read(root/renders[0]['payload'])[1]==(LIBRARY/entry['path']).read_bytes()
    hulls=[row for row in value['pieces'] if row['role']=='collision']
    assert len(hulls)==bool(entry.get('collision'))
    if hulls:assert encoded_glb.read(root/hulls[0]['payload'])[1]==(LIBRARY/entry['collision']['path']).read_bytes()
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}
    planner.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(LIBRARY),'--output',str(root)])
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('*.mesh')}


def test_selected_model_never_reads_the_global_catalogue_or_sibling_bytes(tmp_path,modules,monkeypatch):
    definitions,planner=modules;entry=deepcopy(EXAMPLES[0])
    definition=tmp_path/'selected.json';definition.write_text(json.dumps(definitions.project(dict(meshes=[entry]))[entry['name']]))
    allowed={LIBRARY/entry['path'],LIBRARY/entry['collision']['path']};read=Path.read_bytes;seen=set()
    def limited(path):
        if path.is_relative_to(LIBRARY):
            assert path in allowed;seen.add(path)
        return read(path)
    monkeypatch.setattr(Path,'read_bytes',limited)
    planner.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(LIBRARY),'--output',str(tmp_path/'plan')])
    assert seen==allowed


def test_own_encoded_source_edit_changes_only_selected_model_and_preserves_collision(tmp_path,modules):
    definitions,planner=modules;entry=deepcopy(EXAMPLES[0]);library=tmp_path/'library'
    (library/'meshes').mkdir(parents=True)
    for row in (entry,entry['collision']):(library/row['path']).write_bytes((LIBRARY/row['path']).read_bytes())
    definition=tmp_path/'selected.json'
    def run():
        definition.write_text(json.dumps(definitions.project(dict(meshes=[entry]))[entry['name']]))
        return planner.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(library),'--output',str(tmp_path/'plan')])
    first=run();before={row['name']:(tmp_path/'plan'/row['payload']).read_bytes() for row in first['pieces']}
    # Document-only glTF source change is sufficient to prove exact byte identity,
    # while vertex conservation is independently covered by gltf_partition tests.
    path=library/entry['path'];doc,binary=glb_parts(path.read_bytes());doc.setdefault('extras',{})['atomic_edit']='selected'
    path.write_bytes(glb_pack(doc,binary));entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    run()
    assert (tmp_path/'plan'/(entry['name']+'.mesh')).read_bytes()!=before[entry['name']]
    assert (tmp_path/'plan'/(entry['name']+'_Collision.mesh')).read_bytes()==before[entry['name']+'_Collision']


def test_complete_static_graph_has_one_selected_definition_and_source_per_planner(tmp_path,modules):
    spec=importlib.util.spec_from_file_location('belmonte_atomic_graph_test',GAME/'belmonte_atomic_build.py')
    recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
    steps=recipe.model_steps(SimpleNamespace(out=tmp_path.resolve()))
    check_modules(steps)
    definitions=steps[0]
    assert definitions.name=='world.belmonte.model_definitions' and definitions.cache
    assert len(definitions.products)==289
    planners=[step for step in steps if '.geometry.' in step.name]
    assert len(planners)==232
    for step in planners:
        key=step.name.rsplit('.',1)[1]
        entry=next(row for row in STATIC if row['name']==key)
        assert step.reads==['belmonte.model_definition.'+key]
        assert LIBRARY/'source.json' not in step.inputs
        assert LIBRARY/entry['path'] in step.inputs
        assert isinstance(step.commands[0],Python) and step.cache and step.heavy
        assert all(path.name!='terrain.py' for path in step.inputs)
        assert not any(path.is_relative_to(LIBRARY/'meshes') and path.name not in
                       {Path(entry['path']).name,Path(entry.get('collision',{}).get('path','')).name}
                       for path in step.inputs)
