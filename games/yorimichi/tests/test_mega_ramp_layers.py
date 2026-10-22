"""A change to the mini-mega's shape rebuilds the ramp and the map, never the terrain or the world import."""
import json
from pathlib import Path
from types import SimpleNamespace

from atelier import build, build_cache, build_inputs, build_products

MEGA = Path(__file__).resolve().parents[1] / 'world' / 'regions' / 'mega'


def changed_by(edited, tmp_path, monkeypatch, *, stable_products=()):
    """Action dependencies whose fingerprint changes when `edited` changes. Inputs hash by name, and an input that is or contains
    `edited` hashes differently afterwards, so the test reads the recipe's dependencies and needs no built files."""
    # Preparation observes actual saved package bytes after importer ordering.
    # These action-key stand-ins deliberately do not fabricate changed native packages.
    # Real package-byte invalidation is covered by test_foliage_preparation_module.
    editing = False

    def stand_in(digest, path):
        inside = str(path) == str(edited) or str(edited).startswith(f'{path}/')
        digest.update(str(path).encode() + (b'edited' if editing and inside else b''))

    def inventory(path, **kwargs):
        import hashlib
        digest = hashlib.sha256()
        stand_in(digest, path)
        return {'source': digest.hexdigest()}
    # The real deferred ground collector needs a registry to select membership;
    # geometry bytes still use the name-only fingerprint stand-in below.
    library=json.loads((build.paths.game_dir('yorimichi')/'assets/belmonte/source.json').read_text())
    names=[row['name'] for row in library['meshes'] if row['name'].startswith('SM_BM_BT_Terrain_')]
    names.append('SM_BM_NorthApron')
    transform={'translation_cm':[0.,0.,0.],'rotation_xyzw':[0.,0.,0.,1.],'scale':[1.,1.,1.]}
    registry=tmp_path/'belmonte/runtime.json'
    registry.parent.mkdir(parents=True,exist_ok=True)
    registry.write_text(json.dumps({'origin_cm':[55000.,-450000.,21000.],
                                   'groups':[{'asset':f'/Game/{name}.{name}','transforms':[transform],
                                              'plant':False,'collision':True} for name in names]}))
    # This registry contains ground only. The real structure collector still
    # reads the region report before excluding those ground-owned groups.
    (registry.parent/'build-report.json').write_text(json.dumps({'meshes':[], 'materials':{}}))
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps', uproject=None)
    recipe = build.load_recipe('yorimichi').steps(ctx)
    steps = build.order(recipe, [step.name for step in recipe])

    def prints():
        done = {}
        for step in steps:
            done[step.name] = build.fingerprint(step, done)
            for product in step.products:
                # Model changed output bytes, unless this test intentionally keeps a product
                # identical after its producer changes (the consumer's cutoff boundary).
                done['product:' + product.name] = build_products.identity(product.name if product.name in stable_products
                                                                         else (product.name, done[step.name]))
        return done
    monkeypatch.setattr(build, '_hash_path', stand_in)
    monkeypatch.setattr(build_inputs, 'inventory', inventory)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'fixture': 'unchanged tools'})
    before = prints()
    editing = True
    after = prints()
    return {name for name in before if not name.startswith('product:') and before[name] != after[name]}


def test_ramp_shape_rebuilds_only_the_ramp_and_the_map(tmp_path, monkeypatch):
    # The package certifies and cooks every changed import before assembling its download.
    assert changed_by(MEGA/'ramp.py', tmp_path, monkeypatch) == {'world.mega', 'world.map', 'unreal.mega', 'data.stage',
                                                             'data.content', 'data.network', 'unreal.cook', 'unreal.package'}


def test_ramp_place_still_reshapes_the_terrain(tmp_path, monkeypatch):
    changed = changed_by(MEGA/'layout.py', tmp_path, monkeypatch)
    assert {'world.layout', 'world.terrain', 'world.mega', 'world.map', 'unreal.world', 'unreal.mega'} <= changed
