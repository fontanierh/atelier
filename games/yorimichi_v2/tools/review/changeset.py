"""The change-set report: what a V2 change touches, who owns each file, and whether the change is complete and claimed.

For every changed file under games/yorimichi_v2 it names the kind (asset/region/verification record, generated or
editor package, external actor/object package, companion, config, code, other), the owning asset or region, and for
One File Per Actor packages the map, actor label, class and GUID read from the package header. The change type is
add, edit, delete, rename or move (an actor that changes region). Deleted files are read from the old revision, through
Git LFS when they are pointers, so a deleted actor is still identified.

It fails (exit 1) when the change is incomplete or unclaimed:

- PACKAGE_WITHOUT_RECORD  a package changed but its owner's verified.json / actors.verified.json did not
- RECORD_WITHOUT_PACKAGE  a verification record (or an asset's outputs) changed for packages that did not
- RECORD_MISMATCH         the changed record does not list the changed package's new bytes
- COMPANION / ORPHAN_COMPANION / MISSING_COMPANION   .ubulk/.uexp/.uptnl out of step with their package
- OUT_OF_SCOPE            a changed file outside the declared claims (--scopes / --paths)
- UNOWNED                 a package no asset or region record owns
- REGION_MISMATCH         an actor's location lies in another region than the record that lists it
- REFERENCED_DELETION     a deleted package's /Game name is still written in a committed record
- ORPHAN_ACTOR            a deleted map leaves its external actors behind

Scopes: a parent scope covers its children (`region/hidamari` covers `region/hidamari/harbour`); moving an actor
between regions needs both regions; an asset needs its record's `owner` scope or `asset/<id>`, so a region claim
never covers a shared/* material. `--paths` claims exact files or folders (repository- or game-relative).

    uv run python games/yorimichi_v2/tools/review/changeset.py [RANGE | --staged]
        [--scopes region/w04-skatepark,asset/prop/bench] [--paths games/yorimichi_v2/unreal/Config] [--json]

RANGE defaults to origin/main...HEAD (changes on this branch since it left main). Read-only: it changes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402
from records import RecordError  # noqa: E402

try:
    from atelier import unreal_package_summary as ups
except ImportError:                                      # a plain checkout without the installed studio package
    sys.path.insert(0, str(GAME.parents[1] / 'platform' / 'studio'))
    from atelier import unreal_package_summary as ups

ACTOR_ROOTS = ('__ExternalActors__', '__ExternalObjects__')
PACKAGES = records.PACKAGE_EXTENSIONS
COMPANIONS = records.COMPANION_EXTENSIONS
CODE_SUFFIXES = ('.py', '.cpp', '.h', '.hpp', '.c', '.cs', '.rs', '.js', '.ts', '.sh', '.usf', '.ush')
CONFIG_SUFFIXES = ('.ini', '.toml', '.uproject', '.uplugin', '.json', '.yaml', '.yml')
EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
STATUS = {'A': 'add', 'C': 'add', 'M': 'edit', 'T': 'edit', 'D': 'delete', 'R': 'rename'}


class ChangesetError(RuntimeError):
    """The change set cannot be read (bad range, not a repository, ...)."""


@dataclass(frozen=True)
class Problem:
    code: str
    subject: str
    detail: str
    action: str

    def __str__(self):
        return f'{self.code:22} {self.subject}: {self.detail}\n{"":23}-> {self.action}'


@dataclass
class Change:
    path: str                     # game-relative; the new path, or the old one for a deletion
    old_path: str | None
    change: str                   # add, edit, delete, rename, move
    kind: str
    owner: str | None             # asset ID or region ID after the change (before it, for a deletion)
    old_owner: str | None = None
    writer: str | None = None     # generated / editor, for asset packages
    map: str | None = None
    actor_label: str | None = None
    actor_class: str | None = None
    actor_guid: str | None = None
    location: list[float] | None = None
    scopes: list[str] = field(default_factory=list)
    note: str | None = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def long_name(rel: str) -> str | None:
    """`unreal/Content/A/B.uasset` -> `/Game/A/B`; None outside the project's Content folder."""
    path = PurePosixPath(rel)
    if path.parts[:2] != ('unreal', 'Content') or path.suffix not in PACKAGES + COMPANIONS:
        return None
    return '/Game/' + path.relative_to('unreal/Content').with_suffix('').as_posix()


def stem(rel: str) -> str:
    return rel.rsplit('.', 1)[0] if '.' in PurePosixPath(rel).name else rel


def is_external(rel: str) -> bool:
    return any(f'/{root}/' in f'/{rel}' for root in ACTOR_ROOTS)


def covers(scope: str, wanted: str) -> bool:
    return wanted == scope or wanted.startswith(scope.rstrip('/') + '/')


class Git:
    def __init__(self, game: Path):
        self.game = game.resolve()
        try:
            root = self.run('rev-parse', '--show-toplevel', cwd=self.game).decode().strip()
        except ChangesetError:
            raise ChangesetError(f'{self.game} is not inside a Git repository') from None
        self.root = Path(root).resolve()
        self.prefix = self.game.relative_to(self.root).as_posix()
        self.prefix = '' if self.prefix == '.' else self.prefix

    def run(self, *args, input: bytes | None = None, cwd: Path | None = None, check=True) -> bytes:
        result = subprocess.run(['git', *args], cwd=cwd or self.root, input=input, capture_output=True)
        if check and result.returncode:
            raise ChangesetError(f'git {" ".join(args)}: {result.stderr.decode(errors="replace").strip()}')
        return result.stdout

    def repo_path(self, rel: str) -> str:
        return f'{self.prefix}/{rel}' if self.prefix else rel

    def game_path(self, repo_rel: str) -> str | None:
        if not self.prefix:
            return repo_rel
        return repo_rel[len(self.prefix) + 1:] if repo_rel.startswith(self.prefix + '/') else None

    def resolve(self, rev: str) -> str:
        return self.run('rev-parse', '--verify', '--quiet', f'{rev}^{{commit}}').decode().strip()

    def head_or_empty(self) -> str:
        out = self.run('rev-parse', '--verify', '--quiet', 'HEAD^{commit}', check=False).decode().strip()
        return out or EMPTY_TREE

    def diff(self, old: str, new: str | None) -> list[tuple[str, str | None, str | None]]:
        """(status letter, old game path, new game path) for every change under the game folder."""
        args = ['diff', '--name-status', '-M', '-z']
        args += ['--cached', old] if new is None else [old, new]
        out = self.run(*args, '--', self.prefix or '.').split(b'\0')
        entries, i = [], 0
        while i < len(out) and out[i]:
            status = out[i].decode()[0]
            if status in 'RC':
                a, b = out[i + 1].decode(), out[i + 2].decode()
                i += 3
            else:
                a = b = out[i + 1].decode()
                i += 2
            old_rel, new_rel = self.game_path(a), self.game_path(b)
            if status == 'A':
                old_rel = None
            elif status == 'D':
                new_rel = None
            entries.append((status, old_rel, new_rel))
        return entries

    def files(self, rev: str | None) -> set[str]:
        """Game-relative paths of every file at a commit, or in the index when rev is None."""
        if rev == EMPTY_TREE:
            return set()
        spec = self.prefix or '.'
        out = (self.run('ls-files', '-z', '--cached', '--', spec) if rev is None
               else self.run('ls-tree', '-r', '-z', '--name-only', rev, '--', spec))
        return {g for g in (self.game_path(p.decode()) for p in out.split(b'\0') if p) if g}

    def blobs(self, rev: str | None, rels: list[str]) -> dict[str, bytes | None]:
        """Raw blob bytes for many paths at once (`git cat-file --batch`)."""
        if not rels or rev == EMPTY_TREE:
            return {rel: None for rel in rels}
        specs = [f'{rev or ""}:{self.repo_path(rel)}' for rel in rels]
        out = self.run('cat-file', '--batch', input=('\n'.join(specs) + '\n').encode())
        result, pos = {}, 0
        for rel in rels:
            end = out.index(b'\n', pos)
            header = out[pos:end].split()
            pos = end + 1
            if len(header) < 3 or header[-1] == b'missing':
                result[rel] = None
                continue
            size = int(header[2])
            result[rel] = out[pos:pos + size]
            pos += size + 1
        return result

    def smudge(self, rel: str, pointer: bytes) -> bytes | None:
        """The real content behind an LFS pointer, or None when Git LFS or the object is unavailable."""
        try:
            result = subprocess.run(['git', 'lfs', 'smudge', '--', self.repo_path(rel)], cwd=self.root,
                                    input=pointer, capture_output=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode or result.stdout.startswith(records.LFS_POINTER):
            return None
        return result.stdout


RECORD_PATTERNS = ('assets/**/asset.toml', 'assets/**/verified.json',
                   'world/regions/*/region.toml', 'world/regions/*/actors.verified.json')


def _is_record(rel: str) -> bool:
    return any(PurePosixPath(rel).match(p) for p in RECORD_PATTERNS) or (
        rel.startswith('assets/') and rel.endswith(('/asset.toml', '/verified.json')))


class Snapshot:
    """The records and file list of one side of the change, loaded from Git without touching the work tree."""

    def __init__(self, git: Git, rev: str | None, label: str):
        self.git, self.rev, self.label = git, rev, label
        self.files = git.files(rev)
        self.problems: list[Problem] = []
        self._bytes: dict[str, bytes | None] = {}
        self.unhydrated: set[str] = set()
        record_rels = sorted(rel for rel in self.files if _is_record(rel))
        blobs = git.blobs(rev, record_rels)
        self.texts = {rel: (data or b'').decode('utf-8', errors='replace') for rel, data in blobs.items()}
        self.assets: dict[str, records.Asset] = {}
        self.regions: dict[str, records.Region] = {}
        self.verified: dict[str, dict] = {}          # record rel -> parsed verification record
        self.asset_folder: dict[str, str] = {}      # game-relative asset folder -> asset ID
        self.asset_record: dict[str, str] = {}      # asset ID -> verified.json rel
        self.region_record: dict[str, str] = {}     # region ID -> actors.verified.json rel
        self.owner: dict[str, str] = {}             # file rel -> asset ID (packages, companions)
        self.writer: dict[str, str] = {}            # package stem -> generated/editor
        self.member: dict[str, str] = {}            # external package rel -> region ID
        with tempfile.TemporaryDirectory(prefix='v2-changeset-') as tmp:
            root = Path(tmp).resolve()
            for rel, text in self.texts.items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            self._load(root)

    def _load(self, root: Path):
        for rel in sorted(self.texts):
            path = root / rel
            try:
                if rel.endswith('asset.toml'):
                    asset = records.load_asset(path)
                    folder = PurePosixPath(rel).parent.as_posix()
                    if asset.id in self.assets:
                        self.problems.append(Problem('DUPLICATE_ID', asset.id, f'{self.label}: two records claim it',
                                                     'rename one asset'))
                    self.assets[asset.id] = asset
                    self.asset_folder[folder] = asset.id
                    self.asset_record[asset.id] = f'{folder}/verified.json'
                    for output in asset.outputs:
                        for candidate in records.package_files(root, output.package):
                            s = stem(records.content_relative(root, candidate))
                            self.writer[s] = output.writer
                            for ext in PACKAGES + COMPANIONS:
                                self.owner.setdefault(s + ext, asset.id)
                elif rel.endswith('region.toml'):
                    region = records.load_region(path)
                    self.regions[region.id] = region
                    self.region_record[region.id] = f'{PurePosixPath(rel).parent.as_posix()}/actors.verified.json'
            except RecordError as error:
                self.problems.append(Problem('SCHEMA', rel, f'{self.label}: {error}', 'fix the record'))
        for rel in sorted(self.texts):
            if not rel.endswith('verified.json'):
                continue
            try:
                self.verified[rel] = records.load_verified(root / rel)
            except (RecordError, ValueError) as error:
                self.problems.append(Problem('SCHEMA', rel, f'{self.label}: {error}', 'fix the record'))
                continue
            folder = PurePosixPath(rel).parent.as_posix()
            if rel.endswith('actors.verified.json'):
                region = next((r for r, record in self.region_record.items() if record == rel), None)
                for member in self.verified[rel]['files']:
                    if region:
                        self.member[member] = region
            elif folder in self.asset_folder:
                for member in self.verified[rel]['files']:
                    self.owner[member] = self.asset_folder[folder]

    def asset_of_path(self, rel: str) -> str | None:
        """The asset whose folder holds rel (its record, verification record or a source)."""
        parent = PurePosixPath(rel).parent
        while parent.as_posix() not in ('.', ''):
            if parent.as_posix() in self.asset_folder:
                return self.asset_folder[parent.as_posix()]
            parent = parent.parent
        return None

    def region_of_record(self, rel: str) -> str | None:
        folder = PurePosixPath(rel).parent.as_posix()
        return next((r for r, record in self.region_record.items()
                     if PurePosixPath(record).parent.as_posix() == folder), None)

    def read(self, rel: str) -> bytes | None:
        if rel not in self._bytes:
            data = self.git.blobs(self.rev, [rel])[rel] if rel in self.files else None
            if data is not None and data.startswith(records.LFS_POINTER) and len(data) < 1024:
                real = self.git.smudge(rel, data)
                if real is None:
                    self.unhydrated.add(rel)
                data = real
            self._bytes[rel] = data
        return self._bytes[rel]

    def header(self, rel: str):
        """(parsed package or None, reason it could not be read)."""
        data = self.read(rel)
        if data is None:
            return None, 'LFS content unavailable' if rel in self.unhydrated else 'no bytes'
        try:
            return ups.parse(data), None
        except ups.PackageError as error:
            return None, str(error)

    def region_at(self, map_name: str | None, location) -> str | None:
        if location is None:
            return None
        x, y = location[0], location[1]
        hits = sorted(r.id for r in self.regions.values()
                      if (map_name is None or map_name in r.maps)
                      and r.bounds_cm[0] <= x < r.bounds_cm[2] and r.bounds_cm[1] <= y < r.bounds_cm[3])
        return hits[0] if hits else None


def classify(rel: str, snap: Snapshot) -> str:
    path = PurePosixPath(rel)
    if path.name == 'asset.toml':
        return 'asset record'
    if path.name == 'region.toml':
        return 'region record'
    if path.name.endswith('verified.json'):
        return 'verification record'
    if path.suffix in COMPANIONS:
        return 'companion'
    if path.suffix in PACKAGES:
        if is_external(rel):
            return 'external package'
        writer = snap.writer.get(stem(rel))
        return f'{writer} package' if writer else 'package'
    if path.suffix in CODE_SUFFIXES or 'Source' in path.parts:
        return 'code'
    if path.suffix in CONFIG_SUFFIXES or 'Config' in path.parts:
        return 'config'
    return 'other'


class Report:
    def __init__(self, git: Git, old: Snapshot, new: Snapshot, scopes: list[str], paths: list[str]):
        self.git, self.old, self.new = git, old, new
        self.scopes, self.paths = scopes, [p.strip('/') for p in paths]
        self.changes: list[Change] = []
        self.problems: list[Problem] = list(old.problems) + [p for p in new.problems if p not in old.problems]
        self.requirements: list[tuple[str, tuple[str, ...]]] = []   # (path, alternative scopes)

    # -- ownership -------------------------------------------------------------------------------------------
    def _owner(self, snap: Snapshot, rel: str, kind: str):
        """(owner ID, writer, actor info) of one file on one side of the change."""
        if kind == 'external package' or (kind == 'companion' and is_external(rel)):
            package, reason = snap.header(stem(rel) + '.uasset') if kind == 'companion' else snap.header(rel)
            actor = package.actor if package else None
            located = snap.region_at(actor.map, actor.location) if actor else None
            member = snap.member.get(rel)
            return located or member, None, actor, located, member, reason
        if kind in ('asset record', 'verification record', 'region record'):
            if kind == 'region record' or rel.endswith('actors.verified.json'):
                return snap.region_of_record(rel), None, None, None, None, None
            return snap.asset_of_path(rel), None, None, None, None, None
        owner = snap.owner.get(rel) or (snap.asset_of_path(rel) if rel.startswith('assets/') else None)
        return owner, snap.writer.get(stem(rel)), None, None, None, None

    def _scopes_for(self, owner: str | None, snap: Snapshot) -> tuple[str, ...]:
        if owner is None:
            return ()
        if owner.startswith('region/'):
            return (owner,)
        asset = snap.assets.get(owner)
        return (asset.owner, f'asset/{owner}') if asset else (f'asset/{owner}',)

    def build(self, entries):
        changed = {p for _, a, b in entries for p in (a, b) if p}
        self.changed = changed
        for status, old_rel, new_rel in entries:
            rel = new_rel or old_rel
            snap = self.new if new_rel else self.old
            kind = classify(rel, snap)
            change = Change(rel, old_rel if old_rel != new_rel else None, STATUS.get(status, 'edit'), kind, None)
            new_info = self._owner(self.new, new_rel, kind) if new_rel else (None,) * 6
            old_info = self._owner(self.old, old_rel, kind) if old_rel else (None,) * 6
            change.owner = new_info[0] if new_rel else old_info[0]
            change.old_owner = old_info[0] if new_rel and old_rel else None
            if new_rel and change.owner is None and kind in ('external package', 'companion'):
                change.owner = self.old.member.get(new_rel)    # membership at the previous revision
            change.writer = new_info[1] or old_info[1]
            actor = new_info[2] or old_info[2]
            if actor:
                change.map, change.actor_label = actor.map, actor.label
                change.actor_class, change.actor_guid = actor.class_path, actor.guid
                change.location = [round(v, 3) for v in actor.location] if actor.location else None
            reason = new_info[5] or old_info[5]
            if kind == 'external package' and reason:
                change.note = f'header not read: {reason}'
            if change.change in ('edit', 'rename') and change.old_owner and change.owner \
                    and change.old_owner != change.owner:
                change.change = 'move'
            owners = {o for o in (change.owner, change.old_owner) if o}
            for owner in sorted(owners):
                alts = self._scopes_for(owner, self.new if owner == change.owner and new_rel else self.old)
                change.scopes.append(alts[0])
                self.requirements.append((rel, alts))
            if not owners:
                self.requirements.append((rel, ()))
            self.changes.append(change)
            if kind == 'external package' and new_rel:
                located, member = new_info[3], new_info[4]
                if located and member and located != member:
                    self.problems.append(Problem(
                        'REGION_MISMATCH', rel, f'actor {change.actor_label or change.actor_guid} stands in {located} '
                        f'but {member} lists it', f'move it from {member} to {located} in their actors.verified.json'))
        self._check_records(entries)
        self._check_record_changes()
        self._check_companions(entries)
        self._check_ownership()
        self._check_scopes()
        self._check_deletions(entries)
        return self

    # -- checks ----------------------------------------------------------------------------------------------
    def _record_rel(self, owner: str, snap: Snapshot) -> str | None:
        return snap.region_record.get(owner) if owner.startswith('region/') else snap.asset_record.get(owner)

    def _check_records(self, entries):
        for change in self.changes:
            if change.kind not in ('external package', 'companion', 'package', 'generated package', 'editor package'):
                continue
            for owner, snap, keeps in ((change.owner, self.new if change.change != 'delete' else self.old,
                                        change.change != 'delete'), (change.old_owner, self.old, False)):
                if not owner:
                    continue
                record = self._record_rel(owner, snap) or self._record_rel(owner, self.old)
                if record and record not in self.changed and not self._already_recorded(record, change.path, keeps):
                    self.problems.append(Problem(
                        'PACKAGE_WITHOUT_RECORD', change.path,
                        f'{change.change} of a package owned by {owner}, but {record} is unchanged',
                        f'update {owner}\'s verification record in the same change (save validation or import)'))
            if change.change == 'delete' or not change.owner:
                continue
            record = self._record_rel(change.owner, self.new)
            listed = self.new.verified.get(record, {}).get('files', {}) if record else {}
            if record in self.changed and record in self.new.verified:
                data = self.new.read(change.path)
                if change.path not in listed:
                    self.problems.append(Problem('RECORD_MISMATCH', change.path, f'{record} does not list it',
                                                 f'record its new hash in {record}'))
                elif data is not None and listed[change.path] != sha256(data):
                    self.problems.append(Problem('RECORD_MISMATCH', change.path,
                                                 f'{record} records other bytes than the changed package',
                                                 f'record its new hash in {record}'))
        for change in self.changes:
            if change.change == 'delete' and change.owner and change.kind != 'verification record':
                record = self._record_rel(change.owner, self.new)
                if record and change.path in self.new.verified.get(record, {}).get('files', {}):
                    self.problems.append(Problem('RECORD_MISMATCH', change.path,
                                                 f'deleted, but {record} still lists it', f'remove it from {record}'))

    def _already_recorded(self, record: str, rel: str, keeps: bool) -> bool:
        """An unchanged record that already describes the result: it lists rel's new bytes, or no longer lists it."""
        listed = self.new.verified.get(record, {}).get('files', {})
        if not keeps:
            return rel not in listed
        data = self.new.read(rel)
        return data is not None and listed.get(rel) == sha256(data)

    def _check_record_changes(self):
        """Every hash a changed verification record adds, changes or drops must match a changed file."""
        old_listed = {f: (rec, d) for rec, v in self.old.verified.items() for f, d in v['files'].items()}
        new_listed = {f: (rec, d) for rec, v in self.new.verified.items() for f, d in v['files'].items()}
        for record in sorted(r for r in self.changed if r.endswith('verified.json')):
            before = self.old.verified.get(record, {}).get('files', {})
            after = self.new.verified.get(record, {}).get('files', {})
            for rel in sorted(set(before) | set(after)):
                if before.get(rel) == after.get(rel) or rel in self.changed:
                    continue
                if PurePosixPath(rel).suffix in COMPANIONS and any(stem(rel) + e in self.changed for e in PACKAGES):
                    continue                            # the companion check reports it against its package
                if rel in after:
                    data = self.new.read(rel)
                    truthful = data is not None and sha256(data) == after[rel]
                    moved = old_listed.get(rel, (None, None))[1] == after[rel]
                    if not (truthful or (data is None and rel in self.new.unhydrated and moved)):
                        self.problems.append(Problem(
                            'RECORD_WITHOUT_PACKAGE', record, f'records new bytes for {rel}, which this change does '
                            'not touch', f'commit {rel} with its record, or restore the record'))
                elif rel in self.new.files and rel not in new_listed:
                    self.problems.append(Problem(
                        'RECORD_WITHOUT_PACKAGE', record, f'drops {rel}, which still exists and no record owns',
                        f'delete {rel} in the same change, or keep it recorded'))
        for change in self.changes:
            if change.kind != 'asset record' or change.change == 'delete':
                continue
            asset_id = self.new.asset_of_path(change.path)
            before = self.old.assets.get(self.old.asset_of_path(change.old_path or change.path) or '')
            after = self.new.assets.get(asset_id or '')
            if not after:
                continue
            old_outputs = {o.package for o in before.outputs} if before else set()
            for package in sorted({o.package for o in after.outputs} - old_outputs):
                rels = [r for r in self._package_rels(package) if r in self.new.files]
                if not rels:
                    self.problems.append(Problem('RECORD_WITHOUT_PACKAGE', change.path,
                                                 f'declares {package}, which has no committed package file',
                                                 'commit the package with its record'))
            for package in sorted(old_outputs - {o.package for o in after.outputs}):
                if any(r in self.new.files for r in self._package_rels(package)):
                    self.problems.append(Problem('RECORD_WITHOUT_PACKAGE', change.path,
                                                 f'no longer declares {package}, but its package is still committed',
                                                 'delete the package or give it another owner in the same change'))

    @staticmethod
    def _package_rels(package: str) -> list[str]:
        base = 'unreal/Content/' + package[len('/Game/'):]
        return [base + ext for ext in PACKAGES]

    def _check_companions(self, entries):
        stems = {}
        for _, a, b in entries:
            for rel, side in ((a, 'old'), (b, 'new')):
                if rel and PurePosixPath(rel).suffix in PACKAGES + COMPANIONS:
                    stems.setdefault(stem(rel), set()).add(rel)
        for s, rels in sorted(stems.items()):
            packages = [s + ext for ext in PACKAGES]
            package_changed = any(p in self.changed for p in packages)
            package_now = next((p for p in packages if p in self.new.files), None)
            for rel in sorted(rels):
                if PurePosixPath(rel).suffix in COMPANIONS and not package_changed:
                    self.problems.append(Problem('COMPANION', rel, 'companion changed without its package',
                                                 f'commit {PurePosixPath(s).name}.uasset with its companions'))
            if package_changed and package_now is None:
                for ext in COMPANIONS:
                    if s + ext in self.new.files:
                        self.problems.append(Problem('ORPHAN_COMPANION', s + ext, 'its package was deleted or renamed',
                                                     'delete or rename the companion with its package'))
            if package_now:
                owner = self.new.owner.get(package_now) or self.new.member.get(package_now)
                record = self._record_rel(owner, self.new) if owner else None
                listed = self.new.verified.get(record, {}).get('files', {}) if record else {}
                for ext in COMPANIONS:
                    if s + ext in listed and s + ext not in self.new.files:
                        self.problems.append(Problem('MISSING_COMPANION', s + ext,
                                                     f'{record} records it but it is not committed',
                                                     'commit the companion the editor wrote with its package'))

    def _check_ownership(self):
        for change in self.changes:
            if change.change == 'delete' or change.owner:
                continue
            if change.kind in ('external package', 'package', 'companion') or change.kind.endswith(' package'):
                what = 'no region lists or contains this actor' if change.kind == 'external package' else \
                    'no asset record declares this package'
                self.problems.append(Problem('UNOWNED', change.path, what,
                                             'add it to its owner record through the owning route, or delete it'))

    def _covered(self, rel: str, alts: tuple[str, ...]) -> bool:
        repo_rel = self.git.repo_path(rel)
        if any(covers(p, rel) or covers(p, repo_rel) for p in self.paths):
            return True
        return any(covers(scope, alt) for scope in self.scopes for alt in alts)

    def _check_scopes(self):
        if not self.scopes and not self.paths:
            return
        for rel, alts in self.requirements:
            if not self._covered(rel, alts):
                need = ' or '.join(alts) if alts else 'an explicit --paths claim'
                self.problems.append(Problem('OUT_OF_SCOPE', rel, f'needs {need}; declared: '
                                             f'{", ".join(self.scopes + self.paths) or "nothing"}',
                                             'claim the missing scope (and its owners) before publishing'))

    def _check_deletions(self, entries):
        gone = sorted({a for status, a, b in entries if a and (status == 'D' or (status == 'R' and a != b))
                       and a not in self.new.files and PurePosixPath(a).suffix in PACKAGES})
        for rel in gone:
            name = long_name(rel)
            if not name:
                continue
            pattern = re.compile(re.escape(name) + r'(?![A-Za-z0-9_/-])')
            for record, text in sorted(self.new.texts.items()):
                if pattern.search(text):
                    self.problems.append(Problem('REFERENCED_DELETION', rel, f'{name} is deleted but {record} '
                                                 'still names it', 'update or remove that reference in this change'))
            if rel.endswith('.umap'):
                folder = '/'.join(['unreal/Content', ACTOR_ROOTS[0], name[len('/Game/'):]]) + '/'
                left = sorted(f for f in self.new.files
                              if any(f.startswith(folder.replace(ACTOR_ROOTS[0], root)) for root in ACTOR_ROOTS))
                if left:
                    self.problems.append(Problem('ORPHAN_ACTOR', rel, f'map deleted but {len(left)} external '
                                                 f'package(s) remain, e.g. {left[0]}',
                                                 'delete or move the map\'s actors in the same change'))

    # -- output ----------------------------------------------------------------------------------------------
    def required_scopes(self) -> list[str]:
        return sorted({alts[0] for _, alts in self.requirements if alts})

    def to_json(self, base: str, head: str) -> dict:
        return {'ok': not self.problems, 'base': base, 'head': head,
                'declared': {'scopes': self.scopes, 'paths': self.paths},
                'required_scopes': self.required_scopes(),
                'unclaimed_paths': sorted(rel for rel, alts in self.requirements if not alts),
                'changes': [asdict(c) for c in self.changes], 'problems': [asdict(p) for p in self.problems]}

    def markdown(self, base: str, head: str) -> str:
        lines = [f'## Change set `{base}` → `{head}`', '',
                 f'**{"OK" if not self.problems else "FAIL"}**: {len(self.changes)} changed file(s), '
                 f'{len(self.problems)} problem(s).', '']
        declared = ', '.join(f'`{s}`' for s in self.scopes + self.paths) or 'none (scope check skipped)'
        lines += [f'- **Declared claims:** {declared}',
                  f'- **Required scopes:** {", ".join(f"`{s}`" for s in self.required_scopes()) or "none"}', '']
        if self.changes:
            lines += ['| Change | Kind | Path | Owner | Actor |', '| --- | --- | --- | --- | --- |']
            for c in self.changes:
                owner = c.owner or ('**unowned**' if c.kind.endswith('package') or c.kind == 'companion' else '-')
                if c.old_owner and c.old_owner != c.owner:
                    owner = f'{c.old_owner} → {owner}'
                path = f'{c.old_path} → {c.path}' if c.old_path else c.path
                actor = ''
                if c.map or c.actor_label or c.actor_guid:
                    actor = ' '.join(x for x in (c.actor_label and f'**{c.actor_label}**', c.actor_class and
                                                 f'`{c.actor_class.rsplit(".", 1)[-1]}`', c.actor_guid and
                                                 f'guid `{c.actor_guid}`', c.map and f'in `{c.map}`') if x)
                if c.note:
                    actor = f'{actor} ({c.note})'.strip()
                lines.append(f'| {c.change} | {c.kind} | `{path}` | {owner} | {actor} |')
            lines.append('')
        if self.problems:
            lines += ['### Problems', '']
            for p in self.problems:
                lines.append(f'- **{p.code}** `{p.subject}`: {p.detail}. → {p.action}')
            lines.append('')
        return '\n'.join(lines)


def resolve_range(git: Git, spec: str | None, staged: bool) -> tuple[str, str | None, str, str]:
    """(old rev, new rev or None for the index, old label, new label)."""
    if staged:
        if spec:
            raise ChangesetError('give either a range or --staged, not both')
        old = git.head_or_empty()
        return old, None, 'HEAD' if old != EMPTY_TREE else '(empty)', 'index'
    spec = spec or 'origin/main...HEAD'
    if '...' in spec:
        a, b = spec.split('...', 1)
        a, b = git.resolve(a or 'HEAD'), git.resolve(b or 'HEAD')
        old = git.run('merge-base', a, b).decode().strip()
        label = spec
    elif '..' in spec:
        a, b = spec.split('..', 1)
        old, b = git.resolve(a or 'HEAD'), git.resolve(b or 'HEAD')
        label = spec
    else:
        a, b = git.resolve(spec), git.resolve('HEAD')
        old = git.run('merge-base', a, b).decode().strip()
        label = f'{spec}...HEAD'
    if not old or not b:
        raise ChangesetError(f'cannot resolve range {spec}')
    base_label, head_label = label.split('..', 1)[0].rstrip('.'), label.rsplit('.', 1)[-1]
    return old, b, f'{base_label} ({old[:10]})', f'{head_label or "HEAD"} ({b[:10]})'


def report(game: Path = GAME, spec: str | None = None, *, staged: bool = False, scopes=(), paths=()):
    git = Git(game)
    old_rev, new_rev, base, head = resolve_range(git, spec, staged)
    entries = git.diff(old_rev, new_rev)
    old = Snapshot(git, old_rev, 'before')
    new = Snapshot(git, new_rev, 'after')
    result = Report(git, old, new, [s.strip() for s in scopes if s.strip()],
                    [p.strip() for p in paths if p.strip()]).build(entries)
    return result, base, head


def _split(values):
    return [part for value in values or [] for part in value.split(',') if part.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('range', nargs='?', help='Git range, default origin/main...HEAD')
    parser.add_argument('--staged', action='store_true', help='report the staged change against HEAD')
    parser.add_argument('--scopes', action='append', help='claimed scopes, comma-separated (repeatable)')
    parser.add_argument('--paths', action='append', help='claimed path prefixes, comma-separated (repeatable)')
    parser.add_argument('--json', action='store_true', help='machine-readable report')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result, base, head = report(args.game, args.range, staged=args.staged,
                                    scopes=_split(args.scopes), paths=_split(args.paths))
    except ChangesetError as error:
        print(f'changeset: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result.to_json(base, head), indent=2) if args.json else result.markdown(base, head))
    return 1 if result.problems else 0


if __name__ == '__main__':
    sys.exit(main())
