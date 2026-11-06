"""Who may write protected V2 packages (CONTRACTS yorimichi-v2-single-writer, DECISIONS D04).

A claimed write is checked at the `publish` stage: every path exactly claimed by the task's active claim, with
its recorded Git LFS lock verified live on the remote. Without a claim, only the D04 bootstrap writer may write,
and only in a checkout that has no claims task set; this exception ends when D04 is closed.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BOOTSTRAP_WRITER = 'jim-macbook-5'   # DECISIONS D04, until the claim service adopts protected writes


class Unauthorized(RuntimeError):
    pass


def allow_saves(paths: list[str], list_file: Path, *, repo: Path = REPO) -> None:
    """Limit the next editor's package saves to these repository-relative paths (V2SaveGuard, V2_SAVE_ALLOW)."""
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text(''.join(f'{repo / path}\n' for path in sorted(set(paths))))
    os.environ['V2_SAVE_ALLOW'] = str(list_file)


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


def owning_scopes(game: Path, paths: list[str]) -> tuple[set[str], list[str]]:
    """The scopes of the records owning these repository paths, and the paths no record owns yet."""
    import records
    assets, regions = records.discover(game)
    owner = {}
    for asset in assets:
        for output in asset.outputs:
            stem = records.package_files(game, output.package)[0].with_suffix('')
            for ext in records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS:
                owner[f'games/yorimichi_v2/{stem.with_suffix(ext).relative_to(game).as_posix()}'] = scope_of(asset.id)
    for region in regions:
        if region.actors.is_file():
            for rel in records.load_verified(region.actors)['files']:
                owner[f'games/yorimichi_v2/{rel}'] = scope_of(region.id)
    return {owner[p] for p in paths if p in owner}, [p for p in paths if p not in owner]


def claimed_scopes(claim: str, *, repo: Path = REPO) -> list[str]:
    """The scope items of the task's active claims, read from the claim service."""
    result = subprocess.run(['uv', 'run', 'atelier', 'claims', 'task', 'show', claim], cwd=repo,
                            capture_output=True, text=True)
    if result.returncode:
        raise Unauthorized(f'claim service: cannot read task {claim}: {result.stderr.strip()[-300:]}')
    task = json.loads(result.stdout)
    return [item['value'] for c in task.get('claims', []) if c.get('state') == 'active'
            for item in c.get('items', []) if item.get('kind') == 'scope']


def covered(scope: str, held: list[str]) -> bool:
    """A held scope covers itself and its descendants (claims/scopes.py)."""
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
        missing = sorted(s for s in scopes if not covered(s, held))
        if missing:
            raise Unauthorized(f'{what}: claim {claim} holds no active scope covering {", ".join(missing)}')
        command = ['uv', 'run', 'atelier', 'claims', 'check', '--stage', 'publish', '--task', claim,
                   '--paths', *paths]
        if subprocess.run(command, cwd=repo).returncode:
            raise Unauthorized(f'{what}: claim {claim} does not exactly cover these paths with verified locks; '
                               'extend and acquire it first')
        return
    owner = os.environ.get('ATELIER_AGENT')
    if owner != BOOTSTRAP_WRITER:
        raise Unauthorized(f'{what}: no --claim given and ATELIER_AGENT={owner!r} is not the bootstrap writer '
                           f'{BOOTSTRAP_WRITER!r} (DECISIONS D04)')
    task = checkout_task(repo)
    if task:
        raise Unauthorized(f'{what}: this checkout works under claims task {task!r}; pass --claim {task}')
