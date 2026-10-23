"""A validated village export boundary must stop recipe churn without hiding changed reader inputs."""
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from atelier import build
from test_volcano_layers import DIGEST, RECIPE, fbx


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def village_build(tmp_path, monkeypatch, recipe_graph):
    out, regions = tmp_path / 'build', tmp_path / 'regions'
    folder = out / 'village'
    assets = folder / 'assets'
    assets.mkdir(parents=True)
    sources = {}
    for name in ('build.py', 'layout.py', 'decorations.py'):
        path = regions / 'village' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original ' + name)
        sources['village/' + name] = path
    recipe_source = tmp_path / 'recipe.py'
    layout_source = tmp_path / 'layout.py'
    recipe_source.write_text('1')
    layout_source.write_text('1')
    state = dict(run=0, revision=1, world={'player_start': [1, 2, 3, 4], 'village': {'name': 'Momiji'}},
                 heightmap=b'original heightmap', vertices={},
                 manifest={name: {'collision_boxes': 1, 'max': [1, 2, 3], 'source_sha256': 'manifest metadata'}
                           for name in ('Village_First', 'Village_Last')},
                 export_names={'Village_First.fbx', 'Village_Last.fbx', 'Village_Sign.fbx', 'ReceiptOnly.fbx'},
                 metadata={'source_sha256': 'retained identity metadata', 'nested': {'future_sha256': 'retained'}})
    imported, messages = [], []
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)

    def layout(ctx, log):
        (out / 'world.json').write_text(json.dumps(state['world']))
        (out / 'heightmap.npy').write_bytes(state['heightmap'])

    def export(ctx, log):
        state['run'] += 1
        (folder / 'manifest.json').write_text(json.dumps(state['manifest']))
        names = state['export_names'] | {name + '.fbx' for name in state['manifest']} | {'Village_Sign.fbx'}
        for name in sorted(names):
            vertices = state['vertices'].get(name, [0., 1., 2.])
            (assets / name).write_bytes(fbx(2025 + state['run'], (100 * state['run'], 100 * state['run'] + 1), vertices))
        identity = dict(state['metadata'], sources={name: sha(path) for name, path in sources.items()},
                        world_sha256=sha(out / 'world.json'), heightmap_sha256=sha(out / 'heightmap.npy'),
                        exports={name: sha(assets / name) for name in sorted(state['export_names'])})
        (folder / 'build-identity.json').write_text(json.dumps(identity))

    world = recipe_graph['unreal.world']
    assert 'world.village.import' in world.needs and 'world.village' not in world.needs
    steps = [build.Step('world.layout', [build.Call('layout', layout)], inputs=[layout_source],
                        outputs=[out / 'world.json', out / 'heightmap.npy'], cutoff=True),
             build.Step('world.village', [build.Call('export', export)], inputs=[recipe_source, *sources.values()],
                        needs=['world.layout']),
             RECIPE.village_import_step(out, regions=regions),
             build.Step('unreal.world', [build.Call('import', lambda ctx, log: imported.append('world'))],
                        needs=[name for name in world.needs if name in ('world.layout', 'world.village.import')])]
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: steps))

    def run(*, edited=False):
        if edited:
            state['revision'] += 1
            recipe_source.write_text(str(state['revision']))
        return build.build('yorimichi', ['unreal.world'], echo=messages.append)

    assert run() == 0 and imported == ['world']
    imported.clear()
    return SimpleNamespace(out=out, regions=regions, folder=folder, assets=assets, sources=sources, state=state,
                           imported=imported, messages=messages, steps=steps, run=run, layout_source=layout_source)


@pytest.fixture(scope='module')
def recipe_graph(tmp_path_factory):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path_factory.mktemp('village-recipe'), uproject=None)
    return {step.name: step for step in RECIPE.steps(ctx)}


def test_recipe_changes_only_the_village_import_edge(recipe_graph):
    steps = recipe_graph
    assert steps['world.village.import'].needs == ['world.village']
    assert steps['world.village.import'].cutoff and not steps['world.village.import'].heavy
    assert steps['world.village'].needs == ['world.layout']
    assert steps['unreal.world'].needs == [
        'world.hidamari_ferry_cut', 'world.textures', 'world.layout', 'world.props', 'world.hidamari.city', 'world.hidamari_textures',
        'world.hidamari_props.import', 'world.zeppelin.meshes', 'world.terrain.meshes',
        'world.village.import', 'world.sailboat', 'characters.wanderer']
    assert 'unreal.world' in steps['unreal.north'].needs
    assert 'unreal.world' in steps['unreal.southwest'].needs
    assert 'unreal.world' in steps['unreal.see_through'].needs


@pytest.mark.parametrize('legacy', [True, False], ids=['raw-producer-before', 'validated-cutoff-after'])
def test_identical_exports_after_producer_edit_only_reimport_with_the_old_edge(village_build, legacy):
    p = village_build
    if legacy:
        p.steps[-1] = replace(p.steps[-1], needs=['world.layout', 'world.village'])
        assert p.run() == 0
        p.imported.clear()
    receipt = p.out / 'digests/world.village.import.json'
    before = receipt.read_bytes()
    raw_before = (p.assets / 'Village_Last.fbx').read_bytes()
    assert p.run(edited=True) == 0
    assert p.imported == (['world'] if legacy else [])
    if not legacy:
        assert raw_before != (p.assets / 'Village_Last.fbx').read_bytes()
        assert receipt.read_bytes() == before


def test_an_unchanged_successful_cutoff_is_reused(village_build):
    p = village_build
    assert p.run() == 0 and p.state['run'] == 1 and p.imported == []
    assert any(line.split() == ['world.village.import', 'up', 'to', 'date'] for line in p.messages)


@pytest.mark.parametrize('changed', ['world', 'heightmap', 'source', 'geometry', 'seed', 'receipt-only',
                                    'manifest-metadata', 'identity-metadata', 'add', 'remove'])
def test_every_consumed_village_input_requests_world_when_it_changes(village_build, changed):
    p = village_build
    if changed == 'world':
        p.state['world']['player_start'][0] = 50
        p.layout_source.write_text('2')
    elif changed == 'heightmap':
        p.state['heightmap'] = b'changed terrain'
        p.layout_source.write_text('2')
    elif changed == 'source':
        p.sources['village/decorations.py'].write_text('changed village source')
    elif changed in ('geometry', 'seed', 'receipt-only'):
        name = {'geometry': 'Village_Last.fbx', 'seed': 'Village_Sign.fbx', 'receipt-only': 'ReceiptOnly.fbx'}[changed]
        p.state['vertices'][name] = [0., 1., 4.]
    elif changed == 'manifest-metadata':
        p.state['manifest']['Village_Last']['source_sha256'] = 'changed meaningful manifest field'
    elif changed == 'identity-metadata':
        p.state['metadata']['nested']['future_sha256'] = 'changed metadata'
    elif changed == 'add':
        p.state['manifest']['Village_Added'] = {'collision_boxes': 2, 'max': [1, 2, 5]}
    else:
        del p.state['manifest']['Village_Last']
    assert p.run(edited=True) == 0 and p.imported == ['world']


def test_manifest_mesh_and_seed_are_included_even_when_not_receipted(village_build):
    p = village_build
    p.state['export_names'] -= {'Village_Last.fbx', 'Village_Sign.fbx'}
    assert p.run(edited=True) == 0
    p.imported.clear()
    for name in ('Village_Last.fbx', 'Village_Sign.fbx'):
        p.state['vertices'][name] = [3., 4., 5.]
        assert p.run(edited=True) == 0 and p.imported == ['world']
        p.imported.clear()


@pytest.mark.parametrize('missing', ['village/manifest.json', 'village/build-identity.json', 'world.json', 'heightmap.npy',
                                    'village/assets/Village_Last.fbx', 'village/assets/Village_Sign.fbx',
                                    'village/assets/ReceiptOnly.fbx'])
def test_missing_input_cannot_reuse_a_successful_cutoff(village_build, missing):
    p = village_build
    (p.out / missing).unlink()
    assert not DIGEST.village_present(p.out, p.regions)
    with pytest.raises(FileNotFoundError):
        DIGEST.village(p.out, p.regions)
    if missing in ('world.json', 'heightmap.npy'):
        # The real layout owner detects missing declared outputs and restores them first.
        assert p.run() == 0 and p.imported == []
    else:
        assert p.run() == 1 and p.imported == []


@pytest.mark.parametrize('corrupt', ['village/assets/Village_Last.fbx', 'village/assets/ReceiptOnly.fbx',
                                    'village/assets/Village_Sign.fbx', 'world.json', 'heightmap.npy',
                                    'village/build-identity.json', 'village/manifest.json'])
def test_corrupt_input_fails_before_any_fbx_normalization(village_build, monkeypatch, corrupt):
    p = village_build
    # A producer with a written-output inventory repairs its own files (below); without one, the
    # import's receipt validation is the only guard and must refuse.
    stamp = p.out / 'stamps/world.layout.json'
    stamp.write_text(json.dumps({k: v for k, v in json.loads(stamp.read_text()).items() if k != 'output_inventory'}))
    (p.out / corrupt).write_bytes(b'corrupt')
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('Raw receipts must be validated before FBX normalization'))
    assert p.run() == 1 and p.imported == []
    assert not DIGEST.village_present(p.out, p.regions)


@pytest.mark.parametrize('corrupt', ['world.json', 'heightmap.npy'])
def test_corrupted_layout_output_is_rebuilt_by_its_producer_and_cut_off(village_build, monkeypatch, corrupt):
    p = village_build
    original = (p.out / corrupt).read_bytes()
    (p.out / corrupt).write_bytes(b'corrupt')
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('Repaired identical bytes must not renormalize FBX'))
    assert p.run() == 0 and p.imported == []
    assert (p.out / corrupt).read_bytes() == original
    assert any('outputs changed since its stamp' in m for m in p.messages)


def test_stale_source_receipt_fails_before_normalization(village_build, monkeypatch):
    p = village_build
    p.sources['village/decorations.py'].write_text('source changed without rebuilding village')
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('Stale sources must fail before normalization'))
    with pytest.raises(ValueError, match='Stale or corrupt village build identity: decorations.py'):
        DIGEST.village(p.out, p.regions)
    assert not DIGEST.village_present(p.out, p.regions)


def test_timestamp_only_reexport_with_stale_raw_receipt_is_rejected(village_build, monkeypatch):
    p = village_build
    path = p.assets / 'Village_Last.fbx'
    before = DIGEST.fbx(path.read_bytes())
    path.write_bytes(fbx(2099, (1000, 2000), [0., 1., 2.]))
    assert DIGEST.fbx(path.read_bytes()) == before
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('An unchanged normalized FBX cannot excuse a stale raw receipt'))
    assert p.run() == 1 and p.imported == []


@pytest.mark.parametrize('field', ['world_sha256', 'heightmap_sha256', 'sources', 'exports'])
def test_each_stale_raw_receipt_is_rejected_before_normalization(village_build, monkeypatch, field):
    p = village_build
    path = p.folder / 'build-identity.json'
    identity = json.loads(path.read_text())
    if field in ('sources', 'exports'):
        name = sorted(identity[field])[-1]
        identity[field][name] = '0' * 64
    else:
        identity[field] = '0' * 64
    path.write_text(json.dumps(identity))
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('Every raw receipt must pass before normalization'))
    assert p.run() == 1 and p.imported == []


def test_missing_receipted_source_is_rejected_before_normalization(village_build, monkeypatch):
    p = village_build
    p.sources['village/decorations.py'].unlink()
    monkeypatch.setattr(DIGEST, 'fbx', lambda data: pytest.fail('Missing sources must fail before normalization'))
    with pytest.raises(FileNotFoundError):
        DIGEST.village(p.out, p.regions)
    assert not DIGEST.village_present(p.out, p.regions)


def test_receipt_preserves_raw_source_world_heightmap_and_all_metadata(village_build):
    p = village_build
    identity = json.loads((p.folder / 'build-identity.json').read_text())
    receipt = json.loads((p.out / 'digests/world.village.import.json').read_text())
    assert receipt['manifest'] == p.state['manifest']
    assert {key: value for key, value in receipt['identity'].items() if key != 'exports'} == {
        key: value for key, value in identity.items() if key != 'exports'}
    assert set(receipt['files']) == p.state['export_names']
    assert set(receipt['identity']['exports']) == set(identity['exports'])
    assert receipt['identity']['exports']['Village_Last.fbx'] != identity['exports']['Village_Last.fbx']
    assert set(DIGEST.village_inputs(p.out, p.regions)) == {
        p.folder / 'manifest.json', p.folder / 'build-identity.json', p.out / 'world.json', p.out / 'heightmap.npy',
        *p.sources.values(), *(p.assets / name for name in p.state['export_names'])}


def test_review_files_are_not_village_reader_inputs(village_build):
    p = village_build
    (p.folder / 'review.png').write_bytes(b'new review image')
    (p.folder / 'import-report.json').write_text('{}')
    assert p.run(edited=True) == 0 and p.imported == []
