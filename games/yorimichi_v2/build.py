"""Yorimichi V2's build: validate committed content, compile, and (only when named) package.

The normal build never prepares, imports, resaves or cooks content (CONTRACTS yorimichi-v2-targeted-authoring).
Content arrives through Git LFS; `check.content` reports anything missing or stale and the owner route that fixes
it. Runtime data is committed text under unreal/Content/Data, so nothing is staged into the tree either.
"""
from pathlib import Path

from atelier.build import Call, Python, Step, UnrealCompile, UnrealPackage, UnrealScript

GAME = Path(__file__).resolve().parent
UNREAL = GAME / 'unreal'
# Steps that must run every time they are reached (the content check, a named import) report "not done" until
# they have run in this build process; each build loads this recipe afresh.
RAN = set()


def ran(name):
    return Call(f'ran {name}', lambda ctx, log: RAN.add(name))


def steps(ctx):
    from atelier import paths
    out = ctx.out
    return [
        # Read-only and quick: it always runs, so a build never trusts a stale stamp for committed bytes.
        Step('check.content', [Python(GAME / 'tools/content/check.py', ()), ran('check.content')],
             verify=lambda: 'check.content' in RAN,
             inputs=[GAME / 'tools/content'],
             about='every committed package present, hydrated, owned and current; fixes nothing'),
        Step('unreal.compile', [UnrealCompile('YorimichiV2Editor')],
             inputs=[UNREAL / 'Source', UNREAL / 'Plugins', ctx.uproject, UNREAL / 'Config', paths.ENGINE_PLUGINS],
             after=['check.content'], heavy=True,
             about='the V2 editor target: Yorimichi, YorimichiAssets, YorimichiImport and enabled plugins'),
        Step('unreal.package', [Call('check_package_inputs', _check_package_inputs),
                                UnrealPackage('YorimichiV2', out / 'package' / 'archive')],
             inputs=[GAME / 'build.py', ctx.uproject, UNREAL / 'Config', UNREAL / 'Source', UNREAL / 'Plugins',
                     UNREAL / 'Content', ctx.unreal_root / 'Engine/Build/Build.version'],
             needs=['unreal.compile'], heavy=True, explicit=True, outputs=[out / 'package' / 'archive'],
             about='explicit: cook and package the committed content for macOS (integration milestones, releases)'),
    ] + import_steps()


def import_steps():
    """One explicit editor import per generated asset, run only by tools/import/run.py with its plan.

    The runner decides whether to import (fingerprints), journals and verifies; this step only supplies the guarded,
    admitted editor process, so it always runs when named and never runs in a plain build.
    """
    import sys
    sys.path.insert(0, str(GAME / 'tools/content'))
    import records
    script = UNREAL / 'Scripts/import_asset.py'
    found = []
    for record in sorted((GAME / 'assets').glob('**/asset.toml')):
        try:
            asset = records.load_asset(record)
        except records.RecordError:
            continue        # check.content reports it
        if asset.authority == 'editor':
            continue
        name = f'import.{asset.id}'
        found.append(Step(name, [UnrealScript(script, 'V2 IMPORT DONE'), ran(name)],
                          inputs=[script], after=['unreal.compile'], heavy=True, explicit=True,
                          verify=lambda name=name: name in RAN,
                          about=f'editor import of {asset.id} (use tools/import/run.py)'))
    return found


def _check_package_inputs(ctx, log):
    """A package is made only from complete, current committed content: the full-hash check must pass first."""
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(GAME / 'tools/content/check.py'), '--full'], capture_output=True,
                            text=True)
    log.write(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('content check failed; fix the reported content before packaging')
