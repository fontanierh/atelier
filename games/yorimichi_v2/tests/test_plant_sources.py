"""The Brine Cove plant and city tree residual planner (tools/migrate/plant_sources.py) on fake data, the importer's pure LOD
helpers, and the real-tree plan when the donor build is present (skipped otherwise)."""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'unreal' / 'Scripts'))
import plant_sources as ps  # noqa: E402
import records  # noqa: E402
import import_settings as s  # noqa: E402

def make_glb(material_names) -> bytes:
    """A minimal binary glTF whose materials are named (the planner reads the names)."""
    import struct
    doc = json.dumps({'asset': {'version': '2.0'}, 'materials': [{'name': n} for n in material_names]}).encode()
    doc += b' ' * (-len(doc) % 4)
    return b'glTF' + struct.pack('<II', 2, 12 + 8 + len(doc)) + struct.pack('<II', len(doc), 0x4E4F534A) + doc


GLB = make_glb(['BC_leaf'])
FBX_ORIGINAL = b'fbx original arcade'
FBX_LOD1 = b'fbx lod1'
FBX_LOD2 = b'fbx lod2'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def canonical(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + '\n'


@pytest.fixture
def fake(tmp_path):
    """A donor build with one plant and one city piece (its original and two LODs), and a game tree with the adopted
    records that own those packages, the original's recovered record, and a saved-object record that references the plant."""
    donor = tmp_path / 'donor'
    (donor / 'brinecove' / 'glb').mkdir(parents=True)
    (donor / 'brinecove' / 'glb' / 'SM_BC_Plant_Broad0.glb').write_bytes(GLB)
    (donor / 'city_tree_lods' / 'v4').mkdir(parents=True)
    (donor / 'atomic').mkdir()
    (donor / 'atomic' / 'HD_ArcadeTree_LOD1_cell_-1_-1.fbx').write_bytes(FBX_LOD1)
    (donor / 'atomic' / 'HD_ArcadeTree_LOD2_cell_-1_-1.fbx').write_bytes(FBX_LOD2)
    (donor / 'brinecove' / 'build-report.json').write_text(json.dumps({
        'materials': {'leaf': {'name': 'MI_BC_leaf', 'kind': 'opaque', 'texture': None}},
        'meshes': [{'name': 'SM_BC_Plant_Broad0', 'path': 'glb/SM_BC_Plant_Broad0.glb', 'sha256': sha(GLB),
                    'slots': ['leaf'], 'triangles': 1242, 'collision': False, 'lods': True}]}))
    (donor / 'city_tree_lods' / 'v4' / 'manifest.json').write_text(json.dumps({
        'complete': True, 'tag': 'v4', 'version': 3, 'screen_sizes': [1.0, 0.18, 0.07],
        'sources': {'HD_ArcadeTree': [{
            'name': 'HD_ArcadeTree_cell_-1_-1', 'asset': '/Game/Experiments/CitySurfaces/v1_128m/HD_ArcadeTree_cell_-1_-1.'
                                                          'HD_ArcadeTree_cell_-1_-1',
            'original_triangles': 19182,
            'lods': [{'name': 'HD_ArcadeTree_LOD1_cell_-1_-1', 'file': 'atomic/HD_ArcadeTree_LOD1_cell_-1_-1.fbx', 'sha256': sha(FBX_LOD1),
                      'triangles': 9242},
                     {'name': 'HD_ArcadeTree_LOD2_cell_-1_-1', 'file': 'atomic/HD_ArcadeTree_LOD2_cell_-1_-1.fbx', 'sha256': sha(FBX_LOD2),
                      'triangles': 5266}]}]}}))

    game = tmp_path / 'game'
    adopted = game / 'assets' / 'adopted'
    write(adopted / 'brinecove' / 'plant-broad' / 'asset.toml',
          'schema = 1\nid = "adopted/brinecove/plant-broad"\nkind = "adopted"\nauthority = "editor"\n'
          'owner = "shared/brinecove/plant-broad"\n[[outputs]]\npackage = "/Game/Brinecove/Meshes/SM_BC_Plant_Broad0"\n')
    write(adopted / 'brinecove' / 'materials' / 'asset.toml',
          'schema = 1\nid = "adopted/brinecove/materials"\nkind = "adopted"\nauthority = "editor"\n'
          'owner = "shared/brinecove/materials"\n[[outputs]]\npackage = "/Game/Brinecove/Materials/MI_BC_leaf"\n')
    (adopted / 'brinecove' / 'units.json').write_text(canonical({
        'about': 'fake', 'units': {}, 'packages': {'/Game/Brinecove/Meshes/SM_BC_Plant_Broad0': 'plant-broad'}}))
    write(adopted / 'experiments' / 'citytrees' / 'asset.toml',
          'schema = 1\nid = "adopted/experiments/citytrees"\nkind = "adopted"\nauthority = "editor"\n'
          'owner = "shared/experiments/citytrees"\n'
          '[[outputs]]\npackage = "/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_-1_-1"\n'
          '[[outputs]]\npackage = "/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_-1_-1"\n'
          '[[outputs]]\npackage = "/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_-1_v4"\n')
    write(adopted / 'japan' / 'materials' / 'base' / 'asset.toml',
          'schema = 1\nid = "adopted/japan/materials/base"\nkind = "adopted"\nauthority = "editor"\n'
          'owner = "shared/japan/materials/base"\n[[outputs]]\npackage = "/Game/Japan/Materials/M_Arcade"\n')
    original = game / 'assets' / 'prop' / 'citysurfaces' / 'arcade-m1-m1'
    original.mkdir(parents=True)
    (original / 'src').mkdir()
    (original / 'src' / 'HD_ArcadeTree_cell_-1_-1.fbx').write_bytes(FBX_ORIGINAL)
    write(original / 'asset.toml',
          'schema = 1\nid = "prop/citysurfaces/arcade-m1-m1"\nkind = "static-mesh"\nauthority = "generated"\n'
          'owner = "shared/citysurfaces/arcade-m1-m1"\nreferences = ["adopted/japan/materials/base"]\n\n'
          f'[[sources]]\npath = "src/HD_ArcadeTree_cell_-1_-1.fbx"\nsha256 = "{sha(FBX_ORIGINAL)}"\n\n'
          '[recipe]\nimporter = "static-mesh"\nversion = 1\n\n[recipe.settings]\n'
          'slot_materials = ["/Game/Japan/Materials/M_Arcade"]\ntriangles = 19182\ncollision = "simple_and_complex"\nhulls = 2\n'
          'full_precision_uvs = true\n\n[[outputs]]\npackage = "/Game/Experiments/CitySurfaces/v1_128m/HD_ArcadeTree_cell_-1_-1"\n')
    # A saved-object record that places the plant: it names the adopted plant record, which the claim re-points.
    placer = game / 'assets' / 'prop' / 'fake' / 'placer'
    placer.mkdir(parents=True)
    (placer / 'src').mkdir()
    (placer / 'src' / 'p.glb').write_bytes(b'placer')
    write(placer / 'asset.toml',
          'schema = 1\nid = "prop/fake/placer"\nkind = "static-mesh"\nauthority = "generated"\nowner = "region/w09-brinecove"\n'
          f'references = ["adopted/brinecove/plant-broad"]\n\n[[sources]]\npath = "src/p.glb"\nsha256 = "{sha(b"placer")}"\n\n'
          '[recipe]\nimporter = "static-mesh"\nversion = 1\n\n[recipe.settings]\ntriangles = 1\n\n'
          '[[outputs]]\npackage = "/Game/Fake/Placer"\n')
    return {'donor': donor, 'game': game, 'original': original}


def test_the_fake_tree_plans_every_package_as_one_record(fake):
    p = ps.plan(fake['game'], fake['donor'])
    assert p.unmapped == []
    assert sorted(p.packages) == sorted([
        '/Game/Brinecove/Meshes/SM_BC_Plant_Broad0',
        '/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD1_cell_-1_-1',
        '/Game/Experiments/CityTrees/v4/lods/HD_ArcadeTree_LOD2_cell_-1_-1',
        '/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_-1_v4'])
    assert sorted(r.family for r in p.records) == ['city-lods', 'city-lods', 'city-v4', 'plants']


def test_the_plant_record_states_the_donor_reduction_plan_and_its_material(fake):
    rec = next(r for r in ps.plan(fake['game'], fake['donor']).records if r.family == 'plants')
    assert rec.id == 'prop/brinecove/plant-broad0' and rec.owner == 'shared/brinecove/plant-broad'
    assert rec.settings['slot_materials'] == ['/Game/Brinecove/Materials/MI_BC_leaf']
    assert rec.settings['lods'] == [[1.0, 1.0], [0.45, 0.3], [0.2, 0.12], [0.08, 0.04]]
    assert rec.settings['full_precision_uvs'] is True and 'collision' not in rec.settings
    assert rec.sources[0].sha256 == sha(GLB)


def test_the_city_chain_is_the_original_then_the_two_donor_levels(fake):
    rec = next(r for r in ps.plan(fake['game'], fake['donor']).records if r.family == 'city-v4')
    chain = rec.settings['lod_chain']
    assert [c[0] for c in chain] == ['src/HD_ArcadeTree_cell_-1_-1.fbx', 'src/HD_ArcadeTree_LOD1_cell_-1_-1.fbx',
                                     'src/HD_ArcadeTree_LOD2_cell_-1_-1.fbx']
    assert [c[1] for c in chain] == [1.0, 0.18, 0.07] and [c[2] for c in chain] == [19182, 9242, 5266]
    assert rec.settings['collision'] == 'simple_and_complex' and rec.settings['hulls'] == 2
    assert rec.settings['slots'] == [['HidamariPalette', '/Game/Japan/Materials/M_Arcade']]


def test_the_planned_records_are_valid_records_and_the_claim_moves_them(fake, tmp_path):
    p = ps.plan(fake['game'], fake['donor'])
    for rec in p.records:
        folder = tmp_path / 'assets' / rec.id
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(ps.record_text(rec))
        for src in rec.sources:
            (folder / src.path).parent.mkdir(parents=True, exist_ok=True)
            (folder / src.path).write_bytes(src.file.read_bytes())
        asset = records.load_asset(folder / 'asset.toml')
        assert asset.kind == 'static-mesh' and [o.package for o in asset.outputs] == rec.outputs
    ops = ps.build_writes(fake['game'], p)
    assert 'assets/adopted/brinecove/plant-broad/asset.toml' in ops['deletes']
    assert 'assets/adopted/experiments/citytrees/asset.toml' in ops['deletes']
    units = json.loads(ops['writes']['assets/adopted/brinecove/units.json'].decode())
    assert units['packages'] == {}
    placer = ops['writes']['assets/prop/fake/placer/asset.toml'].decode()
    assert 'adopted/brinecove/plant-broad' not in placer and 'prop/brinecove/plant-broad0' in placer
    assert 'region/w09-brinecove' in ps.scopes_of_ops(fake['game'], ops) and 'shared/brinecove/plant-broad' in ps.scopes_of_ops(fake['game'], ops)


def test_a_package_no_record_plans_is_reported_and_a_missing_donor_file_is_refused(fake):
    (fake['donor'] / 'brinecove' / 'glb' / 'SM_BC_Plant_Broad0.glb').write_bytes(b'changed')
    p = ps.plan(fake['game'], fake['donor'])
    assert any('SM_BC_Plant_Broad0' in u and 'pinned' in u for u in p.unmapped)
    assert not any(r.family == 'plants' for r in p.records)


def test_the_importer_reads_a_reduction_plan_and_a_level_kind_and_refuses_the_rest():
    assert s.reduction_plan({'lods': [[1, 1], [0.45, 0.3], [0.2, 0.12], [0.08, 0.04]]}) == [
        [1.0, 1.0], [0.45, 0.3], [0.2, 0.12], [0.08, 0.04]]
    assert s.reduction_plan({}) is None
    for bad in ([[0.5, 1]], [[1, 1], [0.5, 1.2]], [[1, 1], [1.5, 0.3]], [[1, 0.9]]):
        with pytest.raises(s.SettingError):
            s.reduction_plan({'lods': bad})
    assert s.level_kind('HD_ArcadeTree_LOD1.FBX') == 'fbx' and s.level_kind('x.glb') == 'gltf'
    with pytest.raises(s.SettingError):
        s.level_kind('x.obj')


REAL_DONOR = os.environ.get('YV2_DONOR_BUILD')


@pytest.fixture(scope='module')
def unprepared():
    """The plan tests start from the adopted records; once the move ran on the real tree (state `done`) they skip, and
    test_the_real_tree_is_split pins the result instead."""
    current, _ = ps.state(ROOT)
    if current != 'unprepared':
        pytest.skip(f'the real tree is {current}, not unprepared: the move already ran')


@pytest.mark.skipif(not REAL_DONOR or not (Path(REAL_DONOR).expanduser() / 'brinecove' / 'build-report.json').is_file(),
                    reason='needs the donor build (YV2_DONOR_BUILD)')
def test_real_tree_plans_all_72_packages_without_unmapped_ones(unprepared):
    p = ps.plan(ROOT, Path(REAL_DONOR).expanduser())
    assert p.unmapped == []
    assert len(p.records) == 72 and len(p.packages) == 72
    families = [r.family for r in p.records]
    assert families.count('plants') == 36 and families.count('city-lods') == 24 and families.count('city-v4') == 12


def agreeing_read(plan_):
    """A report_meshes row for every planned package that agrees with its record (the fake read the checks are shown on)."""
    read = {}
    for rec in plan_.records:
        slots = rec.settings.get('slot_materials') or [v[1] for v in rec.settings.get('slots', [])]
        for package in rec.outputs:
            if rec.family == 'plants':
                lods = [{'screen': scr, 'triangles': max(1, rec.settings['triangles'] // (2 ** i)), 'sections': list(range(len(slots)))}
                        for i, (_, scr) in enumerate(rec.settings['lods'])]
                collision = {'trace': 'CTF_USE_DEFAULT: 0>', 'convex': 1, 'simple': 0, 'boxes': [], 'double_sided': False}
            elif rec.family == 'city-lods':
                lods = [{'screen': 1.0, 'triangles': rec.settings['triangles'], 'sections': [0]}]
                collision = {'trace': 'CTF_USE_DEFAULT: 0>', 'convex': 0, 'simple': 0, 'boxes': [], 'double_sided': False}
            else:
                lods = [{'screen': c[1], 'triangles': c[2], 'sections': [0]} for c in rec.settings['lod_chain']]
                collision = {'trace': 'CTF_USE_SIMPLE_AND_COMPLEX: 1>', 'convex': rec.settings.get('hulls', 0), 'simple': 0,
                             'boxes': [], 'double_sided': False}
            names = ps.expected_slot_names(rec)
            read[package] = {'slots': [{'name': n, 'imported': n, 'material': m} for n, m in zip(names, slots)],
                             'lods': lods, 'collision': collision}
    return read


def test_the_fake_read_that_agrees_with_the_plan_has_no_disagreement(fake):
    p = ps.plan(fake['game'], fake['donor'])
    assert ps.disagreements(p, ps.evidence(p, agreeing_read(p))) == []


def test_a_read_that_disagrees_is_named_by_package(fake):
    p = ps.plan(fake['game'], fake['donor'])
    read = agreeing_read(p)
    plant = '/Game/Brinecove/Meshes/SM_BC_Plant_Broad0'
    read[plant]['lods'][1]['screen'] = 0.5                                 # the donor's screen is 0.3
    read[plant]['lods'][2]['triangles'] = read[plant]['lods'][0]['triangles'] + 1   # a level that gains triangles
    v4 = '/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_-1_v4'
    read[v4]['collision']['convex'] = 1                                    # the original has two hulls
    out = ps.disagreements(p, ps.evidence(p, read))
    assert any(plant in d and 'screen 0.5 is not 0.3' in d for d in out)
    assert any(plant in d and 'grow with the level' in d for d in out)
    assert any(v4 in d and 'collision' in d for d in out)


def test_the_committed_read_evidence_has_no_donor_paths_and_names_the_72_packages():
    text = (ROOT / 'docs' / 'inventory' / 'plants-and-city-tree-read.json').read_text()
    assert '/Users/' not in text and 'atelier-yv2-donor' not in text
    evidence = json.loads(text)
    listed = (ROOT / 'docs' / 'inventory' / 'plants-and-city-tree-packages.txt').read_text().split()
    assert sorted(evidence) == sorted(listed) and len(listed) == 72


def test_the_plan_agrees_with_the_committed_mesh_read_evidence():
    """Before the move the plan (from the donor) is checked; after it, the written records are, with no donor needed."""
    current, _ = ps.state(ROOT)
    if current == 'unprepared':
        if not REAL_DONOR or not (Path(REAL_DONOR).expanduser() / 'brinecove' / 'build-report.json').is_file():
            pytest.skip('needs the donor build (YV2_DONOR_BUILD) before the move')
        plan_ = ps.plan(ROOT, Path(REAL_DONOR).expanduser())
    else:
        plan_ = ps.records_plan(ROOT)
    evidence = json.loads((ROOT / 'docs' / 'inventory' / 'plants-and-city-tree-read.json').read_text())
    assert len(plan_.records) == 72
    assert ps.disagreements(plan_, evidence) == []


def test_the_real_tree_is_split():
    """After the move: 72 records of the families list the packages, and no adopted record lists one."""
    current, detail = ps.state(ROOT)
    if current == 'unprepared':
        pytest.skip('the move has not run on the real tree yet')
    assert (current, detail) == ('done', '72 records list the packages; the adopted records list none')
    planned = ps.records_plan(ROOT)
    assert len(planned.records) == 72 and sorted(planned.packages) == sorted(ps.expected_packages())
    assert list((ROOT / 'assets' / 'adopted' / 'brinecove').glob('plant-*/asset.toml')) == []
    assert not (ROOT / 'assets' / 'adopted' / 'experiments' / 'citytrees' / 'asset.toml').exists()


@pytest.mark.skipif(not REAL_DONOR or not (Path(REAL_DONOR).expanduser() / 'brinecove' / 'build-report.json').is_file(),
                    reason='needs the donor build (YV2_DONOR_BUILD)')
def test_the_done_state_checks_the_written_records_in_a_copy(tmp_path, unprepared):
    """The move applied to a copy of the records (no claim, and the real tree is not written): the state is done, and the
    written records agree with the committed evidence, slot names included. It needs the adopted records, so it runs
    only while the real tree is unprepared; the done state is pinned by test_the_real_tree_is_split."""
    import shutil
    game = tmp_path / 'game'
    shutil.copytree(ROOT / 'assets', game / 'assets')
    plan_ = ps.plan(game, Path(REAL_DONOR).expanduser())
    ops = ps.build_writes(game, plan_)
    for rel, data in ops['writes'].items():
        target = game / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for rel in ops['deletes']:
        (game / rel).unlink()
    assert ps.state(game)[0] == 'done'
    written = ps.records_plan(game)
    evidence = json.loads((ROOT / 'docs' / 'inventory' / 'plants-and-city-tree-read.json').read_text())
    assert len(written.records) == 72 and ps.disagreements(written, evidence) == []


def test_a_v4_slot_label_the_import_does_not_save_is_disagreed_with(fake):
    """A _v4 labelled M_Arcade (the material's name) where the import saves HidamariPalette."""
    p = ps.plan(fake['game'], fake['donor'])
    read = agreeing_read(p)
    v4 = '/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_-1_v4'
    rec = next(r for r in p.records if r.outputs[0] == v4)
    rec.settings['slots'] = [['M_Arcade', rec.settings['slots'][0][1]]]
    out = ps.disagreements(p, ps.evidence(p, read))
    assert any(v4 in d and 'slot name' in d and 'M_Arcade' in d for d in out)
