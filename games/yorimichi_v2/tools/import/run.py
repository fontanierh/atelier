"""Targeted import: turn the selected generated assets' sources into their Unreal packages, and nothing else.

    uv run python games/yorimichi_v2/tools/import/run.py prop/harbour-bench-01 [more IDs] [--plan] [--claim TASK]
    uv run python games/yorimichi_v2/tools/import/run.py IDS... --claim TASK --batch N   (one editor per N assets)

For each selected asset and its declared dependents (assets whose `input_dependencies` name it), the run:

1. plans the exact inputs, outputs and dependents first, and stops if a record is invalid;
2. skips an asset whose input fingerprint and verified package bytes already match, without starting Unreal;
3. checks that the caller may write those packages (an active claim, or the bootstrap writer, DECISIONS D04);
4. records the intended write set and the existing bytes in a local journal before anything is written;
5. runs the asset kind's importer once, through `atelier build yorimichi_v2 import.<id, "/" as ".">` (guarded, admitted);
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
sys.path.insert(0, str(TOOLS.parent / 'unreal' / 'Scripts'))
import authority  # noqa: E402
import carve  # noqa: E402
import lod_preservation  # noqa: E402
import records  # noqa: E402
from records import RecordError  # noqa: E402

GAME = TOOLS.parent
REPO = GAME.parents[1]
JOURNAL = Path('unreal/Saved/ImportJournal')
BUILD = REPO / 'build' / 'yorimichi_v2'   # where a carved record's derived remainder is written (carve.materialize)
IMPORTERS = {   # asset kind -> importer name and version understood by unreal/Scripts/import_asset.py
    'static-mesh': ('static-mesh', 1),
    'texture': ('texture', 1),
}
BOOTSTRAP_WRITER = authority.BOOTSTRAP_WRITER
LOD_RESULT = 'lod-result.json'   # written beside the plan by unreal/Scripts/import_asset.py


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
    # Only generated files decide: a split asset's editor-owned outputs change through save validation, never
    # through a reimport of unchanged sources.
    generated = {records.content_relative(game, f) for f in generated_files(game, asset)}
    return all((game / rel).is_file() and records.sha256_file(game / rel) == digest
               for rel, digest in verified['files'].items() if rel in generated)


def authorize(game, asset, claim):
    """Protected writes need the claim's exact paths with verified locks, or the recorded bootstrap writer."""
    authorize_all(game, [asset], claim, f'import of {asset.id}')


def authorize_all(game, assets, claim, what):
    """authorize for many assets in one protected check: each check reads the claim's locks from the remote."""
    paths = [f'games/yorimichi_v2/{records.content_relative(game, f)}' for a in assets for f in generated_files(game, a)]
    try:
        authority.authorize(paths, claim, what, scopes={authority.asset_scope(a) for a in assets})
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

    def pending(self) -> set[str]:
        """The game-relative files an interrupted import's journal would restore."""
        return set(json.loads(self.manifest.read_text())['files']) if self.manifest.is_file() else set()

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
    command = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', records.import_step(asset.id)]
    result = subprocess.run(command, cwd=REPO, env=env)
    if result.returncode:
        raise ImportError_(f'{asset.id}: the editor import failed (exit {result.returncode}); see build/yorimichi_v2/logs')


def write_plan(game, asset, by_id, kind, claim, write_set, plan_file: Path):
    """The import plan the editor step re-checks at its write boundary (build.py _authorize_import)."""
    allowed = {records.content_relative(game, f) for f in write_set}
    deps = {d: state_of(by_id, d) for d in asset.input_dependencies}
    sources = carve.plan_sources(asset, BUILD)      # a carved record's one source is its derived remainder
    plan_file.write_text(json.dumps({
        'asset': asset.id, 'kind': asset.kind, 'importer': kind[0], 'version': kind[1],
        'settings': asset.recipe.get('settings', {}),
        'sources': [str(p.resolve()) for p in sources],
        'portable_sources': [_portable(game, p) for p in sources],
        'packages': [o.package for o in asset.outputs if o.writer == 'generated'],
        'references': {dep: [o.package for o in by_id[dep].outputs] for dep in asset.references + asset.input_dependencies},
        'claim': claim,
        'write_paths': sorted(f'games/yorimichi_v2/{rel}' for rel in allowed),
    }, indent=2))


def _portable(game: Path, path: Path) -> str:
    """A source's repository-relative name: under the game, or under the build folder for a derived remainder."""
    path = path.resolve()
    if path.is_relative_to(game.resolve()):
        return 'games/yorimichi_v2/' + records.content_relative(game, path)
    return 'build/yorimichi_v2/' + path.relative_to(BUILD.resolve()).as_posix()


def read_lod_result(plan_file: Path, asset) -> dict | None:
    """The LOD chain each generated static-mesh package had before its import and has after, checked again here: a chain
    that had several LODs must have the same count and screen sizes (within tolerance). None for other kinds."""
    if asset.kind != 'static-mesh':
        return None
    path = plan_file.with_name(LOD_RESULT)
    if not path.is_file():
        raise ImportError_(f'{asset.id}: the editor wrote no LOD record')
    result = json.loads(path.read_text())
    lods = {}
    for output in asset.outputs:
        if output.writer != 'generated':
            continue
        entry = result.get(output.package)
        if entry is None:
            raise ImportError_(f'{asset.id}: the editor recorded no LOD chain for {output.package}')
        try:
            lod_preservation.verify_record(entry)
        except lod_preservation.LodError as error:
            raise ImportError_(f'{asset.id}: {output.package}: {error}') from None
        lods[output.package] = entry
    return lods


def recorded_files(game, asset, write_set) -> dict:
    """The verified file hashes of an import that wrote its packages: every generated package must exist."""
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
        # The editor-owned part keeps its own saved hashes; a generated file the import no longer wrote
        # (such as a dropped .ubulk) is gone from the record, never carried over.
        editor_files = {records.content_relative(game, p.with_suffix(ext))
                        for o in asset.outputs if o.writer == 'editor'
                        for p in records.package_files(game, o.package)[:1]
                        for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS}
        for rel, digest in records.load_verified(asset.verified)['files'].items():
            if rel in editor_files:
                files.setdefault(rel, digest)
    return files


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
    write_set = generated_files(game, asset)
    # Recovery writes too: it may restore only files this authorized import may write. A journal left from an
    # older record (other outputs) is outside that and is resolved by hand, never restored under this claim.
    outside = sorted(journal.pending() - {records.content_relative(game, f) for f in write_set})
    if outside:
        raise ImportError_(f'{asset.id}: an interrupted import journal would restore files outside its current '
                           f'outputs ({", ".join(outside[:5])}); resolve {journal.dir} by hand')
    recovered = journal.restore()                        # a previous crash left this asset's files half-written
    if recovered:
        echo(f'recovered  {asset.id}: restored {len(recovered)} file(s) an interrupted import left')
    journal.begin(write_set)
    allowed = {records.content_relative(game, f) for f in write_set}
    before = content_snapshot(game)
    plan_file = journal.dir / 'plan.json'
    write_plan(game, asset, by_id, kind, claim, write_set, plan_file)
    try:
        importer(game, asset, plan_file)
        lods = read_lod_result(plan_file, asset)
        after = content_snapshot(game)
        changed = {rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel)}
        outside = sorted(rel for rel in changed - allowed if not rel.startswith('unreal/Saved/'))
        if outside:
            raise ImportError_(f'{asset.id}: the import wrote outside its declared packages: {", ".join(outside[:8])}')
        files = recorded_files(game, asset, write_set)
    except BaseException:
        restored = journal.restore()
        echo(f'failed     {asset.id}: restored {len(restored)} file(s); no record written')
        raise
    update_source_hashes(asset, hashes)
    records.write_json(asset.verified, {
        'schema': records.SCHEMA, 'kind': 'imported', 'asset': asset.id, 'engine': engine,
        'tool': f'{kind[0]}@{kind[1]}', 'input_fingerprint': fingerprint, 'files': files,
        'dependencies': {d: s for d, s in sorted(deps.items())}, **({'lods': lods} if lods else {})})
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


class BatchCrash(RuntimeError):
    """The editor session died: `results` holds the job results it reported before it died."""

    def __init__(self, message, results=None):
        super().__init__(message)
        self.results = results or {}


SESSION = GAME / 'tools' / 'editor' / 'session.py'
JOBS_DIR = Path('unreal/Saved/ImportBatch')
SESSION_FAILED = re.compile(r'editor session failed: job (\d+) ')
SUMMARY_LINE = re.compile(r'summary (\S+summary\.json)')


class SessionOutcome:
    """One editor session's result: each job's status (done, failed or not-run), and the session's exit code."""

    def __init__(self, results: dict, exit_code: int):
        self.results, self.exit_code = results, exit_code


def run_session(jobs_file: Path, *, log_file: Path, headless: bool = False) -> SessionOutcome:
    """Run one editor session over the batch's JOBS.json (tools/editor/session.py). Its output is streamed to this
    console and to `log_file`; the summary path and the failed job are read from the streamed text. The session's
    summary lists each finished job's asset and written files. A job the session reports as failed is 'failed'; every
    other job it did not finish is 'not-run'. Raises BatchCrash only when the session cannot start."""
    if "'import'" not in SESSION.read_text():
        # session.py runs only the job kinds it knows; checking first spares an editor start that would fail after it.
        raise BatchCrash(f"{SESSION.name} has no 'import' job kind, so no batch can run an import yet")
    command = ['nice', '-n', '10', 'uv', 'run', 'python', str(SESSION), str(jobs_file)]
    if headless:
        command.append('--headless')
    jobs = json.loads(jobs_file.read_text())['jobs']
    log_file.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    with log_file.open('w') as log:
        process = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   bufsize=1)
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
            log.flush()
            lines.append(line)
        code = process.wait()
    text = ''.join(lines)
    results = {job['asset']: {'status': 'not-run', 'error': None, 'written': []} for job in jobs}
    summary_path = SUMMARY_LINE.search(text)
    if summary_path and Path(summary_path.group(1)).is_file():
        summary = json.loads(Path(summary_path.group(1)).read_text())
        for entry in summary.get('jobs', []):
            asset = entry.get('asset') or entry['name'].removeprefix('import ')
            if asset in results and 'written' in entry:
                results[asset] = {'status': 'done', 'error': None, 'written': list(entry['written'])}
    if code:
        failed = SESSION_FAILED.search(text)
        if failed and 1 <= int(failed.group(1)) <= len(jobs):
            asset = jobs[int(failed.group(1)) - 1]['asset']
            results[asset] = {'status': 'failed', 'error': text.split('editor session failed: ', 1)[-1].strip(),
                              'written': []}
    return SessionOutcome(results, code)


class _Prepared:
    def __init__(self, asset, journal, write_set, plan_file, deps, hashes, fingerprint):
        self.asset, self.journal, self.write_set = asset, journal, write_set
        self.plan_file, self.deps, self.hashes, self.fingerprint = plan_file, deps, hashes, fingerprint


def _prepare_batch(game, asset, by_id, *, claim, echo, authorized=False):
    """import_one's steps before its editor run: fingerprint, authorize (unless the batch already did), journal,
    plan. None when up to date."""
    deps = {d: state_of(by_id, d) for d in asset.input_dependencies}
    stale = [d for d, s in deps.items() if s is None]
    if stale:
        raise ImportError_(f'{asset.id}: input dependencies {stale} have no verified state; import them first')
    hashes = current_source_hashes(asset)
    fingerprint = fingerprint_with_sources(asset, hashes, deps)
    if up_to_date(game, asset, fingerprint):
        echo(f'unchanged  {asset.id}')
        return None
    if not authorized:
        authorize(game, asset, claim)
    kind = IMPORTERS.get(asset.kind)
    if kind is None or asset.recipe.get('importer') != kind[0] or asset.recipe.get('version') != kind[1]:
        raise ImportError_(f'{asset.id}: no importer {asset.recipe.get("importer")}@{asset.recipe.get("version")} '
                           f'for kind {asset.kind}')
    journal = Journal(game, asset)
    write_set = generated_files(game, asset)
    outside = sorted(journal.pending() - {records.content_relative(game, f) for f in write_set})
    if outside:
        raise ImportError_(f'{asset.id}: an interrupted import journal would restore files outside its current '
                           f'outputs ({", ".join(outside[:5])}); resolve {journal.dir} by hand')
    recovered = journal.restore()
    if recovered:
        echo(f'recovered  {asset.id}: restored {len(recovered)} file(s) an interrupted import left')
    journal.begin(write_set)
    plan_file = journal.dir / 'plan.json'
    write_plan(game, asset, by_id, kind, claim, write_set, plan_file)
    return _Prepared(asset, journal, write_set, plan_file, deps, hashes, fingerprint)


def _verify_batch(game, prepared, result, *, engine, echo):
    """Record one asset whose job finished, exactly as import_one does: its own write set only, every package there."""
    asset = prepared.asset
    allowed = {'games/yorimichi_v2/' + records.content_relative(game, f) for f in prepared.write_set}
    outside = sorted(set(result['written']) - allowed)
    if outside:
        raise ImportError_(f'{asset.id}: the import wrote outside its declared packages: {", ".join(outside[:8])}')
    # A package that existed before the job must have been written by it: the session reports every changed file.
    existed = {rel for rel, before in json.loads(prepared.journal.manifest.read_text())['files'].items()
               if before is not None}
    for output in asset.outputs:
        if output.writer != 'generated':
            continue
        for path in records.package_files(game, output.package):
            rel = records.content_relative(game, path)
            if rel in existed and 'games/yorimichi_v2/' + rel not in result['written']:
                raise ImportError_(f'{asset.id}: {output.package} was not written by its job')
    lods = read_lod_result(prepared.plan_file, asset)
    files = recorded_files(game, asset, prepared.write_set)
    update_source_hashes(asset, prepared.hashes)
    records.write_json(asset.verified, {
        'schema': records.SCHEMA, 'kind': 'imported', 'asset': asset.id, 'engine': engine,
        'tool': f'{asset.recipe["importer"]}@{asset.recipe["version"]}', 'input_fingerprint': prepared.fingerprint,
        'files': files, 'dependencies': {d: s for d, s in sorted(prepared.deps.items())}, **({'lods': lods} if lods else {})})
    prepared.journal.close()
    echo(f'imported   {asset.id}: {len(files)} file(s)')


def import_batch(game, asset_ids, *, engine, claim, batch_size, runner=run_session, echo=print) -> dict:
    """Import many generated assets through warm editor sessions: at most `batch_size` jobs per session, and a session
    holds one asset kind only. A static-mesh session runs headless; a texture session stays rendered.

    Each asset is prepared (fingerprint, authorize, journal, plan) and its write set journaled as import_one does. The
    session runs one job per asset in order. A finished job is verified and recorded; a failed job restores its
    journal and records its error. A session that exits nonzero, or dies, is an interrupted batch even when earlier jobs
    finished: the finished ones are recorded, every other job restores its journal and is listed under not_run, and the
    batch stops without starting another session. Only when the session exits cleanly does a job it did not reach
    wait for the next session. Returns the report: imported, unchanged, failed {ID: error}, interrupted, not_run.
    """
    if batch_size < 1:
        raise ImportError_('--batch needs a size of 1 or more')
    ordered, _ = plan(game, asset_ids)
    report = {'imported': [], 'unchanged': [], 'failed': {}, 'interrupted': None, 'not_run': []}
    by_id = {a.id: a for a in records.discover(game)[0]}
    # One check for every write of the batch, before any: a check per asset cost a remote lock listing per asset.
    # Each job is still re-authorized by its session immediately before it runs.
    authorize_all(game, [by_id[a.id] for a in ordered], claim, f'batch import of {len(ordered)} asset(s)')
    queue = [a.id for a in ordered]
    session_no = 0
    while queue:
        chunk, queue, blocked = [], list(queue), False
        while queue and len(chunk) < batch_size:
            asset_id = queue[0]
            asset = by_id[asset_id]
            if chunk and asset.kind != by_id[chunk[0].asset.id].kind:
                break                                # one kind per session: the next chunk starts with this asset
            failed_deps = [d for d in asset.input_dependencies if d in report['failed']]
            if failed_deps:
                report['failed'][asset_id] = f'input dependency {failed_deps[0]} failed; not imported'
                echo(f'failed     {asset_id}: {report["failed"][asset_id]}')
                queue.pop(0)
                continue
            # A dependency still waiting in this batch must be recorded before its dependent is prepared.
            if any(d in queue and d != asset_id for d in asset.input_dependencies) or \
                    any(d in {p.asset.id for p in chunk} for d in asset.input_dependencies):
                blocked = True
                break
            queue.pop(0)
            try:
                prepared = _prepare_batch(game, asset, by_id, claim=claim, echo=echo, authorized=True)
            except ImportError_ as error:
                report['failed'][asset_id] = str(error)
                echo(f'failed     {asset_id}: {error}; no record written')
                continue
            if prepared is None:
                report['unchanged'].append(asset_id)
            else:
                chunk.append(prepared)
        if not chunk:
            if blocked:                              # cannot happen for a plan that orders dependencies first
                raise ImportError_('an input dependency is not ordered before its dependent; nothing was started')
            continue
        session_no += 1
        headless = all(p.asset.kind == 'static-mesh' for p in chunk)
        jobs_file = game / JOBS_DIR / f'session-{session_no}.json'
        jobs_file.parent.mkdir(parents=True, exist_ok=True)
        jobs_file.write_text(json.dumps({'jobs': [{
            'kind': 'import', 'name': f'import {p.asset.id}', 'asset': p.asset.id, 'claim': claim,
            'script': 'import_asset.py', 'plan': str(p.plan_file),
            'write_paths': json.loads(p.plan_file.read_text())['write_paths'],
            'env': {'V2_IMPORT_PLAN': str(p.plan_file)}} for p in chunk]}, indent=2))
        echo(f'session {session_no}: {len(chunk)} {"headless" if headless else "rendered"} import(s)')
        failure, results = None, {}
        try:
            outcome = runner(jobs_file, log_file=game / JOBS_DIR / f'session-{session_no}.log', headless=headless)
            results = outcome.results
            if outcome.exit_code:
                failure = f'editor session {session_no} exited {outcome.exit_code}'
        except BatchCrash as crash:
            results, failure = crash.results, f'editor session {session_no} died: {crash}'
        progressed, requeue = False, []
        for p in chunk:
            asset_id = p.asset.id
            result = results.get(asset_id, {'status': 'not-run', 'error': None, 'written': []})
            status = result['status']
            if status == 'done':
                try:
                    _verify_batch(game, p, result, engine=engine, echo=echo)
                    report['imported'].append(asset_id)
                    progressed = True
                    continue
                except ImportError_ as error:
                    status, result = 'failed', {'error': str(error)}
            if status == 'failed':
                p.journal.restore()
                report['failed'][asset_id] = result.get('error') or 'its job failed'
                echo(f'failed     {asset_id}: {report["failed"][asset_id]}; restored its files, no record written')
                progressed = True
            elif failure:                            # the session ended badly: this job is not run, not retried here
                p.journal.restore()
                report['not_run'].append(asset_id)
                echo(f'not run    {asset_id}: {failure}; restored its files, no record written')
            else:                                    # clean session exit, job not reached: the next session runs it
                p.journal.restore()
                requeue.append(asset_id)
        if failure:
            report['interrupted'] = failure
            break
        if not progressed:
            # Nothing finished or failed in this session: stop rather than loop on the same jobs.
            report['interrupted'] = 'the session finished no job and reported no failure'
            report['not_run'].extend(requeue)
            for asset_id in requeue:
                echo(f'not run    {asset_id}: the session stopped before it; left for a later run')
            break
        queue = requeue + queue
        by_id = {a.id: a for a in records.discover(game)[0]}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('assets', nargs='+', help='asset IDs to import, e.g. prop/harbour-bench-01')
    parser.add_argument('--plan', action='store_true', help='print what would be imported and exit')
    parser.add_argument('--claim', help='the active claim (task ID) authorizing these writes')
    parser.add_argument('--batch', type=int, default=0, metavar='N',
                        help='import through one warm editor session per N assets (default: one editor per asset)')
    args = parser.parse_args(argv)
    try:
        ordered, by_id = plan(GAME, args.assets)
        if args.plan:
            for asset in ordered:
                print(f'{asset.id:40} -> {", ".join(o.package for o in asset.outputs if o.writer == "generated")}')
            return 0
        from atelier import engine as engine_paths
        engine = engine_identity(Path(engine_paths.unreal_root()))
        if args.batch:
            report = import_batch(GAME, args.assets, engine=engine, claim=args.claim, batch_size=args.batch)
            print(f'batch: {len(report["imported"])} imported, {len(report["unchanged"])} unchanged, '
                  f'{len(report["failed"])} failed, {len(report["not_run"])} not run'
                  + (f'; stopped: {report["interrupted"]}' if report['interrupted'] else ''))
            for asset_id, error in sorted(report['failed'].items()):
                print(f'  failed {asset_id}: {error}', file=sys.stderr)
            return 1 if report['failed'] or report['interrupted'] else 0
        for asset in ordered:
            by_id = {a.id: a for a in records.discover(GAME)[0]}      # fresh: dependencies were just imported
            import_one(GAME, by_id[asset.id], by_id, engine=engine, claim=args.claim)
    except (ImportError_, RecordError) as error:
        print(f'import failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
