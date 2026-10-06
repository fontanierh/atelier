"""The packaged macOS game: one guarded compile-kind turn, then a zip a GitHub release can carry."""
import importlib.util
import json
import plistlib

import pytest
import os
import subprocess
from types import SimpleNamespace

from atelier import build


def archive_tool():
    path = build.load_recipe('yorimichi').TOOLS / 'package_archive.py'
    spec = importlib.util.spec_from_file_location('yorimichi_package_archive', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def recipe_steps(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps',
                          uproject=tmp_path/'Yorimichi.uproject', unreal_root=tmp_path/'UE')
    return ctx, build.load_recipe('yorimichi').steps(ctx)


def test_package_runs_after_every_import_as_one_capped_compile_turn(tmp_path):
    ctx, steps = recipe_steps(tmp_path)
    package = next(s for s in steps if s.name == 'unreal.package')
    imports = {s.name for s in steps if s.name.startswith('unreal.') and s.name != 'unreal.package'}
    assert imports <= set(package.needs) and 'data.stage' in package.needs and package.heavy and package.explicit
    # Never part of a plain or prefix build: only when named.
    assert 'unreal.package' not in {s.name for s in build.order(steps, [])}
    assert 'unreal.package' not in {s.name for s in build.order(steps, ['unreal'])}
    assert 'unreal.package' in {s.name for s in build.order(steps, ['unreal.package'])}
    # Compile kind: the big slot and the small one, like any compile.
    assert build.slot_request(ctx, package) == ('compile', None)
    uat, archive = package.commands
    # The archive phase is its own guarded job (a released boundary after UAT) whose ditto/split children are watched.
    assert archive.script.name == 'package_archive.py' and {'ditto', 'split'} <= set(archive.watch)
    assert archive.marker == 'PACKAGE ARCHIVE COMPLETE' and 0 < archive.progress <= 30 and archive.timeout > 0
    argv = uat.argv(ctx)
    assert argv[0].endswith('RunUAT.sh') and argv[1] == 'BuildCookRun'
    # UAT runs UnrealBuildTool itself, past the capped Build.sh wrapper, so the worker cap is passed explicitly.
    assert '-build' in argv and '-ubtargs=-MaxParallelActions=3' in argv and '-cookall' in argv
    # Without -package the Mac archive copies Binaries/Mac/<game>.app: no paks, no Content/Data.
    assert argv.index('-stage') < argv.index('-package') < argv.index('-archive')
    assert f'-archivedirectory={tmp_path/"package"/"archive"}' in argv and '-nocompileeditor' in argv
    assert uat.timeout > 0 and 'UnrealEditor-Cmd' in uat.watch and 0 < uat.progress <= 30


def test_package_zip_checksums_and_splits_for_release_assets(tmp_path, monkeypatch):
    ctx, steps = recipe_steps(tmp_path)
    recipe, tool = build.load_recipe('yorimichi'), archive_tool()
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
    tool.package_zip(tmp_path/'package', log)
    manifest = json.loads((tmp_path/'package'/'manifest.json').read_text())
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
    assert '-set=desktop=1;performance=1;render_scale=100;renderer=0' in args
    assert any('r.ForwardShading=True' in a and 'DesktopPreviewViewportClient' in a for a in args)
    assert any(a.startswith('-ExecCmds=') and 'japan.CitySurfaceTiles v1_128m 1' in a for a in args)
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


def test_content_changes_rerun_the_package_while_current_prerequisites_stay_current(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps',
                          uproject=tmp_path/'Yorimichi.uproject', unreal_root=tmp_path/'UE')
    content = tmp_path/'import_world.py'; content.write_text('v1')
    world = build.Step('unreal.world', [], inputs=[content], heavy=True)
    data = build.Step('data.stage', [])
    package = recipe.package_step(ctx, [world, data])
    assert {recipe.TOOLS/'package_archive.py', recipe.TOOLS/'desktop_preview.py'} <= set(package.inputs)
    source = tmp_path/'desktop_preview.py'; source.write_text('profile v1')
    package = build.Step(package.name, [], inputs=[source], needs=package.needs, explicit=True, outputs=package.outputs,
                         verify=package.verify)
    steps = [world, data, package]
    ctx.stamps.mkdir()

    def stamp_all():
        done = {}
        for step in steps:
            done[step.name] = build.fingerprint(step, done)
            (ctx.stamps/f'{step.name}.json').write_text(json.dumps({'fingerprint': done[step.name]}))
    (tmp_path/'package').mkdir()
    (tmp_path/'package'/'Yorimichi-macOS-x.zip').write_bytes(b'zip')
    (tmp_path/'package'/'SHA256SUMS').write_text('')
    (tmp_path/'package'/'manifest.json').write_text(json.dumps({'files': [{'file': 'Yorimichi-macOS-x.zip', 'bytes': 3}]}))
    stamp_all()
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: steps))

    def plan():
        lines = []
        assert build.build('yorimichi', ['unreal.package'], dry=True, echo=lines.append) == 0
        return {line.split()[0]: ' '.join(line.split()[1:]) for line in lines if line.split()[0] in {s.name for s in steps}}
    assert plan() == {'unreal.world': 'up to date', 'data.stage': 'up to date', 'unreal.package': 'up to date'}

    # The world is reimported elsewhere (its stamp is current again): only the package reruns.
    content.write_text('v2')
    done = {}
    for step in steps[:2]:
        done[step.name] = build.fingerprint(step, done)
        (ctx.stamps/f'{step.name}.json').write_text(json.dumps({'fingerprint': done[step.name]}))
    assert plan() == {'unreal.world': 'up to date', 'data.stage': 'up to date', 'unreal.package': 'would run'}

    # A launcher or profile edit reruns only the package.
    stamp_all()
    source.write_text('profile v2')
    assert plan() == {'unreal.world': 'up to date', 'data.stage': 'up to date', 'unreal.package': 'would run'}

    # A missing part makes the package stale even with a current stamp.
    stamp_all()
    (tmp_path/'package'/'Yorimichi-macOS-x.zip').unlink()
    assert plan()['unreal.package'] == 'would run'


def test_uat_gets_the_headless_user_directory_build_sh_would_export(tmp_path, monkeypatch):
    from atelier import setup
    ctx, steps = recipe_steps(tmp_path)
    uat = next(s for s in steps if s.name == 'unreal.package').commands[0]
    monkeypatch.delenv('UE_HEADLESS_USER_DIR', raising=False)
    monkeypatch.setattr(setup, 'headless_user_dir', lambda root: None)
    assert uat.argv(ctx)[0].endswith('RunUAT.sh'), 'no headless repair installed: run UAT as it is'
    folder = tmp_path/'user-config'
    monkeypatch.setattr(setup, 'headless_user_dir', lambda root: folder)
    # Without it UAT's in-process XML config and the UnrealBuildTool it starts resolve ~/Documents and wait on TCC.
    assert uat.argv(ctx)[:2] == ['/usr/bin/env', f'UE_HEADLESS_USER_DIR={folder}']
    monkeypatch.setenv('UE_HEADLESS_USER_DIR', '/explicit')
    assert uat.argv(ctx)[0].endswith('RunUAT.sh'), 'an explicit choice from the caller wins'
