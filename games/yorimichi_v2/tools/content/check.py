"""The read-only content check: is every committed V2 asset present, hydrated, owned and current?

It reports exactly what needs authoring and never fixes anything: no import, no save, no stamp. A generated asset whose
sources or recipe changed asks for its own targeted import; an editor-owned package whose bytes no longer match its
record asks for save validation, never a reimport. Every Unreal package under `unreal/Content` must belong to exactly
one asset record or one region's actor record, so an unexplained package fails too.

The quick mode reuses a hash only when a file's size, modification time, change time and inode all still match the
local index (in the ignored `unreal/Saved`); a changed byte always changes the change time. `--full` rehashes
everything, for integration and suspected corruption.

Restricted content (`restricted.toml`, DECISIONS D05 group 2) is never committed: an absent pinned restricted file is
missing content and fails ("fetch required"), like any other. Only `--allow-restricted-absent`, for checkouts without
access to the restricted storage that do not build or play, downgrades it to a notice. A restricted path Git tracks, a
present restricted file that is unpinned or differs from `restricted.lock.json`, or a recorded one with no pin fails.

    uv run python games/yorimichi_v2/tools/content/check.py [--full] [--json] [--allow-restricted-absent]
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
from records import RecordError  # noqa: E402

GAME = Path(__file__).resolve().parents[2]
INDEX = Path('unreal/Saved/AssetCheck/index.json')
ACTOR_ROOTS = ('__ExternalActors__', '__ExternalObjects__')


@functools.lru_cache(maxsize=1)
def lfs_setup() -> str:
    """`git lfs install --local && ` when this clone has no LFS filter yet: a fresh clone's `git lfs pull` then skips
    every object ("Git LFS is not installed for this repository"), so the pull alone would not fix the problem."""
    import subprocess
    try:
        found = subprocess.run(['git', 'config', '--get', 'filter.lfs.process'], cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        return ''
    return '' if found else 'git lfs install --local && '


@dataclass(frozen=True)
class Problem:
    code: str       # SCHEMA, NOT_HYDRATED, MISSING, SOURCE_CHANGED, OUTPUT_CHANGED, RECORD_MISSING, STALE_IMPORT, ...
    subject: str    # asset/region ID or content-relative path
    detail: str
    action: str     # the one thing to do about it

    def __str__(self):
        return f'{self.code:16} {self.subject}: {self.detail}\n{"":17}-> {self.action}'


class Hasher:
    """sha256 of content files, reusing the local index only when every stat field still matches."""

    def __init__(self, game: Path, full: bool):
        self.game, self.full = game, full
        self.path = game / INDEX
        self.entries: dict[str, list] = {}
        self.hashed = 0
        if not full and self.path.is_file():
            try:
                self.entries = json.loads(self.path.read_text())
            except (OSError, ValueError):
                self.entries = {}
        self.changed = False

    def __call__(self, path: Path) -> str:
        rel = records.content_relative(self.game, path)
        st = path.stat()
        key = [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino]
        entry = self.entries.get(rel)
        if not self.full and entry and entry[:4] == key:
            return entry[4]
        digest = records.sha256_file(path)
        self.hashed += 1
        self.entries[rel] = key + [digest]
        self.changed = True
        return digest

    def save(self):
        if self.changed:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records.write_json(self.path, self.entries)


def _import_action(asset):
    return f'targeted import: uv run python games/yorimichi_v2/tools/import/run.py {asset.id}'


def _save_action(subject):
    # Never just "record it": an unexplained change or loss is restored, and only a claimed edit is recorded.
    return ('save validation, only for a claimed edit: uv run python games/yorimichi_v2/tools/content/save_validate.py '
            f'{subject} --claim TASK; otherwise restore the committed bytes (git checkout -- PATH && git lfs pull)')


FETCH = 'uv run python games/yorimichi_v2/tools/restricted/fetch.py'


def _file(game, rel, subject, problems, hasher, *, missing_action, restricted=None, pinned=None, absent=None):
    """The sha256 of one committed file, or None after recording why it cannot be read. An absent restricted file
    is only collected in `absent` (fetched, never committed) when the lock pins it."""
    path = game / rel
    pin = restricted.content_rel(rel) if restricted else None
    if pin is not None and not path.is_file():
        if pin in pinned:
            absent.add(pin)
        else:
            problems.append(Problem('RESTRICTED_UNPINNED', subject, f'{rel} is restricted and absent, and no pin '
                                    'can fetch it', f'pin it where it exists: {FETCH} pin'))
        return None
    if not path.is_file():
        problems.append(Problem('MISSING', subject, f'{rel} does not exist', missing_action))
        return None
    if records.is_lfs_pointer(path):
        problems.append(Problem('NOT_HYDRATED', subject, f'{rel} is a Git LFS pointer, not its content',
                                f'{lfs_setup()}git lfs pull --include="games/yorimichi_v2/{rel}"'))
        return None
    return hasher(path)


def check(game: Path = GAME, *, full: bool = False, write_index: bool = True,
          allow_restricted_absent: bool = False) -> tuple[list[Problem], dict]:
    """(fatal problems, stats); `stats['notices']` holds the non-fatal ones (absent restricted files, when allowed)."""
    problems: list[Problem] = []
    hasher = Hasher(game, full)
    try:
        restricted = records.load_restricted(game)
        pinned = records.load_lock(restricted)
    except RecordError as error:
        problems.append(Problem('SCHEMA', 'restricted', str(error), 'fix restricted.toml or its lock'))
        restricted, pinned = records.Restricted((), game / 'restricted.lock.json', ''), {}
    absent: set[str] = set()
    pins = dict(restricted=restricted, pinned=pinned, absent=absent)
    assets, regions = [], []
    for path in sorted((game / 'assets').glob('**/asset.toml')):
        try:
            assets.append(records.load_asset(path))
        except RecordError as error:
            problems.append(Problem('SCHEMA', records.content_relative(game, path), str(error), 'fix the record'))
    for path in sorted((game / 'world' / 'regions').glob('*/region.toml')):
        try:
            regions.append(records.load_region(path))
        except RecordError as error:
            problems.append(Problem('SCHEMA', records.content_relative(game, path), str(error), 'fix the record'))

    by_id = {}
    for asset in assets:
        if asset.id in by_id:
            problems.append(Problem('DUPLICATE_ID', asset.id, 'two records claim this ID', 'rename one asset'))
        by_id[asset.id] = asset
    owner_of: dict[str, str] = {}      # content-relative file -> owning record ID
    package_owner: dict[str, str] = {}
    for asset in assets:
        for output in asset.outputs:
            if output.package in package_owner:
                problems.append(Problem('OWNERSHIP', output.package,
                                        f'written by both {package_owner[output.package]} and {asset.id}',
                                        'give every package exactly one owning record'))
            package_owner[output.package] = asset.id

    # Verified state first, so dependents can fingerprint against it.
    verified: dict[str, dict] = {}
    for asset in assets:
        if asset.verified.is_file():
            try:
                verified[asset.id] = records.load_verified(asset.verified)
            except (RecordError, ValueError) as error:
                problems.append(Problem('SCHEMA', asset.id, str(error), 'regenerate the record through its owner route'))
    state = {aid: records.state_fingerprint(v) for aid, v in verified.items()}

    for asset in assets:
        generated = asset.authority in ('generated', 'split')
        redo = _import_action(asset) if generated else _save_action(asset.id)
        for dep in asset.references + asset.input_dependencies:
            if dep not in by_id:
                problems.append(Problem('DEPENDENCY', asset.id, f'depends on unknown asset {dep}',
                                        'add its record or remove the dependency'))
        for source in asset.sources:
            rel = records.content_relative(game, asset.folder / source.path)
            digest = _file(game, rel, asset.id, problems, hasher, missing_action='restore the committed source')
            if digest is not None and digest != source.sha256:
                problems.append(Problem('SOURCE_CHANGED', asset.id, f'{rel} differs from its recorded hash',
                                        _import_action(asset) if generated else
                                        'record the new source hash in asset.toml'))
        record = verified.get(asset.id)
        if record is None:
            if asset.id not in {p.subject for p in problems if p.code == 'SCHEMA'}:
                problems.append(Problem('RECORD_MISSING', asset.id, 'no verified.json for its packages', redo))
            continue
        expected_kind = 'imported' if asset.authority == 'generated' else 'editor-saved'
        if asset.authority != 'split' and record['kind'] != expected_kind:
            problems.append(Problem('AUTHORITY', asset.id, f'{asset.authority} asset has a {record["kind"]} record',
                                    redo))
        declared = {}
        for output in asset.outputs:
            for candidate in records.package_files(game, output.package):
                declared[records.content_relative(game, candidate)] = output
        recorded_packages = set()
        for rel, digest in sorted(record['files'].items()):
            stem = rel.rsplit('.', 1)[0]
            output = declared.get(rel) or next((o for f, o in declared.items() if f.rsplit('.', 1)[0] == stem), None)
            if output is None:
                problems.append(Problem('UNDECLARED', asset.id, f'{rel} is recorded but not a declared output',
                                        'declare the package in asset.toml or drop the file'))
                continue
            recorded_packages.add(output.package)
            owner_of[rel] = asset.id
            action = _import_action(asset) if output.writer == 'generated' else _save_action(asset.id)
            actual = _file(game, rel, asset.id, problems, hasher, missing_action=action, **pins)
            if actual is not None and actual != digest:
                problems.append(Problem('OUTPUT_CHANGED', asset.id, f'{rel} differs from its verified bytes', action))
        for output in asset.outputs:
            if output.package not in recorded_packages:
                problems.append(Problem('MISSING', asset.id, f'{output.package} has no recorded package file',
                                        _import_action(asset) if output.writer == 'generated' else _save_action(asset.id)))
        if generated:
            fingerprint = records.input_fingerprint(asset, state)
            if record.get('input_fingerprint') != fingerprint:
                problems.append(Problem('STALE_IMPORT', asset.id,
                                        'sources, recipe or input dependencies changed since its import',
                                        _import_action(asset)))

    # Regions own the saved actors of their maps.
    actor_maps = set()
    for region in regions:
        actor_maps.update(region.maps)
        if not region.actors.is_file():
            problems.append(Problem('RECORD_MISSING', region.id, 'no actors.verified.json', _save_action(region.id)))
            continue
        try:
            record = records.load_verified(region.actors)
        except (RecordError, ValueError) as error:
            problems.append(Problem('SCHEMA', region.id, str(error), _save_action(region.id)))
            continue
        roster = region.folder / 'patches.json'
        if roster.is_file():
            # Migration's roster of this region's scene patches: one deleted outright (with its record entry)
            # would otherwise leave the surviving patches to pass readiness with missing geometry.
            for patch_id, patch in sorted(json.loads(roster.read_text()).get('patches', {}).items()):
                if patch.get('package') not in record['files']:
                    problems.append(Problem('PATCH_MISSING', region.id,
                                            f'scene patch {patch_id} ({patch.get("key")}) is gone: {patch.get("package")}',
                                            'restore it (git checkout -- PATH && git lfs pull) or rerun the migration; '
                                            'retiring a patch is a reviewed edit of patches.json'))
        for rel, digest in sorted(record['files'].items()):
            if not any(f'/{root}/' in f'/{rel}' for root in ACTOR_ROOTS):
                problems.append(Problem('UNDECLARED', region.id, f'{rel} is not an external actor/object package',
                                        'regions own only One File Per Actor packages'))
                continue
            if rel in owner_of:
                problems.append(Problem('OWNERSHIP', rel, f'owned by both {owner_of[rel]} and {region.id}',
                                        'an actor belongs to exactly one region'))
            owner_of[rel] = region.id
            actual = _file(game, rel, region.id, problems, hasher, missing_action=_save_action(region.id), **pins)
            if actual is not None and actual != digest:
                problems.append(Problem('OUTPUT_CHANGED', region.id, f'{rel} differs from its verified bytes',
                                        _save_action(region.id)))

    # Every package in Content is explained by exactly one record.
    content = game / 'unreal' / 'Content'
    if content.is_dir():
        for root, dirs, files in os.walk(content):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS):
                    continue
                rel = records.content_relative(game, Path(root) / name)
                if rel not in owner_of:
                    problems.append(Problem('UNOWNED', rel, 'no asset or region record owns this package',
                                            'add it to its owner record through the owning route, or delete it'))

    # Restricted roots: never tracked, and every present file is exactly its pin.
    for rel in records.restricted_tracked(game, restricted):
        problems.append(Problem('RESTRICTED_TRACKED', rel, 'restricted content is tracked by Git (D05: never public LFS)',
                                f'git rm --cached "{rel}"; if it was pushed, its LFS object must be purged too'))
    for folder in restricted.folders:
        for root, dirs, files in os.walk(content / folder):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS):
                    continue
                path = Path(root) / name
                rel = path.relative_to(content).as_posix()
                if rel not in pinned:
                    problems.append(Problem('RESTRICTED_UNPINNED', rel, 'restricted file is not in restricted.lock.json',
                                            f'after adoption or a claimed, validated edit: {FETCH} pin'))
                elif hasher(path) != pinned[rel]['sha256']:
                    problems.append(Problem('RESTRICTED_CHANGED', rel, 'differs from its pinned hash',
                                            f'restore it (delete it, then {FETCH} fetch), or pin a claimed edit'))
    absent |= {rel for rel in pinned if not (content / rel).is_file()}
    notices = []
    if absent:
        notice = Problem('RESTRICTED_ABSENT', 'restricted', f'{len(absent)} pinned restricted file(s) absent, for '
                         f'example {min(absent)}: fetch required',
                         f'{restricted.source_env}=DIR {FETCH} fetch   (DIR: the authorized restricted storage)')
        (notices if allow_restricted_absent else problems).append(notice)

    if write_index:
        hasher.save()
    stats = {'assets': len(assets), 'regions': len(regions), 'files': len(owner_of), 'hashed': hasher.hashed,
             'restricted_absent': len(absent), 'notices': [asdict(n) for n in notices]}
    return problems, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--full', action='store_true', help='rehash every file instead of trusting the local index')
    parser.add_argument('--json', action='store_true', help='machine-readable report')
    parser.add_argument('--allow-restricted-absent', action='store_true',
                        help='only note absent pinned restricted files (no restricted access; never for build or play)')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    problems, stats = check(args.game.resolve(), full=args.full, allow_restricted_absent=args.allow_restricted_absent)
    if args.json:
        print(json.dumps({'ok': not problems, 'stats': stats, 'problems': [asdict(p) for p in problems]}, indent=2))
    else:
        for problem in problems:
            print(problem)
        for notice in stats['notices']:
            print(f'note: {Problem(**notice)}')
        print(f'{"FAIL" if problems else "OK"}: {stats["assets"]} assets, {stats["regions"]} regions, '
              f'{stats["files"]} files ({stats["hashed"]} hashed), {len(problems)} problem(s)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
