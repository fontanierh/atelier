"""Adopt donor Unreal packages into V2, once, keeping their package paths (plan §6, P3 step 1; DECISIONS D02).

    uv run python games/yorimichi_v2/tools/migrate/adopt.py --donor-content DONOR/games/yorimichi/unreal/Content \
        --folder Japan --folder SkatePark ... [--exclude Japan/Audio] [--data] [--check-only]
    uv run python games/yorimichi_v2/tools/migrate/adopt.py --repartition [--check-only]

A folder's packages are split into ownership units (`partition`: by default one per folder two levels below /Game,
none over 200 packages) and each unit becomes one editor-owned record `assets/adopted/<path>/asset.toml` (kind
`adopted`, owner `shared/<path>`) listing its packages. Only ownership is split: every package keeps its donor path.
Its `verified.json` is written by save validation, so from then on a unit is ordinary editor-owned content: a later
edit claims only its unit, is saved in the editor and validated, and a finer record may take packages over. Nothing
is imported or resaved here: the bytes are the donor's. `--repartition` rewrites the existing adopted records (the
earlier one-record-per-folder ones) into the same units, with identical package membership and split verification
records, and is idempotent. Adoption and repartition must use the same `--depth` and `--cap`.

It writes only under a claim covering every written path, or as the D04 bootstrap writer. It never overwrites an
existing package with different bytes (an edited package belongs to its owner's route) and refuses a package
another record owns. It reports, without copying past it, every hard reference of an adopted package that resolves
to no package in V2 (the closure must be complete) and every package whose bytes name a home folder or private
host (they need the editor scrub before commit). Packages under a restricted root (`restricted.toml`, D05 group 2) are
copied like any other but Git ignores them; pin them afterwards (`tools/restricted/fetch.py pin`). A reference into a
restricted root is satisfied when this run adopts it or the lock pins it, since a checkout fetches rather than commits it.
`--data` copies the donor's staged runtime data (`Content/Data`) as committed runtime data and pins every file in
`runtime-data.lock.json`; `--pin-data` re-pins it after a deliberate, claimed change. The content check requires
exactly the pinned files, hydrated and with their bytes.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
sys.path.insert(0, str(REPO / 'platform/studio'))
import authority  # noqa: E402
import records  # noqa: E402

PACKAGE_SUFFIXES = records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS
# Folders that are never adopted: generated world partitions of donor maps, per-user and runtime-data folders.
SKIP_PARTS = {'__ExternalActors__', '__ExternalObjects__', 'Developers', 'Collections'}
ENGINE_ROOTS = ('/Script/', '/Engine/', '/Temp/', '/Memory/')
SLUG = re.compile(r'[^a-z0-9]+')
DEPTH = 2       # /Game/<top>/<sub>: the default ownership unit
CAP = 200       # most packages one adopted record lists
LOOSE = 'loose_files'   # a split folder's own packages; no slug has '_', so it never collides with a subfolder
GROUPS = GAME / 'assets' / 'adopted' / 'groups.toml'   # logical ownership groups inside adopted folders (D08)
PROVENANCE = 'donor build of games/yorimichi at the V2 source baseline (docs/DECISIONS.md D01, D02)'


class AdoptError(RuntimeError):
    pass


def package_name(content: Path, path: Path) -> str:
    return '/Game/' + path.relative_to(content).with_suffix('').as_posix()


def donor_files(content: Path, folder: str, excludes: list[str]) -> list[Path]:
    root = content / folder
    if not root.is_dir():
        raise AdoptError(f'{root} is not a donor Content folder')
    found = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(content).as_posix()
        if not path.is_file() or path.suffix not in PACKAGE_SUFFIXES or SKIP_PARTS & set(path.parts):
            continue
        if any(rel == e or rel.startswith(e.rstrip('/') + '/') for e in excludes):
            continue
        found.append(path)
    return found


def personal(data: bytes) -> list[str]:
    from atelier.cli import PERSONAL
    texts = [data.decode('latin-1'), data.decode('utf-16-le', errors='ignore'), data[1:].decode('utf-16-le', errors='ignore')]
    return [what for pattern, what, _ in PERSONAL[:2] if any(pattern.search(t) for t in texts)]


def references(path: Path) -> list[str]:
    from atelier import unreal_package_summary as summary
    try:
        return summary.read(path).imported_packages
    except Exception as error:  # noqa: BLE001 — an unreadable header is reported, never guessed
        raise AdoptError(f'{path}: unreadable package header ({error})') from None


def slug(segment: str) -> str:
    name = SLUG.sub('-', segment.lower()).strip('-')
    if not name:
        raise AdoptError(f'folder {segment!r} has no record-safe name')
    return name


def load_groups(path: Path = GROUPS) -> dict[str, tuple[re.Pattern, dict[str, str]]]:
    """Folder -> (the regex whose first group names a package's logical group, readable names for some groups), from
    `assets/adopted/groups.toml`."""
    if not path.is_file():
        return {}
    rules = {}
    for rule in tomllib.loads(path.read_text()).get('group', []):
        folder, key = rule.get('folder'), rule.get('key')
        if not isinstance(folder, str) or not folder.startswith('/Game/') or not isinstance(key, str):
            raise AdoptError(f'{path.name}: each [[group]] needs folder = "/Game/..." and key = "<regex>"')
        pattern = re.compile(key)
        if pattern.groups < 1:
            raise AdoptError(f'{path.name}: the key of {folder} needs a capture group (the group name)')
        names = rule.get('names', {})
        if not isinstance(names, dict) or not all(isinstance(v, str) for v in names.values()):
            raise AdoptError(f'{path.name}: the names of {folder} must map groups to record names')
        if folder.rstrip('/') in rules:
            raise AdoptError(f'{path.name}: {folder} has two rules')
        rules[folder.rstrip('/')] = (pattern, names)
    return rules


def partition(packages, root: str, *, depth: int = DEPTH, cap: int = CAP,
              groups: dict[str, tuple[re.Pattern, dict[str, str]]] | None = None) -> dict[str, tuple[str, str, list[str]]]:
    """Ownership units of packages under the Content folder `root`: record ID -> (owner scope, what it holds, packages).

    A folder is one unit when it is at least `depth` segments below /Game or has no subfolders, and holds at most
    `cap` packages. Otherwise each subfolder is partitioned in turn and the folder's own packages form `loose_files`
    (sorted chunks `loose_files_01`, ... of `cap` when over it). IDs (`adopted/<slugs>`) and owners (`shared/<slugs>`)
    follow the slugged path, so units are prefix-free and a claim on one never covers another. The same packages,
    depth and cap always give the same units; two folders whose names slug alike are refused, never merged.

    A folder with a `groups` rule always splits its own packages by logical group instead: the rule's first capture
    group on the package name names the unit (`adopted/<folder slugs>/<group slug>`, or the rule's readable name for
    that group); a package it does not match is a unit of its own, named after the package. A group over `cap` splits into sorted chunks `<group>_01`, ...
    """
    if cap < 1 or depth < 1:
        raise AdoptError('partition needs depth >= 1 and cap >= 1')
    units: dict[str, tuple[str, str, list[str]]] = {}

    def add(names, about, members):
        units['adopted/' + '/'.join(names)] = ('shared/' + '/'.join(names), about, members)

    def split(parts, names, members):
        folder = '/Game/' + '/'.join(parts)
        here, below = [], {}
        for package in members:
            rest = package[len(folder) + 1:].split('/')
            if len(rest) == 1:
                here.append(package)
            else:
                below.setdefault(rest[0], []).append(package)
        rule = (groups or {}).get(folder)
        if rule is None and (len(parts) >= depth or not below) and len(members) <= cap:
            return add(names, folder, members)
        seen = {}
        if rule is None:
            chunks = [here[i:i + cap] for i in range(0, len(here), cap)]
            for i, chunk in enumerate(chunks, 1):
                name, part = (LOOSE, '') if len(chunks) == 1 else (f'{LOOSE}_{i:02d}', f' (part {i} of {len(chunks)})')
                add(names + (name,), f'packages directly in {folder}{part}', chunk)
        else:
            pattern, readable = rule
            by_group: dict[str, list[str]] = {}
            for package in here:
                leaf = package.rsplit('/', 1)[1]
                match = pattern.match(leaf)
                by_group.setdefault(match.group(1) if match and match.group(1) else leaf, []).append(package)
            for group in sorted(by_group):
                name = slug(readable.get(group, group))
                if name in seen:
                    raise AdoptError(f'{folder}: groups {group} and {seen[name]} would share the record name {name}')
                seen[name] = group
                chunks = [by_group[group][i:i + cap] for i in range(0, len(by_group[group]), cap)]
                for i, chunk in enumerate(chunks, 1):
                    unit, part = (name, '') if len(chunks) == 1 else (f'{name}_{i:02d}', f' (part {i} of {len(chunks)})')
                    add(names + (unit,), f'{group} in {folder}{part}', chunk)
        for segment in sorted(below):
            name = slug(segment)
            if name in seen:
                raise AdoptError(f'{folder}/{segment} and {folder}/{seen[name]} would share the record name {name}')
            seen[name] = segment
            split(parts + (segment,), names + (name,), below[segment])

    parts = tuple(root.strip('/').split('/'))
    prefix = '/Game/' + '/'.join(parts) + '/'
    members = sorted(set(packages))
    outside = [p for p in members if not p.startswith(prefix)]
    if outside:
        raise AdoptError(f'{outside[0]} is not under {prefix}')
    if members:
        split(parts, tuple(slug(p) for p in parts), members)
    return units


def record_text(asset_id: str, owner: str, about: str, packages: list[str], license_text: str,
                provenance: str = PROVENANCE) -> str:
    lines = ['# Adopted once from the donor (tools/migrate/adopt.py); editor-owned from now on.',
             f'# Ownership unit: {about}', 'schema = 1', f'id = "{asset_id}"', 'kind = "adopted"',
             'authority = "editor"', f'owner = "{owner}"', f'provenance = "{provenance}"', f'license = "{license_text}"',
             '']
    for package in packages:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


def _authorize(game: Path, paths: list[Path], claim: str | None, what: str, scopes) -> None:
    try:
        authority.authorize([f'games/yorimichi_v2/{p.relative_to(game).as_posix()}' for p in paths], claim, what,
                            scopes=scopes)
    except authority.Unauthorized as error:
        raise AdoptError(str(error)) from None


def adopt(game: Path, content: Path, folders: list[str], excludes: list[str], license_text: str, *,
          check_only=False, claim: str | None = None, depth: int = DEPTH, cap: int = CAP, echo=print) -> dict:
    target = game / 'unreal' / 'Content'
    assets, _ = records.discover(game)
    owned = {o.package: a.id for a in assets for o in a.outputs}
    adopted_ids = {a.id for a in assets if a.kind == 'adopted'}
    restricted = records.load_restricted(game)
    pinned = records.load_lock(restricted)
    found, plan, problems = {}, {}, []
    rules = load_groups(game / GROUPS.relative_to(GAME))
    for folder in folders:
        files = donor_files(content, folder, excludes)
        packages = sorted({package_name(content, p) for p in files if p.suffix in records.PACKAGE_EXTENSIONS})
        found[folder] = (files, packages)
        for asset_id, unit in partition(packages, folder, depth=depth, cap=cap, groups=rules).items():
            if asset_id in plan:
                raise AdoptError(f'{asset_id} would come from two --folder arguments; name each folder once')
            plan[asset_id] = (folder, *unit)
            for package in unit[2]:
                if owned.get(package, asset_id) != asset_id:
                    hint = ' (run adopt.py --repartition first)' if owned[package] in adopted_ids else ''
                    problems.append(f'{package} is already owned by {owned[package]}{hint}')
    adopted = {p for _, packages in found.values() for p in packages} | set(owned)
    missing, private = {}, []
    for folder, (files, _) in found.items():
        for path in files:
            if path.suffix not in records.PACKAGE_EXTENSIONS:
                continue
            for ref in references(path):
                if ref.startswith(ENGINE_ROOTS) or not ref.startswith('/Game/') or ref in adopted:
                    continue
                if any((target / ref[len('/Game/'):]).with_suffix(s).is_file() for s in records.PACKAGE_EXTENSIONS):
                    continue
                if restricted.covers_package(ref) and any(ref[len('/Game/'):] + s in pinned
                                                          for s in records.PACKAGE_EXTENSIONS):
                    continue   # fetched, not committed; one adopted in this run is already in `adopted`
                missing.setdefault(ref, package_name(content, path))
            if personal(path.read_bytes()):
                private.append(package_name(content, path))
    report = {'folders': {f: len(packages) for f, (_, packages) in found.items()},
              'records': {a: len(u[3]) for a, u in sorted(plan.items())}, 'missing_references': missing,
              'private_bytes': sorted(private), 'conflicts': problems}
    # Adoption only ever adds the donor's bytes: an existing package that differs was edited (or adopted from
    # another donor) and belongs to its owner's route, never to a rerun of adoption.
    copies = []
    for files, _ in found.values():
        for path in files:
            dest = target / path.relative_to(content)
            if not dest.is_file():
                copies.append((path, dest))
            elif records.sha256_file(dest) != records.sha256_file(path):
                problems.append(f'{dest.relative_to(game).as_posix()} exists with different bytes; adoption never '
                                'overwrites (change it through its owner route)')
    report['conflicts'] = problems
    if problems:
        raise AdoptError('; '.join(problems[:5]))
    if check_only:
        return report
    writes = [dest for _, dest in copies] + [game / 'assets' / a / 'asset.toml' for a in plan]
    _authorize(game, writes, claim, 'adoption', {authority.scope_of(a) for a in plan})
    for path, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    for asset_id, (_, owner, about, packages) in sorted(plan.items()):
        record = game / 'assets' / asset_id / 'asset.toml'
        record.parent.mkdir(parents=True, exist_ok=True)
        text = record_text(asset_id, owner, about, packages, license_text)
        if not record.is_file() or record.read_text() != text:
            record.write_text(text)
    for folder, (_, packages) in found.items():
        units = sum(1 for unit in plan.values() if unit[0] == folder)
        echo(f'adopted {folder}: {len(packages)} package(s) in {units} record(s) under assets/adopted/')
    return report


def _json_text(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + '\n'     # records.write_json's canonical form


def repartition(game: Path, *, depth: int = DEPTH, cap: int = CAP, check_only=False, claim: str | None = None,
                echo=print) -> dict:
    """Rewrite every adopted record into the `partition` units, keeping the exact package membership.

    Each unit takes license and provenance from the record(s) its packages came from, and its share of their
    `verified.json` (same engine and kind, files of its own packages only); records no unit keeps are deleted.
    It refuses, writing nothing, when a package is listed twice or also owned by a non-adopted record, when the new
    units would lose or repeat a package or a verified file, or when one unit would merge records that disagree.
    The writes and deletions pass `authority.authorize` like adoption's. A second run finds nothing to change. An
    interrupted run can leave a package listed twice: restore the records (`git checkout -- assets/adopted`), rerun.
    """
    assets, _ = records.discover(game)
    adopted = [a for a in assets if a.kind == 'adopted']
    others = {o.package: a.id for a in assets if a.kind != 'adopted' for o in a.outputs}
    source, problems = {}, []
    for asset in adopted:
        for output in asset.outputs:
            if output.package in source or output.package in others:
                first = source[output.package].id if output.package in source else others[output.package]
                problems.append(f'{output.package} is owned by both {first} and {asset.id}')
            source[output.package] = asset
    if problems:
        raise AdoptError('; '.join(problems[:5]))
    tops: dict[str, list[str]] = {}
    for package in source:
        tops.setdefault(package.split('/')[2], []).append(package)
    units = {}
    rules = load_groups(game / GROUPS.relative_to(GAME))
    for top in sorted(tops):
        units.update(partition(tops[top], top, depth=depth, cap=cap, groups=rules))
    members = [p for _, _, packages in units.values() for p in packages]
    if len(members) != len(set(members)) or set(members) != set(source):
        raise AdoptError(f'repartition would lose {len(set(source) - set(members))} and double-own '
                         f'{len(members) - len(set(members))} package(s); nothing written')
    verified = {a.id: records.load_verified(a.verified) for a in adopted if a.verified.is_file()}
    writes: dict[Path, tuple[str, str]] = {}      # path -> (unit ID, text)
    placed: set[tuple[str, str]] = set()           # (source record, verified file) carried into a unit
    for unit_id, (owner, about, packages) in sorted(units.items()):
        from_ids = {source[p].id for p in packages}
        sources = [s for s in adopted if s.id in from_ids]
        terms = {(s.license or '', s.provenance or PROVENANCE) for s in sources}
        if len(terms) > 1:
            problems.append(f'{unit_id} would merge records with different license or provenance: '
                            f'{", ".join(s.id for s in sources)}')
            continue
        license_text, provenance = terms.pop()
        folder = game / 'assets' / unit_id
        writes[folder / 'asset.toml'] = (unit_id, record_text(unit_id, owner, about, packages, license_text, provenance))
        checked = [s.id for s in sources if s.id in verified]
        if not checked:
            if (folder / 'verified.json').is_file():
                problems.append(f'{unit_id}: a verified.json is already there but its packages are unvalidated')
            continue
        if len(checked) != len(sources):
            problems.append(f'{unit_id} would merge validated and unvalidated records '
                            f'({", ".join(s.id for s in sources)}); save-validate them first')
            continue
        bases = {_json_text({k: v for k, v in verified[s].items() if k not in ('asset', 'files')}) for s in checked}
        if len(bases) > 1:
            problems.append(f'{unit_id} would merge verification records from different engines or kinds')
            continue
        stems = {'unreal/Content/' + p[len('/Game/'):] for p in packages}    # verified.json is game-relative
        files = {}
        for s in checked:
            for rel, digest in verified[s]['files'].items():
                if rel.rsplit('.', 1)[0] in stems:
                    files[rel] = digest
                    placed.add((s, rel))
        body = {**json.loads(bases.pop()), 'asset': unit_id, 'files': files}
        writes[folder / 'verified.json'] = (unit_id, _json_text(body))
    lost = sorted(f'{s}:{rel}' for s, v in verified.items() for rel in v['files'] if (s, rel) not in placed)
    if lost:
        problems.append(f'repartition would drop {len(lost)} verified file(s) no unit owns, e.g. {lost[0]}')
    if problems:
        raise AdoptError('; '.join(problems[:5]))
    deletes = [(a, path) for a in adopted if a.id not in units for path in (a.record, a.verified) if path.is_file()]
    changed = {p: w for p, w in writes.items() if not p.is_file() or p.read_text() != w[1]}
    report = {'records': {u: len(units[u][2]) for u in sorted(units)}, 'packages': len(source),
              'write': sorted(p.relative_to(game).as_posix() for p in changed),
              'delete': sorted(p.relative_to(game).as_posix() for _, p in deletes)}
    if check_only or not (changed or deletes):
        return report
    scopes = {authority.scope_of(u) for u, _ in changed.values()} | {authority.asset_scope(a) for a, _ in deletes}
    _authorize(game, sorted(changed) + [p for _, p in deletes], claim, 'adoption repartition', scopes)
    for path, (_, text) in sorted(changed.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(text)
        tmp.replace(path)
    for _, path in deletes:
        path.unlink()
        folder = path.parent
        while folder != game / 'assets' and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    echo(f'repartitioned {len(source)} adopted package(s) into {len(units)} record(s): '
         f'{len(changed)} file(s) written, {len(deletes)} deleted')
    return report




DATA_SCOPE = 'shared/runtime-data'   # the claim scope of unreal/Content/Data and runtime-data.lock.json


def copy_data(game: Path, content: Path, claim: str | None = None, echo=print) -> int:
    """Copy the donor's staged runtime data (authorized like adoption), then pin every data file."""
    source, dest = content / 'Data', game / 'unreal' / 'Content' / 'Data'
    if not source.is_dir():
        raise AdoptError(f'{source} holds no staged runtime data; build the donor first')
    copies = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise AdoptError(f'{path} is a link; runtime data must be regular files')
        if not path.is_file():
            continue
        out = dest / path.relative_to(source)
        if not (out.is_file() and records.sha256_file(out) == records.sha256_file(path)):
            copies.append((path, out))
    _authorize(game, [out for _, out in copies], claim, 'runtime data adoption', {DATA_SCOPE})
    for path, out in copies:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
    echo(f'runtime data: {len(copies)} file(s) copied, {records.write_data_lock(game)} pinned')
    return len(copies)


def pin_data(game: Path, claim: str | None = None, echo=print) -> int:
    """Pin the runtime data as it is now, after a deliberate change: the changed, added or removed files must be
    covered by the claim (or the D04 bootstrap writer). Returns how many files changed."""
    lock = records.load_data_lock(game) or {}
    present = records.data_files(game)
    content = game / 'unreal' / 'Content'
    changed = sorted({rel for rel in present if lock.get(rel) != records.sha256_file(content / rel)} |
                     {rel for rel in lock if rel not in present})
    if not changed and records.load_data_lock(game) is not None:
        echo('runtime data: unchanged')
        return 0
    _authorize(game, [content / rel for rel in changed], claim, 'runtime data pin', {DATA_SCOPE})
    echo(f'runtime data: {len(changed)} file(s) changed, {records.write_data_lock(game)} pinned')
    return len(changed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--donor-content', type=Path)
    parser.add_argument('--folder', action='append', default=[], help='/Game folder to adopt, e.g. Japan')
    parser.add_argument('--exclude', action='append', default=[], help='Content-relative folder to leave out')
    parser.add_argument('--license', default='owner-published (docs/DECISIONS.md D05 group 1)')
    parser.add_argument('--data', action='store_true', help='also copy the staged runtime data, and pin it')
    parser.add_argument('--pin-data', action='store_true',
                        help='pin unreal/Content/Data as it is now in runtime-data.lock.json (no donor needed)')
    parser.add_argument('--check-only', action='store_true', help='report closure and privacy problems only')
    parser.add_argument('--claim', help='claims task covering every written path (else the D04 bootstrap writer)')
    parser.add_argument('--repartition', action='store_true',
                        help='rewrite existing adopted records into ownership units (no donor needed)')
    parser.add_argument('--depth', type=int, default=DEPTH, help='folder depth below /Game of an ownership unit')
    parser.add_argument('--cap', type=int, default=CAP, help='most packages in one adopted record')
    args = parser.parse_args(argv)
    if args.pin_data:
        try:
            pin_data(GAME, claim=args.claim)
        except (AdoptError, records.RecordError) as error:
            print(f'data pin failed: {error}', file=sys.stderr)
            return 1
        return 0
    if args.repartition:
        try:
            report = repartition(GAME, depth=args.depth, cap=args.cap, check_only=args.check_only, claim=args.claim)
        except (AdoptError, records.RecordError) as error:
            print(f'repartition failed: {error}', file=sys.stderr)
            return 1
        print(f'{report["packages"]} package(s) in {len(report["records"])} record(s); '
              f'{len(report["write"])} file(s) to write, {len(report["delete"])} to delete')
        return 0
    if args.donor_content is None:
        parser.error('--donor-content is required unless --repartition')
    content = args.donor_content.resolve()
    try:
        report = adopt(GAME, content, args.folder, args.exclude, args.license, check_only=args.check_only,
                       claim=args.claim, depth=args.depth, cap=args.cap)
        if args.data and not args.check_only:
            copy_data(GAME, content, claim=args.claim)
    except (AdoptError, records.RecordError) as error:
        print(f'adoption failed: {error}', file=sys.stderr)
        return 1
    for ref, user in sorted(report['missing_references'].items())[:40]:
        print(f'  missing reference {ref} (from {user})')
    print(f'{sum(report["folders"].values())} package(s) in {len(report["records"])} record(s); '
          f'{len(report["missing_references"])} missing reference(s); '
          f'{len(report["private_bytes"])} package(s) with private bytes (scrub before commit)')
    return 1 if report['missing_references'] else 0


if __name__ == '__main__':
    sys.exit(main())
