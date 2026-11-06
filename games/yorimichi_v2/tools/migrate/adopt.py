"""Adopt donor Unreal packages into V2, once, keeping their package paths (plan §6, P3 step 1; DECISIONS D02).

    uv run python games/yorimichi_v2/tools/migrate/adopt.py --donor-content DONOR/games/yorimichi/unreal/Content \
        --folder Japan --folder SkatePark ... [--exclude Japan/Audio] [--data] [--check-only]

Each top-level folder becomes one editor-owned record `assets/adopted/<folder>/asset.toml` (kind `adopted`) that
lists every package it brought; its `verified.json` is written by save validation, so from then on the folder is
ordinary editor-owned content: a later edit is claimed, saved in the editor and validated, and a finer record
may take packages over. Nothing is imported or resaved here: the bytes are the donor's.

It refuses to overwrite a different existing package another record owns, and reports, without copying past
it, every hard reference of an adopted package that resolves to no package in V2 (the closure must be complete)
and every package whose bytes name a home folder or private host (they need the editor scrub before commit).
`--data` copies the donor's staged runtime data (`Content/Data`) as committed runtime data.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
sys.path.insert(0, str(REPO / 'platform/studio'))
import records  # noqa: E402

PACKAGE_SUFFIXES = records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS
# Folders that are never adopted: generated world partitions of donor maps, per-user and runtime-data folders.
SKIP_PARTS = {'__ExternalActors__', '__ExternalObjects__', 'Developers', 'Collections'}
ENGINE_ROOTS = ('/Script/', '/Engine/', '/Temp/', '/Memory/')
SLUG = re.compile(r'[^a-z0-9]+')
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


def owners(game: Path) -> dict[str, str]:
    assets, _ = records.discover(game)
    return {o.package: a.id for a in assets for o in a.outputs}


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


def record_text(asset_id: str, folder: str, packages: list[str], license_text: str) -> str:
    lines = ['# Adopted once from the donor (tools/migrate/adopt.py); editor-owned from now on.', 'schema = 1',
             f'id = "{asset_id}"', 'kind = "adopted"', 'authority = "editor"', f'owner = "shared/{SLUG.sub("-", folder.lower()).strip("-")}"',
             f'provenance = "{PROVENANCE}"', f'license = "{license_text}"', '']
    for package in packages:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


def adopt(game: Path, content: Path, folders: list[str], excludes: list[str], license_text: str, *,
          check_only=False, echo=print) -> dict:
    target = game / 'unreal' / 'Content'
    owned = owners(game)
    plan, problems = {}, []
    for folder in folders:
        asset_id = 'adopted/' + SLUG.sub('-', folder.lower()).strip('-')
        files = donor_files(content, folder, excludes)
        packages = sorted({package_name(content, p) for p in files if p.suffix in records.PACKAGE_EXTENSIONS})
        for package in packages:
            if owned.get(package, asset_id) != asset_id:
                problems.append(f'{package} is already owned by {owned[package]}')
        plan[folder] = (asset_id, files, packages)
    adopted = {p for _, _, packages in plan.values() for p in packages} | set(owned)
    missing, private = {}, []
    for folder, (_, files, _) in plan.items():
        for path in files:
            if path.suffix not in records.PACKAGE_EXTENSIONS:
                continue
            for ref in references(path):
                if ref.startswith(ENGINE_ROOTS) or not ref.startswith('/Game/') or ref in adopted:
                    continue
                if any((target / ref[len('/Game/'):]).with_suffix(s).is_file() for s in records.PACKAGE_EXTENSIONS):
                    continue
                missing.setdefault(ref, package_name(content, path))
            if personal(path.read_bytes()):
                private.append(package_name(content, path))
    report = {'folders': {f: len(p[2]) for f, p in plan.items()}, 'missing_references': missing,
              'private_bytes': sorted(private), 'conflicts': problems}
    if problems:
        raise AdoptError('; '.join(problems[:5]))
    if check_only:
        return report
    for folder, (asset_id, files, packages) in plan.items():
        for path in files:
            dest = target / path.relative_to(content)
            if dest.is_file() and records.sha256_file(dest) == records.sha256_file(path):
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        record = game / 'assets' / asset_id / 'asset.toml'
        record.parent.mkdir(parents=True, exist_ok=True)
        text = record_text(asset_id, folder, packages, license_text)
        if not record.is_file() or record.read_text() != text:
            record.write_text(text)
        echo(f'adopted {folder}: {len(packages)} package(s) -> {asset_id}')
    return report


def copy_data(game: Path, content: Path, echo=print) -> int:
    source, dest = content / 'Data', game / 'unreal' / 'Content' / 'Data'
    if not source.is_dir():
        raise AdoptError(f'{source} holds no staged runtime data; build the donor first')
    copied = 0
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise AdoptError(f'{path} is a link; runtime data must be regular files')
        if not path.is_file():
            continue
        out = dest / path.relative_to(source)
        if out.is_file() and records.sha256_file(out) == records.sha256_file(path):
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        copied += 1
    echo(f'runtime data: {copied} file(s) copied')
    return copied


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--donor-content', type=Path, required=True)
    parser.add_argument('--folder', action='append', default=[], help='top-level /Game folder to adopt')
    parser.add_argument('--exclude', action='append', default=[], help='Content-relative folder to leave out')
    parser.add_argument('--license', default='owner-published (docs/DECISIONS.md D05 group 1)')
    parser.add_argument('--data', action='store_true', help='also copy the staged runtime data')
    parser.add_argument('--check-only', action='store_true', help='report closure and privacy problems only')
    args = parser.parse_args(argv)
    content = args.donor_content.resolve()
    try:
        report = adopt(GAME, content, args.folder, args.exclude, args.license, check_only=args.check_only)
        if args.data and not args.check_only:
            copy_data(GAME, content)
    except (AdoptError, records.RecordError) as error:
        print(f'adoption failed: {error}', file=sys.stderr)
        return 1
    for ref, user in sorted(report['missing_references'].items())[:40]:
        print(f'  missing reference {ref} (from {user})')
    print(f'{sum(report["folders"].values())} package(s); {len(report["missing_references"])} missing reference(s); '
          f'{len(report["private_bytes"])} package(s) with private bytes (scrub before commit)')
    return 1 if report['missing_references'] else 0


if __name__ == '__main__':
    sys.exit(main())
