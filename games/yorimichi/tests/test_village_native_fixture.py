"""The native fixture keeps immutable authority, complete family scope and true seam inputs."""
import ast
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from atelier import mesh_ir

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions')]
PATH=GAME/'tests/native/prepare_village_native.py'
spec=importlib.util.spec_from_file_location('village_fixture_host',PATH)
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)


def test_original_finishing_is_the_complete_exact_original_ast_loop():
    original=(GAME/'tests/fixtures/village-native-predecessor-283329c07.txt').read_text()
    source=ast.parse(original)
    main=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    original_loop=next(node for node in main.body if isinstance(node,ast.For) and ast.unparse(node.iter)=='manifest.items()')
    rewritten=ast.parse(host.original_finishing(original))
    assert ast.dump(rewritten.body[0].body[0])==ast.dump(original_loop)
    text=ast.unparse(rewritten)
    assert "'/Game/Japan/Assets'" in text and 'collision_trace_flag' in text and 'save_loaded_asset' in text
    assert 'terrain.fbx' not in text


def test_host_input_binding_refuses_links_and_detects_byte_or_stat_changes(tmp_path):
    root=tmp_path.resolve();file=root/'source';file.write_bytes(b'first')
    bound=host.identities([file]);assert bound==host.identities([file])
    file.write_bytes(b'other');assert bound!=host.identities([file])
    alias=root/'alias';alias.symlink_to(file)
    with pytest.raises(ValueError,match='linked'):host.identities([alias])


def test_probe_geometry_preserves_actual_shared_edge_neighbors_and_independent_faces(tmp_path):
    out=tmp_path.resolve();folder=out/'planned_exports/village/Whole';folder.mkdir(parents=True)
    for key,positions in [('One',[[0,0,0],[1,0,0],[0,1,0]]),('Two',[[1,0,0],[1,1,0],[0,1,0]])]:
        piece=dict(positions=np.asarray(positions),normals=np.tile([0,0,1],(3,1)),faces=[[0,1,2]],materials=[0],
            smooth=[False],uvs=[('UVMap',np.zeros((3,2)))],colours=[])
        mesh_ir.write(folder/(key+'.npz'),mesh_ir.encode(piece,key=key,slots=['VillagePalette'],matrix=np.eye(4).tolist(),options={}))
    value=host.probe_geometry(out,{'Whole':dict(pieces=[dict(name='One'),dict(name='Two')])})['Whole']
    assert set(value['pieces'])=={'One','Two'} and len(value['seams'])==1
    seam=value['seams'][0];assert (seam['a'],seam['b'])==('One','Two')
    assert all(value['pieces'][key] and seam['points'][key] for key in ('One','Two'))
    assert min(value['negative'])>=10000


def test_native_fixture_has_no_subprocess_or_git_authority_and_calls_real_owner():
    source=(GAME/'tests/native/village_native_equivalence.py').read_text();tree=ast.parse(source)
    imports=[alias.name for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom)) for alias in node.names]
    assert 'subprocess' not in imports
    assert 'owner.receive(out)' in source and 'owner.retire(received,runtime_members=members)' in source
    assert 'capture.capture(' in source and "policy_scope='fixture'" in source
    assert 'retained-original' in source and 'physical_retirement=retired' in source


def test_positive_probe_selection_handles_reflected_winding_without_changing_collision_policy():
    from types import SimpleNamespace
    file=GAME/'tests/native/village_native_equivalence.py';tree=ast.parse(file.read_text())
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('query','controls_for')]
    def part(path):return SimpleNamespace(get_path_name=lambda:path)
    original=part('original');child=part('current')
    def observed(component,query):
        if query['start'][0]>1000:return dict(blocking=False)
        return dict(blocking=query['start'][2]>query['end'][2])
    scope=dict(probe=observed)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(file),'exec'),scope)
    geometry=dict(pieces={'Piece':[dict(point=[0.,0.,0.],normal=[0.,0.,-1.])]},seams=[],negative=[10000.,10000.,10000.])
    before,after,seams=scope['controls_for']('Whole',original,{'Piece':child},geometry)
    assert not seams and len(before)==len(after)==4
    for a,b in zip(before,after):
        assert a['input']==b['input'] and a['input']['trace_complex'] is True
        assert a['target']=='original' and b['target']=='current'
        if a['kind'].endswith('_positive'):assert a['input']['start'][2]>a['input']['end'][2]


def test_original_whole_bounds_include_all_packets_and_original_frames(tmp_path):
    root=tmp_path.resolve()
    piece=dict(positions=np.asarray([[0,0,0],[1,0,0],[0,1,1]]),normals=np.tile([0,0,1],(3,1)),
        faces=[[0,1,2]],materials=[0],smooth=[False],uvs=[('UVMap',np.zeros((3,2)))],colours=[])
    for key,height in [('First',0.),('Second',10.)]:
        matrix=np.eye(4);matrix[2,3]=height
        mesh_ir.write(root/(key+'.npz'),mesh_ir.encode(piece,key=key,slots=['VillagePalette'],matrix=matrix.tolist(),options={}))
    result=host.legacy_bounds(root,[{'path':'First.npz'},{'path':'Second.npz'}])
    assert result==dict(min=[0.,0.,0.],max=[1.,1.,11.],triangles=2)
