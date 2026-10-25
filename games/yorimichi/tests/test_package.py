"""The packaged macOS game: one guarded compile-kind turn, then a zip a GitHub release can carry."""
import importlib.util
import json
import plistlib

import pytest
import os
import sys
import subprocess
from types import SimpleNamespace

from atelier import build

# The artifact is a macOS .app assembled with ditto and launched by a .command script, so it runs
# in the macOS CI group and skips anywhere else.
pytestmark = [pytest.mark.macos_only,
              pytest.mark.skipif(sys.platform != 'darwin',
                                 reason='macOS packaging: ditto and a .command launcher')]


def archive_tool():
    path = build.load_recipe('yorimichi').TOOLS / 'package_archive.py'
    spec = importlib.util.spec_from_file_location('yorimichi_package_archive', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def recipe_steps(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps',
                          uproject=tmp_path/'Yorimichi.uproject', unreal_root=tmp_path/'UE')
    return ctx, build.load_recipe('yorimichi').steps(ctx)


def test_music_selectors_are_part_of_the_build_key(tmp_path, monkeypatch):
    monkeypatch.setenv('YORIMICHI_MUSIC_CATEGORIES', 'calm')
    _, calm_steps = recipe_steps(tmp_path)
    calm = next(s for s in calm_steps if s.name == 'audio.music')
    assert calm.explicit and calm.commands[0].args[:2] == ('--categories', 'calm')
    monkeypatch.setenv('YORIMICHI_MUSIC_CATEGORIES', 'action')
    _, action_steps = recipe_steps(tmp_path)
    action = next(s for s in action_steps if s.name == 'audio.music')
    assert repr(calm.commands) != repr(action.commands)


def test_package_cooks_after_every_import_then_assembles_in_a_separate_turn(tmp_path):
    ctx, steps = recipe_steps(tmp_path)
    package = next(s for s in steps if s.name == 'unreal.package')
    cook = next(s for s in steps if s.name == 'unreal.cook')
    imports = {s.name for s in steps if s.name.startswith('unreal.') and not s.explicit
               and s.name not in {'unreal.cook', 'unreal.package'}}
    assert imports <= set(cook.needs) and 'data.stage' in cook.needs and cook.heavy and cook.explicit
    assert 'unreal.music' not in cook.needs
    assert package.needs == ['unreal.cook'] and package.heavy and package.explicit
    # Never part of a plain or prefix build: only when named.
    assert not {'unreal.package', 'unreal.cook'} & {s.name for s in build.order(steps, [])}
    assert not {'unreal.package', 'unreal.cook'} & {s.name for s in build.order(steps, ['unreal'])}
    assert 'unreal.music' not in {s.name for s in build.order(steps, [])}
    assert 'unreal.music' not in {s.name for s in build.order(steps, ['unreal'])}
    assert 'unreal.music' in {s.name for s in build.order(steps, ['unreal.music'])}
    assert 'unreal.package' in {s.name for s in build.order(steps, ['unreal.package'])}
    # Compile kind: the big slot and the small one, like any compile.
    assert build.slot_request(ctx, cook) == ('compile', None)
    assert build.slot_request(ctx, package)[0] == 'job'
    prepare, uat, certify = cook.commands
    archive, = package.commands
    assert prepare.name == 'prepare_cook'
    assert certify.name == 'certify_cook' and '--cook-receipt' in archive.args
    # The archive phase is its own guarded job (a released boundary after UAT) whose ditto/split children are watched.
    assert archive.script.name == 'package_archive.py' and {'ditto', 'split'} <= set(archive.watch)
    assert archive.marker == 'PACKAGE ARCHIVE COMPLETE' and 0 < archive.progress <= 30 and archive.timeout > 0
    argv = uat.argv(ctx)
    assert argv[0].endswith('RunUAT.sh') and argv[1] == 'BuildCookRun'
    # UAT runs UnrealBuildTool itself, past the capped Build.sh wrapper, so the worker cap is passed explicitly.
    # The game binary is its own step: UAT must not rebuild it inside the cook.
    assert '-skipbuild' in argv and '-build' not in argv
    assert '-ubtargs=-MaxParallelActions=3' in argv and '-cookall' in argv
    assert 'unreal.game_binary' in cook.needs
    # Without -package the Mac archive copies Binaries/Mac/<game>.app: no paks, no Content/Data.
    assert argv.index('-stage') < argv.index('-package') < argv.index('-archive')
    assert f'-archivedirectory={tmp_path/"package"/"archive"}' in argv and '-nocompileeditor' in argv
    assert uat.timeout > 0 and 'UnrealEditor-Cmd' in uat.watch and 0 < uat.progress <= 30


def test_package_zip_checksums_and_splits_for_release_assets(tmp_path, monkeypatch):
    ctx, steps = recipe_steps(tmp_path)
    recipe, tool = build.load_recipe('yorimichi'), archive_tool()
    monkeypatch.setattr(tool, 'audio_compatibility', lambda app, log: None)
    app = tmp_path/'package'/'archive'/'Mac'/'Yorimichi.app'/'Contents'/'MacOS'
    app.mkdir(parents=True)
    binary = os.urandom(100_000)   # incompressible, so the zip really exceeds a tiny part size
    (app/'Yorimichi').write_bytes(binary)
    (app.parent/'Info.plist').write_text('<plist/>')
    (app.parent/'Current').symlink_to('MacOS')
    data = app.parent/'UE'/'Yorimichi'/'Content'/'Data'
    log = open(tmp_path/'log.txt', 'w')
    # Without the loose runtime data the package would start into an empty world: refuse it.
    with pytest.raises(RuntimeError, match='staged runtime data'):
        tool.package_zip(tmp_path/'package', log)
    for rel in tool.STAGED_DATA:
        (data/rel).parent.mkdir(parents=True, exist_ok=True); (data/rel).write_text('{}')
    with monkeypatch.context() as isolated:
        isolated.setattr(tool, 'head', lambda *a, **kw: pytest.fail('isolated v2 archive cannot read Git provenance'))
        tool.package_zip(tmp_path/'package', log, revision='v2-' + 'a' * 64)
    manifest = json.loads((tmp_path/'package'/'manifest.json').read_text())
    assert manifest['revision'] == 'v2-' + 'a' * 64
    assert manifest['app'] == 'Yorimichi.app' and not manifest['split'] and len(manifest['files']) == 1
    assert recipe.package_present(tmp_path)
    sums = (tmp_path/'package'/'SHA256SUMS').read_text()
    assert manifest['files'][0]['sha256'] in sums and manifest['zip'] in sums

    # Larger than one release asset: numbered parts that rejoin into the same zip.
    monkeypatch.setattr(tool, 'PART_BYTES', 20_000)
    tool.package_zip(tmp_path/'package', log)
    manifest = json.loads((tmp_path/'package'/'manifest.json').read_text())
    parts = [tmp_path/'package'/f['file'] for f in manifest['files']]
    assert manifest['split'] and len(parts) > 1 and not (tmp_path/'package'/manifest['zip']).exists()
    joined = tmp_path/'joined.zip'
    joined.write_bytes(b''.join(p.read_bytes() for p in parts))
    out = tmp_path/'unzipped'
    subprocess.run(['ditto', '-x', '-k', str(joined), str(out)], check=True)
    folder = out/'Yorimichi'
    assert (folder/'Yorimichi.app'/'Contents'/'MacOS'/'Yorimichi').read_bytes() == binary
    assert (folder/'Yorimichi.app'/'Contents'/'Current').is_symlink()
    assert os.access(folder/'Play Yorimichi.command', os.X_OK) and 'Play Yorimichi.command' in (folder/'README.txt').read_text()


def test_the_packaged_launcher_carries_the_desktop_profile_and_saved_settings(tmp_path):
    folder = tmp_path/'Yorimichi'
    game = folder/'Yorimichi.app'/'Contents'/'MacOS'/'Yorimichi'
    game.parent.mkdir(parents=True)
    bundle_id = 'org.atelier.PackageTest'
    (game.parent.parent/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': bundle_id}))
    game.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$HOME/args.txt"\n'); game.chmod(0o755)
    launcher = folder/'Play Yorimichi.command'
    launcher.write_text(archive_tool().desktop_preview().packaged_launcher()); launcher.chmod(0o755)
    home = tmp_path/'home'; home.mkdir()

    def launch():
        subprocess.run([str(launcher)], env={'HOME': str(home), 'PATH': '/usr/bin:/bin'}, check=True)
        return (home/'args.txt').read_text().splitlines()
    args = launch()
    container = home/'Library'/'Containers'/bundle_id/'Data'
    settings = container/'Library'/'Application Support'/'Yorimichi'/'settings.txt'
    assert f'-abslog={container/"Library"/"Logs"/"Yorimichi"/"game.log"}' in args
    assert '-desktopnative1440' in args and f'-preferencesfile={settings}' in args
    assert '-characterselect' in args
    assert '-llm' not in args   # tried and dropped: the retry below covers the startup crash (docs/PACKAGING.md)
    assert '-set=desktop=1;performance=1;render_scale=100;renderer=0' in args
    assert any('r.ForwardShading=True' in a and 'DesktopPreviewViewportClient' in a for a in args)
    assert any(a.startswith('-ExecCmds=') for a in args)
    assert not any('japan.CitySurfaceTiles' in a for a in args)
    # Saved choices win, except the renderer: the package is cooked for forward shading, so a saved Lumen choice still
    # starts Forward.
    settings.write_text('performance=0\nrender_scale=80\nrenderer=1\n')
    args = launch()
    assert '-set=desktop=1;renderer=0' in args and any('r.ForwardShading=True' in a for a in args)
    assert not any('r.ForwardShading=False' in a for a in args)
    # A malformed bundle identity must not redirect the launcher outside the container or run the game.
    (game.parent.parent/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': '../outside'}))
    (home/'args.txt').unlink()
    refused = subprocess.run([str(launcher)], env={'HOME': str(home), 'PATH': '/usr/bin:/bin'}, capture_output=True)
    assert refused.returncode != 0 and not (home/'args.txt').exists()


@pytest.mark.parametrize('runs, startup_seconds, expected_runs, expected_status', [
    (['segv', 'ok'], 20, 2, 0),           # the startup race: one retry, then the game runs
    (['segv', 'segv'], 20, 2, -11),       # never more than one retry: the retry is the game itself (exec)
    (['log-segv', 'ok'], 20, 1, 139),     # the engine had started (game.log written): a real crash
    (['rewrite-segv', 'ok'], 20, 1, 139), # a same-size rewrite of the old log within the same second also counts
    (['segv', 'ok'], 0, 1, 139),          # a crash after the startup window is never retried
    (['fail', 'ok'], 20, 1, 3),           # other exits pass straight through
    (['ok', 'ok'], 20, 1, 0),
])
def test_the_packaged_launcher_retries_only_an_early_startup_segfault(tmp_path, runs, startup_seconds, expected_runs,
                                                                     expected_status):
    folder = tmp_path/'Yorimichi'
    game = folder/'Yorimichi.app'/'Contents'/'MacOS'/'Yorimichi'
    game.parent.mkdir(parents=True)
    bundle_id = 'org.atelier.PackageTest'
    (game.parent.parent/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': bundle_id}))
    # Each run takes the next behaviour: exit 0, exit 3, SIGSEGV, or append to or rewrite game.log and then SIGSEGV.
    game.write_text('#!/bin/bash\n'
                    'n=$(( $(wc -l < "$HOME/runs.txt" 2>/dev/null || echo 0) + 1 )); printf "%s\\n" "$*" >> "$HOME/runs.txt"\n'
                    'log=$(printf "%s\\n" "$@" | sed -n "s/^-abslog=//p")\n'
                    'case $(sed -n "${n}p" "$HOME/plan.txt") in\n'
                    '  ok) exit 0 ;; fail) exit 3 ;; segv) kill -SEGV $$ ;; log-segv) echo started >> "$log"; kill -SEGV $$ ;;\n'
                    '  rewrite-segv) echo earlier > "$log"; kill -SEGV $$ ;;\n'
                    'esac\n'); game.chmod(0o755)
    launcher = folder/'Play Yorimichi.command'
    launcher.write_text(archive_tool().desktop_preview().packaged_launcher(startup_seconds)); launcher.chmod(0o755)
    home = tmp_path/'home'; home.mkdir()
    (home/'plan.txt').write_text('\n'.join(runs) + '\n')
    logs = home/'Library'/'Containers'/bundle_id/'Data'/'Library'/'Logs'/'Yorimichi'
    logs.mkdir(parents=True); (logs/'game.log').write_text('earlier\n')   # the previous session's log
    result = subprocess.run([str(launcher), '-extra'], env={'HOME': str(home), 'PATH': '/usr/bin:/bin'},
                            capture_output=True, text=True)
    lines = (home/'runs.txt').read_text().splitlines()
    assert (len(lines), result.returncode) == (expected_runs, expected_status)
    assert len(set(lines)) == 1 and lines[0].endswith('-extra')   # the retry repeats the same arguments
    note = logs/'launcher.log'
    assert note.exists() == (expected_runs == 2)
    if expected_runs == 2:
        assert 'crashed at startup' in note.read_text() and 'crashed at startup' in result.stderr


# The default CLI uses v2 rather than the retired v1 fingerprint/stamp planner.
# Normal routing/refusal coverage lives in test_build_v2_controller_entry.py; content,
# order-only edges and parameter key semantics live in build-v2/tests/keys.rs.


def test_uat_gets_the_headless_user_directory_build_sh_would_export(tmp_path, monkeypatch):
    from atelier import setup
    ctx, steps = recipe_steps(tmp_path)
    uat = next(s for s in steps if s.name == 'unreal.cook').commands[1]
    monkeypatch.delenv('UE_HEADLESS_USER_DIR', raising=False)
    monkeypatch.setattr(setup, 'headless_user_dir', lambda root: None)
    assert uat.argv(ctx)[0].endswith('RunUAT.sh'), 'no headless repair installed: run UAT as it is'
    folder = tmp_path/'user-config'
    monkeypatch.setattr(setup, 'headless_user_dir', lambda root: folder)
    # Without it UAT's in-process XML config and the UnrealBuildTool it starts resolve ~/Documents and wait on TCC.
    assert uat.argv(ctx)[:2] == ['/usr/bin/env', f'UE_HEADLESS_USER_DIR={folder}']
    monkeypatch.setenv('UE_HEADLESS_USER_DIR', '/explicit')
    assert uat.argv(ctx)[0].endswith('RunUAT.sh'), 'an explicit choice from the caller wins'


def test_audio_signing_preserves_sandbox_and_existing_allowances(tmp_path, monkeypatch):
    import io
    tool = archive_tool()
    original = {'com.apple.security.app-sandbox': True, 'com.apple.security.network.client': True,
                tool.MACH_LOOKUP: ['existing.service']}
    current, calls = dict(original), []

    def run(args, **kwargs):
        nonlocal current
        calls.append(args)
        if '--entitlements' in args and '--xml' in args:
            return SimpleNamespace(stdout=plistlib.dumps(current), stderr=b'')
        if '--verbose=4' in args:
            return SimpleNamespace(stdout=b'', stderr=b'Signature=adhoc\n')
        if '--sign' in args:
            current = plistlib.loads(open(args[args.index('--entitlements') + 1], 'rb').read())
        return SimpleNamespace(stdout=b'', stderr=b'')

    monkeypatch.setattr(tool.subprocess, 'run', run)
    tool.audio_compatibility(tmp_path/'Yorimichi.app', io.StringIO())
    assert current == {**original, tool.MACH_LOOKUP: ['existing.service', tool.AUDIO_SERVICE]}
    assert '--verify' in calls[-1] and '--deep' in calls[-1] and '--strict' in calls[-1]
    first_signs = sum('--sign' in call for call in calls)
    tool.audio_compatibility(tmp_path/'Yorimichi.app', io.StringIO())
    assert sum('--sign' in call for call in calls) == first_signs


def test_audio_signing_refuses_to_replace_developer_id_signature(tmp_path, monkeypatch):
    import io
    tool = archive_tool()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=plistlib.dumps({'com.apple.security.app-sandbox': True}),
                               stderr=b'Authority=Developer ID Application\n')

    monkeypatch.setattr(tool.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='ad-hoc'):
        tool.audio_compatibility(tmp_path/'Yorimichi.app', io.StringIO())
    assert not any('--sign' in call for call in calls)


def test_audio_signing_accepts_verified_apps_without_sandbox_entitlements(tmp_path, monkeypatch):
    import io
    tool = archive_tool()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'', stderr=b'')

    monkeypatch.setattr(tool.subprocess, 'run', run)
    tool.audio_compatibility(tmp_path/'Yorimichi.app', io.StringIO())
    assert not any('--sign' in call for call in calls) and '--verify' in calls[-1]
