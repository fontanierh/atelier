"""Source recovery: give the packages of a donor-generated family back their sources (docs/inventory/sources.md, section 5).

    uv run python games/yorimichi_v2/tools/migrate/recover.py FAMILY --donor DONOR_OUT          (plan only)
    uv run python games/yorimichi_v2/tools/migrate/recover.py FAMILY --donor DONOR_OUT --apply  (write the records)

FAMILY names an entry of FAMILIES. DONOR_OUT is the donor build's output folder for that family. For each donor
output the family maps to the adopted package it became, the tool writes a generated record: the donor file is copied
into the record's `src/` and pinned by sha256, its recipe is the donor's own import setting (only importers the V2
editor supports: static-mesh and texture), and the record owns that one package. The adopted record that held the
package keeps only what is not generated (its `[[outputs]]` and their verified files), and is deleted when nothing is
left. Each generated record is imported later by the controller (`tools/import/run.py ID`), which writes its
`verified.json`; this tool never runs Unreal, claims or pushes.

Unmapped donor outputs and unmapped adopted packages are reported, never guessed: they keep their current record.
A second `--apply` finds nothing to change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'content'))
import records  # noqa: E402
from records import RecordError  # noqa: E402

GAME = HERE.parents[1]
HIPPODROME_ROOT = '/Game/Hippodrome'
# The donor's surface materials (unreal/Scripts/import_hippodrome.py SURFACES): a mesh with one of these materials binds
# the matching V2 material by slot. Painted structures (their material is a GLB instance with a Color_ map) are not here.
HIPPODROME_SURFACE_MATERIALS = {'HD_Grass': 'M_HD_Grass', 'HD_Dirt': 'M_HD_Dirt',
                                'HD_Stone': 'M_HD_Stone', 'HD_Rail': 'M_HD_Rail'}


class RecoverError(RuntimeError):
    pass


@dataclass
class Generated:
    id: str                       # new record ID, e.g. prop/hippodrome/ground
    kind: str                     # static-mesh or texture
    owner: str                    # claim scope
    package: str                  # the one /Game package the record now owns
    source: Path                  # donor file (absolute, read only)
    settings: dict                # the recipe settings of the V2 importer
    references: list[str] = field(default_factory=list)
    origin: str = ''              # the adopted record that held the package
    about: str = ''
    expected_sha: str | None = None   # the donor report's sha256 of the file, when it names one


@dataclass
class Plan:
    family: str
    generated: list[Generated]
    unmapped_outputs: list[str]   # donor files no generated record uses
    kept: dict[str, list[str]]    # adopted record -> packages that stay with it


def slug(name: str) -> str:
    """LaneSkirt -> lane-skirt, NorthCountry_Piece000 -> north-country-piece000: a record-ID segment."""
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', name.replace('_', '-')).lower()


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RecoverError(f'{path}: {error}') from None


def ident(name: str) -> str:
    """A record-ID segment from a donor mesh name: Terrain_cell_-3_-3 -> terrain-cell-m3-m3."""
    return slug(name.replace('-', 'm'))


def record_owners(game: Path) -> dict[str, str]:
    """package -> record ID, for every record (generated or adopted): material and reference lookups need all of them."""
    owner = {}
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        for output in asset.outputs:
            owner[output.package] = asset.id
    return owner


def adopted_packages(game: Path, family: str) -> dict[str, str]:
    """package -> adopted record ID, for every adopted record of the family."""
    owner = {}
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if asset.id.startswith(f'adopted/{family}/') and not asset.sources and asset.recipe is None:
            for output in asset.outputs:          # a record with its own sources is not a source-less one
                owner[output.package] = asset.id
    return owner


def plan_hippodrome(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's world.hippodrome outputs: glb/<SM_HD_*>.glb, textures/<T_HD_*>.png, hippodrome.json, build-report.json."""
    region = _json(donor / 'hippodrome.json')
    report = _json(donor / 'build-report.json')
    generated, unmapped = [], []
    for key, file in sorted(region.get('textures', {}).items()):
        name = 'T_' + key[3:]                                  # the donor's texture(..., 'T_' + key[3:], wrap=True)
        generated.append(Generated(
            id=f'texture/hippodrome/{slug(name[2:])}', kind='texture', owner=f'shared/hippodrome/{slug(name[2:])}',
            package=f'{HIPPODROME_ROOT}/Textures/{name}', source=donor / 'textures' / file,
            settings={'srgb': True, 'compression': 'TC_DEFAULT', 'address': 'wrap'},
            about=f'{name}: the tiling ground colour of the course (donor texture {file})'))
    used = {g.source.name for g in generated}
    for entry in region.get('meshes', []):
        name = entry['name']
        info = report['meshes'][name]
        material = info['material']
        glb = donor / 'glb' / f'{name}.glb'
        if material not in HIPPODROME_SURFACE_MATERIALS:
            unmapped.append(f'glb/{name}.glb (painted structure, material {material}: its Color_ map is not recovered)')
            continue
        generated.append(Generated(
            id=f'prop/hippodrome/{slug(name[len("SM_HD_"):])}', kind='static-mesh',
            owner=f'shared/hippodrome/{slug(name[len("SM_HD_"):])}', package=f'{HIPPODROME_ROOT}/{name}', source=glb,
            settings={'slot_materials': [f'{HIPPODROME_ROOT}/Materials/{HIPPODROME_SURFACE_MATERIALS[material]}'],
                      'triangles': info['triangles'], 'collision': 'complex'},
            references=['adopted/hippodrome/materials'],
            about=f'{name}: one course surface ({info["triangles"]} triangles, material {material})',
            expected_sha=info['sha256']))
        used.add(glb.name)
    unmapped_outputs = [*unmapped]
    for path in sorted((donor / 'textures').glob('*')):
        if path.name not in used:
            unmapped_outputs.append(f'textures/{path.name}')
    return Plan('hippodrome', generated, unmapped_outputs, {})


def plan_brinecove(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's brinecove meshes (build-report.json): one glb per mesh, slots bound to the region's material instances
    (report materials, /Game/Brinecove/Materials). Full-precision UVs for non-terrain meshes and complex collision where the
    report says so, as the donor import sets them. Meshes with LODs are generated by the donor in the editor (generate_lods);
    the V2 importer has no LOD step, so they stay open in their adopted records."""
    report = _json(donor / 'build-report.json')
    materials = report['materials']
    generated, unmapped = [], []
    for row in report['meshes']:
        name = row['name']
        package = f'/Game/Brinecove/Meshes/{name}'
        if package not in owner:
            unmapped.append(f'glb/{name}.glb (its package is not in a source-less brinecove record)')
            continue
        if row.get('lods'):
            unmapped.append(f'glb/{name}.glb (LODs generated by the donor editor: no V2 LOD step)')
            continue
        packages = [f'/Game/Brinecove/Materials/{materials[key]["name"]}' for key in row['slots']]
        missing = [m for m in packages if m not in all_owner]
        if not packages or missing:
            unmapped.append(f'glb/{name}.glb (material {missing or row["slots"]} owned by no record)')
            continue
        tail = ident(name[len('SM_BC_'):]) if name.startswith('SM_BC_') else ident(name)
        settings = {'slot_materials': packages, 'triangles': row['triangles']}
        if row['collision']:
            settings['collision'] = 'complex'
        if any(materials[key]['kind'] != 'terrain' for key in row['slots']):
            settings['full_precision_uvs'] = True
        generated.append(Generated(
            id=f'prop/brinecove/{tail}', kind='static-mesh', owner=f'shared/brinecove/{tail}', package=package,
            source=donor / row['path'], settings=settings,
            references=sorted({all_owner[m] for m in packages}),
            about=f'{name}: one Brine Cove mesh ({row["triangles"]} triangles)', expected_sha=row['sha256']))
    return Plan('brinecove', generated, unmapped, {})


ISLAND_DESTINATION = '/Game/Experiments/IslandTerrain/v1_atomic'
ISLAND_SEA = 'Sea'   # the generator record holds the sea mesh and its final water binding (M_Sea): it stays there


def plan_island(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's island atomic exports (assets/manifest.json): one FBX per cell and per road, lane, guardrail, wire and
    far-hill piece. Each piece binds, slot by slot, to MI_<slot> in /Game/Japan/Materials (the donor's material_paths);
    a piece is recovered only when every one of those materials is owned by a record. Collision is complex-as-simple,
    as the donor sets it on every island mesh; the exports carry no collision hulls."""
    manifest = _json(donor / 'assets' / 'manifest.json')
    generated, unmapped = [], []
    for row in manifest['exports']:
        name = row['asset']
        package = f'{ISLAND_DESTINATION}/{name}'
        origin = owner.get(package, '')
        if name == ISLAND_SEA or origin.endswith('/generator') or not origin:
            unmapped.append(f'assets/{row["primary"]} ({name}: held by the generator record, not recovered)')
            continue
        slots = row['metadata']['slots']
        materials = [f'/Game/Japan/Materials/MI_{slot}' for slot in slots]
        missing = [m for m in materials if m not in all_owner]
        if not slots or missing:
            unmapped.append(f'assets/{row["primary"]} (material {missing or slots} owned by no record)')
            continue
        tail = ident(name)
        generated.append(Generated(
            id=f'prop/islandterrain/{tail}', kind='static-mesh', owner=f'shared/islandterrain/{tail}',
            package=package, source=donor / 'assets' / row['primary'],
            settings={'slot_materials': materials, 'triangles': row['triangles'], 'collision': 'complex'},
            references=sorted({all_owner[m] for m in materials}),
            about=f'{name}: one island piece ({row["triangles"]} triangles, materials {", ".join(slots)})',
            expected_sha=row['sha256']))
    return Plan('experiments/islandterrain', generated, unmapped, {})


BELMONTE_PIECES = {'SM_BM_NorthApron_': 'north-apron', 'SM_BM_NorthCountry_': 'north-country'}


def plan_belmonte(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's world.belmonte.meshes outputs. belmonte/build-report.json lists each mesh with its glb, triangles and
    sha256, and products/belmonte/materials.json binds each mesh's slot to a material instance. The North Apron and North
    Country pieces have no committed model (the region scripts generate them), so each piece is recovered as its own
    record, since the triangle counts differ. A piece is recovered only when its one slot is a material some record owns."""
    report = _json(donor / 'build-report.json')
    bindings = _json(donor.parent / 'products' / 'belmonte' / 'materials.json')['bindings']
    generated, unmapped = [], []
    for entry in report['meshes']:
        name = entry['name']
        if not any(name.startswith(prefix) for prefix in BELMONTE_PIECES):
            continue
        slots = [m.split('.', 1)[0] for m in bindings.get(name, [])]
        if len(slots) != 1 or slots[0] not in all_owner:
            unmapped.append(f'glb/{name}.glb (its material {slots} is owned by no adopted record)')
            continue
        tail = slug(name[len('SM_BM_'):])
        generated.append(Generated(
            id=f'prop/belmonte/{tail}', kind='static-mesh', owner=f'shared/belmonte/{tail}',
            package=f'/Game/Belmonte/Meshes/{name}', source=donor / entry['path'],
            settings={'slot_materials': slots, 'triangles': entry['triangles']},
            references=[all_owner[slots[0]]],
            about=f'{name}: one generated {BELMONTE_PIECES[next(p for p in BELMONTE_PIECES if name.startswith(p))]} '
                  f'piece ({entry["triangles"]} triangles, its ground material)',
            expected_sha=entry['sha256']))
    return Plan('belmonte', generated, unmapped, {})


FAMILIES = {'hippodrome': plan_hippodrome, 'belmonte': plan_belmonte, 'experiments/islandterrain': plan_island,
            'brinecove': plan_brinecove}


def build_plan(game: Path, family: str, donor: Path) -> Plan:
    if family not in FAMILIES:
        raise RecoverError(f'unknown family {family!r}; known: {", ".join(sorted(FAMILIES))}')
    owner = adopted_packages(game, family)
    plan = FAMILIES[family](game, donor, owner, record_owners(game))
    for gen in plan.generated:
        gen.origin = owner.get(gen.package, '')
        if not gen.origin:
            # Already applied: the generated record owns the package and the adopted one has let go of it.
            asset_toml = game / 'assets' / gen.id / 'asset.toml'
            if asset_toml.is_file() and f'package = "{gen.package}"' in asset_toml.read_text():
                gen.origin = 'applied'
            else:
                raise RecoverError(f'{gen.package} is in no adopted {family} record; nothing to recover there')
    ids = [g.id for g in plan.generated]
    packages = [g.package for g in plan.generated]
    if len(set(ids)) != len(ids) or len(set(packages)) != len(packages):
        raise RecoverError('two generated records share an ID or a package')
    for gen in plan.generated:
        if not gen.source.is_file():
            raise RecoverError(f'donor file {gen.source.name} is missing')
    # Every donor file must be the bytes the donor's report names (hippodrome: build-report sha256), or nothing is written.
    for gen in plan.generated:
        if gen.expected_sha and records.sha256_file(gen.source) != gen.expected_sha:
            raise RecoverError(f'{gen.source.name} differs from the donor report ({gen.expected_sha[:12]}); '
                               'rebuild the donor first')
    kept = {}
    generated_packages = set(packages)
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if asset.id.startswith(f'adopted/{family}/'):
            left = [o.package for o in asset.outputs if o.package not in generated_packages]
            kept[asset.id] = left
    plan.kept = kept
    return plan


def _record_text(gen: Generated, source_name: str, digest: str) -> str:
    lines = [f'# Recovered from the donor generator (tools/migrate/recover.py): {gen.about}.',
             '# The donor file is committed in src/ and pinned by sha256; the record is imported by the V2 editor and',
             '# verified by tools/import/run.py, never edited by hand.',
             'schema = 1', f'id = "{gen.id}"', f'kind = "{gen.kind}"', 'authority = "generated"',
             f'owner = "{gen.owner}"']
    if gen.references:
        lines.append('references = [' + ', '.join(f'"{r}"' for r in gen.references) + ']')
    lines += ['', '[[sources]]', f'path = "src/{source_name}"', f'sha256 = "{digest}"', '',
              '[recipe]', f'importer = "{gen.kind}"', 'version = 1', '', '[recipe.settings]']
    for key, value in gen.settings.items():
        if isinstance(value, list):
            lines.append(f'{key} = [' + ', '.join(f'"{v}"' for v in value) + ']')
        elif isinstance(value, bool):
            lines.append(f'{key} = {"true" if value else "false"}')
        elif isinstance(value, int):
            lines.append(f'{key} = {value}')
        else:
            lines.append(f'{key} = "{value}"')
    lines += ['', '[[outputs]]', f'package = "{gen.package}"', '']
    return '\n'.join(lines)


def _drop_outputs(text: str, packages: set[str]) -> str:
    """The asset.toml text without the [[outputs]] blocks of the given packages (other lines stay byte for byte)."""
    head, *blocks = re.split(r'(?m)^(?=\[\[outputs\]\]\n)', text)
    kept = [head]
    for block in blocks:
        match = re.search(r'package = "([^"]+)"', block)
        if not match or match.group(1) not in packages:
            kept.append(block)
    return ''.join(kept)


def _unit_text(text: str) -> str:
    """A source-less adopted record re-rendered as tools/migrate/adopt.py writes it (same header, same outputs)."""
    header = re.search(r'(?m)^# Ownership unit: (.*)$', text)
    if header is None:                          # not an adoption record: its text stays as it is
        return text
    sys.path.insert(0, str(HERE))
    import adopt
    field_ = lambda key: re.search(rf'(?m)^{key} = "(.*)"$', text).group(1)  # noqa: E731
    about = header.group(1)
    refs = re.search(r'(?m)^references = \[(.*)\]$', text)
    refs = re.findall(r'"([^"]+)"', refs.group(1)) if refs else []
    packages = re.findall(r'(?m)^package = "([^"]+)"$', text)
    return adopt.record_text(field_('id'), field_('owner'), about, packages, field_('license'), field_('provenance'),
                             (), refs)


def _drop_verified(path: Path, packages: set[str]) -> None:
    """Remove the verified files of the given packages (their .uasset/.umap and companions), keep the rest."""
    stems = {'unreal/Content/' + p[len('/Game/'):] for p in packages}
    data = _json(path)
    data['files'] = {rel: d for rel, d in data['files'].items() if rel.rsplit('.', 1)[0] not in stems}
    if data['files']:
        records.write_json(path, data)
    else:
        path.unlink()


def apply(game: Path, plan: Plan, donor: Path) -> dict:
    """Write the generated records and shrink the adopted ones. Returns what changed (empty when already applied)."""
    changed = {'created': [], 'shrunk': [], 'deleted': []}
    gen_packages = {g.package for g in plan.generated}
    for gen in plan.generated:
        folder = game / 'assets' / gen.id
        src = folder / 'src' / gen.source.name
        digest = records.sha256_file(gen.source)
        text = _record_text(gen, gen.source.name, digest)
        if (folder / 'asset.toml').is_file() and (folder / 'asset.toml').read_text() == text and src.is_file():
            continue
        if folder.exists() and any(folder.iterdir()) and not (folder / 'asset.toml').is_file():
            raise RecoverError(f'{folder} exists and is not a record of this tool; refusing to write over it')
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gen.source, src)
        (folder / 'asset.toml').write_text(text)
        changed['created'].append(gen.id)
    for record_id, left in sorted(plan.kept.items()):
        folder = game / 'assets' / record_id
        asset_toml = folder / 'asset.toml'
        if not asset_toml.is_file():
            continue
        mine = {o for o in records.load_asset(asset_toml).outputs}
        before = {o.package for o in mine}
        if not before & gen_packages:
            text = asset_toml.read_text()          # an earlier apply may have shrunk it: keep it in adoption's form
            if left and '[[sources]]' not in text and _unit_text(text) != text:
                asset_toml.write_text(_unit_text(text))
                changed['shrunk'].append(record_id)
            continue
        if not left:
            for path in (asset_toml, folder / 'verified.json'):
                if path.is_file():
                    path.unlink()
            while folder != game / 'assets' and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
            changed['deleted'].append(record_id)
            continue
        text = asset_toml.read_text()
        new_text = _drop_outputs(text, gen_packages)
        if '[[sources]]' not in new_text:
            new_text = _unit_text(new_text)     # the writer adoption repartition uses, so its check stays clean
        asset_toml.write_text(new_text)
        if (folder / 'verified.json').is_file():
            _drop_verified(folder / 'verified.json', gen_packages & before)
        changed['shrunk'].append(record_id)
    return changed


def report(plan: Plan) -> str:
    lines = [f'family {plan.family}: {len(plan.generated)} generated record(s)']
    for gen in plan.generated:
        lines.append(f'  {gen.id:32} {gen.kind:12} {gen.package}  <- {gen.source.name}  (from {gen.origin})')
    for record_id, left in sorted(plan.kept.items()):
        lines.append(f'  remainder {record_id}: {len(left)} package(s) kept')
    for item in plan.unmapped_outputs:
        lines.append(f'  unmapped donor output: {item}')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('family', choices=sorted(FAMILIES))
    parser.add_argument('--donor', required=True, type=Path, help='the donor build output folder of the family')
    parser.add_argument('--apply', action='store_true', help='write the records (default: plan only)')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.game.resolve(), args.family, args.donor.resolve())
        print(report(plan))
        if args.apply:
            changed = apply(args.game.resolve(), plan, args.donor.resolve())
            print(f'applied: created {len(changed["created"])}, shrunk {len(changed["shrunk"])}, '
                  f'deleted {len(changed["deleted"])}')
    except (RecoverError, RecordError) as error:
        print(f'recover failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
