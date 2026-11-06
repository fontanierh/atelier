"""Targeted import: turn the selected generated assets' sources into their Unreal packages, and nothing else.

    uv run python games/yorimichi_v2/tools/import/run.py prop/harbour-bench-01 [more IDs] [--plan] [--claim TASK]

For each selected asset and its declared dependents (assets whose `input_dependencies` name it), the run:

1. plans the exact inputs, outputs and dependents first, and stops if a record is invalid;
2. skips an asset whose input fingerprint and verified package bytes already match, without starting Unreal;
3. checks that the caller may write those packages (an active claim, or the bootstrap writer, DECISIONS D04);
4. records the intended write set and the existing bytes in a local journal before anything is written;
5. runs the asset kind's importer once, through `atelier build yorimichi_v2 import.<id>` (guarded and admitted);
6. accepts the result only if every declared package exists and no file outside the write set changed, then writes
   the asset's source hashes and `verified.json`;
7. on any failure, or at the start of the next run after a crash, restores the journal's files exactly and writes no
   record. Someone else's files are never touched: the write set is only this asset's declared packages.

Unchanged runs write nothing. The journal lives in the ignored `unreal/Saved/ImportJournal`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
from records import RecordError  # noqa: E402

GAME = TOOLS.parent
REPO = GAME.parents[1]
JOURNAL = Path('unreal/Saved/ImportJournal')
IMPORTERS = {   # asset kind -> importer name and version understood by unreal/Scripts/import_asset.py
    'static-mesh': ('static-mesh', 1),
    'texture': ('texture', 1),
}
BOOTSTRAP_WRITER = authority.BOOTSTRAP_WRITER


class ImportError_(RuntimeError):
    pass


def engine_identity(unreal_root: Path) -> str:
    data = json.loads((unreal_root / 'Engine/Build/Build.version').read_text())
    return f'{data["MajorVersion"]}.{data["MinorVersion"]}.{data["PatchVersion"]}-{data["Changelist"]}'


def plan(game: Path, wanted: list[str]):
    """The selected generated assets plus every dependent, in dependency order, and the verified state they read."""
    assets, _ = records.discover(game)
    by_id = {a.id: a for a in assets}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise ImportError_(f'unknown asset ID(s): {", ".join(missing)}')
    selected, frontier = set(wanted), list(wanted)
    while frontier:
        current = frontier.pop()
        for asset in assets:
            if current in asset.input_dependencies and asset.id not in selected:
                selected.add(asset.id)
                frontier.append(asset.id)
    ordered, seen = [], set()

    def visit(asset_id, stack=()):
        if asset_id in seen:
            return
        if asset_id in stack:
            raise ImportError_(f'dependency cycle through {asset_id}')
        for dep in by_id[asset_id].input_dependencies:
            if dep in selected:
                visit(dep, stack + (asset_id,))
        seen.add(asset_id)
        ordered.append(by_id[asset_id])
    for asset_id in sorted(selected):
        visit(asset_id)
    for asset in ordered:
        if asset.authority == 'editor':
            raise ImportError_(f'{asset.id} is editor-owned: it is saved in the editor and save-validated, never imported')
    return ordered, by_id


def state_of(by_id, asset_id) -> str | None:
    path = by_id[asset_id].verified
    return records.state_fingerprint(records.load_verified(path)) if path.is_file() else None


def current_source_hashes(asset):
    return {s.path: records.sha256_file(asset.folder / s.path) for s in asset.sources}


def fingerprint_with_sources(asset, hashes, deps):
    # Record order, as the importer pairs sources with packages (records.input_fingerprint 'mapping').
    current = records.Asset(**{**asset.__dict__,
                               'sources': [records.Source(s.path, hashes[s.path]) for s in asset.sources]})
    return records.input_fingerprint(current, deps)


def generated_files(game: Path, asset) -> list[Path]:
    """Every file this asset's importer may write: its generated packages and their uncooked companions."""
    files = []
    for output in asset.outputs:
        if output.writer != 'generated':
            continue
        stem = records.package_files(game, output.package)[0].with_suffix('')
        files += [stem.with_suffix(ext) for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS]
    return files


def up_to_date(game, asset, fingerprint) -> bool:
    if not asset.verified.is_file():
        return False
    verified = records.load_verified(asset.verified)
    if verified.get('input_fingerprint') != fingerprint:
        return False
    return all((game / rel).is_file() and records.sha256_file(game / rel) == digest
               for rel, digest in verified['files'].items())


def authorize(game, asset, claim):
    """Protected writes need the claim's exact paths with verified locks, or the recorded bootstrap writer."""
    paths = [f'games/yorimichi_v2/{records.content_relative(game, f)}' for f in generated_files(game, asset)]
    try:
        authority.authorize(paths, claim, f'import of {asset.id}')
    except authority.Unauthorized as error:
        raise ImportError_(str(error)) from None


class Journal:
    """The intended write set and the bytes it had before, so a failed or crashed import restores exactly them."""

    def __init__(self, game, asset):
        self.game = game
        self.dir = game / JOURNAL / asset.id.replace('/', '__')
        self.manifest = self.dir / 'journal.json'
        self.asset = asset

    def begin(self, files: list[Path]):
        self.dir.mkdir(parents=True, exist_ok=True)
        entries = {}
        for path in files:
            rel = records.content_relative(self.game, path)
            if path.is_file():
                backup = self.dir / 'before' / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                entries[rel] = records.sha256_file(path)
            else:
                entries[rel] = None
        self.manifest.write_text(json.dumps({'asset': self.asset.id, 'files': entries}, indent=2))
        return entries

    def restore(self):
        """Put every journaled file back exactly as it was; remove the ones that did not exist."""
        if not self.manifest.is_file():
            return []
        entries = json.loads(self.manifest.read_text())['files']
        restored = []
        for rel, digest in entries.items():
            path = self.game / rel
            if digest is None:
                if path.exists():
                    path.unlink()
                    restored.append(rel)
                continue
            if not path.is_file() or records.sha256_file(path) != digest:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.dir / 'before' / rel, path)
                restored.append(rel)
        self.close()
        return restored

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


content_snapshot = authority.content_snapshot   # what an import wrote, checked against its packages


def native_import(game, asset, plan_file: Path):
    """Run the guarded editor import for one asset; the plan file tells the editor script what to write."""
    env = {**os.environ, 'V2_IMPORT_PLAN': str(plan_file)}
    command = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', f'import.{asset.id}']
    result = subprocess.run(command, cwd=REPO, env=env)
    if result.returncode:
        raise ImportError_(f'{asset.id}: the editor import failed (exit {result.returncode}); see build/yorimichi_v2/logs')


def import_one(game, asset, by_id, *, engine, claim, importer=native_import, echo=print):
    deps = {d: state_of(by_id, d) for d in asset.input_dependencies}
    stale = [d for d, s in deps.items() if s is None]
    if stale:
        raise ImportError_(f'{asset.id}: input dependencies {stale} have no verified state; import them first')
    hashes = current_source_hashes(asset)
    fingerprint = fingerprint_with_sources(asset, hashes, deps)
    if up_to_date(game, asset, fingerprint):
        echo(f'unchanged  {asset.id}')
        return False
    authorize(game, asset, claim)
    kind = IMPORTERS.get(asset.kind)
    if kind is None or asset.recipe.get('importer') != kind[0] or asset.recipe.get('version') != kind[1]:
        raise ImportError_(f'{asset.id}: no importer {asset.recipe.get("importer")}@{asset.recipe.get("version")} '
                           f'for kind {asset.kind}')
    journal = Journal(game, asset)
    journal.restore()                                    # a previous crash left this asset's files half-written
    write_set = generated_files(game, asset)
    journal.begin(write_set)
    allowed = {records.content_relative(game, f) for f in write_set}
    before = content_snapshot(game)
    plan_file = journal.dir / 'plan.json'
    plan_file.write_text(json.dumps({
        'asset': asset.id, 'kind': asset.kind, 'importer': kind[0], 'version': kind[1],
        'settings': asset.recipe.get('settings', {}),
        'sources': [str((asset.folder / s.path).resolve()) for s in asset.sources],
        'portable_sources': ['games/yorimichi_v2/' + records.content_relative(game, asset.folder / s.path)
                             for s in asset.sources],
        'packages': [o.package for o in asset.outputs if o.writer == 'generated'],
        'references': {dep: [o.package for o in by_id[dep].outputs] for dep in asset.references + asset.input_dependencies},
        'claim': claim,
        'write_paths': sorted(f'games/yorimichi_v2/{rel}' for rel in allowed),
    }, indent=2))
    try:
        importer(game, asset, plan_file)
        after = content_snapshot(game)
        changed = {rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel)}
        outside = sorted(rel for rel in changed - allowed if not rel.startswith('unreal/Saved/'))
        if outside:
            raise ImportError_(f'{asset.id}: the import wrote outside its declared packages: {", ".join(outside[:8])}')
        files = {}
        for output in asset.outputs:
            if output.writer != 'generated':
                continue
            present = [p for p in records.package_files(game, output.package) if p.is_file()]
            if not present:
                raise ImportError_(f'{asset.id}: {output.package} was not written')
        for path in write_set:
            if path.is_file():
                files[records.content_relative(game, path)] = records.sha256_file(path)
        if asset.authority == 'split' and asset.verified.is_file():
            # The editor-owned part keeps its own saved hashes.
            for rel, digest in records.load_verified(asset.verified)['files'].items():
                files.setdefault(rel, digest)
    except BaseException:
        restored = journal.restore()
        echo(f'failed     {asset.id}: restored {len(restored)} file(s); no record written')
        raise
    update_source_hashes(asset, hashes)
    records.write_json(asset.verified, {
        'schema': records.SCHEMA, 'kind': 'imported', 'asset': asset.id, 'engine': engine,
        'tool': f'{kind[0]}@{kind[1]}', 'input_fingerprint': fingerprint, 'files': files,
        'dependencies': {d: s for d, s in sorted(deps.items())}})
    journal.close()
    echo(f'imported   {asset.id}: {len(files)} file(s)')
    return True


def update_source_hashes(asset, hashes):
    """Record the imported sources' hashes in asset.toml, editing only those values."""
    text = asset.record.read_text()
    for source in asset.sources:
        new = hashes[source.path]
        if new == source.sha256:
            continue
        pattern = re.compile(r'(path\s*=\s*"' + re.escape(source.path) + r'"\s*\n\s*sha256\s*=\s*")' + source.sha256)
        text, count = pattern.subn(r'\g<1>' + new, text)
        if count != 1:
            raise ImportError_(f'{asset.id}: cannot update the hash of {source.path} in asset.toml; keep path and '
                               f'sha256 on consecutive lines')
    asset.record.write_text(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('assets', nargs='+', help='asset IDs to import, e.g. prop/harbour-bench-01')
    parser.add_argument('--plan', action='store_true', help='print what would be imported and exit')
    parser.add_argument('--claim', help='the active claim (task ID) authorizing these writes')
    args = parser.parse_args(argv)
    try:
        ordered, by_id = plan(GAME, args.assets)
        if args.plan:
            for asset in ordered:
                print(f'{asset.id:40} -> {", ".join(o.package for o in asset.outputs if o.writer == "generated")}')
            return 0
        from atelier import engine as engine_paths
        engine = engine_identity(Path(engine_paths.unreal_root()))
        for asset in ordered:
            by_id = {a.id: a for a in records.discover(GAME)[0]}      # fresh: dependencies were just imported
            import_one(GAME, by_id[asset.id], by_id, engine=engine, claim=args.claim)
    except (ImportError_, RecordError) as error:
        print(f'import failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
