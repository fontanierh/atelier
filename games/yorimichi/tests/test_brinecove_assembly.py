"""Coastal assembly preserves source bytes and refuses foreign destination ownership."""
import ast
import hashlib
import json
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/brinecove'


@pytest.fixture
def files(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    import yori  # noqa: F401
    from brinecove import assembly_files
    return assembly_files


@pytest.mark.parametrize('kind', ['foreign', 'directory', 'linked', 'broken'])
def test_coastal_staging_refuses_before_changing_foreign_bytes(tmp_path, files, kind):
    source = tmp_path / 'Current.glb'; source.write_bytes(b'current model')
    target = tmp_path / 'models'; target.mkdir()
    foreign = target / 'foreign'
    outside = tmp_path / 'outside'; outside.write_bytes(b'not ours')
    if kind == 'foreign': foreign.write_bytes(b'untouched')
    elif kind == 'directory': foreign.mkdir()
    else: foreign.symlink_to(outside if kind == 'linked' else tmp_path / 'missing')
    with pytest.raises(ValueError): files.preflight(target, {'Current.glb': source}, ['Previous.glb'])
    assert outside.read_bytes() == b'not ours'
    assert not (target / 'Current.glb').exists()
    assert foreign.is_symlink() or foreign.exists()


def test_coastal_staging_keeps_unchanged_mtime_and_retires_only_after_complete_publication(tmp_path, files):
    from atelier.export_manifest import sha
    source = tmp_path / 'Current.glb'; source.write_bytes(b'current model')
    target = tmp_path / 'models'; target.mkdir()
    stale = target / 'Previous.glb'; stale.write_bytes(b'old owned model')
    sources = {'Current.glb': source}; identities = {'Current.glb': sha(source)}
    files.preflight(target, sources, ['Previous.glb'])
    files.stage(target, sources, identities)
    assert stale.exists()  # staging cannot retire the previous published library
    previous = (target / 'Current.glb').stat().st_mtime_ns
    files.stage(target, sources, identities)
    assert (target / 'Current.glb').stat().st_mtime_ns == previous
    source.write_bytes(b'changed source')
    with pytest.raises(ValueError): files.stage(target, sources, identities)
    assert stale.exists() and (target / 'Current.glb').read_bytes() == b'current model'
    files.retire(target, sources)
    assert not stale.exists()


def test_extracted_hero_and_foliage_definitions_match_recorded_original_source():
    """Independent immutable Git source, rather than a duplicate of the new implementation."""
    baseline = json.loads((GAME / 'tests/fixtures/brinecove-placement-source.json').read_text())
    assert baseline['revision'].startswith('099b747ed')
    for original, current, selected in (
        ('hero_assets.py', 'hero_model.py', {'_import'}),
        ('hero_assets.py', 'hero_placements.py', {'placements'}),
        ('flora.py', 'foliage_placements.py', {'Poisson', '_ridge', 'scatter', 'groundcover', 'bloom_spots'}),
    ):
        expected = {key: value for key, value in baseline['files'][original]['definitions'].items() if key in selected}
        actual = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                  for node in ast.parse((REGION / current).read_text()).body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in selected}
        assert expected.keys() == selected
        assert actual == expected


def test_real_coastal_assembly_preserves_declared_auxiliary_rock_sources(tmp_path, files, monkeypatch):
    import struct
    from atelier.gltf import glb_pack
    from atelier.export_manifest import sha
    from brinecove import assemble, foliage_library, runtime_data
    from brinecove.runtime_data import IDENTITY
    textures = tmp_path / 'source-textures'; textures.mkdir()
    for stem in ('rock', 'terrain_sand', 'terrain_meadow', 'terrain_forest', 'terrain_rock'):
        (textures / (stem+'.jpg')).write_bytes(stem.encode())
    for stem in ('terrain_sand_n', 'terrain_meadow_n', 'terrain_forest_n', 'terrain_rock_n'):
        (textures / (stem+'.png')).write_bytes(stem.encode())
    monkeypatch.setattr(runtime_data, 'TEXTURES', textures)
    # Plant product admission is covered separately; this fixture exercises full
    # assembly/material/staging logic with no placed plants.
    monkeypatch.setattr(foliage_library, 'load', lambda _: {})
    root = tmp_path / 'build'; assets = root / 'atomic_regions/brinecove/assets'; assets.mkdir(parents=True)
    def model(key, slot):
        doc = dict(asset=dict(version='2.0'), buffers=[dict(byteLength=44)],
            bufferViews=[dict(buffer=0,byteOffset=0,byteLength=36),dict(buffer=0,byteOffset=36,byteLength=6)],
            accessors=[dict(bufferView=0,componentType=5126,count=3,type='VEC3',min=[0,0,0],max=[1,0,1]),
                       dict(bufferView=1,componentType=5123,count=3,type='SCALAR')],
            materials=[dict(name='BC_'+slot)],meshes=[dict(primitives=[dict(attributes=dict(POSITION=0),indices=1,material=0)])],
            nodes=[dict(mesh=0)],scenes=[dict(nodes=[0])],scene=0)
        path = assets / (key+'.glb')
        path.write_bytes(glb_pack(doc,struct.pack('<9f3H',0,0,0,1,0,0,0,0,1,0,1,2)+b'\0\0'))
        return dict(asset=key,primary=path.name,sha256=sha(path),triangles=1)
    ground, hero = 'SM_BC_Ground_cell_0_0','SM_BC_Hero_Fixture'
    rows = [model(ground,'rock'),model(hero,'hero_fixture_0')]
    (assets/'manifest.json').write_text(json.dumps(dict(schema=1,complete=True,exports=rows)))
    policy = dict(collision=True,shadow=True,cull_cm=0)
    library = dict(schema=1,parents={'SM_BC_Ground':[ground],hero:[hero]},ownership={
        'SM_BC_Ground':dict(kind='mesh_set',metadata={ground:policy},diagnostics=dict(seam={'pass':True},outside=0,drowned=0,degenerate=0)),hero:{}})
    (assets.parent/'logical-pieces.json').write_text(json.dumps(library))
    data = root / 'brinecove-data'; (data/'heroes/fixture').mkdir(parents=True)
    (data/'placements.json').write_text(json.dumps(dict(schema=1,heroes={'fixture':[IDENTITY]},plants={},scrub={},quay_z=1)))
    image = data/'heroes/fixture/T_BC_hero_fixture_0.png'; image.write_bytes(b'fixture texture')
    (image.parent/'materials.json').write_text(json.dumps(dict(complete=True,slug='fixture',
        materials={'hero_fixture_0':dict(texture=image.name)},files={image.name:sha(image)})))
    report_path = root/'brinecove/build-report.json'
    assemble.assemble(root,expected_parents=list(library['parents']),heroes=['fixture'])
    result = json.loads(report_path.read_text())
    assert result['auxiliary_textures']=={'T_BC_rock.jpg':sha(textures/'rock.jpg')}
    assert (root/'brinecove/textures/T_BC_rock.jpg').read_bytes()==b'rock'
    assert len(result['meshes'])==2
    before = report_path.read_bytes()
    foreign = root/'brinecove/textures/Foreign.png'; foreign.write_bytes(b'untouched')
    with pytest.raises(ValueError,match='Foreign'):
        assemble.assemble(root,expected_parents=list(library['parents']),heroes=['fixture'])
    assert foreign.read_bytes()==b'untouched' and report_path.read_bytes()==before


def test_retiring_auxiliary_texture_needs_its_exact_prior_bytes(tmp_path, files):
    from brinecove.assemble import previous_textures
    from atelier.export_manifest import sha
    path = tmp_path/'T_BC_previous.jpg'; path.write_bytes(b'owned')
    prior = dict(materials={},auxiliary_textures={path.name:sha(path)})
    assert previous_textures(prior,tmp_path,{})=={path.name}
    path.write_bytes(b'foreign replacement')
    with pytest.raises(ValueError,match='differs'): previous_textures(prior,tmp_path,{})
    assert path.read_bytes()==b'foreign replacement'
