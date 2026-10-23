"""Fault injection for the independent 48-export prop proof observer."""
import copy
import json
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('hidamari_prop_proof_test',HERE/'hidamari_prop_equivalence.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
spec=importlib.util.spec_from_file_location('hidamari_prop_source_fixture',HERE.parent/'test_atomic_equivalence.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


@pytest.mark.parametrize('field',['position','winding','normal','uv','color','material','matrix','smooth','channel'])
def test_every_ordered_source_corner_channel_and_frame_is_observed(field):
    piece=fixture.piece();matrix=copy.deepcopy(fixture.MATRIX)
    expected=proof.piece_signature(piece,['Rock','Wood'],matrix)
    if field=='position':piece['positions'][0,0]+=.01
    elif field=='winding':piece['faces'][0].reverse()
    elif field=='normal':piece['normals'][0,0]+=.01
    elif field=='uv':piece['uvs'][0][1][0,0]+=.01
    elif field=='color':piece['colours'][0][3][0,0]+=.01
    elif field=='material':piece['materials'][0]=1
    elif field=='matrix':matrix[0][3]=.01
    elif field=='smooth':piece['smooth'][0]=True
    else:piece['uvs'].pop()
    assert proof.piece_signature(piece,['Rock','Wood'],matrix)!=expected


def test_unused_positions_and_point_attributes_are_preserved_separately_from_corners():
    piece=fixture.piece();expected=proof.piece_signature(piece,['Rock','Wood'],fixture.MATRIX)
    piece['positions']=np.concatenate([piece['positions'],[[.2,.3,.4]]])
    name,domain,kind,values=piece['colours'][0]
    piece['colours'][0]=(name,domain,kind,np.concatenate([values,[[.1,.2,.3,.4]]]))
    observed=proof.piece_signature(piece,['Rock','Wood'],fixture.MATRIX)
    assert observed['positions']==expected['positions'] and observed['colours']==expected['colours']
    assert observed['all_positions']!=expected['all_positions'] and observed['point_colours']!=expected['point_colours']


@pytest.mark.parametrize('field',['geometry','smoothing','material_property','global_axis','pivot'])
def test_complete_serialized_fbx_fields_include_more_than_corner_counters(monkeypatch,field):
    tree=fixture.fbx_tree()
    monkeypatch.setitem(sys.modules,'io_scene_fbx',SimpleNamespace(parse_fbx=SimpleNamespace(parse=lambda path:(tree,7400))))
    expected=proof.fbx_fields('actual.fbx');objects=tree.elems[0].elems
    if field=='geometry':objects[0].elems[0].props[0][0]=.01
    elif field=='smoothing':objects[0].elems.append(SimpleNamespace(id=b'LayerElementSmoothing',props=[0],elems=[]))
    elif field=='material_property':objects[2].elems.append(SimpleNamespace(id=b'Shininess',props=[.1],elems=[]))
    elif field=='global_axis':tree.elems[2].elems[0].elems[0].props[4]=1
    else:objects[1].elems[0].elems[1].props[4]=.01
    assert proof.fbx_fields('actual.fbx')!=expected


def test_object_uids_are_local_but_complete_numeric_arrays_are_not(monkeypatch):
    tree=fixture.fbx_tree()
    monkeypatch.setitem(sys.modules,'io_scene_fbx',SimpleNamespace(parse_fbx=SimpleNamespace(parse=lambda path:(tree,7400))))
    expected=proof.fbx_fields('actual.fbx')
    for node in tree.elems[0].elems:node.props[0]+=1000
    for row in tree.elems[1].elems:
        row.props[1]+=1000;row.props[2]+=1000
    assert proof.fbx_fields('actual.fbx')==expected


def test_geometry_datablock_labels_follow_unique_actual_model_but_model_names_remain_exact(monkeypatch):
    tree=fixture.fbx_tree()
    monkeypatch.setitem(sys.modules,'io_scene_fbx',SimpleNamespace(parse_fbx=SimpleNamespace(parse=lambda path:(tree,7400))))
    expected=proof.fbx_fields('actual.fbx')
    tree.elems[0].elems[0].props[1]=b'Cube\x00\x01Geometry'
    assert proof.fbx_fields('actual.fbx')==expected
    tree.elems[0].elems[1].props[1]=b'OtherNativeName\x00\x01Model'
    assert proof.fbx_fields('actual.fbx')!=expected
    tree.elems[1].elems.pop(0)
    with pytest.raises(ValueError,match='unique actual Model'):proof.fbx_fields('actual.fbx')


@pytest.mark.parametrize('field',['missing','extra','duplicate'])
def test_complete_original_census_cannot_be_narrowed_or_invented(field):
    props=['P'+str(n) for n in range(32)];trees=['T'+str(n) for n in range(4)]
    assert len(proof.members(props,trees))==48
    if field=='missing':props.pop()
    elif field=='extra':props.append('foreign')
    else:props[-1]=props[0]
    with pytest.raises(ValueError):proof.members(props,trees)


@pytest.mark.parametrize('field',['source_lods','render_lods','cooked','hulls','policy','settings','source_presence'])
def test_native_readback_never_weakens_geometry_lods_collision_or_policy(tmp_path,monkeypatch,field):
    props=['P'+str(n) for n in range(32)];trees=['T'+str(n) for n in range(4)]
    row=dict(policy_scope='fixture',**{key:[] for key in ('source_lods','render_lods','cooked','hulls','policy','settings','source_presence')})
    policy=whole_policy(tmp_path)
    row.update(component_policies=[dict(path=str(policy),sha256=proof.sha(policy))],meshes=['/Game/M.M'])
    before={name:copy.deepcopy(row) for name in proof.members(props,trees)};after=copy.deepcopy(before)
    monkeypatch.setattr(proof,'native_raw_set',lambda descriptor,key:descriptor)
    accepted=proof.compare_native(before,after,props,trees)
    assert accepted['native_geometry_complete'] and not accepted['native_complete'] and not accepted['complete']
    after[props[0]][field]=['changed']
    with pytest.raises(ValueError,match='differs'):proof.compare_native(before,after,props,trees)


def whole_policy(root):
    path=root/'policy.json'
    path.write_text(json.dumps(dict(mesh='/Game/M.M',component_bounds=dict(origin=[0,0,0],extent=[1,1,1],sphere_radius=1.2),
        mesh_bounds=[[-1,-1,-1],[1,1,1]],bounds_scale=1,lod_coordinated=False)))
    return path


@pytest.mark.parametrize('field',['sphere','extent','mesh_bounds','scale','missing'])
def test_whole_physical_bounds_are_never_normalized_as_spatial_pieces(tmp_path,field):
    path=whole_policy(tmp_path)
    def record():return dict(meshes=['/Game/M.M'],component_policies=[dict(path=str(path),sha256=proof.sha(path))])
    before=proof.whole_bounds(record());value=json.loads(path.read_text())
    if field=='sphere':value['component_bounds']['sphere_radius']+=.01
    elif field=='extent':value['component_bounds']['extent'][0]+=.01
    elif field=='mesh_bounds':value['mesh_bounds'][1][0]+=.01
    elif field=='scale':value['bounds_scale']=1.1
    else:value.pop('component_bounds')
    path.write_text(json.dumps(value))
    if field=='missing':
        with pytest.raises(ValueError):proof.whole_bounds(record())
    else:assert proof.whole_bounds(record())!=before
