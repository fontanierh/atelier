"""Run the real authoring wrapper and builder main without launching Blender or exporting."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]
WORLD = GAME/'world'


def fixture(tmp_path, monkeypatch, *, fail=None):
    output = tmp_path/'belmonte-train-authoring'
    builder = ModuleType('train.build')
    builder.OUT = tmp_path/'belmonte-train'
    builder.TEX = builder.OUT/'textures'
    coaches = [SimpleNamespace(name='restaurant', title='Restaurant'),
               SimpleNamespace(name='first-class', title='First class')]
    saved=[];sources=[];raw=[]
    collections={}
    def raw_export(*args, **kwargs):
        raw.append(True)
        raise AssertionError('Raw export invoked: old authoring wrapper reaches this path')
    builder.export_glb=raw_export
    def hide(obj):
        obj.hidden=False
        obj.hide_set=lambda value:setattr(obj,'hidden',value)
        return obj
    def construct(coach, images, *, source_sink=None):
        if source_sink is None:return builder.export_glb('oversized-combined.glb', [])
        title=''.join(p.title() for p in coach.name.split('-'))
        reservation=hide(SimpleNamespace(hide_render=True))
        lod2=hide(SimpleNamespace(hide_render=False))
        collision=hide(SimpleNamespace(hide_render=True))
        geometry=SimpleNamespace(vertices=[(1, 2, 3)], materials=['Actual-source-material'])
        collections.clear()
        collections.update({title+'_Reservations':SimpleNamespace(objects=[reservation],hide_render=False),
                            title+'_LOD2':SimpleNamespace(objects=[lod2],hide_render=True),
                            title+'_Collision':SimpleNamespace(objects=[collision],hide_render=True),
                            title+'_Shell':SimpleNamespace(objects=[geometry],hide_render=False)})
        placements=dict(frame=dict(up='Z'),placements=[dict(asset='table',x=1.,y=2.,z=3.,yaw=45.)],doors_runtime=['hinge'])
        info=dict(title=coach.title,mesh='SM_BT_'+title,triangles=dict(LOD0=33458,LOD1=12000,LOD2=400),
                  layout_checks=[],mesh_checks=['retained diagnostic'],materials=['Actual-source-material'])
        lod_sets={0:[geometry],1:[geometry],2:[lod2]}
        before=copy.deepcopy(info)
        sources.append(dict(coach=coach,info=before,placements=copy.deepcopy(placements),geometry=geometry))
        if fail=='construction':raise RuntimeError('construction failed')
        if fail=='export':return builder.export_glb('forbidden.glb',lod_sets[0])
        result=source_sink(coach,mesh=info['mesh'],lod_sets=lod_sets,placements=placements,info=info)
        assert info==before and geometry.vertices==[(1,2,3)] and geometry.materials==['Actual-source-material']
        return result
    builder.build=construct
    def save(**kwargs):
        name=Path(kwargs['filepath']).stem;title=''.join(p.title() for p in name.split('-'))
        assert collections[title+'_Reservations'].objects[0].hide_render is False
        assert collections[title+'_LOD2'].objects[0].hidden is True
        assert collections[title+'_LOD2'].hide_render is True
        assert collections[title+'_Collision'].hide_render is True
        assert len(collections[title+'_Shell'].objects)==1
        saved.append(kwargs)
        if fail=='save':raise RuntimeError('save failed')
        Path(kwargs['filepath']).write_bytes(b'complete scene test fixture')
        return {'FINISHED'}
    builder.bpy=SimpleNamespace(data=SimpleNamespace(collections=collections),ops=SimpleNamespace(wm=SimpleNamespace(
        read_factory_settings=lambda **kwargs:None,save_as_mainfile=save)))
    builder.FU=SimpleNamespace(stage=lambda path:0)
    builder.make_textures=lambda:{}
    builder.T=SimpleNamespace(JPEG=set())
    builder.L=SimpleNamespace(vehicles=lambda:coaches,restaurant=lambda:coaches[0],as_dict=lambda c:dict(frame={'up':'Z'}),
        envelope=lambda:dict(width=3),coupling=lambda:dict(pitch_m=24),CAIRO=dict(height=1.7),HUMAN=dict(height=1.8))
    builder.json=json;builder.hashlib=hashlib
    # Exercise the unmodified real main's staging, coach loop, manifest and checks.
    source=WORLD/'train/build.py'
    nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ('main','sha')]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),builder.__dict__)
    package=ModuleType('train');package.build=builder
    monkeypatch.setitem(sys.modules,'train',package)
    monkeypatch.setitem(sys.modules,'yori',SimpleNamespace(OUT=tmp_path))
    monkeypatch.setattr(sys,'path',list(sys.path))
    spec=importlib.util.spec_from_file_location('train_authoring_review_under_test',WORLD/'train/authoring_review.py')
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    originals=(builder.OUT,builder.TEX,builder.build,builder.export_glb)
    return wrapper,builder,output,saved,sources,raw,originals


def test_real_wrapper_saves_preexport_scene_placements_and_main_manifest(tmp_path,monkeypatch):
    wrapper,builder,output,saved,sources,raw,originals=fixture(tmp_path,monkeypatch)
    wrapper.main(['--output',str(output)])
    assert raw==[] and len(saved)==len(sources)==2
    assert (builder.OUT,builder.TEX,builder.build,builder.export_glb)==originals
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['frame']=={'up':'Z'} and manifest['coupling']=={'pitch_m':24}
    assert manifest['human_gauges']==dict(cairo={'height':1.7},adult={'height':1.8})
    for row,call in zip(sources,saved):
        coach=row['coach'];folder=output/coach.name;scene=folder/(coach.name+'.blend');placements=folder/(coach.name+'-placements.json')
        assert call==dict(filepath=str(scene),compress=True,relative_remap=True)
        assert json.loads(placements.read_text())==row['placements']
        actual=manifest['coaches'][coach.name]
        assert {k:v for k,v in actual.items() if k!='files'}==row['info']
        assert set(actual['files'])=={scene.name,placements.name}
        for path in (scene,placements):
            assert actual['files'][path.name]==dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert not list(output.rglob('*.glb')) and not list(output.rglob('*.fbx'))


@pytest.mark.parametrize('failure',['construction','save','export'])
def test_wrapper_restores_every_override_and_refuses_export_on_failures(tmp_path,monkeypatch,failure):
    wrapper,builder,output,saved,sources,raw,originals=fixture(tmp_path,monkeypatch,fail=failure)
    with pytest.raises(RuntimeError,match={'construction':'construction failed','save':'save failed','export':'must not export'}[failure]):
        wrapper.main(['--output',str(output)])
    assert raw==[]
    assert (builder.OUT,builder.TEX,builder.build,builder.export_glb)==originals
    assert not (output/'manifest.json').exists()
