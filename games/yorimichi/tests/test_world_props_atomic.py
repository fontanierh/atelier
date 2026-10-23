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


def test_skydome_public_original_packet_is_exact_complete_and_explicitly_consumed(tmp_path):
    from atelier import mesh_ir
    root=GAME/'assets/props/skydome';provenance=json.loads((root/'provenance.json').read_text())
    raw=(root/'mesh.source.npz').read_bytes();meta,piece=mesh_ir.decode(raw)
    assert hashlib.sha256(raw).hexdigest()==provenance['packet']['sha256']=='59994b166caf603ace942ff7b8444c5bebe4a6a74f0e5939707551ac382dde73'
    assert hashlib.sha256((root/'source.fbx').read_bytes()).hexdigest()==provenance['original_export']['sha256']
    assert piece['triangles']==2208 and len(piece['faces'])==1152 and meta['slots']==['Sky']
    values=SOURCES.project(OLD.read_text())
    assert [key for key,row in values.items() if 'canonical_source' in row]==['SkyDome']
    recipe=load('world_prop_canonical_recipe',GAME/'props_atomic_build.py')
    steps=recipe.steps(SimpleNamespace(out=tmp_path.resolve()))
    for step in steps:
        if step.name.startswith('world.props.geometry.'):
            if step.name.endswith('.SkyDome'):
                assert root/'mesh.source.npz' in step.inputs and root/'provenance.json' in step.inputs
            else:assert root/'mesh.source.npz' not in step.inputs and root/'provenance.json' not in step.inputs


def test_changed_sphere_constructor_cannot_silently_keep_an_old_packet():
    with pytest.raises(ValueError,match='constructor changed'):
        SOURCES.project(OLD.read_text().replace('u_segments=48','u_segments=49'))


def test_skydome_constructor_authority_includes_empty_ast_fields_on_new_python(monkeypatch):
    import skydome_source
    original_dump=ast.dump
    def newer_dump(node,*,include_attributes=False,show_empty=False):
        assert show_empty, 'Python 3.13 default drops fields from the recorded complete AST'
        return original_dump(node,include_attributes=include_attributes)
    function=next(node for node in ast.parse(OLD.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='sky_dome')
    expected=skydome_source.reference(function)
    monkeypatch.setattr(ast,'dump',newer_dump)
    assert skydome_source.reference(function)==expected


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


def test_actual_proof_host_freezes_complete_inputs_before_native_admission(tmp_path,monkeypatch):
    host=load('world_prop_proof_host_test',GAME/'tests/native/run_world_props_equivalence.py')
    root=tmp_path.resolve();donor=root/'donor';textures=donor/'build/yorimichi/textures';textures.mkdir(parents=True)
    for row in SOURCES.MATERIALS.values():
        if row.get('texture'):(textures/row['texture']).write_bytes(b'bound-image-input')
    monkeypatch.setattr(host,'git',lambda *args,**kwargs:'' if args[0]=='status' else 'a'*40)
    monkeypatch.setattr(host.subprocess,'check_output',lambda argv,**kwargs:(GAME/'world'/argv[-1].rsplit('/',1)[-1]).read_bytes())
    monkeypatch.setattr(host.build,'Context',lambda *args:SimpleNamespace(env=lambda:{}))
    monkeypatch.setattr(host.build,'Blender',lambda *args,**kwargs:SimpleNamespace(argv=lambda ctx:['not-launched']))
    class AdmissionBoundary(Exception):pass
    observed=[]
    def boundary(argv,report,**kwargs):
        spec=json.loads((root/'proof/spec.json').read_text())
        assert len(spec['sources'])==14 and set(spec['sources'])==set(SOURCES.BUILDERS)
        assert len(list((root/'proof/textures').iterdir()))==16
        assert all(Path(path).is_file() and hashlib.sha256(Path(path).read_bytes()).hexdigest()==row['sha256']
                   for path,row in spec['inputs'].items())
        observed.append(spec)
        raise AdmissionBoundary
    monkeypatch.setattr(host.guarded,'run',boundary)
    monkeypatch.setattr(__import__('sys'),'argv',['proof-host','--donor',str(donor),'--output',str(root/'proof')])
    with pytest.raises(AdmissionBoundary):host.main()
    assert len(observed)==1
