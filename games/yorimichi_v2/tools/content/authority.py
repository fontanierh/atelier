"""Who may write protected V2 packages (CONTRACTS yorimichi-v2-single-writer, DECISIONS D04).

A claimed write is checked at the `publish` stage: every path exactly claimed by the task's active claim, with
its recorded Git LFS lock verified live on the remote. Without a claim, only the D04 bootstrap writer may write,
and only in a checkout that has no claims task set; this exception ends when `governance.toml` closes D04.

A write that creates actor packages World Partition names only when it saves them (the migration) runs under a
claim holding each region it touches: it may create new files in those regions' actor folders, which are then
bound to the claim with their LFS locks before publication (`creation_claim`, `bind_created`; a failed bind sets
them aside for `resume_created`).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
GAME = Path(__file__).resolve().parents[2]
GOVERNANCE = GAME / 'governance.toml'   # the committed D04 switch


class Unauthorized(RuntimeError):
    pass


def d04(path: Path | None = None) -> tuple[str | None, bool]:
    """(bootstrap writer, closed) from the committed switch; a missing or malformed switch is closed (fail closed)."""
    try:
        section = tomllib.loads((path or GOVERNANCE).read_text()).get('d04', {})
    except (OSError, tomllib.TOMLDecodeError):
        return None, True
    writer, closed = section.get('writer'), section.get('closed')
    if not isinstance(writer, str) or closed is not False:
        return (writer if isinstance(writer, str) else None), True
    return writer, False


BOOTSTRAP_WRITER = d04()[0]   # DECISIONS D04: the writer named in governance.toml, exempt only while D04 is open


def allow_saves(paths: list[str], list_file: Path, *, repo: Path = REPO) -> None:
    """Limit the next editor's package saves to these repository-relative paths (V2SaveGuard, V2_SAVE_ALLOW)."""
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text(''.join(f'{repo / path}\n' for path in sorted(set(paths))))
    os.environ['V2_SAVE_ALLOW'] = str(list_file)


def deny_saves(paths, list_file: Path, *, repo: Path = REPO) -> None:
    """Refuse the next editor's saves of these repository-relative paths (V2SaveGuard, V2_SAVE_DENY)."""
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text(''.join(f'{repo / path}\n' for path in sorted(set(paths))))
    os.environ['V2_SAVE_DENY'] = str(list_file)


def content_snapshot(game: Path) -> dict[str, tuple]:
    """(size, mtime, ctime, inode) of every file under unreal/Content, game-relative, to find what a run wrote."""
    content = game / 'unreal' / 'Content'
    found = {}
    if content.is_dir():
        for root, _, names in os.walk(content):
            for name in names:
                path = Path(root) / name
                st = path.lstat()
                found[path.relative_to(game).as_posix()] = (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino)
    return found


def written(before: dict[str, tuple], after: dict[str, tuple]) -> set[str]:
    """Game-relative files created, changed or deleted between two snapshots."""
    return {rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel)}


def checkout_task(repo: Path = REPO) -> str | None:
    """The claims task this checkout works under (ATELIER_CLAIMS_TASK or `atelier claims use-task`), if any."""
    if os.environ.get('ATELIER_CLAIMS_TASK'):
        return os.environ['ATELIER_CLAIMS_TASK']
    result = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--absolute-git-dir'], capture_output=True, text=True)
    path = Path(result.stdout.strip()) / 'atelier-claims-task' if result.returncode == 0 else None
    return (path.read_text().strip() or None) if path is not None and path.is_file() else None


def scope_of(subject: str) -> str:
    """The claim scope of an owning record: `region/<name>` for a region, `asset/<id>` for an asset."""
    return subject if subject.startswith('region/') else f'asset/{subject}'


def asset_scope(asset) -> tuple[str, str]:
    """Either scope covers an asset: `asset/<id>` or its record's `owner` (the change-set report's rule)."""
    return f'asset/{asset.id}', asset.owner


def subject_scope(game: Path, subject: str):
    """The scope of a region ID, or of an asset ID through its record (scope_of when no record exists yet)."""
    import records
    if subject.startswith('region/'):
        return subject
    asset = next((a for a in records.discover(game)[0] if a.id == subject), None)
    return asset_scope(asset) if asset else scope_of(subject)


def owning_scopes(game: Path, paths: list[str]) -> tuple[set[str], list[str]]:
    """The scopes of the records owning these repository paths, and the paths no record owns yet."""
    import records
    assets, regions = records.discover(game)
    owner = {}
    for asset in assets:
        for output in asset.outputs:
            stem = records.package_files(game, output.package)[0].with_suffix('')
            for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS:
                owner[f'games/yorimichi_v2/{stem.with_suffix(ext).relative_to(game).as_posix()}'] = asset_scope(asset)
    for region in regions:
        if region.actors.is_file():
            for rel in records.load_verified(region.actors)['files']:
                stem = Path(rel).with_suffix('')   # an actor package's companions belong to its region too
                for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS:
                    owner[f'games/yorimichi_v2/{stem.with_suffix(ext).as_posix()}'] = scope_of(region.id)
    return {owner[p] for p in paths if p in owner}, [p for p in paths if p not in owner]


def generated_paths(game: Path) -> set[str]:
    """Repository paths of every generated package and its companions: only their recorded importer writes them."""
    import records
    found = set()
    for asset in records.discover(game)[0]:
        for output in asset.outputs:
            if output.writer != 'generated':
                continue
            stem = records.package_files(game, output.package)[0].with_suffix('')
            found |= {f'games/yorimichi_v2/{stem.with_suffix(ext).relative_to(game).as_posix()}'
                      for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS}
    return found


def active_claims(claim: str, *, repo: Path = REPO) -> list[dict]:
    """The task's active claims (id, principal, items), read from the claim service."""
    result = subprocess.run(['uv', 'run', 'atelier', 'claims', 'task', 'show', claim], cwd=repo,
                            capture_output=True, text=True)
    if result.returncode:
        raise Unauthorized(f'claim service: cannot read task {claim}: {result.stderr.strip()[-300:]}')
    return [c for c in json.loads(result.stdout).get('claims', []) if c.get('state') == 'active']


def items_of(claim: dict, kind: str) -> list[str]:
    return [item['value'] for item in claim.get('items', []) if item.get('kind') == kind]


def claimed_scopes(claim: str, *, repo: Path = REPO) -> list[str]:
    """The scope items of the task's active claims, read from the claim service."""
    return [scope for c in active_claims(claim, repo=repo) for scope in items_of(c, 'scope')]


def covered(scope, held: list[str]) -> bool:
    """A held scope covers itself and its descendants (claims/scopes.py); a tuple is covered by any of its scopes."""
    if isinstance(scope, tuple):
        return any(covered(s, held) for s in scope)
    parts = scope.casefold().split('/')
    return any(parts[:len(h.split('/'))] == h.casefold().split('/') for h in held)


def authorize(paths: list[str], claim: str | None, what: str, *, scopes=(), repo: Path = REPO) -> None:
    """Raise Unauthorized unless this write of repository-relative `paths`, owned by `scopes`, is allowed."""
    if claim:
        if not paths:
            raise Unauthorized(f'{what}: a claimed write must name the paths it writes')
        if not scopes:
            raise Unauthorized(f'{what}: a claimed write must name the scopes that own its paths')
        held = claimed_scopes(claim, repo=repo)
        missing = sorted(' or '.join(s) if isinstance(s, tuple) else s for s in scopes if not covered(s, held))
        if missing:
            raise Unauthorized(f'{what}: claim {claim} holds no active scope covering {", ".join(missing)}')
        command = ['uv', 'run', 'atelier', 'claims', 'check', '--stage', 'publish', '--task', claim,
                   '--paths', *paths]
        result = subprocess.run(command, cwd=repo, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            reason = (result.stderr or '').strip()
            raise Unauthorized(f'{what}: claim {claim} does not exactly cover these paths with verified locks; '
                               f'extend and acquire it first' + (f' ({reason[-300:]})' if reason else ''))
        return
    writer, closed = d04()
    if closed:
        raise Unauthorized(f'{what}: no --claim given, and DECISIONS D04 is closed ({GOVERNANCE.name}): every binary '
                           'write needs a claim, the bootstrap writer\'s included')
    owner = os.environ.get('ATELIER_AGENT')
    if owner != writer:
        raise Unauthorized(f'{what}: no --claim given and ATELIER_AGENT={owner!r} is not the bootstrap writer '
                           f'{writer!r} (DECISIONS D04)')
    task = checkout_task(repo)
    if task:
        raise Unauthorized(f'{what}: this checkout works under claims task {task!r}; pass --claim {task}')


def creation_claim(claim: str, regions: list[str], what: str, *, repo: Path = REPO) -> dict:
    """The task's active claim, held by this actor, whose region scopes cover every region a creating write touches
    (scopes are exclusive in the claim service); the files the write creates are bound to it."""
    if not regions or not all(r.startswith('region/') for r in regions):
        raise Unauthorized(f'{what}: only region writes may create actor packages, not {regions}')
    actor = os.environ.get('ATELIER_CLAIMS_ACTOR') or os.environ.get('ATELIER_AGENT')
    for held in active_claims(claim, repo=repo):
        if held.get('principal') == actor and all(covered(r, items_of(held, 'scope')) for r in regions):
            return held
    raise Unauthorized(f'{what}: task {claim} has no active claim held by {actor!r} whose scopes cover '
                       f'{", ".join(regions)}; request one with each region scope')


BIND_RETRY_S = 20.0   # a busy claim service (a reconcile listing every lock) times a batch out
PENDING = REPO / 'build/yorimichi_v2/migrate/pending'   # checked created files a failed bind set aside


# What the claims CLI reports when the service, not a decision, failed: it is unreachable or timed out, still
# reconciling, cannot reach the LFS or Git remote, or holds an earlier lock request whose outcome is unknown.
SERVICE_FAULTS = ('claims service at ', 'unsettled', 'reconciling', 'lfs_unavailable', 'git_unavailable', 'uncertain',
                  ': unknown')


class BindFailed(Unauthorized):
    """The claim service failed while created files that passed their own checks were bound: they wait in PENDING,
    outside the content tree, for `resume_created` once it can take their locks (no editor rerun)."""


def service_fault(error: BaseException) -> bool:
    """Whether a refused write failed for the claim service, not for a decision (SERVICE_FAULTS)."""
    return isinstance(error, Unauthorized) and any(f in str(error) for f in SERVICE_FAULTS)


def _check_created(claim: str, regions: list[str], created: list[str], what: str, *, game: Path,
                   repo: Path) -> tuple[dict, list[str]]:
    """The claim that may bind these created files and their repository paths, or Unauthorized."""
    import records
    held = creation_claim(claim, regions, what, repo=repo)
    by_id = {r.id: r for r in records.discover(game)[1]}
    unknown = [r for r in regions if r not in by_id]
    if unknown:
        raise Unauthorized(f'{what}: no region record for {", ".join(unknown)}')
    folders = [folder + '/' for r in regions for folder in by_id[r].actor_folders]
    outside = [rel for rel in created if not rel.startswith(tuple(folders))]
    if outside:
        raise Unauthorized(f'{what}: created {", ".join(outside[:8])} outside the actor folders of '
                           f'{", ".join(regions)}; delete them (a claimed write creates only its regions\' actors)')
    paths = [f'games/yorimichi_v2/{rel}' for rel in created]
    owned, _ = owning_scopes(game, paths)
    if owned:
        raise Unauthorized(f'{what}: created files a record already lists ({", ".join(sorted(map(str, owned)))}); '
                           'a new file must not have existed before the write')
    return held, paths


def _bind(held: dict, paths: list[str], claim: str, regions: list[str], what: str, *, repo: Path) -> None:
    for start in range(0, len(paths), 500):   # bounded command lines for a large migration
        batch = paths[start:start + 500]
        command = ['uv', 'run', 'atelier', 'claims', 'extend', str(held['id']),
                   *(arg for path in batch for arg in ('--lock-path', path)), '--acquire']
        for attempt in range(3):   # extending again is safe: held items stay, and only missing locks are taken
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True)
            if not result.returncode:
                break
            time.sleep(BIND_RETRY_S * (attempt + 1))
        if result.returncode:
            raise Unauthorized(f'{what}: cannot bind {len(batch)} created file(s) to claim {held["id"]} of task '
                               f'{claim}: {result.stderr.strip()[-300:]}')
    if paths:
        authorize(paths, claim, what, scopes=set(regions), repo=repo)


def _move(rels: list[str], source: Path, target: Path) -> None:
    for rel in rels:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        os.replace(source / rel, target / rel)


def bind_created(claim: str, regions: list[str], before: dict, after: dict, what: str, *, game: Path = GAME,
                 repo: Path = REPO) -> list[str]:
    """Check a claimed creating write from content snapshots taken around it and bind what it created; returns the
    created repository paths. A created file is one absent before the write, unrecorded, under the actor folders
    of the claim's regions; any other created file is refused. Changed or deleted existing files must be exactly
    claimed, as for every write. The created files are added to the claim with their LFS locks (`atelier claims
    extend ID --lock-path ... --acquire`) and then checked like any claimed path, so nothing unbound is published."""
    changed = written(before, after)
    created = sorted(rel for rel in changed if rel not in before and rel in after)
    checked = False
    try:
        held, paths = _check_created(claim, regions, created, what, game=game, repo=repo)
        checked = True
        existing = [f'games/yorimichi_v2/{rel}' for rel in sorted(changed - set(created))]
        if existing:
            scopes, _ = owning_scopes(game, existing)
            authorize(existing, claim, what, scopes=scopes | set(regions), repo=repo)
        _bind(held, paths, claim, regions, what, repo=repo)
    except BaseException as error:
        # Created files exist before their paths can be claimed (World Partition names them at save). Unbound,
        # they are unauthorized writes and leave the content tree: after a claim service fault, files that passed
        # their own checks wait in `pending` for a resumed bind, so the fault does not discard a long editor run;
        # after any refusal or other error they are removed. Existing files and claims are left as they were.
        pending = PENDING
        if not (checked and service_fault(error)) or pending.exists():   # one set waits at a time
            for rel in created:
                (game / rel).unlink(missing_ok=True)
            raise
        _move(created, game, pending / 'files')
        (pending / 'pending.json').write_text(json.dumps({'claim': claim, 'regions': regions, 'what': what,
                                                          'created': created}, indent=2) + '\n')
        raise BindFailed(f'{error}; the {len(created)} created file(s) wait in {pending}: resume the bind '
                         'once the claim service settles (tools/migrate/run.py --resume)') from error
    return paths


def resume_created(*, game: Path = GAME, repo: Path = REPO) -> list[str]:
    """Bind the created files a failed bind set aside: re-check them, put them back and bind them as `bind_created`
    does; returns their game-relative paths and removes `pending`. After another claim service fault they go back
    to `pending`; after a refusal (or any other error) they are deleted with it."""
    import shutil
    pending = PENDING
    record = json.loads((pending / 'pending.json').read_text())
    created = record['created']
    present = [rel for rel in created if (game / rel).exists()]
    if present:
        raise Unauthorized(f'{record["what"]}: {present[0]} is already in the content tree; not resuming')
    try:
        held, paths = _check_created(record['claim'], record['regions'], created, record['what'], game=game,
                                     repo=repo)
    except BaseException as error:
        if not service_fault(error):
            shutil.rmtree(pending)
        raise
    _move(created, pending / 'files', game)
    try:
        _bind(held, paths, record['claim'], record['regions'], record['what'], repo=repo)
    except BaseException as error:
        if service_fault(error):
            _move(created, game, pending / 'files')
            raise BindFailed(f'{error}; the created files wait in {pending} again') from error
        for rel in created:
            (game / rel).unlink(missing_ok=True)
        shutil.rmtree(pending)
        raise
    shutil.rmtree(pending)
    return created
