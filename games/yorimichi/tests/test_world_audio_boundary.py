"""A world rebuild must preserve the independent footstep owner and its true type boundary."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_products


GAME = Path(__file__).resolve().parents[1]


def catalog():
    spec = importlib.util.spec_from_file_location('world_audio_catalog', GAME / 'world/asset_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_world_purge_preserves_audio_bytes_and_keeps_legacy_cleanup():
    owned = {'/Game/Japan/Audio/A_Footstep', '/Game/Japan/Audio/DA_Footsteps',
             '/Game/Japan/Audio/Footsteps/wood/step_00', '/Game/Japan/Assets/Tree_Broad_A'}
    legacy = {'/Game/Japan/Audio/UnknownLegacy', '/Game/Japan/Audio/FootstepsOld/step',
              '/Game/Japan/Assets/OldProp'}
    packages = {name: b'original saved package' for name in owned | legacy}
    assets = [SimpleNamespace(package_name=name, asset_class_path=SimpleNamespace(asset_name='SoundWave'))
              for name in packages]
    registry = SimpleNamespace(get_assets_by_path=lambda *a, **k: assets)
    unreal = SimpleNamespace(AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry))
    script = GAME / 'unreal/Scripts/setup_project.py'
    body = [node for node in ast.parse(script.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name == 'purge']
    namespace = {'unreal': unreal, 'independently_owned': catalog().independently_owned,
                 'EAL': SimpleNamespace(delete_asset=lambda path: packages.pop(path)), 'LOG': lambda value: None}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(script), 'exec'), namespace)
    namespace['purge']()
    assert packages == {name: b'original saved package' for name in owned}


def test_sound_key_uses_its_saved_type_and_audio_instead_of_the_world(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    graph = build_products.Graph(build.load_recipe('yorimichi').steps(ctx))
    sound = graph.by_name['unreal.sounds']
    assert 'unreal.world' not in sound.needs + sound.after
    assert 'unreal.compile' not in sound.needs
    assert 'unreal.module.YorimichiAssets' in sound.needs
    assert len(sound.commands) == 6
    assert all(command.modules == ('YorimichiAssets',) for command in sound.commands)
    monkeypatch.setattr(build, '_hash_path', lambda digest, path: digest.update(str(path).encode()))
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **k: {'tools': 'unchanged'})
    before = {name: 'same' for name in graph.by_name}
    key = build.fingerprint(sound, before)
    assert build.fingerprint(sound, dict(before, **{'unreal.world': 'new world',
                                                   'unreal.compile': 'new prep compiler output'})) == key
    assert build.fingerprint(sound, dict(before, **{'unreal.module.YorimichiAssets': 'changed saved type'})) != key
    for name in ('footsteps', 'combat', 'skate', 'kart', 'bike', 'transport'):
        assert build.fingerprint(sound, dict(before, **{'audio.' + name: 'changed source audio'})) != key


def test_audio_type_moves_keep_serialized_names_and_runtime_include():
    source = GAME / 'unreal/Source'
    header = (source / 'YorimichiAssets/Public/JapanFootstepSet.h').read_text()
    runtime = (source / 'Yorimichi/JapanFootsteps.h').read_text()
    redirects = (GAME / 'unreal/Config/DefaultEngine.ini').read_text()
    assert 'class YORIMICHIASSETS_API UJapanFootstepSet' in header
    assert 'struct YORIMICHIASSETS_API FJapanFootstepBank' in header
    assert '#include "JapanFootstepSet.h"' in runtime
    assert 'class YORIMICHI_API UJapanFootstepSet' not in runtime
    for kind, name in (('Class', 'JapanFootstepSet'), ('Struct', 'JapanFootstepBank')):
        assert (f'+{kind}Redirects=(OldName="/Script/Yorimichi.{name}",'
                f'NewName="/Script/YorimichiAssets.{name}")') in redirects


def test_sound_inventory_covers_all_waves_reports_and_late_sidecars(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    monkeypatch.setattr(recipe, 'GAME', tmp_path / 'game')
    product, = recipe.sound_native_products(tmp_path / 'build')
    for path in product.paths:
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'complete saved asset or report')
        else:
            path.mkdir(parents=True)
            (path / 'wave.uasset').write_bytes(b'saved wave')
    original = build_products.inventory(product)
    sidecar = next(path for path in product.optional_paths if path.name == 'DA_Footsteps.m.ubulk')
    sidecar.write_bytes(b'new bulk sidecar')
    assert build_products.inventory(product) != original
    sidecar.unlink()
    wave = next(path / 'wave.uasset' for path in product.paths if path.name == 'Driving')
    wave.write_bytes(b'changed driving wave')
    assert build_products.inventory(product) != original
    missing = next(path for path in product.paths if path.name == 'footsteps_import.json')
    missing.unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        build_products.inventory(product)
