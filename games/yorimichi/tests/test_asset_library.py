"""Fresh-checkout models and park recipes use complete, committed library sources."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tomllib

import numpy as np

from atelier import build
from atelier.gltf import glb_parts

GAME = Path(__file__).resolve().parents[1]
ASSETS = GAME / 'assets'


def test_declared_glb_models_are_self_contained():
    inventory = {name: entry for name, entry in json.loads((ASSETS / 'source-library.json').read_text())['files'].items()
                 if name.endswith('.glb')}
    recorded = {ASSETS / name for name in inventory}
    declared = {path.parent / spec['model'] for path in ASSETS.rglob('asset.toml')
                if isinstance((spec := tomllib.loads(path.read_text())).get('model'), str)
                and spec['model'].endswith('.glb')}
    reference = ASSETS / 'characters/adventure/source'
    declared.update(reference / entry['glb'] for entry in json.loads((reference / 'manifest.json').read_text())['entries'].values())
    declared.add(ASSETS / 'characters/grips/modori/body.glb')
    declared.add(ASSETS / 'communitypark/megapark-textured.glb')
    declared.update(ASSETS / 'skatepark' / entry['file']
                    for entry in json.loads((ASSETS / 'skatepark/modules.json').read_text())['parts'].values())
    assert declared <= recorded
    assert recorded == set(ASSETS.rglob('*.glb'))
    for name, entry in inventory.items():
        path = ASSETS / name
        data = path.read_bytes()
        assert len(data) == entry['bytes'], path
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], path
        doc, binary = glb_parts(data)
        assert doc['meshes'] and binary, path
        assert all('uri' not in buffer for buffer in doc['buffers']), path
        assert all('bufferView' in image for image in doc.get('images', [])), path
        for view in doc['bufferViews']:
            assert view.get('byteOffset', 0) + view['byteLength'] <= len(binary), path


def test_park_geometry_matches_library_contract():
    # These readers run from the source tree with no fetched files or generated assets.
    import sys
    sys.path.insert(0, str(GAME / 'world'))
    import yori  # noqa: F401
    from communitypark.source import FILE, SPEC, scene
    # Scenario collection also imports a skatepark.py; load the region reader independently.
    module_spec = importlib.util.spec_from_file_location('library_skate_modules', GAME / 'world/regions/skatepark/modules.py')
    modules = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(modules)

    pin = json.loads(SPEC.read_text())
    assert FILE == ASSETS / 'communitypark' / pin['file']
    assert hashlib.sha256(FILE.read_bytes()).hexdigest() == pin['sha256']
    park = scene()
    assert (len(park.instances), len(park.gltf['meshes']), len(park.triangles())) == (586, 30, 39595)
    assert modules.available()
    for name, entry in modules.spec()['parts'].items():
        path = ASSETS / 'skatepark' / entry['file']
        assert path == modules.FOLDER / f'{name}.glb'
        assert path.stat().st_size == entry['bytes']
        triangles = modules.local_triangles(name)
        assert len(triangles) == entry['triangles']
        vertices = triangles.reshape(-1, 3)
        np.testing.assert_allclose([vertices.min(0), vertices.max(0)], entry['bounds'], atol=.00011, rtol=0)


def test_fresh_checkout_selects_park_steps_without_fetch(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'no-build-output', uproject=None)
    steps = {step.name: step for step in recipe.steps(ctx)}
    assert not ctx.out.exists()
    source = ASSETS / 'communitypark/megapark-textured.glb'
    assert recipe.communitypark(ctx.out) == source
    assert 'unreal.communitypark' in steps
    assert 'world.communitypark' in steps['data.stage'].needs
    assert 'communitypark/park.json' in recipe.staged(ctx.out)
    assert ASSETS / 'skatepark/modules' in steps['world.skatepark'].inputs
    for name in ('world.hidamari', 'world.terrain', 'world.map'):
        assert source in steps[name].inputs, name
    fetch = tomllib.loads((GAME / 'game.toml').read_text())['fetch']['scripts']
    assert fetch and all(script.startswith('assets/audio/') for script in fetch)


def test_texture_geometry_collision_and_animation_sources_are_complete():
    spec = importlib.util.spec_from_file_location('source_library_verifier', GAME / 'tools/verify_asset_library.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    report = verifier.verify()
    assert report['formats']['.blend'] == 4
    for path in (ASSETS / 'characters').glob('*/character.toml'):
        character = tomllib.loads(path.read_text())
        if character.get('source'):
            assert (path.parent / character['source']).relative_to(ASSETS).as_posix() in report['files']
    park = json.loads((ASSETS / 'megapark/map.json').read_text())
    for entry in [*park['models'], *park['collision'], *park['textures'].values()]:
        file = 'megapark/' + entry.get('npz', entry.get('png', ''))
        assert report['files'][file]['sha256'] == entry['sha256']
