"""Southwest logical and native membership must remain complete and bounded."""
import importlib.util
import json
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('southwest_products_test', GAME / 'southwest_atomic_products.py')
products = importlib.util.module_from_spec(spec); spec.loader.exec_module(products)


def runtime():
    return dict(version=1, complete=True, triangle_limit=32768, parents={parent:dict(
        source_triangles=12, bounds=[[-1,-2,0],[1,2,3]], pieces=[dict(name=parent,triangles=12)])
        for parent in products.PARENTS})


def test_complete_explicit_roster_includes_lean_pines_and_preserves_old_keys():
    value = runtime()
    assert products.validate_runtime(value) is value
    assert len(value['parents']) == 16
    assert {'Tree_PineLean_A','Tree_PineLean_B','SW_Island','SW_Temple'} <= value['parents'].keys()
    spec = importlib.util.spec_from_file_location('southwest_graph_test', GAME / 'southwest_atomic_build.py')
    graph = importlib.util.module_from_spec(spec); spec.loader.exec_module(graph)
    assert tuple(asset for _,asset in graph.MODELS) == products.PARENTS


@pytest.mark.parametrize('change', ['missing_pine','empty','foreign','unbounded','duplicate','count','nonfinite'])
def test_invalid_membership_never_falls_back_to_a_whole_parent(change):
    value = runtime(); island = value['parents']['SW_Island']
    if change == 'missing_pine': del value['parents']['Tree_PineLean_B']
    elif change == 'empty': island['pieces'] = []
    elif change == 'foreign': island['pieces'][0]['name'] = 'SW_Island_Foreign'
    elif change == 'unbounded': island['pieces'][0]['triangles'] = island['source_triangles'] = 32769
    elif change == 'duplicate': island['pieces'] *= 2; island['source_triangles'] *= 2
    elif change == 'count': island['source_triangles'] += 1
    else: island['bounds'][0][0] = float('nan')
    with pytest.raises(ValueError): products.validate_runtime(value)


def test_atomic_piece_names_do_not_admit_prefix_collisions():
    assert products.owned('SW_Island_cell_-1_0_Piece012','SW_Island')
    assert not products.owned('SW_Island_cell_-01_0','SW_Island')
    assert not products.owned('SW_Island_cell_0_0/Foreign','SW_Island')
    assert not products.owned('SW_Island_cell_0_0','SW_Island_cell')


def test_prior_native_inventory_refuses_foreign_root_nested_and_case_alias():
    root = products.DESTINATION
    class Editor:
        def __init__(self, paths): self.paths = paths
        def list_assets(self, *args, **kwargs): return self.paths
    asset = root + '/SW_Island_cell_0_0'
    assert products.native_inventory(Editor([asset+'.SW_Island_cell_0_0'])) == {asset}
    for entries in ([root+'/Other.Other'],[root+'/Nested/SW_Island.SW_Island'],[asset,asset]):
        with pytest.raises(ValueError): products.native_inventory(Editor(entries))


def test_source_assembly_refuses_missing_parent_before_runtime_publication(tmp_path):
    root = tmp_path / 'atomic_regions/southwest'; (root/'assets').mkdir(parents=True)
    (root/'logical-pieces.json').write_text(json.dumps(dict(schema=1,parents={},ownership={},exports=[])))
    (root/'assets/manifest.json').write_text(json.dumps(dict(schema=1,complete=True,exports=[])))
    with pytest.raises(ValueError): products.assemble(tmp_path, None)
    assert not (tmp_path/'southwest/runtime.json').exists()


def test_native_disk_inventory_is_complete_and_refuses_link_before_writes(tmp_path):
    root = tmp_path/'Japan/Southwest/Pieces';root.mkdir(parents=True)
    primary = root/'SW_Island_cell_0_0.uasset';primary.write_bytes(b'package')
    sidecar = root/'SW_Island_cell_0_0.uexp';sidecar.write_bytes(b'sidecar')
    assert products.native_files(tmp_path) == (primary, sidecar)
    foreign = root/'other.uasset';foreign.write_bytes(b'foreign')
    with pytest.raises(ValueError,match='Foreign'): products.native_files(tmp_path)
    foreign.unlink(); target = tmp_path/'outside';target.write_bytes(b'untouched')
    primary.unlink();primary.symlink_to(target)
    with pytest.raises(ValueError): products.native_files(tmp_path)
    assert target.read_bytes() == b'untouched'


def test_normal_graph_has_independent_selected_sources_and_preexport_queries(tmp_path):
    from types import SimpleNamespace
    from atelier import build
    spec = importlib.util.spec_from_file_location('southwest_graph_inventory',GAME/'southwest_atomic_build.py')
    graph = importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    steps = graph.steps(SimpleNamespace(out=tmp_path))
    planners = [s for s in steps if '.geometry.' in s.name]
    assert len(planners) == 16
    assert {s.products[1].name for s in planners} == {'southwest.query.'+p for p in products.PARENTS}
    for step in planners:
        assert step.cache and not step.needs and not step.reads
        assert step.commands[0].factory_startup and step.commands[0].threads == 3
        contexts = [p for p in step.inputs if p.suffix == '.json']
        assert len(contexts) == 1 and contexts[0].stem == step.name.split('.')[-1]
        assert not any(p.suffix in ('.fbx','.glb') for p in step.inputs)
    island = next(s for s in planners if s.name.endswith('.SW_Island'))
    assert not any(p.name in ('stand.py','fishing.py','temple.py') for p in island.inputs)
    build.check_modules(steps)
    final = graph.assembly_step(SimpleNamespace(out=tmp_path))
    assert final.name == 'world.southwest' and final.reads == ['southwest.atomic']
    assert final.cache and isinstance(final.commands[0],build.Call)


def test_file_only_assembly_binds_every_current_primary_hash_and_roster(tmp_path):
    import hashlib
    from io import StringIO
    root = tmp_path/'atomic_regions/southwest';assets=root/'assets';assets.mkdir(parents=True)
    logical = dict(schema=1,parents={},ownership={},exports=[])
    receipts=[]
    for parent in products.PARENTS:
        payload=(parent+' payload').encode();(assets/(parent+'.fbx')).write_bytes(payload)
        row=dict(name=parent,triangles=12,polygons=6,collision_hulls=0,min=[-1,-2,0],max=[1,2,3])
        logical['parents'][parent]=[parent];logical['exports'].append(parent)
        logical['ownership'][parent]=dict(source_triangles=12,source_polygons=6,source_collision_hulls=0,
            slots=['Southwest_Palette'],matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]],pieces=[row])
        receipts.append(dict(schema=1,asset=parent,primary=parent+'.fbx',triangles=12,bounds=[row['min'],row['max']],
            sha256=hashlib.sha256(payload).hexdigest(),metadata=dict(slots=['Southwest_Palette'],uv_channels=['UVMap'],collision_hulls=0)))
    (root/'logical-pieces.json').write_text(json.dumps(logical))
    (assets/'manifest.json').write_text(json.dumps(dict(schema=1,complete=True,exports=receipts)))
    result=products.assemble(tmp_path,StringIO())
    assert products.validate_runtime(result) is result
    assert json.loads((tmp_path/'southwest/runtime.json').read_text()) == result
    before=(tmp_path/'southwest/runtime.json').read_bytes()
    (assets/'SW_Island.fbx').write_bytes(b'corruption')
    with pytest.raises(ValueError,match='bytes'): products.assemble(tmp_path,StringIO())
    assert (tmp_path/'southwest/runtime.json').read_bytes() == before
