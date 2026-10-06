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
    assert imports <= set(package.after) and 'data.stage' in package.after and package.heavy
    # Compile kind: the big slot and the small one, like any compile.
    assert build.slot_request(ctx, package) == ('compile', None)
    uat = package.commands[0]
    argv = uat.argv(ctx)
    assert argv[0].endswith('RunUAT.sh') and argv[1] == 'BuildCookRun'
    # UAT runs UnrealBuildTool itself, past the capped Build.sh wrapper, so the worker cap is passed explicitly.
    assert '-build' in argv and '-ubtargs=-MaxParallelActions=3' in argv and '-cookall' in argv
    assert f'-archivedirectory={tmp_path/"package"/"archive"}' in argv and '-nocompileeditor' in argv
    assert uat.timeout > 0 and 'UnrealEditor-Cmd' in uat.watch and uat.progress > 0


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
    assert (out/'Yorimichi.app'/'Contents'/'MacOS'/'Yorimichi').read_bytes() == binary
    assert (out/'Yorimichi.app'/'Contents'/'Current').is_symlink()
