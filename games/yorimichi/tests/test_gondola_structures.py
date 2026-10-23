"""Imported wall collision and final instance identities participate in fitting."""
import json
from pathlib import Path
import struct
import sys

import numpy as np
import pytest
from atelier.gltf import glb_pack

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
from gondola import structures
from gondola.clearance import StructureClearance


def write_triangle(path, points):
    path.parent.mkdir(parents=True,exist_ok=True)
    vertices=[(x,z,-y) for x,y,z in points]
    binary=b''.join(struct.pack('<3f',*p) for p in vertices)+struct.pack('<3H',0,1,2)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
         'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36},
                        {'buffer':0,'byteOffset':36,'byteLength':6}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'},
                      {'bufferView':1,'componentType':5123,'count':3,'type':'SCALAR'}],
         'nodes':[{'mesh':0}], 'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}]}
    path.write_bytes(glb_pack(doc,binary))


@pytest.fixture
def exported(tmp_path):
    folder=tmp_path/'belmonte';folder.mkdir()
    row={'asset':'/Game/Belmonte/Meshes/Wall.Wall','plant':False,'collision':True,
         'transforms':[{'translation_cm':[0.,0.,0.],'scale':[1.,1.,1.],'rotation_xyzw':[0.,0.,0.,1.]}]}
    (folder/'runtime.json').write_text(json.dumps({'origin_cm':[0,0,0],'groups':[row]}))
    (folder/'build-report.json').write_text(json.dumps({'meshes':[{'name':'Wall','path':'glb/Wall.glb',
        'collision':{'path':'meshes/Wall_Collision.glb'}}]}))
    write_triangle(folder/'glb/Wall.glb',[(1000,4500,0),(1001,4500,0),(1000,4501,1)])
    write_triangle(folder/'glb/Wall_Collision.glb',[(400,4500,0),(401,4500,0),(400,4501,1)])
    return tmp_path,row


def test_separate_collision_source_selects_an_otherwise_distant_visual(exported):
    folder,row=exported
    result=structures.inputs(folder)
    assert len(result['selection']['groups'])==1
    assert set(result['files'])=={'belmonte/glb/Wall.glb','belmonte/glb/Wall_Collision.glb'}
    old=result['files'].copy()
    write_triangle(folder/'belmonte/glb/Wall_Collision.glb',[(400,4500,0),(402,4500,0),(400,4501,2)])
    assert structures.inputs(folder)['files']!=old


def test_render_only_children_remain_in_actual_clearance_extraction_once(exported):
    from gondola import structure_probe
    folder, row = exported
    row['parent_collision'] = True
    child = dict(row, asset='/Game/Belmonte/Meshes/Second.Second', collision=False)
    root = folder/'belmonte'
    (root/'runtime.json').write_text(json.dumps({'origin_cm':[0,0,0],'groups':[row,child]}))
    report = json.loads((root/'build-report.json').read_text())
    report['meshes'].append({'name':'Second','path':'glb/Second.glb'})
    (root/'build-report.json').write_text(json.dumps(report))
    write_triangle(root/'glb/Second.glb',[(420,4500,0),(421,4500,0),(420,4501,1)])
    selection = structures.selected(folder)['groups']
    assert len(selection) == 2
    assert sorted(sorted(group['geometry']) for group in selection) == [['collision','visual'],['visual']]
    structure_probe.extract(folder)
    with np.load(folder/'gondola/world/structures.npz') as arrays:
        assert len(arrays['visual']) == 2
        assert len(arrays['collision']) == 1
        assert set(arrays['visual'][:,0,0]) == {420.,1000.}


@pytest.mark.parametrize('parent', [None, 1, 'yes', False])
def test_invalid_parent_collision_ownership_refuses(exported, parent):
    folder, row = exported
    row['parent_collision'] = parent
    (folder/'belmonte/runtime.json').write_text(json.dumps({'origin_cm':[0,0,0],'groups':[row]}))
    with pytest.raises(ValueError, match='parent collision'):
        structures.selected(folder)


def test_instance_rotation_scale_translation_and_region_origin():
    q=2**-.5
    matrix,offset=structures.affine({'translation_cm':[100,-200,300],
        'scale':[2,3,4],'rotation_xyzw':[0,0,q,q]},[500,-600,700])
    assert np.allclose(np.asarray(matrix)@np.array([1,2,3])+offset,[12,6,22])
    low,high=structures.placed_bounds([[0,0,0],[1,2,3]],matrix,offset)
    assert np.allclose(low,[6,6,10]) and np.allclose(high,[12,8,22])


def test_selector_applies_nonidentity_instance_translation(exported):
    folder,row=exported
    row['transforms'][0]['translation_cm']=[-60000,0,0]
    path=folder/'belmonte/runtime.json'
    path.write_text(json.dumps({'origin_cm':[0,0,0],'groups':[row]}))
    result=structures.selected(folder)
    # Visual x1000 becomes400, while the separate hull becomes-200.
    assert result['groups'][0]['transforms']==row['transforms']
    row['transforms'][0]['translation_cm']=[600000,0,0]
    path.write_text(json.dumps({'origin_cm':[0,0,0],'groups':[row]}))
    assert structures.selected(folder)['groups']==[]


def test_missing_geometry_and_unsupported_transform_refuse(exported):
    folder,row=exported
    (folder/'belmonte/glb/Wall_Collision.glb').unlink()
    with pytest.raises(FileNotFoundError):structures.inputs(folder)
    with pytest.raises(ValueError,match='transform'):
        structures.affine({'translation_cm':[0,0,0],'scale':[1,0,1],'rotation_xyzw':[0,0,0,1]},[0,0,0])


def test_structure_loader_refuses_changed_extraction_code_without_geometry_change(exported,monkeypatch):
    import hashlib
    folder,row=exported
    code=folder/'extractor.py';code.write_text('old extraction')
    monkeypatch.setattr(structures,'REPO',folder)
    monkeypatch.setattr(structures,'CODE',('extractor.py',))
    before=structures.inputs(folder)
    product=folder/'gondola/world';product.mkdir(parents=True)
    output=product/'structures.npz';output.write_bytes(b'unchanged output')
    (product/'structures.json').write_text(json.dumps({'inputs':before,'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
    assert structures.validate(folder)
    code.write_text('corrected extraction')
    assert structures.inputs(folder)['files']==before['files']
    with pytest.raises(ValueError,match='stale'):structures.validate(folder)


def test_structure_proof_is_required_and_failed_or_incomplete_proofs_refuse():
    from gondola.validation import validate_structure_proof
    for proof in ({},{'pass':True},{'pass':False,'margin_m':.05}):
        with pytest.raises(ValueError):validate_structure_proof(proof)


def test_static_box_catches_a_large_crossing_face_and_rejects_unowned_contact():
    face=np.array([[[-10,-10,.5],[10,-10,.5],[0,10,.5]]])
    query=StructureClearance({'visual':face,'collision':face},[-20,-20,20,20])
    with pytest.raises(ValueError,match='intersects'):
        query.static([[-1,-1,0],[1,1,1]])
    assert query.static([[-1,-1,2],[1,1,3]])['pass']
    # A town footing/guy envelope must not occupy a walking footprint even
    # when the currently selected object lies above its paving surface.
    with pytest.raises(ValueError,match='intersects'):
        query.static([[-1,-1,2],[1,1,3]],plan_clear=True)


def test_complete_curve_refuses_a_thin_interior_crest_and_missing_query_coverage():
    face=np.array([[[4.99,-1,0],[5.01,-1,0],[5,1,4]]])
    query=StructureClearance({'visual':face,'collision':face},[-20,-20,20,20])
    with pytest.raises(ValueError,match='conflicts'):
        query.path([[0,0,2],[10,0,2]],radius=.2,drop=0)
    with pytest.raises(ValueError,match='extraction footprint'):
        query.path([[0,0,5],[30,0,5]],radius=.2,drop=0)


def test_recorded_belmonte_departure_fails_against_actual_collision_hull():
    from regions.belmonte import source
    path=source.LIBRARY/'meshes/SM_BM_BC_Mura_1_Collision.glb'
    faces=source.triangles(path)+[550.,4500.,210.]
    query=StructureClearance({'visual':faces,'collision':faces},structures.BOUNDS)
    with pytest.raises(ValueError,match='conflicts'):
        query.path([[433.0117,4604.2535,225.9040062],[433.0117,4603.2535,225.9040062]],radius=1.6,drop=3.75)


def test_continuous_kit_envelope_bounds_plumb_rotating_and_open_door_vertices():
    from types import SimpleNamespace
    from gondola.clearance import structure_envelope
    rng=np.random.default_rng(9182)
    vertices=rng.uniform([-1.2,-1.1,-4],[1.2,1.1,.3],(100,3))
    grip=rng.uniform(-.5,.5,(30,3));pivot=np.array([0,-.185,-.13])
    offset=np.array([.525,-.06,0.])
    meshes={'GD_Cabin':SimpleNamespace(verts=vertices),'GD_CabinGrip':SimpleNamespace(verts=grip),
            'GD_CabinDoorLeft':SimpleNamespace(verts=vertices)}
    result=structure_envelope(meshes,pivot,{'GD_CabinDoorLeft':offset})
    for _ in range(100):
        rotation,_=np.linalg.qr(rng.normal(size=(3,3)))
        heading=rng.uniform(-np.pi,np.pi)
        h=np.array([[np.cos(heading),-np.sin(heading),0],[np.sin(heading),np.cos(heading),0],[0,0,1.]])
        for name,mesh in meshes.items():
            if name=='GD_CabinGrip':actual=mesh.verts@rotation.T
            else:
                slide=offset*rng.random() if name.endswith('Left') else np.zeros(3)
                actual=(mesh.verts+slide)@h.T+rotation@pivot-h@pivot
            assert np.linalg.norm(actual[:,:2],axis=1).max()<=result['radius_m']-.3+1e-12
            assert actual[:,2].min()>=-result['drop_m']-1e-12
    with pytest.raises(ValueError):structure_envelope({},pivot,{})


def test_span_requires_six_metres_over_complete_structure_faces():
    face=np.array([[[4,-1,0],[6,-1,0],[5,1,2.]]])
    query=StructureClearance({'visual':face,'collision':face},[-20,-20,20,20])
    with pytest.raises(ValueError,match='conflicts'):
        query.span([[0,7],[10,7]],[0,0],[1,0],radius=.5,gauge=2,drop=0)
    assert query.span([[0,8],[10,8]],[0,0],[1,0],radius=.5,gauge=2,drop=0)['required_clearance_m']==6.


def test_flight_proof_covers_all_legs_and_refuses_low_cruise_or_climb_obstruction():
    from gondola.interactions import flight_clearance
    metadata={'stations':[{'ship':[400,4500,20]}]*3+[{'ship':[416,4664,219.4]}],
        'propeller_centers':[[3.6,-6.,6.1],[3.6,6.,6.1]],'propeller_radius':1.65,
        'legs':[{'stops':[i,3],'height':h} for i,h in enumerate((600,910,520))]}
    manifest={'ZP_Airship':{'min':[-13,-4.031,-.52],'max':[13,4.031,10.5]},
              'ZP_Motors':{'min':[2.25,-6.5,5.6],'max':[3.76,6.5,6.6]}}
    boxes=[[[370,4590,210],[410,4630,235]]]
    assert flight_clearance(metadata,manifest,boxes,[[0,225],[100,250]],{'radius_m':2.5})['pass']
    with pytest.raises(ValueError,match='climb'):
        flight_clearance(metadata,manifest,[[[410,4650,210],[420,4660,235]]],[[0,225],[100,250]],{'radius_m':2.5})
    metadata['legs'][2]['height']=240
    with pytest.raises(ValueError,match='cruise'):
        flight_clearance(metadata,manifest,boxes,[[0,225],[100,250]],{'radius_m':2.5})


def test_walking_headroom_uses_the_complete_sloping_ground_plane():
    from gondola_kit_fixture import gondola_modules
    from gondola.interactions import walking_headroom
    floor=np.array([[[0,0,0],[1,0,.5],[0,1,0]]])
    below=floor-.1
    with gondola_modules('solid',pure=False):
        query=StructureClearance({'visual':below,'collision':below},[-20,-20,20,20])
        walking_headroom(query,floor)
        # A thin obstruction inside the footprint remains mandatory even when
        # all its vertices lie outside the ground triangle.
        obstacle=np.array([[[-10,-10,1],[10,-10,1],[0,10,1]]])
        query=StructureClearance({'visual':below,'collision':obstacle},[-20,-20,20,20])
        with pytest.raises(ValueError,match='headroom'):
            walking_headroom(query,floor)


def test_structure_preflight_remains_available_without_geometry_libraries(exported):
    import subprocess
    folder,_=exported
    world=Path(__file__).resolve().parents[1]/'world'
    script='''import sys
sys.path[:0]=sys.argv[1:3]
from pathlib import Path
from gondola.structures import inputs
assert inputs(Path(sys.argv[3]))['selection']['groups']
assert 'numpy' not in sys.modules and 'bpy' not in sys.modules
'''
    result=subprocess.run([sys.executable,'-S','-c',script,str(world),str(structures.REPO/'platform/studio'),str(folder)],
                          capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('defect',['obstacle','hole','steep'])
def test_actual_walking_link_refuses_the_capsule_corner_gap(defect):
    from types import SimpleNamespace
    from gondola_kit_fixture import gondola_modules
    from gondola.interactions import walking_link
    from gondola.terrain import Ground
    from terrain_product import Mesh
    from terrain_query import Surface
    triangles=[]
    xs=[-30,-2.94,-2.82,30];ys=[-30,-2.18,-2.06,30]
    for i,(a,b) in enumerate(zip(xs,xs[1:])):
        for j,(c,d) in enumerate(zip(ys,ys[1:])):
            if i==j==1 and defect=='hole':continue
            z=2. if i==j==1 and defect=='steep' else 0.
            triangles.extend([[[a,c,0],[b,c,0],[b,d,z]],[[a,c,0],[b,d,z],[a,d,0]]])
    def surface(owner,faces):
        faces=np.asarray(faces,float).reshape(-1,3,3)
        return Surface(Mesh.from_polygons(faces.reshape(-1,3),np.arange(len(faces)*3).reshape(-1,3)),owner=owner,stage='final')
    G=Ground(city=surface('city',triangles),mountain=surface('mountain',[]),
             valley=surface('valley',[]),apron=surface('apron',[]),trail=surface('trail',[]),
             city_bounds=(-30,-30,30,30),mountain_bounds=(-30,30,30,40),
             valley_bounds=(-30,50,30,60),apron_bounds=(-30,40,30,60))
    obstacle=np.array([[[-2.885,-2.125,1],[-2.875,-2.125,1],[-2.88,-2.115,1]]]) if defect=='obstacle' else np.empty((0,3,3))
    query=StructureClearance({'visual':obstacle,'collision':obstacle},[-30,-30,30,30])
    frame=(np.array([0.,0.]),np.array([1.,0.]),np.array([0.,1.]),0.)
    mesh=SimpleNamespace(verts=[[0,0,0],[10,10,0]],faces=[])
    with gondola_modules('solid',pure=False),pytest.raises(ValueError):
        walking_link(G,frame,[[-4,-2,0],[-5,-2,0]],[mesh],query,[[20,13],[20,14],[20,15]])


def test_explicit_stair_cap_owns_join_contact_but_never_hides_a_rail():
    from gondola_kit_fixture import gondola_modules
    from gondola.interactions import walking_floor,walking_headroom
    floor=np.array([[[0,0,0],[1,0,0],[0,1,0]]])
    cap=floor+[0,0,.2]
    with gondola_modules('solid',pure=False):
        contact=walking_floor(floor,[[0,0],[1,0],[0,1]],list(cap))
        assert np.allclose(contact[:,:,2],.2)
        query=StructureClearance({'visual':cap,'collision':cap},[-20,-20,20,20])
        walking_headroom(query,contact)
        query=StructureClearance({'visual':cap+[0,0,.3],'collision':cap},[-20,-20,20,20])
        with pytest.raises(ValueError,match='headroom'):walking_headroom(query,contact)


def test_structure_bounds_are_cached_by_file_identity(tmp_path, monkeypatch):
    import os
    calls = []
    (tmp_path/'.state').mkdir()
    glb = tmp_path/'piece.glb'; glb.write_bytes(b'first')
    monkeypatch.setattr(structures, 'mesh_bounds', lambda path: calls.append(path) or ([0., 0., 0.], [1., 1., 1.]))
    monkeypatch.setattr(structures, '_bounds_memo', {})
    assert structures.cached_bounds(tmp_path, 'piece.glb') == ([0., 0., 0.], [1., 1., 1.])
    monkeypatch.setattr(structures, '_bounds_memo', {})  # A new process reads the persisted cache.
    assert structures.cached_bounds(tmp_path, 'piece.glb') == ([0., 0., 0.], [1., 1., 1.]) and len(calls) == 1
    glb.write_bytes(b'other bytes')
    structures.cached_bounds(tmp_path, 'piece.glb')
    assert len(calls) == 2
