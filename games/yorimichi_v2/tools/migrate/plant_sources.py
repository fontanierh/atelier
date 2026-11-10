"""Source recovery for two families still without sources: the Brine Cove plants (9 adopted records, 36 packages) and the
city tree residual packages (experiments/citytrees, 36 packages). Plan mode is the default; nothing is written.

    uv run python games/yorimichi_v2/tools/migrate/plant_sources.py [--donor DIR]            # plan; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/plant_sources.py [--donor DIR] --table    # the markdown table
    uv run python games/yorimichi_v2/tools/migrate/plant_sources.py [--donor DIR] --paths    # claim paths and scopes
    uv run python games/yorimichi_v2/tools/migrate/plant_sources.py [--donor DIR] --claim TASK  # the one journaled write

DIR is the donor's build/yorimichi folder (default: $YV2_DONOR_BUILD). It is read only.

Origins, from the donor (games/yorimichi generators, with their build):

- Brine Cove plants (36 meshes, `brinecove/build-report.json` rows named SM_BC_Plant_*). Each is one GLB (LOD0, pinned by sha256)
  imported with its material slots, full-precision UVs where the report says so, and then given the donor's fixed four-level
  reduction plan (`generate_lods` in import_brinecove.py: 100%/45%/20%/8% at screens 1/0.3/0.12/0.04). The record states that plan
  as `lods`; the importer applies it to a new package.
- City tree residuals (`city_tree_lods/v4/manifest.json`). Each of 12 pieces is a duplicate of a recovered citysurfaces original
  (`prop/citysurfaces/*`, whose FBX is committed), with two LOD levels attached (FBX, pinned by sha256, screens 0.18 and 0.07). The
  24 `lods/` packages are those FBX levels imported as standalone meshes with the original's material. The 12 `_v4` packages are the
  LOD chains: the original's FBX as LOD0, then the two FBX levels (`lod_chain`, as the donor's import_city_tree_lods.py attaches them).

Every package gets one record, of kind static-mesh, with its donor file copied into src/ and pinned. Nothing here decides what
the saved meshes look like: the reads (report_meshes.py on the 72 packages) confirm slots, LOD counts, triangles and collision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
import recover  # noqa: E402  (slug, _drop_outputs, _toml)

GAME_REL = 'games/yorimichi_v2'
PLANT_PREFIX = 'SM_BC_Plant_'
PLANT_MESH = '/Game/Brinecove/Meshes/{name}'
PLANT_MATERIAL = '/Game/Brinecove/Materials/{name}'
PLANT_LODS = [[1.0, 1.0], [0.45, 0.3], [0.2, 0.12], [0.08, 0.04]]   # import_brinecove.py generate_lods
CITY_ADOPTED = 'adopted/experiments/citytrees'
CITY_ORIGINAL = '/Game/Experiments/CitySurfaces/v1_128m/{name}'
CITY_V4 = '/Game/Experiments/CityTrees/v4/{name}_v4'
CITY_LOD = '/Game/Experiments/CityTrees/v4/lods/{name}'
DONOR_ENV = 'YV2_DONOR_BUILD'
COPIED_SETTINGS = ('collision', 'hulls', 'full_precision_uvs')   # the original's mesh settings, as its own import sets them
PACKAGE_LIST = GAME / 'docs' / 'inventory' / 'plants-and-city-tree-packages.txt'
PLANT_ADOPTED = 'adopted/brinecove/plant-'


class PlanError(RuntimeError):
    pass


@dataclass
class Src:
    path: str            # record-relative, src/<name>
    sha256: str
    file: Path           # the file read to copy (donor or repository, read only)


@dataclass
class Rec:
    id: str
    family: str          # plants | city-lods | city-v4
    owner: str
    kind: str
    sources: list
    settings: dict
    references: list
    outputs: list
    about: str
    adopted: str         # the adopted record whose package this is


@dataclass
class Plan:
    records: list
    unmapped: list
    packages: dict      # package -> record ID
    donor: Path



V4_SLOT = 'HidamariPalette'   # the original FBX's material name: the saved _v4 slot, as the editor import reads it
def donor_default():
    root = os.environ.get(DONOR_ENV)
    return Path(root).expanduser() if root else None


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise PlanError(f'{path}: {error}') from None


def ident(name: str) -> str:
    return recover.slug(name.replace('-', 'm'))


def load_records(game: Path):
    """(record ID -> loaded record, package -> owning record ID) for every record under the game."""
    by_id, owner_of = {}, {}
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        by_id[asset.id] = asset
        for output in asset.outputs:
            owner_of[output.package] = asset.id
    return by_id, owner_of


def _check_file(file: Path, sha: str, what: str, unmapped: list) -> bool:
    if not file.is_file():
        unmapped.append(f'{what}: the donor file is missing')
        return False
    if hashlib.sha256(file.read_bytes()).hexdigest() != sha:
        unmapped.append(f'{what}: the file is not its pinned sha256')
        return False
    return True


def slot_name(material: str) -> str:
    """The name a plant's slot saves: its material's name without the MI_ prefix (MI_BC_leaf_deep -> BC_leaf_deep), which is
    the GLB's own material name (the mesh read agrees)."""
    return material.rsplit('/', 1)[1].removeprefix('MI_')


def glb_material_names(path: Path) -> list:
    """The glTF material names of a binary glTF, in slot order (read only)."""
    data = path.read_bytes()
    if data[:4] != b'glTF':
        raise PlanError(f'{path.name}: not a binary glTF')
    size = int.from_bytes(data[12:16], 'little')
    doc = json.loads(data[20:20 + size])
    return [m.get('name', '') for m in doc.get('materials', [])]


def family_of(record_id: str) -> str:
    """The family of a planned record ID, or '' for any other record."""
    if record_id.startswith('prop/brinecove/plant-'):
        return 'plants'
    if record_id.startswith('prop/citytrees/'):
        return 'city-v4' if record_id.endswith('-v4') else 'city-lods'
    return ''


def expected_packages() -> list:
    """The 72 packages the plan covers, from the committed list."""
    return PACKAGE_LIST.read_text().split()


def plan_plants(game: Path, donor: Path, by_id: dict, owner_of: dict, unmapped: list) -> list:
    report = _json(donor / 'brinecove' / 'build-report.json')
    materials = report['materials']
    adopted = {o.package: a for a in by_id.values() if a.id.startswith('adopted/brinecove/plant-') for o in a.outputs}
    out = []
    for row in report['meshes']:
        name = row['name']
        if not name.startswith(PLANT_PREFIX):
            continue
        package = PLANT_MESH.format(name=name)
        if package not in adopted:
            unmapped.append(f'{name}: not an output of a plant record')
            continue
        glb = donor / 'brinecove' / row['path']
        if not _check_file(glb, row['sha256'], name, unmapped):
            continue
        slots = [PLANT_MATERIAL.format(name=materials[key]['name']) for key in row['slots']]
        missing = [m for m in slots if m not in owner_of]
        if not slots or missing:
            unmapped.append(f'{name}: material(s) {missing or row["slots"]} owned by no record')
            continue
        glb_names = glb_material_names(glb)
        if glb_names != [slot_name(m) for m in slots]:
            unmapped.append(f'{name}: the GLB names its materials {glb_names}, not the slots\' {[slot_name(m) for m in slots]}')
            continue
        settings = {'slot_materials': slots, 'triangles': row['triangles']}
        if row['collision']:
            settings['collision'] = 'complex'
        if any(materials[key]['kind'] != 'terrain' for key in row['slots']):
            settings['full_precision_uvs'] = True
        if row.get('lods'):
            settings['lods'] = [list(step) for step in PLANT_LODS]
        out.append(Rec(id=f'prop/brinecove/{ident(name[len("SM_BC_"):])}', family='plants',
                       owner=adopted[package].owner, kind='static-mesh',
                       sources=[Src(f'src/{Path(row["path"]).name}', row['sha256'], glb)],
                       settings=settings, references=sorted({owner_of[m] for m in slots}),
                       outputs=[package], about=f'{name}: one Brine Cove plant, LOD0 GLB with its four-level reduction plan',
                       adopted=adopted[package].id))
    return out


def plan_city(game: Path, donor: Path, by_id: dict, owner_of: dict, unmapped: list) -> list:
    manifest = _json(donor / 'city_tree_lods' / 'v4' / 'manifest.json')
    screens = manifest['screen_sizes']
    city = by_id.get(CITY_ADOPTED)
    if city is None:
        raise PlanError(f'{CITY_ADOPTED} is missing')
    city_packages = {o.package for o in city.outputs}
    out = []
    for family, pieces in manifest['sources'].items():
        for piece in pieces:
            name = piece['name']
            original_package = CITY_ORIGINAL.format(name=name)
            original = by_id.get(owner_of.get(original_package, ''))
            if original is None or original.kind != 'static-mesh' or not original.sources:
                unmapped.append(f'{name}: no recovered citysurfaces record owns {original_package}')
                continue
            settings = original.recipe['settings']
            if not settings.get('slot_materials'):
                unmapped.append(f'{name}: the original record names no slot material')
                continue
            slot = settings['slot_materials'][0]
            if slot not in owner_of:
                unmapped.append(f'{name}: material {slot} owned by no record')
                continue
            levels = []
            for lod, screen in zip(piece['lods'], screens[1:]):
                file = donor / lod['file']
                package = CITY_LOD.format(name=lod['name'])
                if package not in city_packages:
                    unmapped.append(f'{lod["name"]}: not an output of {CITY_ADOPTED}')
                    continue
                if not _check_file(file, lod['sha256'], lod['name'], unmapped):
                    continue
                levels.append((lod, screen, file, package))
            if len(levels) != len(piece['lods']):
                continue
            for lod, _, file, package in levels:
                out.append(Rec(id=f'prop/citytrees/{ident(lod["name"])}', family='city-lods', owner=city.owner,
                               kind='static-mesh', sources=[Src(f'src/{file.name}', lod['sha256'], file)],
                               settings={'slot_materials': [slot], 'triangles': lod['triangles']},
                               references=[owner_of[slot]], outputs=[package],
                               about=f'{lod["name"]}: the {family} LOD level as a standalone mesh (donor FBX)',
                               adopted=CITY_ADOPTED))
            original_src = original.sources[0]
            chain = [[f'src/{Path(original_src.path).name}', 1.0, piece['original_triangles'], [0]]]
            files = [Src(f'src/{Path(original_src.path).name}', original_src.sha256, original.folder / original_src.path)]
            for (lod, screen, file, _) in levels:
                chain.append([f'src/{file.name}', screen, lod['triangles'], [0]])
                files.append(Src(f'src/{file.name}', lod['sha256'], file))
            v4_settings = {'lod_chain': chain, 'slots': [[V4_SLOT, slot]],
                           'triangles': piece['original_triangles']}
            v4_settings.update({key: settings[key] for key in COPIED_SETTINGS if key in settings})
            out.append(Rec(id=f'prop/citytrees/{ident(name + "_v4")}', family='city-v4', owner=city.owner,
                           kind='static-mesh', sources=files, settings=v4_settings,
                           references=[owner_of[slot]], outputs=[CITY_V4.format(name=name)],
                           about=f'{name}_v4: the citysurfaces original as LOD0 with its two donor FBX levels',
                           adopted=CITY_ADOPTED))
    return out


def state(game: Path) -> tuple:
    """(state, detail). `unprepared`: the adopted records hold the 72 packages and no planned record exists. `done`: 72 records
    of these families list them and no adopted record does. Anything else is refused, never guessed."""
    expected = set(expected_packages())
    by_id, _ = load_records(game)
    adopted = {o.package for rid, asset in by_id.items()
               if rid.startswith(PLANT_ADOPTED) or rid == CITY_ADOPTED for o in asset.outputs}
    planned = {o.package for rid, asset in by_id.items() if family_of(rid) for o in asset.outputs}
    if adopted & expected == expected and not planned & expected:
        return 'unprepared', f'{len(expected)} packages in the adopted records; prepare with --claim'
    if not adopted & expected and planned & expected == expected:
        return 'done', f'{len(expected)} records list the packages; the adopted records list none'
    raise PlanError(f'partly moved: {len(adopted & expected)} package(s) adopted, {len(planned & expected)} planned; resolve by hand')


def records_plan(game: Path) -> Plan:
    """The plan as the written records state it (the done state): the same families, settings, sources and outputs."""
    by_id, _ = load_records(game)
    out = []
    for rid, asset in sorted(by_id.items()):
        family = family_of(rid)
        if not family:
            continue
        out.append(Rec(id=rid, family=family, owner=asset.owner, kind=asset.kind,
                       sources=[Src(src.path, src.sha256, asset.folder / src.path) for src in asset.sources],
                       settings=dict((asset.recipe or {}).get('settings', {})), references=list(asset.references),
                       outputs=[o.package for o in asset.outputs], about='written record', adopted=''))
    packages = {package: rec.id for rec in out for package in rec.outputs}
    return Plan(out, [], packages, None)


def plan(game: Path, donor: Path) -> Plan:
    by_id, owner_of = load_records(game)
    unmapped = []
    rows = plan_plants(game, donor, by_id, owner_of, unmapped) + plan_city(game, donor, by_id, owner_of, unmapped)
    packages = {}
    for rec in rows:
        for package in rec.outputs:
            packages[package] = rec.id
    for family, ids in (('plants', [i for i in by_id if i.startswith('adopted/brinecove/plant-')]), ('city', [CITY_ADOPTED])):
        for adopted_id in ids:
            for output in by_id[adopted_id].outputs:
                if output.package not in packages:
                    unmapped.append(f'{output.package}: no record plans it ({family})')
    return Plan(rows, unmapped, packages, donor)


# --- the record text ---------------------------------------------------------------------------------------------------------

def record_text(rec: Rec) -> str:
    lines = [f'# Recovered from the donor (tools/migrate/plant_sources.py): {rec.about}.',
             '# The donor files are committed in src/ and pinned by sha256; the record is imported by the V2 editor and',
             '# verified by tools/import/run.py, never edited by hand.',
             'schema = 1', f'id = "{rec.id}"', f'kind = "{rec.kind}"', 'authority = "generated"', f'owner = "{rec.owner}"']
    if rec.references:
        lines.append('references = [' + ', '.join(f'"{r}"' for r in rec.references) + ']')
    for src in rec.sources:
        lines += ['', '[[sources]]', f'path = "{src.path}"', f'sha256 = "{src.sha256}"']
    lines += ['', '[recipe]', f'importer = "{rec.kind}"', 'version = 1', '', '[recipe.settings]']
    lines += [f'{key} = {recover._toml(value)}' for key, value in rec.settings.items()]
    lines += ['']
    for package in rec.outputs:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


# --- the evidence: the mesh read, compacted to what the records assert -------------------------------------------------------

def _trace(value) -> str:
    """A read collision trace flag's bare name ("CTF_USE_DEFAULT: 0>" -> "CTF_USE_DEFAULT")."""
    return str(value).split(':')[0].strip()


def evidence(plan_: Plan, read: dict) -> dict:
    """The compact evidence of report_meshes.py for every planned package: the slot materials, each LOD's screen (3 decimals),
    triangles and sections, and the collision facts the record can assert. The donor's absolute source paths are left out."""
    out = {}
    for rec in plan_.records:
        for package in rec.outputs:
            row = read[package]
            out[package] = {
                'family': rec.family,
                'slots': [{'name': slot['name'], 'imported': slot['imported'], 'material': slot['material']}
                          for slot in row['slots']],
                'lods': [{'screen': round(lod['screen'], 3), 'triangles': lod['triangles'], 'sections': lod['sections']}
                         for lod in row['lods']],
                'collision': {'trace': _trace(row['collision']['trace']), 'convex': row['collision']['convex'],
                              'simple': row['collision']['simple'], 'boxes': len(row['collision']['boxes']),
                              'double_sided': row['collision']['double_sided']}}
    return out


def expected_slot_names(rec: Rec) -> list:
    """The slot names the record expects the import to save: a plant's are its materials' names, a _v4's are its own label
    (`slots`), and a city LOD's are the FBX material's name. A label M_Arcade in a _v4 therefore disagrees with the read."""
    if rec.family == 'plants':
        return [slot_name(m) for m in rec.settings['slot_materials']]
    if rec.family == 'city-v4':
        return [label for label, _ in rec.settings['slots']]
    return [V4_SLOT]


def disagreements(plan_: Plan, ev: dict) -> list:
    """Every way the plan disagrees with the read evidence (empty when it agrees). A plant's four levels must sit at the donor's
    screens, never gain triangles, and its LOD0 must use every slot; a city LOD is one level; a _v4 chain must have the
    planned screens and triangles and the original's convex hulls. An unset collision is the importer's default."""
    out = []
    for rec in plan_.records:
        for package in rec.outputs:
            got = ev.get(package)
            if got is None:
                out.append(f'{package}: no evidence')
                continue
            slots = rec.settings.get('slot_materials') or [v[1] for v in rec.settings.get('slots', [])]
            got_materials = [slot['material'] for slot in got['slots']]
            if got_materials != slots:
                out.append(f'{package}: slots {got_materials} are not {slots}')
            names = expected_slot_names(rec)
            for key in ('name', 'imported'):
                got_names = [slot[key] for slot in got['slots']]
                if got_names != names:
                    out.append(f'{package}: slot {key} names {got_names} are not {names}')
            lods = got['lods']
            if lods[0]['sections'] != list(range(len(slots))):
                out.append(f'{package}: LOD0 sections {lods[0]["sections"]} do not use every slot')
            if lods[0]['triangles'] != rec.settings['triangles']:
                out.append(f'{package}: LOD0 triangles {lods[0]["triangles"]} are not {rec.settings["triangles"]}')
            collision = got['collision']
            if rec.family == 'plants':
                plan_lods = rec.settings['lods']
                if len(lods) != len(plan_lods):
                    out.append(f'{package}: {len(lods)} LOD(s), the plan has {len(plan_lods)}')
                for lod, (_, screen) in zip(lods, plan_lods):
                    if abs(lod['screen'] - screen) > 1e-3:
                        out.append(f'{package}: screen {lod["screen"]} is not {screen}')
                tris = [lod['triangles'] for lod in lods]
                if any(b > a for a, b in zip(tris, tris[1:])):
                    out.append(f'{package}: triangles {tris} grow with the level')
                if (collision['trace'], collision['convex'], collision['simple'], collision['boxes']) != (
                        'CTF_USE_DEFAULT', 1, 0, 0):
                    out.append(f'{package}: collision {collision} is not the importer default (one convex hull)')
            elif rec.family == 'city-lods':
                if len(lods) != 1:
                    out.append(f'{package}: {len(lods)} LOD(s), the plan has 1')
                if (collision['trace'], collision['convex'], collision['simple']) != ('CTF_USE_DEFAULT', 0, 0):
                    out.append(f'{package}: collision {collision} is not none')
            else:
                chain = rec.settings['lod_chain']
                if [lod['triangles'] for lod in lods] != [c[2] for c in chain]:
                    out.append(f'{package}: chain triangles {[l["triangles"] for l in lods]} are not {[c[2] for c in chain]}')
                if [lod['screen'] for lod in lods] != [round(c[1], 3) for c in chain]:
                    out.append(f'{package}: chain screens {[l["screen"] for l in lods]} are not {[c[1] for c in chain]}')
                if collision['trace'] != 'CTF_USE_SIMPLE_AND_COMPLEX' or collision['convex'] != rec.settings.get('hulls', 0) \
                        or collision['simple'] != 0:
                    out.append(f'{package}: collision {collision} is not the original\'s (hulls {rec.settings.get("hulls", 0)})')
    return out


# --- the byte checks ------------------------------------------------------------------------------------------------------------

def package_file(game: Path, package: str) -> Path:
    return game / 'unreal' / 'Content' / (package[len('/Game/'):] + '.uasset')


def byte_check(game: Path, plan_: Plan) -> dict:
    """package -> (status, notes). The committed bytes must name every slot material of the planned record; the LOD chain
    and the triangle counts are not in them, so every package still needs the mesh read."""
    out = {}
    for rec in plan_.records:
        for package in rec.outputs:
            path = package_file(game, package)
            if not path.is_file() or records.is_lfs_pointer(path):
                out[package] = ('no bytes', ['committed package is an LFS pointer or missing'])
                continue
            data = path.read_bytes()
            slots = rec.settings.get('slot_materials') or [v[1] for v in rec.settings.get('slots', [])]
            notes = [f'{m} is not in the bytes' for m in slots if m.encode() not in data]
            out[package] = ('read', notes or ['slot materials are in the bytes; LOD chain and triangles need the read'])
    return out


# --- the claim ----------------------------------------------------------------------------------------------------------------------

def _owner_of_text(text: str) -> str:
    match = re.search(r'(?m)^owner = "([^"]+)"$', text)
    return match.group(1) if match else ''


def build_writes(game: Path, plan_: Plan) -> dict:
    """The one write: {'writes': {rel: bytes}, 'deletes': [rel]}. The new records and their src/ copies; the adopted records
    give up their outputs (a record left with none is deleted, with its verified.json); and each saved-object record that
    references a moved adopted record names the new records instead (over-referencing the unit's records, as the train's
    prop records do: `references` is not part of a fingerprint)."""
    writes, deletes = {}, []
    for rec in plan_.records:
        folder = 'assets/' + rec.id
        writes[f'{folder}/asset.toml'] = record_text(rec).encode()
        for src in rec.sources:
            writes[f'{folder}/{src.path}'] = src.file.read_bytes()
    by_adopted = {}
    for rec in plan_.records:
        by_adopted.setdefault(rec.adopted, set()).update(rec.outputs)
    new_ids = {}
    for rec in plan_.records:
        new_ids.setdefault(rec.adopted, set()).add(rec.id)
    for adopted_id, packages in sorted(by_adopted.items()):
        folder = game / 'assets' / adopted_id
        rel = f'assets/{adopted_id}/asset.toml'
        text = (folder / 'asset.toml').read_text()
        listed = {o.package for o in records.load_asset(folder / 'asset.toml').outputs}
        if not listed <= packages:
            raise PlanError(f'{adopted_id}: lists packages no record plans; refused')
        new = recover._drop_outputs(text, listed)
        if not tomllib.loads(new).get('outputs'):
            deletes.append(rel)
            if (folder / 'verified.json').is_file():
                deletes.append(f'assets/{adopted_id}/verified.json')
        else:
            writes[rel] = new.encode()
    moved = set(by_adopted)
    all_moved = {rec_pkg for rec in plan_.records for rec_pkg in rec.outputs}
    for folder_rel in sorted({'/'.join(i.split('/')[:-1]) for i in moved}):
        units_rel = f'assets/{folder_rel}/units.json'
        units_path = game / units_rel
        if not units_path.is_file():
            continue
        text = units_path.read_text()
        units = json.loads(text)
        if json.dumps(units, indent=1, ensure_ascii=False) + '\n' != text:
            raise PlanError(f'{units_rel} is not in the form adoption writes; edit it by hand')
        packages = units.get('packages', {})
        for package in list(packages):
            if package in all_moved:
                packages.pop(package)
        new_text = json.dumps(units, indent=1, ensure_ascii=False) + '\n'
        if new_text != text:
            writes[units_rel] = new_text.encode()
    for path in records.record_paths(game):
        rel = path.relative_to(game).as_posix()
        if rel in writes or any(rel == f'assets/{i}/asset.toml' for i in moved):
            continue
        text = path.read_text()
        match = re.search(r'(?m)^references = \[(.*)\]$', text)
        refs = re.findall(r'"([^"]+)"', match.group(1)) if match else []
        hit = [r for r in refs if r in moved]
        if not hit:
            continue
        others = text[:match.start()] + text[match.end():]
        if any(f'"{r}"' in others for r in hit):
            raise PlanError(f'{rel} names {hit} outside its references line; refused')
        kept = [r for r in refs if r not in moved]
        for adopted_id in hit:
            kept += sorted(new_ids[adopted_id])
        line = 'references = [' + ', '.join(f'"{r}"' for r in sorted(set(kept))) + ']'
        writes[rel] = (text[:match.start()] + line + text[match.end():]).encode()
    return {'writes': writes, 'deletes': sorted(set(deletes))}


def scopes_of_ops(ops: dict) -> list:
    """Every owner scope a write or delete touches: the new records' and the rewritten referencers' (and the adopted ones')."""
    owners = set()
    for rel, data in ops['writes'].items():
        if rel.endswith('asset.toml'):
            owners.add(_owner_of_text(data.decode()))
    for rel in ops['deletes']:
        if rel.endswith('asset.toml'):
            owners.add(_owner_of_text((Path(GAME, rel)).read_text()))
    return sorted(o for o in owners if o)


def claimed_paths(ops: dict) -> list:
    return sorted(set(ops['writes']) | set(ops['deletes']))


def materialize(game: Path, plan_: Plan, claim: str, *, lockable=apply.lockable_present, echo=print) -> str:
    apply.Journal(game).recover(claim)
    ops = build_writes(game, plan_)
    scopes = scopes_of_ops(ops)
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in claimed_paths(ops)], claim,
                            'Brine Cove plants and city tree packages', scopes=scopes)
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=scopes, lockable=lockable)
    echo(f'materialize: {len(plan_.records)} record(s) written; {len(plan_.packages)} package(s) moved')
    return 'moved'


# --- reporting -----------------------------------------------------------------------------------------------------------------------

def summary(plan_: Plan, checks: dict) -> str:
    counts = {}
    for status, _ in checks.values():
        counts[status] = counts.get(status, 0) + 1
    fams = {}
    for rec in plan_.records:
        fams[rec.family] = fams.get(rec.family, 0) + len(rec.outputs)
    lines = [f'records planned: {len(plan_.records)}; packages planned: {len(plan_.packages)} {fams}; unmapped: {len(plan_.unmapped)}',
             'byte checks: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items()))]
    lines += [f'  unmapped: {u}' for u in plan_.unmapped[:10]]
    return '\n'.join(lines)


def table(plan_: Plan, checks: dict) -> str:
    """One row per package: its origin, its record, the committed bytes, and what the mesh read settled."""
    rows = ['| Package | Planned record | Donor origin and evidence | Committed bytes | Status |', '|---|---|---|---|---|']
    status_of = {'city-lods': 'determined by the read (agrees); ready for the claimed import',
                 'plants': 'determined by the read (agrees); waits on the editor run of the new-package LOD step',
                 'city-v4': 'determined by the read (agrees); waits on the editor run of the FBX chain-level step'}
    origin_of = {'plants': 'GLB LOD0 and the donor generate_lods plan', 'city-lods': 'donor FBX level (standalone)',
                 'city-v4': 'citysurfaces original FBX and two donor FBX levels'}
    for rec in plan_.records:
        for package in rec.outputs:
            status, notes = checks.get(package, ('no bytes', []))
            pin = rec.sources[0].sha256[:10] + '…'
            rows.append(f'| `{package}` | `{rec.id}` | {origin_of[rec.family]}; {rec.sources[0].path} sha256 `{pin}` | '
                        f'{"; ".join(notes)} | {status_of[rec.family]} |')
    return '\n'.join(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Plan the Brine Cove plant and city tree residual records (see the docstring).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--table', action='store_true', help='print the markdown table')
    mode.add_argument('--paths', action='store_true', help='print every claim path and scope, and exit')
    mode.add_argument('--claim', metavar='TASK', help='write the records and move the outputs under this claim')
    parser.add_argument('--donor', metavar='DIR', help='the donor build/yorimichi folder (default: $YV2_DONOR_BUILD)')
    args = parser.parse_args(argv)
    donor = Path(args.donor).expanduser() if args.donor else donor_default()
    if donor is None or not donor.is_dir():
        print('plant_sources: no donor folder (pass --donor or set YV2_DONOR_BUILD)', file=sys.stderr)
        return 1
    try:
        plan_ = plan(GAME, donor)
        if args.claim:
            materialize(GAME, plan_, args.claim)
            return 0
        if args.paths:
            ops = build_writes(GAME, plan_)
            print('\n'.join(f'{GAME_REL}/{rel}' for rel in claimed_paths(ops)))
            print('scopes: ' + ' '.join(scopes_of_ops(ops)))
            return 0
        checks = byte_check(GAME, plan_)
        print(table(plan_, checks) if args.table else summary(plan_, checks))
        return 0
    except (PlanError, records.RecordError, apply.SplitError) as error:
        print(f'plant_sources: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
