"""Write the park objects of w11-megapark and w12-craterpark into their objects.toml: one object per adopted unit.

    uv run python games/yorimichi_v2/tools/migrate/parks.py [--megapark-data PARK.json] [--craterpark-data PARK.json] [--check]

A park's render and collision meshes (unreal/Content/Data/<park>/park.json, ASuperUltraMegaPark::Spawn reads them) are
saved as one object per adopted unit that owns them: Mega Park's 16 units (assets/adopted/megapark/units.json: 15 stream
cells and the seam) and Crater Park's 58 (the adopted records of assets/adopted/craterpark, each owning its meshes, with
craterpark_ownership.json checked against them). Rails, zones, spawn points and trees are not objects and stay out.

The entries are a pure function of those files: running it again writes the same text. Each render and collision name of
a park file must belong to exactly one unit, or nothing is written. `--check` writes nothing and exits 1 when the
objects.toml files would change. Pass the park files explicitly when the worktree holds them only as Git LFS pointers.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]

MEGA_MESHES = '/Game/MegaPark/Meshes/'
CRATER_MESHES = '/Game/CraterPark/Meshes/'
PACKAGE = re.compile(r'^package = "(/Game/CraterPark/Meshes/[^"]+)"', re.M)
STREAM_CELL = re.compile(r'^cell-x(\d+)-zm(\d+)$')
CRATER_PIECE = re.compile(r'^(p\d+)-(.+)$')
CRATER_FLOOR = re.compile(r'^crater-floor-(\d+)-(\d+)$')
REGIONS = {'megapark': 'w11-megapark', 'craterpark': 'w12-craterpark'}


class ConvertError(RuntimeError):
    pass


def park_pieces(park: dict) -> list[str]:
    """Every render and collision mesh name of a park file, in the file's order; each name must be listed once."""
    names = [entry['name'] for kind in ('render', 'collision') for entry in park[kind]]
    if len(names) != len(set(names)):
        raise ConvertError('a park file lists a mesh twice')
    return names


def mega_owners(units: dict) -> dict[str, str]:
    """{mesh name: unit} from units.json's packages: each Mega Park mesh package names the unit that owns it."""
    owners = {}
    for package, unit in units['packages'].items():
        if package.startswith(MEGA_MESHES):
            owners[package[len(MEGA_MESHES):]] = unit
    return owners


def crater_owners(adopted: Path) -> dict[str, str]:
    """{mesh name: record directory} from the package lines of each adopted Crater Park record: every mesh is one
    record's output."""
    owners = {}
    for record in sorted(adopted.glob('*/asset.toml')):
        for package in PACKAGE.findall(record.read_text()):
            name = package[len(CRATER_MESHES):]
            if name in owners:
                raise ConvertError(f'{name} is the output of two records: {owners[name]} and {record.parent.name}')
            owners[name] = record.parent.name
    return owners


def check_ownership(ownership: dict, owners: dict[str, str], park: dict) -> None:
    """craterpark_ownership.json names each mesh's feature; the record that owns it must be that feature's record."""
    for kind in ('render', 'collision'):
        for entry in park[kind]:
            name = entry['name']
            if kind == 'render':
                feature = ownership['render'][name]
            else:
                feature = ownership['collision'][name]['owner']
            record = owners[name]
            if feature == 'mixed':
                ok = record == 'collision-mixed'
            elif feature == 'crater_floor':
                ok = record.startswith('crater-floor-')
            else:
                ok = record == feature or record.startswith(feature + '-')
            if not ok:
                raise ConvertError(f'{name}: the ownership file says {feature}, its record is {record}')


def mega_object(unit: str, pieces: list[str]) -> dict:
    cell = STREAM_CELL.match(unit)
    if cell:
        about = f'the Mega Park section at stream cell ({int(cell[1])}, -{int(cell[2])})'
    elif unit == 'seam':
        about = 'the Mega Park seam meshes joining the park to the zeppelin footbridge'
    else:
        raise ConvertError(f'{unit}: no Mega Park unit this converter knows')
    return {'id': f'object/megapark/{unit}', 'park': pieces, 'model': f'adopted/megapark/{unit}', 'about': about}


def crater_object(unit: str, pieces: list[str]) -> dict:
    piece = CRATER_PIECE.match(unit)
    floor = CRATER_FLOOR.match(unit)
    if floor:
        about = f'the Crater Park crater floor, block {floor[1]}-{floor[2]}'
    elif piece:
        about = f'the Crater Park piece {piece[1]} ({piece[2]})'
    elif unit == 'collision-mixed':
        about = 'the Crater Park collision pieces that several features share'
    else:
        raise ConvertError(f'{unit}: no Crater Park unit this converter knows')
    return {'id': f'object/craterpark/{unit}', 'park': pieces, 'model': f'adopted/craterpark/{unit}', 'about': about}


def units_of(park: dict, owners: dict[str, str], make) -> list[dict]:
    """The park's objects, one per unit, sorted by ID. Every piece must have an owner, and the unit's record must exist."""
    per_unit: dict[str, list[str]] = {}
    for name in park_pieces(park):
        if name not in owners:
            raise ConvertError(f'{name} is owned by no unit')
        per_unit.setdefault(owners[name], []).append(name)
    return sorted((make(unit, pieces) for unit, pieces in per_unit.items()), key=lambda entry: entry['id'])


def check_records(game: Path, objects: list[dict]) -> None:
    for entry in objects:
        if not (game / 'assets' / entry['model'] / 'asset.toml').is_file():
            raise ConvertError(f'{entry["id"]}: its model record {entry["model"]} is missing')


def toml_entry(entry: dict) -> str:
    """One [[objects]] entry, the park names four to a line (a unit of Crater Park has up to 65)."""
    lines = ['[[objects]]', f'id = "{entry["id"]}"', 'park = [']
    names = entry['park']
    for start in range(0, len(names), 4):
        lines.append('    ' + ', '.join(f'"{name}"' for name in names[start:start + 4]) + ',')
    lines += [']', f'model = "{entry["model"]}"', f'about = "{entry["about"]}"']
    return '\n'.join(lines) + '\n'


def merge(text: str, data: str, entries: list[dict]) -> str:
    """The objects.toml text with its `data` line set and its park entries replaced; every other entry, and the header
    comments, stay as they are."""
    head, *blocks = re.split(r'(?m)^(?=\[\[objects\]\])', text)
    head = re.sub(r'(?m)^data = ".*"$', f'data = "{data}"', head).rstrip('\n') + '\n'
    kept = [block.strip('\n') + '\n' for block in blocks if not re.search(r'(?m)^park = ', block)]
    return head + '\n' + '\n'.join(kept + [toml_entry(entry) for entry in entries])


def build(game: Path, megapark_park: dict, craterpark_park: dict) -> dict[str, list[dict]]:
    """{park tag: its objects} for both parks, from the committed unit records and the park files."""
    units = json.loads((game / 'assets/adopted/megapark/units.json').read_text())
    ownership = json.loads((game / 'assets/adopted/craterpark/craterpark_ownership.json').read_text())
    mega = units_of(megapark_park, mega_owners(units), mega_object)
    crater_owner = crater_owners(game / 'assets/adopted/craterpark')
    check_ownership(ownership, crater_owner, craterpark_park)
    crater = units_of(craterpark_park, crater_owner, crater_object)
    check_records(game, mega + crater)
    return {'megapark': mega, 'craterpark': crater}


def outputs(game: Path, megapark_data: Path, craterpark_data: Path) -> dict[Path, str]:
    """{objects.toml path: its new text} for both parks."""
    objects = build(game, json.loads(megapark_data.read_text()), json.loads(craterpark_data.read_text()))
    result = {}
    for tag, entries in objects.items():
        path = game / 'world/regions' / REGIONS[tag] / 'objects.toml'
        result[path] = merge(path.read_text(), f'{tag}/park.json', entries)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--megapark-data', type=Path, default=GAME / 'unreal/Content/Data/megapark/park.json')
    parser.add_argument('--craterpark-data', type=Path, default=GAME / 'unreal/Content/Data/craterpark/park.json')
    parser.add_argument('--check', action='store_true', help='write nothing; exit 1 if an objects.toml would change')
    args = parser.parse_args(argv)
    try:
        texts = outputs(GAME, args.megapark_data, args.craterpark_data)
    except (ConvertError, OSError, ValueError, KeyError) as error:
        print(f'parks: {error}', file=sys.stderr)
        return 1
    changed = []
    for path, text in texts.items():
        if path.read_text() == text:
            continue
        changed.append(path)
        if args.check:
            sys.stdout.writelines(difflib.unified_diff(path.read_text().splitlines(True), text.splitlines(True),
                                                       str(path), str(path)))
        else:
            path.write_text(text)
    print(f'parks: {len(changed)} objects.toml file(s) ' + ('would change' if args.check else 'written')
          + ': ' + ', '.join(str(p.relative_to(GAME)) for p in changed))
    return 1 if args.check and changed else 0


if __name__ == '__main__':
    sys.exit(main())
