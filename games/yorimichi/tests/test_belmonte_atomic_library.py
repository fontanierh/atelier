"""Final file assembly reads actual independently published model receipts."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest

from atelier import encoded_glb,export_assembly
from atelier.atomic_files import atomic_json

GAME=Path(__file__).resolve().parents[1]
LIBRARY=GAME/'assets/belmonte'
SOURCE=json.loads((LIBRARY/'source.json').read_text())
STATIC=[row for row in SOURCE['meshes'] if not row['name'].startswith('SM_BM_BT_Terrain_')]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    monkeypatch.syspath_prepend(str(GAME/'world'))
    return tuple(importlib.import_module('belmonte.'+key) for key in ('atomic_library','model_sources','plan_model'))


def publish(tmp_path,entries,modules):
    reader,definitions,planner=modules
    parents={};ownership={};items=[]
    for entry in entries:
        key=entry['name'];definition=tmp_path/(key+'.json')
        atomic_json(definition,definitions.project(dict(meshes=[entry]))[key])
        root=tmp_path/'plans'/key
        plan=planner.main(['--asset',key,'--definition',str(definition),'--library',str(LIBRARY),'--output',str(root)])
        parents[key]=[row['name'] for row in plan['pieces']]
        ownership[key]={field:plan[field] for field in ('kind','source_triangles','source_render_triangles','source_collision_triangles','pieces')}
        for row in plan['pieces']:
            exported=tmp_path/'exports'/row['name'];encoded_glb.export(root/row['payload'],exported)
            items.append(export_assembly.Item(row['name'],exported))
    library=tmp_path/'assembled';result=export_assembly.assemble(items,library/'assets')
    atomic_json(library/'logical-pieces.json',dict(schema=1,parents=parents,ownership=ownership,exports=[r['asset'] for r in result['exports']]))
    return library


def test_actual_small_whole_hull_and_large_model_assemble_with_original_bindings(tmp_path,modules):
    entries=[next(row for row in STATIC if row['triangles']<1000 and row.get('collision')),
             max(STATIC,key=lambda row:row['triangles'])]
    root=publish(tmp_path,entries,modules);reader=modules[0]
    value=reader.read(root,expected=[r['name'] for r in entries],original={r['name']:r for r in entries})
    assert sum(row['triangles'] for row in value['meshes'])==sum(row['triangles'] for row in entries)
    assert max(row['triangles'] for row in value['meshes'])<=32768
    for entry in entries:
        rows=value['by_parent'][entry['name']]
        assert all(row['source_asset']==entry['source_asset'] for row,_,_ in rows)
        assert sum(bool(row.get('collision')) for row,_,_ in rows)==bool(entry.get('collision'))
        assert all(all(type(slot) is int for slot in slots) for _,slots,_ in rows)
    first=value['by_parent'][entries[0]['name']][0]
    assert first[1] and all(type(slot) is int for slot in first[1])
    assert value['files'][entries[0]['name']+'.glb'].read_bytes()==(LIBRARY/entries[0]['path']).read_bytes()


@pytest.mark.parametrize('fault',['missing_parent','duplicate_child','wrong_count','changed_bytes','foreign','wrong_collision_owner'])
def test_library_refuses_incomplete_or_mutated_assembly(tmp_path,modules,fault):
    entry=next(row for row in STATIC if row['triangles']<1000 and row.get('collision'))
    root=publish(tmp_path,[entry],modules);path=root/'logical-pieces.json';logical=json.loads(path.read_text())
    if fault=='missing_parent':logical['parents']={}
    elif fault=='duplicate_child':logical['parents'][entry['name']].append(entry['name'])
    elif fault=='wrong_count':logical['ownership'][entry['name']]['source_render_triangles']+=1
    elif fault=='changed_bytes':
        primary=root/'assets'/(entry['name']+'.glb');primary.write_bytes(primary.read_bytes()+b'changed')
    elif fault=='foreign':(root/'assets/Foreign.glb').write_bytes(b'keep')
    elif fault=='wrong_collision_owner':
        manifest=root/'assets/manifest.json';data=json.loads(manifest.read_text())
        collision=next(row for row in data['exports'] if row['metadata']['role']=='collision')
        collision['metadata']['parent']='Other';atomic_json(manifest,data)
    atomic_json(path,logical)
    with pytest.raises((ValueError,KeyError)):
        modules[0].read(root,expected=[entry['name']],original={entry['name']:deepcopy(entry)})
