"""Shared helpers for the `<region>_units.py` writers (units maps for tools/migrate/adopt.py).

Each writer builds {"about", "units": {name: {"about", "sources", "references"}}, "packages": {package: unit}} from the
adopted records of one folder and the donor game's committed sources, and writes or checks `units.json`.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402

DONOR = REPO / 'games' / 'yorimichi'


def kebab(text: str) -> str:
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|_', '-', text).lower().strip('-')


def packages_of(game: Path, prefix: str, folder: str) -> list[str]:
    """Every package of the adopted records `adopted/<prefix>...` that lies under `folder`."""
    found = sorted(o.package for a in records.discover(game)[0] if a.id.startswith(prefix) for o in a.outputs)
    if not found or any(not p.startswith(folder + '/') for p in found):
        raise ValueError(f'the {prefix} records must own packages under {folder} only')
    return found


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def donor(path: str) -> Path:
    return DONOR / path


def files_in(path: Path) -> list[str]:
    """Repository paths of a donor file, or of every file under a donor folder."""
    if path.is_file():
        return [rel(path)]
    return [rel(p) for p in sorted(path.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
            and not p.name.startswith('.')]


def code_closure(roots: list[str], search: tuple[str, ...] = ('world', 'world/regions')) -> list[str]:
    """The donor files `roots` (donor-relative) and the donor modules they import (the donor build's own scanner)."""
    sys.path.insert(0, str(REPO / 'platform' / 'studio'))
    from atelier.build_inputs import local_imports
    found: set[Path] = set()
    for root in roots:
        path = DONOR / root
        if not path.exists():
            raise ValueError(f'{root} is missing from the donor')
        for file in ([p for p in path.rglob('*') if p.is_file()] if path.is_dir() else [path]):
            found.add(file)
            if file.suffix == '.py':
                found |= {Path(p) for p in local_imports(file, tuple(DONOR / s for s in search))}
    return sorted(rel(p) for p in found if DONOR in p.parents and '__pycache__' not in p.parts)


def finish(result: dict, out: Path, argv, doc: str) -> int:
    parser = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    args = parser.parse_args(argv)
    for name, unit in result['units'].items():
        for source in unit.get('sources', []):
            if not (REPO / source).is_file():
                raise ValueError(f'{name}: source {source} is missing')
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        same = out.is_file() and out.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    out.write_text(text)
    counts = collections.Counter(result['packages'].values())
    print(f'{rel(out)}: {sum(counts.values())} packages in {len(counts)} units; largest '
          + ', '.join(f'{u} {n}' for u, n in counts.most_common(4)))
    return 0
