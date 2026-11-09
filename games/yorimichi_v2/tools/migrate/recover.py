"""Source recovery: give the packages of a donor-generated family back their sources (docs/inventory/sources.md, section 5).

    uv run python games/yorimichi_v2/tools/migrate/recover.py FAMILY --donor DONOR_OUT          (plan only)
    uv run python games/yorimichi_v2/tools/migrate/recover.py FAMILY --donor DONOR_OUT --apply  (write the records)

FAMILY names an entry of FAMILIES. DONOR_OUT is the donor build's output folder for that family. For each donor
output the family maps to the adopted package it became, the tool writes a generated record: the donor file is copied
into the record's `src/` and pinned by sha256, its recipe is the donor's own import setting (only importers the V2
editor supports: static-mesh and texture), and the record owns that one package. The adopted record that held the
package keeps only what is not generated (its `[[outputs]]` and their verified files), and is deleted when nothing is
left. A record that referenced it (a saved object placing its model) then references the records owning the packages
it uses, read from its own saved bytes. Each generated record is imported later by the controller (`tools/import/run.py ID`), which writes its
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
    lod_sources: list[Path] = field(default_factory=list)   # LOD1.. donor files of a per-LOD-source chain
    expected: dict[str, str] = field(default_factory=dict)  # file name -> the donor report's sha256 (lod_sources)

    def files(self) -> list[Path]:
        return [self.source, *self.lod_sources]


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


def in_family(record_id: str, family: str) -> bool:
    """An adopted record of the family: adopted/<family>/..., or adopted/<family> itself (a one-record family)."""
    return record_id == f'adopted/{family}' or record_id.startswith(f'adopted/{family}/')


def adopted_packages(game: Path, family: str) -> dict[str, str]:
    """package -> adopted record ID, for every adopted record of the family."""
    owner = {}
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if in_family(asset.id, family) and not asset.sources and asset.recipe is None:
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


CITY_DESTINATION = '/Game/Experiments/CitySurfaces/v1_128m'


def city_slot_materials(slots: list[str]) -> dict[str, str]:
    """The donor's binding of a piece's authored slots (city_tile_products.py material_paths): HDS_road binds
    MI_Road, every other HDS_<slug> the Hidamari MI_HD_<slug>."""
    out = {}
    for name in slots:
        if not re.fullmatch(r'HDS_[a-z][a-z0-9_]*', name):
            raise RecoverError(f'unsupported city material slot {name!r}')
        slug = name.removeprefix('HDS_')
        out[name] = '/Game/Japan/Materials/MI_Road' if slug == 'road' else f'/Game/Japan/Hidamari/Materials/MI_HD_{slug}'
    return out


def plan_citysurfaces(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's city surface partition (city_surface_tiles/v1_128m: manifest.json, import-report.json): one FBX per
    tile piece. A source with one authored slot binds the report's material; one with several binds each imported
    slot by its authored name (city_slot_materials, the donor's piece_material_paths), as a piece may hold only some
    of its source's slots. The donor sets
    full-precision UVs on every piece and picks collision per source: complex-as-simple for a source without authored
    UCX hulls, simple-and-complex (hulls imported, each piece's own count checked) for one with them."""
    manifest, report = _json(donor / 'manifest.json'), _json(donor / 'import-report.json')
    generated, unmapped = [], []
    for name, source in manifest['sources'].items():
        bound = {row['name']: row for row in report.get(name, [])}
        for tile in source['tiles']:
            piece = tile['name']
            package = f'{CITY_DESTINATION}/{piece}'
            tail = ident(piece[len('HD_'):]) if piece.startswith('HD_') else ident(piece)
            # A piece this family already recovered is planned again, so a corrected recipe reaches its record.
            if package not in owner and all_owner.get(package) != f'prop/citysurfaces/{tail}':
                unmapped.append(f'{name}/{piece}.fbx (its package is not in a source-less city surface record)')
                continue
            row = bound.get(piece)
            material = row['material'].split('.', 1)[0] if row else ''
            authored = source.get('source_material_slots') or []
            materials = sorted(set(city_slot_materials(authored).values())) if len(authored) > 1 else [material]
            orphans = [m for m in materials if not m or m not in all_owner]
            if orphans:
                unmapped.append(f'{name}/{piece}.fbx (material {orphans[0] or "unbound"} owned by no record)')
                continue
            # The report is what Unreal kept; it drops a few degenerate slivers of a UCX-hull source. The record keeps
            # the source's count, and the importer accepts down to 98 % of it, so the report must be in that window.
            if not tile['triangles'] * .98 <= row['triangles'] <= tile['triangles']:
                raise RecoverError(f'{piece}: the import report has {row["triangles"]} triangles, outside 98-100 % '
                                   f'of the source {tile["triangles"]}')
            generated.append(Generated(
                id=f'prop/citysurfaces/{tail}', kind='static-mesh', owner=f'shared/citysurfaces/{tail}',
                package=package, source=donor / name / f'{piece}.fbx',
                settings={**({'slot_map': city_slot_materials(authored)} if len(authored) > 1
                             else {'slot_materials': [material]}),
                          'triangles': tile['triangles'], 'full_precision_uvs': True,
                          **({'collision': 'simple_and_complex', 'hulls': tile['collision_hulls']}
                             if source['source_collision_hulls'] else {'collision': 'complex'})},
                references=sorted({all_owner[m] for m in materials}),
                about=f'{piece}: one city surface piece of {name} ({tile["triangles"]} triangles)',
                expected_sha=tile['sha256']))
    return Plan('experiments/citysurfaces', generated, unmapped, {})


TRAIN_SAVED = HERE / 'saved' / 'belmontetrain.json'


def plan_belmontetrain(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's Belmonte train (belmonte-train: service/service.json, service/import-report.json, the Train Builder's
    GLBs; import_belmonte_train.py): each vehicle from its LOD0-LOD2 files with its fixed boxes as simple-as-complex
    collision, and each door leaf (one LOD, no shapes). Their materials and textures stay editor-owned in the adopted
    records (the plan's separated responsibilities). The furniture records already carry their authored models and
    are not source-less, so they are not part of this family's recovery. The donor
    made the slots while importing, so each recipe names the saved slot table and LOD sections
    (saved/belmontetrain.json, read from the committed packages), which the import must reproduce exactly."""
    service, report = _json(donor / 'service' / 'service.json'), _json(donor / 'service' / 'import-report.json')
    saved = _json(TRAIN_SAVED)['meshes']
    generated, unmapped = [], []

    def add(package, rid, scope, files, about, collision, expected=None):
        if package not in owner:
            unmapped.append(f'{files[0].relative_to(donor)} (its package is not in a source-less train record)')
            return
        mesh = saved[package]
        materials = [material for _, material in mesh['slots']]
        missing = sorted({m for m in materials if m not in all_owner})
        if missing:
            unmapped.append(f'{files[0].relative_to(donor)} (materials owned by no record: {", ".join(missing[:3])})')
            return
        chain = [[f'src/{f.name}', *lod] for f, lod in zip(files, mesh['lods'], strict=True)]
        generated.append(Generated(
            id=rid, kind='static-mesh', owner=scope, package=package, source=files[0], lod_sources=files[1:],
            settings={'lod_chain': chain, 'slots': mesh['slots'], **collision},
            references=sorted({all_owner[m] for m in materials}), about=about, expected=expected or {}))

    for vehicle in service['consist']['vehicles']:
        name, package = vehicle['name'], vehicle['mesh'].split('.', 1)[0]
        unit = owner.get(package, '').rsplit('/', 1)[-1] or slug(name[len('SM_BT_'):])
        files = [(donor / level).resolve() for level in vehicle['levels']]
        boxes = [[float(v) for v in box] for box in vehicle['collision']]
        held = saved[package]['boxes'] if package in saved else []
        as_saved = [[(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2, b[3] - b[0], b[4] - b[1], b[5] - b[2]]
                    for b in boxes]
        if len(held) != len(boxes) or any(abs(a - b) > .01 for x, y in zip(held, as_saved) for a, b in zip(x, y)):
            raise RecoverError(f'{name}: the donor\'s {len(boxes)} collision boxes are not the saved {len(held)}')
        add(package, f'prop/belmontetrain/{unit}', f'shared/belmontetrain/{unit}', files,
            f'{name}: the {unit} vehicle, LOD0-LOD{len(files) - 1}, {len(boxes)} collision boxes',
            {'collision': 'boxes', 'boxes': boxes}, report['vehicles'].get(name, {}).get('sources'))
        for door in vehicle['doors']:
            for leaf in door['leaves']:
                if not leaf.get('glb'):
                    continue
                leaf_package = leaf['mesh'].split('.', 1)[0]
                tail = slug(leaf_package.rsplit('/', 1)[1][len(f'SM_BTD_{name[len("SM_BT_"):]}_'):])
                add(leaf_package, f'prop/belmontetrain/{unit}-door-{tail}', f'shared/belmontetrain/{unit}',
                    [(donor / leaf['glb']).resolve()], f'{leaf_package.rsplit("/", 1)[1]}: a {unit} door leaf',
                    {'collision': 'boxes', 'boxes': []})
    return Plan('belmontetrain', generated, unmapped, {})


# --- Small source-less families: skatepark, megapark seam, swordcamp, fx, villageatomic ---------------------------------
# Not planned, with the reason (docs/inventory/sources.md): materials and material instances are built in the donor editor
# (no V2 importer for them); racing (M_RacingTv) and skateruntime (a custom data asset) have no mesh or texture input;
# experiments/citytrees are LOD-chain duplicates of citysurfaces pieces whose LOD files are FBX, and the V2 LOD chain imports
# glTF levels only (see the report of the recovery branch).
SKATEPARK_ROOT = '/Game/SkatePark'
SKATEPARK_BOARD_MATERIAL = '/Game/Japan/Materials/M_Village'   # import_skatepark.py: the board parts take M_Village


def _texture_record(rid: str, package: str, source: Path, settings: dict, about: str, sha: str | None = None) -> Generated:
    tail = rid.split('/', 1)[1]
    return Generated(id=rid, kind='texture', owner=f'shared/{tail}', package=package, source=source, settings=settings,
                     about=about, expected_sha=sha)


def plan_skatepark(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's skatepark outputs (import_skatepark.py): assets/<SM_*>.fbx (the park pieces), board/<SM_Skate*>.fbx,
    textures/<key>-<role>.png. A park piece binds each imported slot (Pier_<key>) to /Game/SkatePark/Materials/M_Pier_<key>
    (build-report material_slots); a board part has one slot on M_Village. A piece that blocks (runtime-park.json) is
    complex-as-simple, any other has no shapes (the donor sets simple-as-complex and imports none). 'painted' reuses the
    steel maps (the donor's specs['painted']), and each texture is sRGB for albedo, normal-map compression for normal."""
    build, park = _json(donor / 'build-report.json'), _json(donor / 'runtime-park.json')
    maps = _json(donor / 'textures' / 'textures.json')
    maps['painted'] = maps['steel']
    blocks = {row['name']: row['blocks'] for row in park['meshes']}
    exports = build['identity']['exports']
    generated, unmapped, used = [], [], set()
    for key, spec in sorted(maps.items()):
        for role, file in sorted(spec['maps'].items()):
            name = f'T_Pier_{key}_{role}'
            used.add(file)
            generated.append(_texture_record(
                f'texture/skatepark/pier-{key}-{role}', f'{SKATEPARK_ROOT}/Textures/{name}', donor / 'textures' / file,
                {'srgb': role == 'albedo', 'compression': 'TC_NORMALMAP' if role == 'normal' else 'TC_DEFAULT'},
                f'{name}: the {role} map of the {key} pier surface (donor texture {file})', spec['sha256'][role]))
    for rel, digest in sorted(exports.items()):
        name = rel.rsplit('/', 1)[1][:-len('.fbx')]
        board = rel.startswith('board/')
        package = f'{SKATEPARK_ROOT}/Board/{name}' if board else f'{SKATEPARK_ROOT}/{name}'
        if package not in owner:
            unmapped.append(f'{rel} (its package is not in a source-less skatepark record)')
            continue
        if board:
            slots = {'slot_materials': [SKATEPARK_BOARD_MATERIAL]}
            collision, refs = 'none', [all_owner[SKATEPARK_BOARD_MATERIAL]]
        else:
            surfaces = {slot: f'{SKATEPARK_ROOT}/Materials/M_{slot}' for slot in build['material_slots'][name]}
            missing = [m for m in surfaces.values() if m not in all_owner]
            if missing:
                unmapped.append(f'{rel} (material {missing[0]} owned by no record)')
                continue
            slots = {'slot_map': surfaces}
            collision, refs = ('complex' if blocks[name] else 'none'), sorted({all_owner[m] for m in surfaces.values()})
        tail = ident(name[len('SM_'):])
        generated.append(Generated(
            id=f'prop/skatepark/{tail}', kind='static-mesh', owner=f'shared/skatepark/{tail}', package=package,
            source=donor / rel, settings={**slots, 'triangles': build['meshes'][name]['triangles'], 'collision': collision},
            references=refs, about=f'{name}: one skate park mesh ({build["meshes"][name]["triangles"]} triangles)',
            expected_sha=digest))
    for path in sorted((donor / 'textures').glob('*.png')):
        if path.name not in used:
            unmapped.append(f'textures/{path.name}')
    return Plan('skatepark', generated, unmapped, {})


def plan_megapark(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The two seam meshes joining the park to the zeppelin footbridge (fbx/manifest.json): SM_MP_Seam binds each imported
    slot M_<hash>_Seam to /Game/MegaPark/Materials/MI_<hash>_Seam (import_megapark.py), UC_MP_Seam is its one-sided
    collision twin with no material. Both are complex-as-simple with full-precision UVs. The section meshes have their own
    npz sources in their adopted records and are not part of this recovery; the material instances stay editor-owned."""
    manifest = _json(donor / 'fbx' / 'manifest.json')
    generated, unmapped = [], []
    for row in manifest['exports']:
        name = row['asset']
        if not name.endswith('_Seam'):
            continue
        package = f'/Game/MegaPark/Meshes/{name}'
        slots = row['metadata']['slots']
        materials = {} if name.startswith('UC_') else {s: f'/Game/MegaPark/Materials/MI_{s[2:]}' for s in slots}
        missing = [m for m in materials.values() if m not in all_owner]
        if package not in owner or missing:
            unmapped.append(f'fbx/{row["primary"]} (' + (f'material {missing[0]} owned by no record' if missing
                                                          else 'its package is not in a source-less megapark record') + ')')
            continue
        generated.append(Generated(
            id=f'prop/megapark/{"seam" if materials else "seam-collision"}', kind='static-mesh',
            owner=f'shared/megapark/{"seam" if materials else "seam-collision"}', package=package,
            source=donor / 'fbx' / row['primary'],
            settings={**({'slot_map': materials} if materials else {}), 'triangles': row['triangles'],
                      'collision': 'complex', 'full_precision_uvs': True},
            references=sorted({all_owner[m] for m in materials.values()}),
            about=f'{name}: the {"render" if materials else "collision"} mesh of the park seam ({row["triangles"]} triangles)',
            expected_sha=row['sha256']))
    return Plan('megapark', generated, unmapped, {})


SWORDCAMP_SOLID = {'SM_CampJinmaku', 'SM_CampFirePit', 'SM_CampWeaponRack', 'SM_CampBales'}   # import_swordcamp.py SOLID_PROPS


def plan_swordcamp(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's swordcamp outputs (import_swordcamp.py): fbx/<SM_*>.fbx on M_SwordCamp, and the atlas texture. The four
    camp props keep their one authored UCX hull as simple-and-complex collision (SOLID_PROPS); the ronin equipment has none."""
    manifest = _json(donor / 'fbx' / 'manifest.json')
    material = '/Game/SwordCamp/Materials/M_SwordCamp'
    generated, unmapped = [], []
    if material not in all_owner:
        raise RecoverError(f'{material} is owned by no record')
    generated.append(_texture_record(
        'texture/swordcamp/atlas', '/Game/SwordCamp/Textures/T_SwordCampAtlas', donor / 'swordcamp_atlas.jpg',
        {'srgb': True}, 'T_SwordCampAtlas: the Sunburst colour atlas of every Sword Camp mesh (donor swordcamp_atlas.jpg)'))
    for row in manifest['exports']:
        name, hulls = row['asset'], row['metadata']['collision_hulls']
        package = f'/Game/SwordCamp/Assets/{name}'
        if package not in owner or row['metadata']['slots'] != ['M_SwordCamp']:
            unmapped.append(f'fbx/{row["primary"]} (not a one-slot M_SwordCamp mesh of a source-less swordcamp record)')
            continue
        if (name in SWORDCAMP_SOLID) != (hulls > 0):
            raise RecoverError(f'{name}: {hulls} hulls does not match the donor collision policy')
        tail = ident(name[len('SM_'):])
        generated.append(Generated(
            id=f'prop/swordcamp/{tail}', kind='static-mesh', owner=f'shared/swordcamp/{tail}', package=package,
            source=donor / 'fbx' / row['primary'],
            settings={'slot_materials': [material], 'triangles': row['triangles'],
                      **({'collision': 'simple_and_complex', 'hulls': hulls} if hulls else {'collision': 'none'})},
            references=[all_owner[material]], about=f'{name}: one Sword Camp mesh ({row["triangles"]} triangles)',
            expected_sha=row['sha256']))
    return Plan('swordcamp', generated, unmapped, {})


def plan_fx(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's combat_fx textures (unreal_import.json: /Game/FX/Textures/T_FX_*, one PNG each, imported not-sRGB).
    The FX materials are built in the donor editor and stay editor-owned."""
    listed = _json(donor / 'unreal_import.json')['textures']
    generated, unmapped = [], []
    for path in listed:
        package = path.split('.', 1)[0]
        name = package.rsplit('/', 1)[1]
        if package not in owner:
            unmapped.append(f'{name}.png (its package is not in a source-less fx record)')
            continue
        generated.append(_texture_record(
            f'texture/fx/{slug(name[len("T_FX_"):])}', package, donor / f'{name}.png', {'srgb': False},
            f'{name}: a combat effect sprite mask (donor texture {name}.png)'))
    return Plan('fx', generated, unmapped, {})


VILLAGE_DESTINATION = '/Game/Experiments/VillageAtomic/v1_atomic'
VILLAGE_MATERIAL = '/Game/Japan/Materials/M_Village'


def plan_villageatomic(game: Path, donor: Path, owner: dict[str, str], all_owner: dict[str, str]) -> Plan:
    """The donor's village atomic exports (DONOR is atomic_regions/village: assets/manifest.json, assets/<piece>.fbx;
    village/atomic-manifest.json two folders up names each parent's collision policy). Every piece has the one slot
    VillagePalette, bound to M_Village. A parent with source_collision_hulls imports its UCX hulls (a piece with none
    keeps no shapes), the ground is complex-as-simple, as import_village_atomic.py sets them. Half-precision UVs are
    the importer's default."""
    manifest = _json(donor / 'assets' / 'manifest.json')
    parents = _json(donor.parents[1] / 'village' / 'atomic-manifest.json')['parents']
    policy = {piece['name']: group['collision'] for group in parents.values() for piece in group['pieces']}
    generated, unmapped = [], []
    if VILLAGE_MATERIAL not in all_owner:
        raise RecoverError(f'{VILLAGE_MATERIAL} is owned by no record')
    for row in manifest['exports']:
        name = row['asset']
        package = f'{VILLAGE_DESTINATION}/{name}'
        if package not in owner or row['metadata']['slots'] != ['VillagePalette'] or name not in policy:
            unmapped.append(f'assets/{row["primary"]} (not a VillagePalette piece of a source-less village record)')
            continue
        hulls = row['metadata']['collision_hulls']
        collision = ({'collision': 'complex'} if policy[name] == 'complex_as_simple'
                     else {'collision': 'simple_and_complex', 'hulls': hulls})
        tail = ident(name[len('Village_'):])
        generated.append(Generated(
            id=f'prop/villageatomic/{tail}', kind='static-mesh', owner=f'shared/villageatomic/{tail}', package=package,
            source=donor / 'assets' / row['primary'],
            settings={'slot_materials': [VILLAGE_MATERIAL], 'triangles': row['triangles'], **collision},
            references=[all_owner[VILLAGE_MATERIAL]],
            about=f'{name}: one village piece ({row["triangles"]} triangles, {hulls} collision hulls)',
            expected_sha=row['sha256']))
    return Plan('experiments/villageatomic', generated, unmapped, {})


FAMILIES = {'hippodrome': plan_hippodrome, 'belmonte': plan_belmonte, 'experiments/islandterrain': plan_island,
            'brinecove': plan_brinecove, 'experiments/citysurfaces': plan_citysurfaces,
            'belmontetrain': plan_belmontetrain}
FAMILIES.update({'skatepark': plan_skatepark, 'megapark': plan_megapark, 'swordcamp': plan_swordcamp, 'fx': plan_fx,
                 'experiments/villageatomic': plan_villageatomic})


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
        for path in gen.files():
            if not path.is_file():
                raise RecoverError(f'donor file {path.name} is missing')
    # Every donor file must be the bytes the donor's report names (hippodrome: build-report sha256), or nothing is written.
    for gen in plan.generated:
        wanted = {gen.source.name: gen.expected_sha, **gen.expected}
        for path in gen.files():
            if wanted.get(path.name) and records.sha256_file(path) != wanted[path.name]:
                raise RecoverError(f'{path.name} differs from the donor report ({wanted[path.name][:12]}); '
                                   'rebuild the donor first')
    kept = {}
    generated_packages = set(packages)
    for path in records.record_paths(game):
        asset = records.load_asset(path)
        if in_family(asset.id, family):
            left = [o.package for o in asset.outputs if o.package not in generated_packages]
            kept[asset.id] = left
    plan.kept = kept
    return plan


def _toml(value) -> str:
    if isinstance(value, dict):     # an inline table: slot_map = {HDS_paint = "...", ...}
        return '{' + ', '.join(f'{k} = {_toml(v)}' for k, v in value.items()) + '}'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml(v) for v in value) + ']'
    return json.dumps(value)        # a string, int or float: the same text in TOML


def _record_text(gen: Generated, digests: list[tuple[str, str]]) -> str:
    lines = [f'# Recovered from the donor generator (tools/migrate/recover.py): {gen.about}.',
             '# The donor file is committed in src/ and pinned by sha256; the record is imported by the V2 editor and',
             '# verified by tools/import/run.py, never edited by hand.',
             'schema = 1', f'id = "{gen.id}"', f'kind = "{gen.kind}"', 'authority = "generated"',
             f'owner = "{gen.owner}"']
    if gen.references:
        lines.append('references = [' + ', '.join(f'"{r}"' for r in gen.references) + ']')
    for name, digest in digests:
        lines += ['', '[[sources]]', f'path = "src/{name}"', f'sha256 = "{digest}"']
    lines += ['', '[recipe]', f'importer = "{gen.kind}"', 'version = 1', '', '[recipe.settings]']
    lines += [f'{key} = {_toml(value)}' for key, value in gen.settings.items()]
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
    moved_from: dict[str, set[str]] = {}   # shrunk or deleted record -> the packages it lost to generated records
    for gen in plan.generated:
        folder = game / 'assets' / gen.id
        digests = [(path.name, records.sha256_file(path)) for path in gen.files()]
        text = _record_text(gen, digests)
        if ((folder / 'asset.toml').is_file() and (folder / 'asset.toml').read_text() == text
                and all((folder / 'src' / path.name).is_file() for path in gen.files())):
            continue
        if folder.exists() and any(folder.iterdir()) and not (folder / 'asset.toml').is_file():
            raise RecoverError(f'{folder} exists and is not a record of this tool; refusing to write over it')
        (folder / 'src').mkdir(parents=True, exist_ok=True)
        for path in gen.files():
            shutil.copy2(path, folder / 'src' / path.name)
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
        moved_from[record_id] = before & gen_packages
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
    changed['retargeted'] = _retarget(game, plan, moved_from)
    return changed


def _used_bytes(game: Path, asset) -> bytes | None:
    """The consumer's own saved package bytes (which name the packages it uses), or None when they are not here."""
    data = b''
    for output in asset.outputs:
        for path in records.package_files(game, output.package):
            if path.is_file():
                if records.is_lfs_pointer(path):
                    return None
                data += path.read_bytes()
    return data or None


def _retarget(game: Path, plan: Plan, moved_from: dict[str, set[str]]) -> list[str]:
    """Point each consumer of a shrunk or deleted record at the records that now own the packages it uses.

    A consumer that names the old record keeps it only while it still uses a package the old record kept; each moved
    package it uses (read from its own saved bytes; all moved ones when those are not here) adds its new owner.
    Links to records that lost nothing (materials, generators) are untouched."""
    new_owner = {g.package: g.id for g in plan.generated}
    retargeted = []
    for asset_toml in records.record_paths(game):   # a record's copied donor sources may hold their own asset.toml
        asset = records.load_asset(asset_toml)
        hit = [r for r in asset.references + asset.input_dependencies if moved_from.get(r)]
        if not hit or asset.id in new_owner.values():
            continue
        used = _used_bytes(game, asset)
        uses = (lambda package: True) if used is None else (lambda package: package.encode() in used)
        replace = {}
        for old in hit:
            ids = sorted({new_owner[p] for p in moved_from[old] if uses(p)})
            old_toml = game / 'assets' / old / 'asset.toml'
            kept = [o.package for o in records.load_asset(old_toml).outputs] if old_toml.is_file() else []
            if kept and (not ids or any(uses(p) for p in kept)):
                ids = [old] + ids
            if not ids:
                raise RecoverError(f'{asset.id} references deleted {old} but uses none of its moved packages')
            replace[old] = ids
        text = asset_toml.read_text()
        for key in ('references', 'input_dependencies'):
            names = getattr(asset, key)
            if not any(n in replace for n in names):
                continue
            new = []
            for name in names:
                new += [n for n in replace.get(name, [name]) if n not in new]
            text = re.sub(rf'(?m)^{key} = \[.*\]$', f'{key} = [' + ', '.join(f'"{n}"' for n in new) + ']', text, count=1)
        if text == asset_toml.read_text():
            continue
        asset_toml.write_text(text)
        verified = asset_toml.parent / 'verified.json'
        if verified.is_file():
            body = _json(verified)
            deps = body.get('dependencies') or {}
            if any(d in replace for d in deps):
                out = {}
                for dep, digest in deps.items():
                    for name in replace.get(dep, [dep]):
                        state = game / 'assets' / name / 'verified.json'
                        if name == dep:
                            out[name] = digest
                        elif state.is_file():   # a generated record not imported yet records its state on import
                            out[name] = records.state_fingerprint(records.load_verified(state))
                body['dependencies'] = dict(sorted(out.items()))
                records.write_json(verified, body)
        retargeted.append(asset.id)
    return retargeted


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
                  f'deleted {len(changed["deleted"])}, retargeted {len(changed["retargeted"])}')
    except (RecoverError, RecordError) as error:
        print(f'recover failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
