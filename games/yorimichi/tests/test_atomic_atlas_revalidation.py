"""Exact atlas source carry and final query ownership, without private artifacts."""
import ast
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atlas_atomic_carry_tests', GAME / 'tools/atlas_atomic_revalidation.py')
carry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(carry)
ATLAS = GAME / 'world/map/atlas'


def test_live_atlas_carry_has_exact_current_source_and_immutable_predecessor():
    witness = json.loads((ATLAS / carry.WITNESS).read_text())
    assert carry.prove() == witness['source_proof']
    assert len(witness['source_proof']['comparisons']) == 13
    previous = witness['records']['coasts/source.json']['previous_tables']['geography']
    originals = json.loads(carry.FIXTURE.read_text())['files']
    for rel, digest in previous.items():
        if 'games/yorimichi/' + rel in originals:
            assert originals['games/yorimichi/' + rel]['sha256'] == digest
    assert originals['games/yorimichi/world/regions/belmonte/source.py']['sha256'] == witness['query_data_equivalence']['old_decoder_sha256']
    for rel in witness['records']:
        record = json.loads((ATLAS / rel).read_text())
        restored = carry.restore_record(rel, record)
        # Restoring the carry changes no original paid generation or recut lineage.
        for field in ('generation', 'recut', 'display', 'output_sha256', 'prompt'):
            assert record.get(field) == restored.get(field)
    for rel, digest in witness['unchanged_art_sha256'].items():
        assert carry.sha((ATLAS / rel).read_bytes()) == digest


@pytest.mark.parametrize('rel,function', [
    ('world/regions/hidamari/layout.py', 'height'),
    ('world/regions/hidamari/arrival_placement.py', 'road_distance'),
    ('world/regions/southwest/island.py', 'height'),
    ('world/regions/brinecove/ground_sampling.py', 'jag_point'),
    ('world/regions/belmonte/query_surface.py', 'sample'),
])
def test_an_actual_height_placement_or_sampling_edit_cannot_use_the_carry(tmp_path, rel, function):
    witness = json.loads((ATLAS / carry.WITNESS).read_text())
    for source in [*witness['source_proof']['bound_sources'], 'tests/fixtures/atlas-atomic-predecessor.json']:
        path = tmp_path / source
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(GAME / source, path)
    path = tmp_path / rel
    tree = ast.parse(path.read_text())
    node, = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
    node.body.insert(0, ast.Return(value=ast.Constant(value=127.0)))
    path.write_text(ast.unparse(ast.fix_missing_locations(tree)))
    with pytest.raises(ValueError, match='declarations differ'):
        carry.prove(tmp_path)


def test_map_reads_complete_final_query_arrays_in_the_original_frame(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    from belmonte.query_arrays import read, write
    from belmonte.query_surface import Surface

    source = ast.parse((GAME / 'world/map/build_map.py').read_text())
    calls = [n for n in ast.walk(source) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'final_query']
    assert len(calls) == 1
    expression = calls[0]
    assert {k.arg: ast.literal_eval(k.value) for k in expression.keywords if k.arg == 'stage'} == {'stage': 'final'}
    assert next(k.value.id for k in expression.keywords if k.arg == 'owner') == 'name'
    assert 'ground/glb/' not in (GAME / 'world/map/build_map.py').read_text()
    faces = np.array([[[0., 0., 2.], [2., 0., 4.], [0., 2., 6.]]], dtype='<f8')
    path = tmp_path / 'SM_BM_NorthApron-final.npz'
    write(path, faces, owner='SM_BM_NorthApron', stage='final')
    actual = read(path, owner='SM_BM_NorthApron', stage='final')['faces']
    assert actual.tobytes() == faces.tobytes()
    old = json.loads(carry.FIXTURE.read_text())['files']['games/yorimichi/world/regions/belmonte/source.py']['source']
    node, = [n for n in ast.parse(old).body if isinstance(n, ast.ClassDef) and n.name == 'Surface']
    namespace = {'np': np}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'immutable-atlas-surface', 'exec'), namespace)
    xs, ys = np.array([.25, .5, 1.]), np.array([.25, .5, .25])
    assert namespace['Surface'](faces).height(xs, ys).tobytes() == Surface(actual).height(xs, ys).tobytes()
    with pytest.raises(ValueError):
        read(path, owner='SM_BM_NorthApron', stage='natural')


@pytest.mark.parametrize('fault',['stage','owners','sampler','cache','reader'])
def test_natural_reader_carry_is_finite_and_refuses_semantic_or_signature_edits(tmp_path,fault):
    witness=json.loads((ATLAS/carry.WITNESS).read_text())
    for source in [*witness['source_proof']['bound_sources'],'tests/fixtures/atlas-atomic-predecessor.json']:
        path=tmp_path/source;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(GAME/source,path)
    path=tmp_path/'world/train/route.py';text=path.read_text()
    if fault=='stage':text=text.replace("stage='natural'","stage='final'")
    if fault=='owners':text=text.replace("owners = ('SM_BM_NorthCountry', 'SM_BM_NorthApron')","owners = ('SM_BM_NorthApron', 'SM_BM_NorthCountry')")
    if fault=='sampler':text=text.replace('z = np.array(CITY.north_height(x, y, carved=False), float)','z = np.array(CITY.north_height(x, y, carved=False), float) + .001')
    if fault=='cache':text=text.replace("'SM_BM_NorthApron.surface'","'SM_BM_NorthApron-final.surface'")
    path.write_text(text)
    if fault=='reader':
        reader=tmp_path/'world/regions/belmonte/surface_data.py';reader.write_text(reader.read_text()+'\n# unproved reader change\n')
    with pytest.raises(ValueError,match='differ'):carry.prove(tmp_path)


def test_natural_route_reader_preserves_every_corner_and_sample_from_immutable_predecessor(tmp_path,monkeypatch):
    import hashlib
    from functools import lru_cache
    from types import SimpleNamespace
    from atelier.gltf import glb_parts,glb_pack
    from test_belmonte_ground_pieces import model
    monkeypatch.syspath_prepend(str(GAME/'world'));monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    from belmonte import source,surface_data
    fixture=json.loads(carry.FIXTURE.read_text());originals=fixture['files']
    old_source=carry.declarations(originals['games/yorimichi/world/regions/belmonte/source.py']['source'])
    namespace=dict(np=np,glb_parts=glb_parts)
    exec(compile(ast.Module(body=[old_source[name] for name in ('FRAME','triangles','Surface')],type_ignores=[]),'immutable-natural-sampler','exec'),namespace)
    doc,binary=glb_parts(model());binary=bytearray(binary)
    np.frombuffer(binary,dtype='<f4',count=36).reshape(-1,3)[:,1]=np.linspace(198.125,214.875,12,dtype='<f4')
    data=glb_pack(doc,bytes(binary))
    for owner in ('SM_BM_NorthCountry','SM_BM_NorthApron'):
        path=tmp_path/'belmonte/natural'/f'{owner}.glb';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        entry=dict(name=owner,sha256=hashlib.sha256(data).hexdigest(),triangles=4)
        surface_data.write(tmp_path/'belmonte-natural-source-data'/f'{owner}.surface',entry,data,stage='natural')
    marker=object();monkeypatch.setattr(source,'terrain',lambda *,natural:marker if natural is True else None)
    def reader(text):
        node=carry.declarations(text)['_belmonte_surfaces'];env=dict(lru_cache=lru_cache,yori=SimpleNamespace(OUT=tmp_path))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'route-reader-only','exec'),env);return env['_belmonte_surfaces']
    before=reader(originals['games/yorimichi/world/train/route.py']['source'])
    after=reader((GAME/'world/train/route.py').read_text())
    with monkeypatch.context() as old:
        old.setattr(source,'triangles',namespace['triangles']);old.setattr(source,'Surface',namespace['Surface'])
        old_terrain,old_surfaces=before()
    new_terrain,new_surfaces=after();assert old_terrain is new_terrain is marker
    for old,new in zip(old_surfaces,new_surfaces):
        assert old.faces.tobytes()==new.faces.tobytes()
        points=old.faces.mean(axis=1)
        assert old.height(points[:,0],points[:,1]).tobytes()==new.height(points[:,0],points[:,1]).tobytes()
    # A final-stage packet cannot be substituted even while legacy natural GLBs exist.
    owner='SM_BM_NorthCountry';entry=dict(name=owner,sha256=hashlib.sha256(data).hexdigest(),triangles=4)
    surface_data.write(tmp_path/'belmonte-natural-source-data'/f'{owner}.surface',entry,data,stage='final')
    after.cache_clear()
    with pytest.raises(ValueError):after()
