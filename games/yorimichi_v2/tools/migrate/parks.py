"""Write the park objects of w11-megapark and w12-craterpark into their objects.toml: one object per adopted unit.

    uv run python games/yorimichi_v2/tools/migrate/parks.py [--megapark-data PARK.json] [--craterpark-data PARK.json] [--check]

A park's render and collision meshes (unreal/Content/Data/<park>/park.json, ASuperUltraMegaPark::Spawn reads them) are
saved as one object per adopted unit that owns them: Mega Park's 16 units (assets/adopted/megapark/units.json: 15 stream
cells and the seam) and Crater Park's 58 (the adopted records of assets/adopted/craterpark, each owning its meshes, with
craterpark_ownership.json checked against them). Rails and zones stay runtime.

The park's trees are one object per unit too (`trees = <unit>`, id object/<area>/trees-<unit>): each tree belongs to the
unit that owns the park piece whose origin is nearest in the plane (ties: the earlier piece of the file). A tree whose
species has no adopted record (an Experiments rock, HD_NorthRock) stays runtime. The kei cars of Mega Park's car park
are one object each (`props = [...]`, id object/<area>/<record>): the record that outputs the car's mesh.

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
JAPAN_ASSETS = '/Game/Japan/Assets/'
PACKAGE = re.compile(r'^package = "(/Game/CraterPark/Meshes/[^"]+)"', re.M)
ANY_PACKAGE = re.compile(r'^package = "([^"]+)"', re.M)
RECORD_ID = re.compile(r'^id = "([^"]+)"', re.M)
STREAM_CELL = re.compile(r'^cell-x(\d+)-zm(\d+)$')
CRATER_PIECE = re.compile(r'^(p\d+)-(.+)$')
CRATER_FLOOR = re.compile(r'^crater-floor-(\d+)-(\d+)$')
REGIONS = {'megapark': 'w11-megapark', 'craterpark': 'w12-craterpark'}
LABELS = {'megapark': 'Mega Park', 'craterpark': 'Crater Park'}
GENERATED = re.compile(r'(?m)^(park|trees|props) = ')   # the entries this converter writes; a rerun replaces them


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


def park_owners(game: Path, tag: str) -> dict[str, str]:
    """{piece mesh name: unit} of a park: Mega Park's units.json, Crater Park's adopted records."""
    if tag == 'megapark':
        return mega_owners(json.loads((game / 'assets/adopted/megapark/units.json').read_text()))
    return crater_owners(game / 'assets/adopted/craterpark')


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


def mega_about(unit: str) -> str:
    cell = STREAM_CELL.match(unit)
    if cell:
        return f'the Mega Park section at stream cell ({int(cell[1])}, -{int(cell[2])})'
    if unit == 'seam':
        return 'the Mega Park seam meshes joining the park to the zeppelin footbridge'
    raise ConvertError(f'{unit}: no Mega Park unit this converter knows')


def crater_about(unit: str) -> str:
    piece = CRATER_PIECE.match(unit)
    floor = CRATER_FLOOR.match(unit)
    if floor:
        return f'the Crater Park crater floor, block {floor[1]}-{floor[2]}'
    if piece:
        return f'the Crater Park piece {piece[1]} ({piece[2]})'
    if unit == 'collision-mixed':
        return 'the Crater Park collision pieces that several features share'
    raise ConvertError(f'{unit}: no Crater Park unit this converter knows')


def mega_object(unit: str, pieces: list[str]) -> dict:
    return {'id': f'object/megapark/{unit}', 'park': pieces, 'model': f'adopted/megapark/{unit}', 'about': mega_about(unit)}


def crater_object(unit: str, pieces: list[str]) -> dict:
    return {'id': f'object/craterpark/{unit}', 'park': pieces, 'model': f'adopted/craterpark/{unit}',
            'about': crater_about(unit)}


def units_of(park: dict, owners: dict[str, str], make) -> list[dict]:
    """The park's objects, one per unit, sorted by ID. Every piece must have an owner, and the unit's record must exist."""
    per_unit: dict[str, list[str]] = {}
    for name in park_pieces(park):
        if name not in owners:
            raise ConvertError(f'{name} is owned by no unit')
        per_unit.setdefault(owners[name], []).append(name)
    return sorted((make(unit, pieces) for unit, pieces in per_unit.items()), key=lambda entry: entry['id'])


def japan_records(game: Path) -> dict[str, list[str]]:
    """{mesh name: the ids of the records that output /Game/Japan/Assets/<name>} (the island's meshes: trees, bushes, the
    kei cars). A package with a deeper path (a LOD, a material) is no mesh of that folder."""
    found: dict[str, list[str]] = {}
    for record in sorted((game / 'assets').glob('**/asset.toml')):
        text = record.read_text()
        for package in ANY_PACKAGE.findall(text):
            if package.startswith(JAPAN_ASSETS) and '/' not in package[len(JAPAN_ASSETS):]:
                found.setdefault(package[len(JAPAN_ASSETS):], []).append(RECORD_ID.search(text)[1])
    return found


def single_record(name: str, records: dict[str, list[str]]) -> str | None:
    """The one record that outputs a mesh; None when no record does; an error when two do."""
    owners = sorted(set(records.get(name, [])))
    if len(owners) > 1:
        raise ConvertError(f'{name} is the output of two records: {", ".join(owners)}')
    return owners[0] if owners else None


def tree_units(park: dict, owners: dict[str, str], records: dict[str, list[str]]) -> tuple[list[dict], list[str]]:
    """The park's trees, each as {species, index, unit} in the file's order, and the species with no record (they stay at
    runtime). A tree belongs to the unit that owns the park piece whose origin is nearest in the plane; ties go to the
    earlier piece. Nothing depends on which units are saved, so every rerun assigns the same trees."""
    pieces = []
    for kind in ('render', 'collision'):
        for entry in park[kind]:
            if entry['name'] not in owners:
                raise ConvertError(f'{entry["name"]} is owned by no unit')
            pieces.append((owners[entry['name']], float(entry['origin_cm'][0]), float(entry['origin_cm'][1])))
    trees, unmodelled = [], []
    for species, instances in park.get('trees', {}).items():
        if single_record(species, records) is None:
            unmodelled.append(species)
            continue
        for index, place in enumerate(instances):
            x, y = float(place[0]), float(place[1])
            nearest = min(range(len(pieces)), key=lambda i: ((pieces[i][1] - x) ** 2 + (pieces[i][2] - y) ** 2, i))
            trees.append({'species': species, 'index': index, 'unit': pieces[nearest][0]})
    return trees, sorted(unmodelled)


def tree_entries(tag: str, park: dict, owners: dict[str, str], records: dict[str, list[str]]) -> list[dict]:
    """One object per unit that holds trees: `trees = <unit>`, its model the records of the species it holds."""
    per_unit: dict[str, list[str]] = {}
    trees, _ = tree_units(park, owners, records)
    for tree in trees:
        per_unit.setdefault(tree['unit'], []).append(tree['species'])
    make_about = mega_about if tag == 'megapark' else crater_about
    entries = []
    for unit in sorted(per_unit):
        models = sorted({single_record(species, records) for species in per_unit[unit]})
        entries.append({'id': f'object/{tag}/trees-{unit}', 'trees': unit, 'model': models,
                        'about': f'the trees and bushes of {make_about(unit)}'})
    return entries


def prop_entries(tag: str, park: dict, records: dict[str, list[str]]) -> list[dict]:
    """One object per prop of the park file (a kei car): `props = [<mesh>]`, its model the record that outputs the mesh."""
    entries = []
    for prop in park.get('props', []):
        mesh = prop['mesh']
        record = single_record(mesh, records)
        if record is None:
            raise ConvertError(f'{mesh}: no record outputs {JAPAN_ASSETS}{mesh}')
        unit = record.rsplit('/', 1)[1]
        entries.append({'id': f'object/{tag}/{unit}', 'props': [mesh], 'model': record,
                        'about': f'the {LABELS[tag]} car park prop {mesh}'})
    return entries


def check_records(game: Path, objects: list[dict]) -> None:
    for entry in objects:
        models = [entry['model']] if isinstance(entry['model'], str) else entry['model']
        for model in models:
            if not (game / 'assets' / model / 'asset.toml').is_file():
                raise ConvertError(f'{entry["id"]}: its model record {model} is missing')


def toml_model(model: str | list[str]) -> str:
    if isinstance(model, str):
        return f'"{model}"'
    return '[' + ', '.join(f'"{m}"' for m in model) + ']'


def toml_entry(entry: dict) -> str:
    """One [[objects]] entry: park names four to a line (a unit of Crater Park has up to 65), trees name their unit, props
    their meshes."""
    lines = ['[[objects]]', f'id = "{entry["id"]}"']
    if 'park' in entry:
        lines.append('park = [')
        names = entry['park']
        for start in range(0, len(names), 4):
            lines.append('    ' + ', '.join(f'"{name}"' for name in names[start:start + 4]) + ',')
        lines.append(']')
    elif 'trees' in entry:
        lines.append(f'trees = "{entry["trees"]}"')
    else:
        lines.append('props = [' + ', '.join(f'"{name}"' for name in entry['props']) + ']')
    lines += [f'model = {toml_model(entry["model"])}', f'about = "{entry["about"]}"']
    return '\n'.join(lines) + '\n'


def merge(text: str, data: str, entries: list[dict]) -> str:
    """The objects.toml text with its `data` line set and its generated entries replaced; every other entry, and the
    header comments, stay as they are."""
    head, *blocks = re.split(r'(?m)^(?=\[\[objects\]\])', text)
    head = re.sub(r'(?m)^data = ".*"$', f'data = "{data}"', head).rstrip('\n') + '\n'
    kept = [block.strip('\n') + '\n' for block in blocks if not GENERATED.search(block)]
    return head + '\n' + '\n'.join(kept + [toml_entry(entry) for entry in entries])


def build(game: Path, megapark_park: dict, craterpark_park: dict) -> dict[str, list[dict]]:
    """{park tag: its objects} for both parks, from the committed unit records and the park files."""
    units = json.loads((game / 'assets/adopted/megapark/units.json').read_text())
    ownership = json.loads((game / 'assets/adopted/craterpark/craterpark_ownership.json').read_text())
    records = japan_records(game)
    mega_owner = mega_owners(units)
    mega = units_of(megapark_park, mega_owner, mega_object)
    mega += tree_entries('megapark', megapark_park, mega_owner, records) + prop_entries('megapark', megapark_park, records)
    crater_owner = crater_owners(game / 'assets/adopted/craterpark')
    check_ownership(ownership, crater_owner, craterpark_park)
    crater = units_of(craterpark_park, crater_owner, crater_object)
    crater += tree_entries('craterpark', craterpark_park, crater_owner, records)
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
