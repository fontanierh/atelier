"""The packaged macOS game: one guarded compile-kind turn, then a zip a GitHub release can carry."""
import json
import os
import subprocess
from types import SimpleNamespace

from atelier import build


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
    uat = package.commands[0]
    argv = uat.argv(ctx)
    assert argv[0].endswith('RunUAT.sh') and argv[1] == 'BuildCookRun'
    # UAT runs UnrealBuildTool itself, past the capped Build.sh wrapper, so the worker cap is passed explicitly.
    assert '-build' in argv and '-ubtargs=-MaxParallelActions=3' in argv and '-cookall' in argv
    assert f'-archivedirectory={tmp_path/"package"/"archive"}' in argv and '-nocompileeditor' in argv
    assert uat.timeout > 0 and 'UnrealEditor-Cmd' in uat.watch and 0 < uat.progress <= 30


def test_package_zip_checksums_and_splits_for_release_assets(tmp_path, monkeypatch):
    ctx, steps = recipe_steps(tmp_path)
    recipe = build.load_recipe('yorimichi')
    app = tmp_path/'package'/'archive'/'Mac'/'Yorimichi.app'/'Contents'/'MacOS'
    app.mkdir(parents=True)
    binary = os.urandom(100_000)   # incompressible, so the zip really exceeds a tiny part size
    (app/'Yorimichi').write_bytes(binary)
    (app.parent/'Info.plist').write_text('<plist/>')
    (app.parent/'Current').symlink_to('MacOS')
    log = open(tmp_path/'log.txt', 'w')
    recipe.package_zip(ctx, log)
    manifest = json.loads((tmp_path/'package'/'manifest.json').read_text())
    assert manifest['app'] == 'Yorimichi.app' and not manifest['split'] and len(manifest['files']) == 1
    assert recipe.package_present(tmp_path)
    sums = (tmp_path/'package'/'SHA256SUMS').read_text()
    assert manifest['files'][0]['sha256'] in sums and manifest['zip'] in sums

    # Larger than one release asset: numbered parts that rejoin into the same zip.
    monkeypatch.setattr(recipe, 'PART_BYTES', 20_000)
    recipe.package_zip(ctx, log)
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
    recipe = build.load_recipe('yorimichi')
    folder = tmp_path/'Yorimichi'
    game = folder/'Yorimichi.app'/'Contents'/'MacOS'/'Yorimichi'
    game.parent.mkdir(parents=True)
    game.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$HOME/args.txt"\n'); game.chmod(0o755)
    launcher = folder/'Play Yorimichi.command'
    launcher.write_text(recipe.desktop_preview().packaged_launcher()); launcher.chmod(0o755)
    home = tmp_path/'home'; home.mkdir()

    def launch():
        subprocess.run([str(launcher)], env={'HOME': str(home), 'PATH': '/usr/bin:/bin'}, check=True)
        return (home/'args.txt').read_text().splitlines()
    args = launch()
    settings = home/'Library'/'Application Support'/'Yorimichi'/'settings.txt'
    assert '-desktopnative1440' in args and f'-preferencesfile={settings}' in args
    assert '-set=desktop=1;performance=1;render_scale=100;renderer=0' in args
    assert any('r.ForwardShading=True' in a and 'DesktopPreviewViewportClient' in a for a in args)
    assert any(a.startswith('-ExecCmds=') and 'japan.CitySurfaceTiles v1_128m 1' in a for a in args)
    # Saved choices win: no default overrides them, and a saved Lumen renderer starts Lumen.
    settings.write_text('performance=0\nrender_scale=80\nrenderer=1\n')
    args = launch()
    assert '-set=desktop=1;renderer=1' in args and any('r.ForwardShading=False' in a for a in args)


def test_content_changes_rerun_the_package_while_current_prerequisites_stay_current(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs', stamps=tmp_path/'stamps',
                          uproject=tmp_path/'Yorimichi.uproject', unreal_root=tmp_path/'UE')
    content = tmp_path/'import_world.py'; content.write_text('v1')
    world = build.Step('unreal.world', [], inputs=[content], heavy=True)
    data = build.Step('data.stage', [])
    package = recipe.package_step(ctx, [world, data])
    package = build.Step(package.name, [], needs=package.needs, explicit=True, outputs=package.outputs, verify=package.verify)
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

    # A missing part makes the package stale even with a current stamp.
    stamp_all()
    (tmp_path/'package'/'Yorimichi-macOS-x.zip').unlink()
    assert plan()['unreal.package'] == 'would run'
