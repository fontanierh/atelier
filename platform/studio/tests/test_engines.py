"""Engines: which one a game runs on, how each launches a play profile, the Cargo build command and the Bevy template.

    uv run pytest platform/studio/tests/test_engines.py -q

Nothing is compiled or launched, except `atelier.run_in` running `pwd`.
"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, engines, manifest, new, paths
from atelier.build_cargo import Cargo


def test_a_manifest_names_its_engine_and_an_old_unreal_one_still_loads(tmp_path):
    assert engines.name_of({'engine': 'bevy'}, tmp_path) == 'bevy'
    with pytest.raises(SystemExit, match='names no engine'):
        engines.name_of({}, tmp_path)
    (tmp_path / 'unreal').mkdir()
    (tmp_path / 'unreal/Game.uproject').write_text('{}')
    assert engines.name_of({}, tmp_path) == 'unreal'
    with pytest.raises(SystemExit, match='unknown engine'):
        engines.named('godot')


def test_every_game_in_the_repository_names_an_engine_there_is():
    for folder in sorted(path for path in paths.GAMES.iterdir() if (path / 'game.toml').is_file()):
        data = manifest.game(folder.name)
        assert 'engine' in data, f'{folder.name}/game.toml names no engine'
        assert engines.named(data['engine']).name == data['engine']


def test_unreal_launches_the_editor_binary_on_the_project():
    ctx = SimpleNamespace(unreal_app=Path('/UE/UnrealEditor'), uproject=Path('/g/unreal/G.uproject'), game_dir=Path('/g'))
    command, env = engines.named('unreal').launch(ctx, {}, 'play', {'args': ['-game', '-log={run}/x']}, Path('/run'),
                                                  'a=1', ['-windowed'])
    assert command == ['/UE/UnrealEditor', '/g/unreal/G.uproject', '-game', '-log=/run/x', '-stdout',
                       '-abslog=/run/game.log', '-windowed', '-set=a=1']
    assert env == ()


def bevy_game(tmp_path, spec):
    (tmp_path / 'Cargo.toml').write_text('[package]\nname = "g"\n')
    data = {'engine': 'bevy', 'play': {'play': spec}}
    return SimpleNamespace(game='g', game_dir=tmp_path), data


def test_bevy_runs_the_built_binary_from_its_workspace(tmp_path):
    ctx, data = bevy_game(tmp_path, {})
    spec = {'binary': 'target/release/g', 'args': ['--log', '{run}/g.log'],
            'env': {'BEVY_ASSET_ROOT': '{workspace}'}, 'settings_env': 'G_SET'}
    bevy = engines.named('bevy')
    with pytest.raises(SystemExit, match='is not built'):
        bevy.launch(ctx, data, 'play', spec, tmp_path / 'run', '', [])
    binary = tmp_path / 'target/release/g'
    binary.parent.mkdir(parents=True)
    binary.write_text('')
    command, env = bevy.launch(ctx, data, 'play', spec, tmp_path / 'run', 'a=1', ['--fast'])
    assert command == [str(binary), '--log', f'{tmp_path / "run"}/g.log', '--fast']
    assert dict(env) == {'BEVY_ASSET_ROOT': str(tmp_path.resolve()), 'G_SET': 'a=1'}
    with pytest.raises(SystemExit, match='takes no --set'):
        bevy.launch(ctx, data, 'play', {'binary': 'target/release/g'}, tmp_path / 'run', 'a=1', [])
    with pytest.raises(SystemExit, match='names no binary'):
        bevy.launch(ctx, data, 'play', {}, tmp_path / 'run', '', [])


def test_bevy_doctor_checks_cargo_and_the_workspace(tmp_path):
    ctx, data = bevy_game(tmp_path, {})
    messages = [message for _, message in engines.named('bevy').checks(ctx, data)]
    assert any('cargo' in message for message in messages)
    assert (True, f'Cargo workspace {tmp_path.resolve() / "Cargo.toml"}') in engines.named('bevy').checks(ctx, data)


def test_only_unreal_streams_and_has_the_live_bridge():
    assert (engines.named('unreal').stream, engines.named('unreal').live) == (True, True)
    assert (engines.named('bevy').stream, engines.named('bevy').live) == (False, False)


def test_cargo_runs_in_its_workspace_with_capped_workers_and_takes_the_compile_slot(tmp_path):
    command = Cargo(('build', '--release'), workspace=tmp_path)
    assert command.argv(None) == [sys.executable, '-m', 'atelier.run_in', str(tmp_path), 'cargo', 'build', '--release']
    assert dict(command.env) == {'CARGO_BUILD_JOBS': '3'}
    ctx = SimpleNamespace(logs=tmp_path / 'logs')
    assert build.slot_request(ctx, build.Step('binary', [command], heavy=True)) == ('compile', None)
    assert build.slot_request(ctx, build.Step('compile', [build.UnrealCompile('GameEditor')], heavy=True)) == ('compile', None)
    assert build.slot_request(ctx, build.Step('job', [build.Python(tmp_path / 'x.py')], heavy=True))[0] == 'job'


def test_the_cargo_fingerprint_names_its_arguments_and_workspace_only(tmp_path):
    assert repr(Cargo(('build',), workspace=tmp_path)) == f"Cargo(args=('build',), workspace={tmp_path!r}, jobs=3, timeout=7200, progress=25.0)"


def test_the_cargo_launcher_and_adapter_enter_the_steps_inputs(tmp_path):
    step = build.Step('binary', [Cargo(('build',), workspace=tmp_path)], heavy=True)
    assert {Path(build.__file__).with_name(name) for name in ('build_cargo.py', 'run_in.py')} <= set(
        build.required_inputs(step))


def test_run_in_runs_the_command_in_the_folder_as_this_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'atelier.run_in', str(tmp_path), 'pwd'], cwd=root,
                            capture_output=True, text=True, check=True)
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


def test_a_new_bevy_game_is_the_template_named_after_it(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, 'GAMES', tmp_path)
    assert new.main('my_game', 'My Game', engine='bevy') == 0
    game = tmp_path / 'my_game'
    assert sorted(str(p.relative_to(game)) for p in game.rglob('*') if p.is_file()) == [
        '.gitignore', 'Cargo.toml', 'README.md', 'build.py', 'game.toml', 'src/main.rs']
    for path in game.rglob('*'):
        if path.is_file():
            assert '__game__' not in path.read_text() and '__Title__' not in path.read_text(), path
    import tomllib
    data = tomllib.loads((game / 'game.toml').read_text())
    assert (data['id'], data['title'], data['engine']) == ('my_game', 'My Game', 'bevy')
    assert data['play']['play']['binary'] == 'target/release/my_game'
    assert 'name = "my_game"' in (game / 'Cargo.toml').read_text()
    # Its build step names the program as an output, so a missing program makes the step run again.
    import importlib.util
    spec = importlib.util.spec_from_file_location('new_game_recipe', game / 'build.py')
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    step, = recipe.steps(None)
    assert step.outputs == [game / 'target/release/my_game']
    assert not build.outputs_present(step)
    with pytest.raises(SystemExit, match='already exists'):
        new.main('my_game', engine='bevy')
