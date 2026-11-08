"""Shared writer for the transport units maps (gondola_units.py, ferry_units.py, train_units.py).

Each system's adopted records (assets/adopted/<system>/...) hold its meshes in a few big records. A script names the
unit of every package and the originals of each unit; this module checks the packages, adds the generator unit's
sources and writes `assets/adopted/<system>/units.json` in the format adopt.py's `Units` reads (the Brine Cove
convention: the unit `materials` carries the generator of every package of the system and every other unit
references it; a unit's own `sources` are the generator files that make only it). Paths are repository paths.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402

DONOR = REPO / 'games' / 'yorimichi'
GENERATOR_UNIT = 'materials'


def donor_files(*paths: str) -> list[str]:
    """Donor files (a file, or every file under a folder) as repository paths, sorted."""
    found = set()
    for path in paths:
        target = DONOR / path
        files = [target] if target.is_file() else [p for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        if not files:
            raise ValueError(f'donor path {path} has no files')
        found.update(f'games/yorimichi/{p.relative_to(DONOR).as_posix()}' for p in files)
    return sorted(found)


def build(game: Path, system: str, root: str, unit_of, about: dict, own: dict, generator: list[str],
          title: str) -> dict:
    """packages -> unit via `unit_of(mesh name)`; `own` maps a unit to its own source files; `about` to its text."""
    packages = sorted(o.package for a in records.discover(game)[0] if a.id.startswith(f'adopted/{system}/')
                      for o in a.outputs)
    if any(not p.startswith(root) for p in packages):
        raise ValueError(f'an adopted/{system} record owns a package outside {root}')
    unit = {p: unit_of(p.rsplit('/', 1)[1], p) for p in packages}
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        text = about.get(name, f'{title} {name} ({counts[name]} package(s))')
        info[name] = {'about': text}
        if name == GENERATOR_UNIT:
            info[name]['sources'] = sorted(set(generator) | set(own.get(name, [])))
        else:
            info[name]['sources'] = sorted(own.get(name, []))
            info[name]['references'] = [f'adopted/{system}/{GENERATOR_UNIT}']
    stray = sorted(set(own) - set(counts))
    if stray:
        raise ValueError(f'sources for unknown units {stray}')
    return {'about': f'{title} editing units for tools/migrate/adopt.py (written by tools/migrate/{system}_units.py)',
            'units': info, 'packages': unit}


def main(system: str, make) -> int:
    parser = argparse.ArgumentParser(description=f'Write {system}\'s editing units map.')
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    args = parser.parse_args()
    out = GAME / 'assets' / 'adopted' / system / 'units.json'
    text = json.dumps(make(GAME), indent=1) + '\n'
    if args.check:
        same = out.is_file() and out.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    out.write_text(text)
    counts = collections.Counter(json.loads(text)['packages'].values())
    print(f'{out.relative_to(REPO)}: {sum(counts.values())} packages in {len(counts)} units; largest '
          + ', '.join(f'{u} {n}' for u, n in counts.most_common(4)))
    return 0
