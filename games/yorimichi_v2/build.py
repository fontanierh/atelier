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
             # No edge to check.content: a named import or editor script compiles without the content gate, so
             # the route that repairs missing or stale content is never blocked by the check that reports it.
             inputs=[UNREAL / 'Source', UNREAL / 'Plugins', ctx.uproject, UNREAL / 'Config', paths.ENGINE_PLUGINS],
             heavy=True,
             about='the V2 editor target: Yorimichi, YorimichiAssets, YorimichiImport and enabled plugins'),
        Step('unreal.package', [Call('check_package_inputs', _check_package_inputs),
                                UnrealPackage('YorimichiV2', out / 'package' / 'archive')],
             inputs=[GAME / 'build.py', ctx.uproject, UNREAL / 'Config', UNREAL / 'Source', UNREAL / 'Plugins',
                     UNREAL / 'Content', ctx.unreal_root / 'Engine/Build/Build.version'],
             needs=['unreal.compile'], heavy=True, explicit=True, outputs=[out / 'package' / 'archive'],
             about='explicit: cook and package the committed content for macOS (integration milestones, releases)'),
        # Explicit: the one-time static-world migration, run only by tools/migrate/run.py with its plan.
        Step('migrate.map', [Call('authorize migration', _authorize_migration),
                             UnrealScript(UNREAL / 'Scripts/migrate_map.py', 'V2 MIGRATE DONE'), ran('migrate.map')],
             inputs=[UNREAL / 'Scripts/migrate_map.py'], after=['unreal.compile'], heavy=True, explicit=True,
             verify=lambda: 'migrate.map' in RAN,
             about='one-time migration of regions into a World Partition map (use tools/migrate/run.py)'),
        # Explicit: one named bootstrap-writer editor script (unreal/Scripts), guarded like every editor write.
        Step('editor.run', [Call('authorize editor script', _authorize_editor),
                            UnrealScript(UNREAL / 'Scripts/run_named.py', 'V2 EDITOR SCRIPT DONE'),
                            Call('check editor writes', _check_editor_writes), ran('editor.run')],
             inputs=[UNREAL / 'Scripts'], after=['unreal.compile'], heavy=True, explicit=True,
             verify=lambda: 'editor.run' in RAN,
             about='one named editor script (V2_EDITOR_SCRIPT, V2_EDITOR_CLAIM + V2_EDITOR_PATHS for a claimed write)'),
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
        found.append(Step(name, [Call(f'authorize {name}', _authorize_import), UnrealScript(script, 'V2 IMPORT DONE'),
                                 ran(name)],
                          inputs=[script], after=['unreal.compile'], heavy=True, explicit=True,
                          verify=lambda name=name: name in RAN,
                          about=f'editor import of {asset.id} (use tools/import/run.py)'))
    return found


def _authority():
    import sys
    sys.path.insert(0, str(GAME / 'tools/content'))
    import authority
    return authority


# What unreal/Content held before the running editor script, to verify its writes afterwards.
EDITOR_BEFORE = {}


def _editor_paths():
    """V2_EDITOR_PATHS with each package's complete file set: saving a .uasset or .umap may also write its
    companions (.uexp, .ubulk, ...), so they are claimed, locked and admitted by the save guard together."""
    import os
    import records
    paths = set()
    for path in os.environ.get('V2_EDITOR_PATHS', '').split():
        paths.add(path)
        stem, ext = os.path.splitext(path)
        if ext in records.PACKAGE_EXTENSIONS:
            paths |= {stem + other for other in records.COMPANION_EXTENSIONS}
    return sorted(paths)


def _authorize_editor(ctx, log):
    """An editor script may save packages, so it runs under a claim covering its declared paths or as the D04
    bootstrap writer (CONTRACTS yorimichi-v2-single-writer); afterwards its actual writes are checked."""
    import os
    authority = _authority()
    claim = os.environ.get('V2_EDITOR_CLAIM') or None
    script = Path(os.environ.get('V2_EDITOR_SCRIPT', '')).name
    if script == 'import_asset.py':
        raise RuntimeError('import_asset.py runs only through its import.<id> step (tools/import/run.py)')
    declared = _editor_paths()
    generated = sorted(set(declared) & authority.generated_paths(GAME))
    if generated:
        raise RuntimeError(f'generated packages are written only by their importer: {", ".join(generated[:5])}')
    if claim and not declared:
        raise RuntimeError('V2_EDITOR_CLAIM needs V2_EDITOR_PATHS: the repository paths the script may write')
    # Existing packages bring their owners' scopes; new ones are owned by the scopes the run declares.
    scopes, unowned = authority.owning_scopes(GAME, declared) if claim else (set(), [])
    named = set(os.environ.get('V2_EDITOR_SCOPES', '').split())
    if claim and unowned and not named:
        raise RuntimeError('new packages need V2_EDITOR_SCOPES: the claim scopes that will own them')
    authority.authorize(declared, claim, f"editor script {os.environ.get('V2_EDITOR_SCRIPT', '?')}",
                        scopes=scopes | named)
    if claim:   # the save boundary: the editor refuses any other package save
        authority.allow_saves(declared, ctx.out / 'editor-run' / 'save-allow.txt')
    else:
        os.environ.pop('V2_SAVE_ALLOW', None)
    # Every editor script, the bootstrap writer's included: generated packages are refused at the save itself.
    authority.deny_saves(authority.generated_paths(GAME), ctx.out / 'editor-run' / 'save-deny.txt')
    EDITOR_BEFORE.clear()
    EDITOR_BEFORE.update(authority.content_snapshot(GAME))
    log.write(f"editor script authorized ({'claim ' + claim if claim else 'bootstrap writer'})\n")


def _check_editor_writes(ctx, log):
    """A claimed script must have written only its declared paths; every write is listed for save validation."""
    import os
    authority = _authority()
    os.environ.pop('V2_SAVE_ALLOW', None)
    os.environ.pop('V2_SAVE_DENY', None)
    changed = sorted('games/yorimichi_v2/' + rel for rel in authority.written(EDITOR_BEFORE, authority.content_snapshot(GAME)))
    log.write(''.join(f'editor script wrote {path}\n' for path in changed) or 'editor script wrote nothing\n')
    generated = sorted(set(changed) & authority.generated_paths(GAME))
    if generated:   # the bootstrap writer included: a generated package belongs to its importer
        raise RuntimeError(f'the editor script wrote generated packages: {", ".join(generated[:8])}; '
                           'reimport them with tools/import/run.py')
    if os.environ.get('V2_EDITOR_CLAIM'):
        outside = [path for path in changed if path not in set(_editor_paths())]
        if outside:
            raise RuntimeError(f'the editor script wrote outside its claimed paths: {", ".join(outside[:8])}')
    if changed:
        log.write('record these packages with tools/content/save_validate.py before committing\n')


def _authorize_migration(ctx, log):
    """The one-time migration is a D04 bootstrap write (tools/migrate/run.py); selecting the step directly is too."""
    _authority().authorize([], None, 'map migration')


def _authorize_import(ctx, log):
    """Re-check the import plan at the write boundary, so selecting import.<id> directly is not a bypass: the plan
    must be exactly its asset record's recorded import, and no other record may own a destination."""
    import json
    import os
    authority = _authority()
    import records
    plan_file = Path(os.environ['V2_IMPORT_PLAN'])
    plan = json.loads(plan_file.read_text())
    by_id = {a.id: a for a in records.discover(GAME)[0]}
    asset = by_id.get(plan['asset'])
    if asset is None or asset.authority not in ('generated', 'split'):
        raise RuntimeError(f"import plan names {plan['asset']!r}, which has no generated outputs")
    expected = [o.package for o in asset.outputs if o.writer == 'generated']
    if (plan['packages'] != expected or plan.get('importer') != asset.recipe.get('importer')
            or plan.get('version') != asset.recipe.get('version')):
        raise RuntimeError(f"import plan for {asset.id} does not match its record (packages {expected}, "
                           f"importer {asset.recipe.get('importer')!r})")
    destinations = set()
    for package in expected:
        stem = records.package_files(GAME, package)[0].with_suffix('')
        destinations |= {'games/yorimichi_v2/' + records.content_relative(GAME, stem.with_suffix(ext))
                         for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS}
    owners, _ = authority.owning_scopes(GAME, sorted(destinations))
    if owners - {authority.asset_scope(asset)}:
        raise RuntimeError(f'{asset.id}: a destination is owned by {sorted(map(str, owners - {authority.asset_scope(asset)}))}')
    paths = sorted(destinations | set(plan.get('write_paths', ())))
    authority.authorize(paths, plan.get('claim'), f'import of {asset.id}', scopes={authority.asset_scope(asset)})
    authority.allow_saves(sorted(destinations), plan_file.with_name('save-allow.txt'))


def _check_package_inputs(ctx, log):
    """A package is made only from complete, current committed content: the full-hash check must pass first, with
    every pinned restricted file fetched (the check fails on an absent one)."""
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(GAME / 'tools/content/check.py'), '--full'], capture_output=True,
                            text=True)
    log.write(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('content check failed; fix the reported content before packaging')
