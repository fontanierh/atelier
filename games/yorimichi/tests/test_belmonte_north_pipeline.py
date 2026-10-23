"""Separate construction/data stages preserve the original shared terrain behavior."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    pipeline=importlib.import_module('belmonte.north_pipeline')
    earthworks=importlib.import_module('train.earthworks')
    monkeypatch.setattr(earthworks,'line',lambda:None)
    monkeypatch.setattr(pipeline,'joins',lambda:[(0,0.)])
    return pipeline,earthworks


def inputs(tmp_path,pipeline):
    from test_belmonte_seam_data import terrains
    meshes=terrains()
    for owner,mesh in meshes.items():pipeline.mesh_data.write(tmp_path/'raw'/(owner+'.npz'),mesh,owner=owner)
    faces=np.array([[[-10000,-10000,0],[10000,-10000,0],[10000,10000,0]],
                    [[-10000,-10000,0],[10000,10000,0],[-10000,10000,0]]],float)
    palette=tmp_path/'BelmonteValleyColours-natural.npz'
    pipeline.query_arrays.write(palette,faces,np.tile([.1,.2,.05],(2,3,1)),owner='BelmonteValleyColours',stage='natural')
    return meshes,palette


def test_actual_numeric_pipeline_matches_joint_stitch_then_paint_encoding(tmp_path,modules):
    pipeline,earthworks=modules;meshes,palette=inputs(tmp_path,pipeline)
    original=deepcopy(meshes)
    earthworks.stitch(list(original.values()),pipeline.L.ORIGIN,[(0,0.)],whole_seam=True)
    # Test meshes are local at x=0; keep the original origin's exact arithmetic
    # in both paths rather than forcing a replacement frame.
    arguments=['--mode','boundary','--output',str(tmp_path/'natural-seams')]
    for owner in pipeline.OWNERS:arguments.extend(('--input',str(tmp_path/'raw'/(owner+'.npz'))))
    pipeline.main(arguments)
    for owner in pipeline.OWNERS:
        pipeline.main(['--mode','natural','--owner',owner,'--input',str(tmp_path/'raw'/(owner+'.npz')),
            '--seam',str(tmp_path/'natural-seams'/(owner+'.json')),
            '--query',str(tmp_path/'natural-query'/(owner+'.surface')),
            '--output',str(tmp_path/'natural'/(owner+'.npz'))])
        pipeline.surface_data.read(tmp_path/'natural-query'/(owner+'.surface'),owner=owner,stage='natural')
        with pytest.raises(ValueError):pipeline.surface_data.read(tmp_path/'natural-query'/(owner+'.surface'),owner=owner)
        pipeline.main(['--mode','carve','--owner',owner,'--input',str(tmp_path/'natural'/(owner+'.npz')),
            '--output',str(tmp_path/'carved'/(owner+'.npz'))])
    arguments=['--mode','boundary','--output',str(tmp_path/'final-seams')]
    for owner in pipeline.OWNERS:arguments.extend(('--input',str(tmp_path/'carved'/(owner+'.npz'))))
    pipeline.main(arguments)
    earthworks.stitch(list(original.values()),pipeline.L.ORIGIN,[(0,0.)],whole_seam=True)
    from hippodrome.build import encoded_glb
    from belmonte.appearance import paint_join_data
    values=pipeline.query_arrays.read(palette,owner='BelmonteValleyColours',stage='natural')
    colour_surface=pipeline.source.Surface(values['faces'],values['values'])
    for owner in pipeline.OWNERS:
        target=tmp_path/'final'/(owner+'.surface')
        pipeline.main(['--mode','final','--owner',owner,'--input',str(tmp_path/'carved'/(owner+'.npz')),
            '--seam',str(tmp_path/'final-seams'/(owner+'.json')),'--palette',str(palette),'--output',str(target)])
        mesh=original[owner]
        data,_=encoded_glb(owner,mesh.p,mesh.n,mesh.t,mesh.i,'BM_000_Ground')
        expected=paint_join_data(data,owner,mesh,palette=colour_surface)
        assert pipeline.surface_data.read(target,owner=owner)[1]==expected


def test_natural_stage_checks_both_destinations_before_writing_owned_mesh(tmp_path,modules):
    pipeline,_=modules;inputs(tmp_path,pipeline);owner=pipeline.OWNERS[0]
    args=['--mode','boundary','--output',str(tmp_path/'seams')]
    for key in pipeline.OWNERS:args.extend(('--input',str(tmp_path/'raw'/(key+'.npz'))))
    pipeline.main(args)
    outside=tmp_path/'outside';outside.write_bytes(b'keep');query=tmp_path/(owner+'.surface');query.symlink_to(outside)
    output=tmp_path/'natural'/(owner+'.npz')
    with pytest.raises(ValueError,match='regular'):
        pipeline.main(['--mode','natural','--owner',owner,'--input',str(tmp_path/'raw'/(owner+'.npz')),
            '--seam',str(tmp_path/'seams'/(owner+'.json')),'--query',str(query),'--output',str(output)])
    assert not output.exists() and outside.read_bytes()==b'keep'


def test_carve_persisted_mesh_matches_original_mutable_mesh_with_active_line(tmp_path,modules,monkeypatch):
    from types import SimpleNamespace
    from test_belmonte_earthworks import made_up_line
    from hidamari import mountains
    pipeline,earthworks=modules
    monkeypatch.setattr(earthworks,'line',made_up_line)
    monkeypatch.setattr(pipeline.L,'ORIGIN',(0.,0.,0.))
    monkeypatch.setattr(pipeline.L,'BOUNDS',(-1000.,-1000.,1000.,1000.))
    monkeypatch.setattr(mountains,'BOUNDS',(10000.,10000.,11000.,11000.))
    mesh=SimpleNamespace(p=[(40.,-10.,120.),(60.,-10.,120.),(60.,10.,120.),(40.,10.,120.)],
        n=[(0.,0.,1.)]*4,t=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)],i=[0,1,2,0,2,3])
    original=deepcopy(mesh);owner=pipeline.OWNERS[0]
    source=tmp_path/'natural'/(owner+'.npz');target=tmp_path/'carve'/(owner+'.npz')
    pipeline.mesh_data.write(source,mesh,owner=owner)
    earthworks.quads(original,pipeline.L.ORIGIN,2.5,
        hidden=lambda x,y:(x>mountains.BOUNDS[0])&(x<mountains.BOUNDS[2])&(y>mountains.BOUNDS[1])&(y<pipeline.L.SOUTH_JOIN),
        weight=lambda x,y:earthworks.seam_weight(x,y,pipeline.L.BOUNDS))
    assert len(original.i)>len(mesh.i)
    pipeline.main(['--mode','carve','--owner',owner,'--input',str(source),'--output',str(target)])
    actual=pipeline.mesh_data.arrays(pipeline.mesh_data.read(target,owner=owner))
    expected=pipeline.mesh_data.arrays(original)
    assert actual.keys()==expected.keys()
    for key in expected:assert actual[key].tobytes()==expected[key].tobytes()


@pytest.mark.parametrize('apron',[False,True])
def test_raw_constructor_invokes_only_selected_factory_with_explicit_context(tmp_path,modules,monkeypatch,apron):
    pipeline,_=modules
    from test_belmonte_north_graph import inputs as world_inputs
    from test_belmonte_seam_data import terrains
    from belmonte import north_context
    from hidamari import layout
    world,heightmap,farhills=world_inputs(tmp_path)
    monkeypatch.setattr(layout.yori,'OUT',tmp_path)
    monkeypatch.setattr(layout,'H',None);monkeypatch.setattr(layout,'BACKDROP',None)
    monkeypatch.setattr(layout.street_height,'start',None,raising=False)
    context=tmp_path/'context.json'
    context.write_text(json.dumps(north_context.project(world,heightmap,farhills)))
    owner=pipeline.OWNERS[0 if apron else 1];geometry=terrains()[owner];called=[]
    args=['--output',str(tmp_path/'raw'/(owner+'.npz')),'--context',str(context),
          '--heightmap',str(heightmap),'--farhills',str(farhills)]
    if apron:
        path=tmp_path/'BelmonteValley-natural.npz'
        faces=np.array([[[0,0,0],[1,0,0],[0,1,0]]],float)
        pipeline.query_arrays.write(path,faces,owner='BelmonteValley',stage='natural')
        args.extend(('--valley',str(path),'--report',str(tmp_path/'report.json')))
        def factory(*,surface):
            called.append(surface.faces.tobytes());return geometry,dict(boundary_samples=3)
    else:
        def factory():called.append(owner);return geometry
    pipeline.raw(owner,factory,args,valley=apron)
    assert len(called)==1
    actual=pipeline.mesh_data.read(tmp_path/'raw'/(owner+'.npz'),owner=owner)
    for key,value in pipeline.mesh_data.arrays(geometry).items():assert pipeline.mesh_data.arrays(actual)[key].tobytes()==value.tobytes()
