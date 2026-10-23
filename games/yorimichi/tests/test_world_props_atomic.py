"""Original prop constructors keep their geometry/pivots and independent source/export keys."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier import build

GAME=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


SOURCES=load('world_prop_sources_test',GAME/'world/prop_sources.py')
OLD=GAME/'tests/fixtures/world-props-predecessor-283329c07.txt'


def test_source_authority_and_current_selected_constructor_bodies_match():
    assert hashlib.sha256(OLD.read_bytes()).hexdigest()=='dcdba009bbf0f001b4e309d327b42b74a286751740c895b904b1218eb51b4946'
    assert SOURCES.project(SOURCES.SOURCE.read_text())==SOURCES.project(OLD.read_text())
    assert len(SOURCES.BUILDERS)==14


def test_unrelated_constructor_and_palette_edits_leave_other_packets_unchanged(monkeypatch):
    text=OLD.read_text();original=SOURCES.project(text)
    edited=SOURCES.project(text.replace('length=2.0','length=2.25'))
    assert {key for key in original if original[key]!=edited[key]}=={'Guardrail'}
    monkeypatch.setitem(SOURCES.MATERIALS,'Rock',dict(color=(.1,.2,.3)))
    edited=SOURCES.project(text)
    assert {key for key in original if original[key]!=edited[key]}=={'Rock_A','Rock_B','Rock_C'}


def test_selected_birds_preserve_original_primitive_events_and_build_no_siblings():
    built=[]
    class Mesh:
        def __init__(self,name):self.name=name;self.events=[]
        def tube(self,*args,**kwargs):self.events.append(('tube',args,kwargs))
        def quad(self,*args,**kwargs):self.events.append(('quad',args,kwargs))
        def build(self):
            value=dict(name=self.name,events=self.events);built.append(value);return value
    scope=dict(Mesh=Mesh,MATS={name:name for name in ('Feather','FeatherDark','Vermilion')})
    tree=ast.parse(OLD.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='bird_parts')
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(OLD),'exec'),scope)
    original={row['name']:row for row in scope['bird_parts']()}
    values=SOURCES.project(OLD.read_text())
    for key in ('BirdBody','BirdWingL','BirdWingR'):
        built.clear();row=values[key];tree=ast.parse(row['program'])
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),key,'exec'),scope)
        actual=scope[row['builder']](key,*row['args'])
        assert actual==original[key] and built==[actual]


def test_actual_recipe_has_fourteen_cached_prop_planners_and_no_whole_export(tmp_path):
    ctx=SimpleNamespace(game='yorimichi',out=tmp_path.resolve(),logs=tmp_path/'logs',stamps=tmp_path/'stamps',uproject=None)
    steps=build.load_recipe('yorimichi').steps(ctx);by_name={step.name:step for step in steps}
    build.order(steps,['unreal.world'])
    planners=[step for step in steps if step.name.startswith('world.props.geometry.')]
    assert len(planners)==14 and all(step.cache for step in planners)
    assert 'props.library' in by_name['unreal.world'].reads
    assert by_name['world.props'].products[0].paths==(ctx.out/'props',)
    assert all(getattr(command,'script',None)!=GAME/'world/build_assets.py' for step in steps for command in step.commands)


@pytest.mark.parametrize('fault',[None,'missing','changed','link','foreign','duplicate','oversized'])
def test_native_preflight_refuses_incomplete_props_before_import(tmp_path,monkeypatch,fault):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    reader=load('world_prop_native_test',GAME/'unreal/Scripts/world_props.py')
    root=tmp_path/'props';assets=root/'assets';assets.mkdir(parents=True);rows=[]
    for key in reader.WORLD_PROPS:
        raw=key.encode();(assets/(key+'.fbx')).write_bytes(raw)
        rows.append(dict(asset=key,primary=key+'.fbx',triangles=1,sha256=hashlib.sha256(raw).hexdigest(),metadata=dict(collision_hulls=0)))
    (assets/'manifest.json').write_text('{}')
    if fault=='missing':rows.pop()
    elif fault=='changed':(assets/'Torii.fbx').write_bytes(b'changed')
    elif fault=='link':
        path=assets/'Torii.fbx';path.unlink();path.symlink_to(assets/'Leaf.fbx')
    elif fault=='foreign':(assets/'Foreign.fbx').write_bytes(b'foreign')
    elif fault=='duplicate':rows.append(rows[0])
    elif fault=='oversized':rows[0]['triangles']=32769
    (root/'manifest.json').write_text(json.dumps(dict(schema=1,complete=True,exports=rows)))
    if fault is None:
        assert set(reader.read(tmp_path))==set(reader.WORLD_PROPS)
        return
    with pytest.raises(ValueError):reader.read(tmp_path)
