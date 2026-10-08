"""Runtime tree metadata must not invalidate the much larger world import."""
from types import SimpleNamespace
import hashlib
import json

from atelier import build


def test_cpu_metadata_edit_reruns_only_the_tree_overlay_desktop_and_package(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = build.order(recipe.steps(ctx), ['unreal.package'])
    versions = {}
    # Exercise the entire real dependency graph without reading assets or executing any commands.
    monkeypatch.setattr(build, '_hash_path', lambda digest, path:
                        digest.update((str(path) + versions.get(path, 'v1')).encode()))

    def fingerprints():
        result = {}
        for step in steps:
            result[step.name] = build.fingerprint(step, result)
        return result

    before = fingerprints()
    versions[recipe.SCRIPTS / 'city_tree_cpu_access.py'] = 'v2'
    after = fingerprints()
    # Changed imported bytes must also refresh the multiplayer compatibility manifest.
    assert {name for name in before if before[name] != after[name]} == {
        'unreal.city_tree_cpu_access', 'unreal.desktop', 'data.network', 'unreal.cook', 'unreal.package'}

    # A real world importer change still invalidates the world and overlays.
    versions[recipe.SCRIPTS / 'import_hidamari.py'] = 'v2'
    world_changed = fingerprints()
    assert all(world_changed[name] != after[name] for name in (
        'unreal.world', 'unreal.city_tree_cpu_access', 'unreal.desktop', 'unreal.bike', 'unreal.package'))


def test_cpu_overlay_is_ordered_before_variants_and_records_a_required_output(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = build.order(recipe.steps(ctx), ['unreal.desktop'])
    names = [s.name for s in steps]
    assert names.index('unreal.world') < names.index('unreal.city_tree_cpu_access') < names.index('unreal.desktop')
    overlay = next(s for s in steps if s.name == 'unreal.city_tree_cpu_access')
    assert overlay.heavy and overlay.outputs == [tmp_path / 'city_tree_lods' / 'production-cpu-access.json']


def test_overwritten_tree_invalidates_the_overlay_even_with_unchanged_world_inputs(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(out=tmp_path / 'build', uproject=tmp_path / 'unreal' / 'Yorimichi.uproject')
    assert not recipe.city_tree_cpu_access_present(ctx)
    root = ctx.uproject.parent / 'Content' / 'Japan' / 'Assets'
    root.mkdir(parents=True)
    report = {}
    for name in ('HD_ArcadeTree', 'HD_PlazaTreeGold', 'HD_PlazaTreeOrange'):
        data = (name + '-cpu-access').encode()
        (root / (name + '.uasset')).write_bytes(data)
        report[name] = {'allow_cpu_access': True, 'sha256': hashlib.sha256(data).hexdigest()}
    path = ctx.out / 'city_tree_lods' / 'production-cpu-access.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report))
    assert recipe.city_tree_cpu_access_present(ctx)
    # A forced/partial import can reset the flag with the same recipe inputs. Cached JSON alone is insufficient.
    (root / 'HD_ArcadeTree.uasset').write_bytes(b'reimported mesh')
    assert not recipe.city_tree_cpu_access_present(ctx)


def test_bounds_rounding_preserves_exact_topology_and_material(monkeypatch):
    import copy
    import runpy
    import sys

    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace())
    module = runpy.run_path(str(build.load_recipe('yorimichi').SCRIPTS / 'city_tree_cpu_access.py'))
    matches = module['geometry_matches']
    before = dict(lods=1, triangles=56964, sections=1, material='/Game/Japan/Materials/M_Arcade',
                  bounds=dict(origin=[4.8125457763671875, 2.2609710693359375, 484.3774404525757],
                              box_extent=[432.87681579589844, 434.5858612060547, 514.3774423599243]))
    # Actual native before/after values from changing and saving the production tree CPU flag.
    after = copy.deepcopy(before)
    after['bounds'] = dict(origin=[4.8125457763671875, 2.2609710693359375, 484.37744140625],
                          box_extent=[432.8768310546875, 434.58587646484375, 514.37744140625])
    assert matches(before, after)
    moved = copy.deepcopy(after)
    moved['bounds']['origin'][0] += .0011
    assert not matches(before, moved)
    for field, changed in (('lods', 2), ('triangles', 56963), ('sections', 2), ('material', '/Different')):
        modified = copy.deepcopy(after)
        modified[field] = changed
        assert not matches(before, modified), field
