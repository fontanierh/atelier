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
    assert {name for name in before if before[name] != after[name]} == {
        'unreal.city_tree_cpu_access', 'unreal.desktop', 'unreal.package'}

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
