"""@cc [owner:fontanierh,label:correctness] yorimichi-v2-single-writer
Source closure plan for the small open families (docs/inventory/exceptions.md, "Source closure still to classify").

Plan mode, the default, reads the committed adopted records, their verified bytes and, when --donor is given, the donor
checkout (read-only). It writes nothing:

    uv run python games/yorimichi_v2/tools/migrate/small_families.py [--game PATH] [--donor PATH] [--json]

`--claim TASK` is refused in this change: the journaled record write (one claim, moves outputs out of the adopted records)
has not been run and is not implemented here. Each family's classification, its donor evidence and its native reads are
in the table this prints; the donor is never written.

Each registry row states one adopted record, its family, what made its packages (the donor script and line), and the
status a reader can rely on:
- `planned`: an existing importer fits and every input is pinned by sha256 (plan only; nothing is imported);
- `need-read`: the donor script determines the origin, but a native read is needed to confirm the saved parameters;
- `blocked`: no importer or no recorded original fits, and the reason is stated;
- `unreal-authored`: the package is saved by the editor (a map), and keeps its editor-saved record form.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402

HIPPO_LOOSE = {   # adopted/hippodrome/loose_files package -> donor GLB name (region/glb, same bytes as the export)
    '/Game/Hippodrome/SM_HD_FinishPost': 'SM_HD_FinishPost',
    '/Game/Hippodrome/SM_HD_Grandstand': 'SM_HD_Grandstand',
    '/Game/Hippodrome/SM_HD_JudgesTower': 'SM_HD_JudgesTower',
    '/Game/Hippodrome/SM_HD_ToteBoard': 'SM_HD_ToteBoard',
}
TREEHOUSE_TEXTURES = {   # T_TH_<slug> <- build/yorimichi/treehouse/textures/<file> (import_treehouse.py:3)
    '/Game/Japan/Treehouse/Textures/T_TH_flat': 'flat.png',
    '/Game/Japan/Treehouse/Textures/T_TH_glass': 'glass.png',
    '/Game/Japan/Treehouse/Textures/T_TH_rope': 'rope.png',
}
ALPHA_PARENTS = ('M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent')   # import_megapark.py:76

# adopted record -> (family, origin, donor evidence, status, blocker or note)
REGISTRY = {
    'adopted/hippodrome/loose_files': ('hippodrome', 'generated static mesh (GLB, region/glb)',
        'donor world/regions/hippodrome/build.py via unreal/Scripts/import_hippodrome.py:161-177', 'planned',
        'static-mesh recipe needs the GLB copied to src/ and a native import; object records still reference this record'),
    'adopted/hippodrome/materials': ('hippodrome', 'generator master materials M_HD_Structure and M_HD_<surface>',
        'import_hippodrome.py:32-33 (SURFACES), :60-61 (M_HD_Structure)', 'blocked',
        'no importer for material masters (kind material has no recipe); parameters need a native read'),
    'adopted/hippodrome/meshes': ('hippodrome', 'Interchange sub-objects of the loose GLB imports',
        'import_hippodrome.py:102-103 (Meshes/<name> folder per GLB)', 'blocked',
        'referenced by the four loose meshes (18 files under unreal/Content name Hippodrome/Meshes/); retire only after a loose re-import'),
    'adopted/japan/treehouse/surface-flat': ('treehouse', 'generated texture T_TH_flat and MI_TH_flat',
        'import_treehouse.py:3-4; build/yorimichi/treehouse/textures/flat.png', 'planned',
        'texture recipe from the donor PNG; the glass PNG has the same sha256 (see the table)'),
    'adopted/japan/treehouse/surface-glass': ('treehouse', 'generated texture T_TH_glass and MI_TH_glass',
        'import_treehouse.py:3-4; build/yorimichi/treehouse/textures/glass.png', 'planned',
        'glass.png and flat.png are byte-identical in the donor; the two textures differ in V2 (8297 and 8303 bytes), so the import settings are not yet established'),
    'adopted/japan/treehouse/surface-pane': ('treehouse', 'generated MI_TH_pane (parent M_TH_Light)',
        'treehouse generator (adopted/japan/treehouse/generator); parent M_TH_Light', 'need-read',
        'material instance without its own texture; parameters need a native read'),
    'adopted/japan/treehouse/surface-rope': ('treehouse', 'generated texture T_TH_rope and MI_TH_rope',
        'import_treehouse.py:3-4; build/yorimichi/treehouse/textures/rope.png', 'planned',
        'the MI parent M_TreeHouse is owned by adopted/japan/treehouse/generator; the import settings are not yet confirmed'),
    'adopted/japan/treehouse/surface-trunk': ('treehouse', 'generated MI_TH_trunk (bark, RoomCut 0)',
        'import_treehouse.py:10; texture T_TH_bark owned by adopted/japan/treehouse/surface-bark', 'need-read',
        'material instance; its bark texture is owned elsewhere'),
    'adopted/megapark/shared-materials-wood': ('megapark', 'generator-built material instances MI_<key>',
        'import_megapark.py:166-221 (materials(report))', 'need-read',
        'parameters come from the donor import-report materials; the two-sided base-property override (lines 218-219) is not expressible in recipe v2'),
    'adopted/megapark/seam': ('megapark', 'generator-built seam instances MI_<key>_Seam',
        'import_megapark.py:166-221 with the seam scalars (SpecularScale, Gloss, LightmapOcclusion)', 'need-read',
        'as shared-materials-wood, plus the seam scalars'),
    'adopted/megapark/shared-materials-pavement': ('megapark', 'generator-built material instance',
        'import_megapark.py:166-221', 'need-read', 'as shared-materials-wood'),
    'adopted/megapark/standalone-level': ('megapark', 'editor-saved level built by a script from committed native source',
        'import_megapark.py:20-28 (LEVEL), :347 (main)', 'unreal-authored',
        'keeps its editor-saved form (authority editor); a native read lists the actors it references'),
    'adopted/skatepark/board': ('skatepark', 'generator master M_BoardDissolve',
        'board_dissolve_material.py:11-15', 'blocked', 'no importer for material masters; native read of the graph needed'),
    'adopted/skatepark/materials': ('skatepark', 'generator masters M_Pier_<surface>',
        'import_skatepark.py:137-173 (M_Pier_ and T_Pier_ textures)', 'blocked',
        'no importer for material masters; their textures are owned by texture/skatepark records'),
    'adopted/belmonte/shared-metal-glass': ('belmonte', 'generator-built MI_BM_<hash>',
        'world/regions/belmonte/material_preparation.py:21 (name from sha256 of the path)', 'need-read',
        'parent M_Belmonte is owned by adopted/belmonte/generator'),
    'adopted/belmonte/shared-water': ('belmonte', 'generator-built MI_BM_<hash>',
        'world/regions/belmonte/material_preparation.py:21', 'need-read', 'as shared-metal-glass'),
    'adopted/fx': ('fx', 'generator masters and instances (sprite materials)',
        'unreal/Scripts/import_combat_fx.py:82-87 (sprite_material, instance)', 'need-read',
        'the T_FX_* textures are owned by texture/fx records; the masters are script-built'),
    'adopted/japan/textures/plaza-harbor': ('plaza', 'textures of unknown generator',
        'plaza_material.py:45 only loads /Game/Japan/Textures/T_Arcade_paving; harbor_material.py:24-27 loads T_Harbor_<name>',
        'blocked', 'the producer of the donor paving PNGs is not located; not relabelled as editor-authored'),
    'adopted/japan/assets/bike': ('bike', 'generated wheel static meshes (Blender bike build)',
        'import_bike.py:40 (manifest parts); build/yorimichi/bike/Bike.blend and manifest.json', 'need-read',
        'the importer needs the bike manifest sha256 and the M_Bike parent (owned by adopted/japan/materials/base-materials)'),
    'adopted/swordcamp/materials': ('swordcamp', 'generator masters M_SwordCamp and M_RoninBody',
        'import_swordcamp.py:47-51 (M_SwordCamp), :117-122 (M_RoninBody)', 'need-read',
        'the atlas T_SwordCampAtlas is owned by texture/swordcamp/atlas'),
    'adopted/japan/hidamari/surface-flat': ('hidamari', 'generated MI_HD_flat (parent M_HDCity)',
        'city_material.py (hidamari generator), tools/hidamari_textures.py', 'need-read',
        'parent M_HDCity and T_HD_plaster are owned by adopted/japan/hidamari records'),
    'adopted/racing': ('racing', 'generator master M_RacingTv',
        'racing_tv_material.py:12-16', 'blocked', 'no importer for material masters; native read of the graph needed'),
    'adopted/seethrough': ('seethrough', 'generator material parameter collection MPC_SeeThrough',
        'see_through.py:47 and :246-253', 'blocked', 'no importer for parameter collections'),
    'adopted/skateruntime': ('skateruntime', 'generated RuntimeData data asset (31 MB)',
        'build.py:1813 (RuntimeData output); unreal/Scripts/skate_ride/verify_data.py:15', 'blocked',
        'no importer for data assets; the cooked data is the only copy in the editor'),
}
FAMILY_ORDER = ('megapark', 'hippodrome', 'treehouse', 'skatepark', 'belmonte', 'fx', 'plaza', 'bike', 'swordcamp', 'hidamari',
                'racing', 'seethrough', 'skateruntime')


class FamilyError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_pointer(path: Path) -> bool:
    with path.open('rb') as f:
        return f.read(40).startswith(b'version https://git-lfs')


def load_record(game: Path, record_id: str) -> records.Asset:
    rel = f'assets/{record_id}/asset.toml'
    path = game / rel
    if not path.is_file():
        raise FamilyError(f'{rel} is missing')
    asset = records.load_asset(path)
    if asset.id != record_id or asset.kind != 'adopted' or asset.sources or asset.recipe is not None:
        raise FamilyError(f'{rel}: not the source-less adopted record {record_id}')
    return asset


def byte_problems(game: Path, record_id: str) -> list[str]:
    """Each package file of the record must be hydrated and match its verified.json sha256."""
    verified = game / f'assets/{record_id}/verified.json'
    entries = json.loads(verified.read_text()).get('files', {}) if verified.is_file() else {}
    problems = []
    for rel, sha in sorted(entries.items()):
        path = game / rel
        if not path.is_file():
            problems.append(f'{rel}: missing')
        elif is_pointer(path):
            problems.append(f'{rel}: LFS pointer (not hydrated)')
        elif sha256_file(path) != sha:
            problems.append(f'{rel}: sha256 differs from verified.json')
    return problems


def package_refs(path: Path, own: str) -> list[str]:
    """/Game names a package's bytes name, other than itself and its own objects (LC_ALL=C grep -a)."""
    pattern = re.compile(rb'/Game/[A-Za-z0-9_/.\-]+')
    names = {m.decode() for m in pattern.findall(path.read_bytes())}
    return sorted(n.split('.')[0] for n in names if n.split('.')[0] != own and not n.endswith('/'))


def glb_materials(path: Path) -> list[str]:
    """The material names in a binary glTF's JSON chunk."""
    data = path.read_bytes()
    if data[:4] != b'glTF':
        raise FamilyError(f'{path.name} is not a binary glTF')
    length, kind = struct.unpack('<I4s', data[12:20])
    if kind != b'JSON':
        raise FamilyError(f'{path.name}: the first chunk is not JSON')
    doc = json.loads(data[20:20 + length].decode())
    return [m.get('name', '') for m in doc.get('materials', [])]


def donor_path(donor: Path | None, rel: str) -> Path | None:
    if donor is None:
        return None
    path = donor / rel
    return path if path.exists() else None


def hippodrome_meshes(game: Path, donor: Path | None) -> list[dict]:
    """Plan rows for the four loose hippodrome meshes: a static-mesh recipe on their donor GLB, pinned by sha256."""
    rows = []
    report_path = donor_path(donor, 'build/yorimichi/hippodrome/import-report.json')
    report = json.loads(report_path.read_text()) if report_path else {}
    for package, name in HIPPO_LOOSE.items():
        glb = donor_path(donor, f'build/yorimichi/hippodrome/region/glb/{name}.glb')
        row = {'package': package, 'glb': f'build/yorimichi/hippodrome/region/glb/{name}.glb',
               'glb_sha256': sha256_file(glb) if glb else None,
               'triangles': report.get(name, {}).get('triangles') if report else None}
        if glb:
            # The GLB's own material names. The slot binding is not guessed: the loose package's bytes name the master it
            # uses (M_HD_Structure, refs of adopted/hippodrome/loose_files), and that is the recipe's slot material.
            row['glb_materials'] = glb_materials(glb)
        rows.append(row)
    return rows


def treehouse_textures(game: Path, donor: Path | None) -> list[dict]:
    rows = []
    for package, png in TREEHOUSE_TEXTURES.items():
        path = donor_path(donor, f'build/yorimichi/treehouse/textures/{png}')
        rows.append({'package': package, 'png': f'build/yorimichi/treehouse/textures/{png}',
                     'png_sha256': sha256_file(path) if path else None})
    return rows


def megapark_report(donor: Path | None) -> dict:
    """The donor's MegaPark build report (build.json, read by import_megapark.py main): the instances it names, their
    parent by alpha mode, and the seam rows. Names are 'MI_' + the key without its 'M_' prefix (materials(), :194)."""
    path = donor_path(donor, 'build/yorimichi/megapark/build.json')
    if path is None:
        return {}
    materials = json.loads(path.read_text()).get('materials', {})
    parents, seams = {}, 0
    for entry in materials.values():
        parent = ALPHA_PARENTS[int(entry.get('alpha_mode', 0))]
        parents[parent] = parents.get(parent, 0) + 1
        seams += bool(entry.get('seam'))
    return {'materials': len(materials), 'parents': parents, 'seam_rows': seams,
            'names': sorted('MI_' + key[2:] for key in materials)}


def classify(game: Path, donor: Path | None = None) -> dict:
    """Every adopted record of the families: its packages, the byte checks and the registry row."""
    out = {'families': {}, 'records': [], 'packages': 0, 'problems': []}
    for record_id, (family, origin, evidence, status, note) in REGISTRY.items():
        asset = load_record(game, record_id)
        problems = byte_problems(game, record_id)
        packages = [o.package for o in asset.outputs]
        refs = {}
        for rel in json.loads((game / f'assets/{record_id}/verified.json').read_text()).get('files', {}):
            path = game / rel
            if path.is_file() and not is_pointer(path):
                refs[path.stem] = package_refs(path, '/Game/' + rel.split('unreal/Content/', 1)[1].rsplit('.', 1)[0])
        row = {'record': record_id, 'family': family, 'origin': origin, 'evidence': evidence, 'status': status,
               'note': note, 'packages': packages, 'byte_problems': problems, 'refs': refs}
        out['records'].append(row)
        out['packages'] += len(packages)
        out['problems'] += [f'{record_id}: {p}' for p in problems]
        fam = out['families'].setdefault(family, {'records': 0, 'packages': 0, 'planned': 0, 'need-read': 0,
                                                  'blocked': 0, 'unreal-authored': 0})
        fam['records'] += 1
        fam['packages'] += len(packages)
        fam[status] += 1
    out['hippodrome_meshes'] = hippodrome_meshes(game, donor)
    out['treehouse_textures'] = treehouse_textures(game, donor)
    out['megapark_report'] = megapark_report(donor)
    return out


def summary_lines(result: dict) -> list[str]:
    lines = [f"{'family':<12} {'records':>7} {'packages':>8} {'planned':>7} {'need-read':>9} {'blocked':>7} {'editor':>6}"]
    for family in FAMILY_ORDER:
        f = result['families'].get(family)
        if f:
            lines.append(f"{family:<12} {f['records']:>7} {f['packages']:>8} {f['planned']:>7} {f['need-read']:>9} "
                         f"{f['blocked']:>7} {f['unreal-authored']:>6}")
    lines.append(f"total packages {result['packages']}; byte problems {len(result['problems'])}")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--donor', type=Path, default=None, help='a donor checkout (read-only); donor evidence is skipped without it')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--claim', metavar='TASK', help='refused in this change (see the module docstring)')
    args = parser.parse_args(argv)
    if args.claim:
        print('refused: --claim is not implemented in this change; plan mode only', file=sys.stderr)
        return 2
    result = classify(args.game, args.donor)
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print('\n'.join(summary_lines(result)))
        for p in result['problems']:
            print('PROBLEM', p)
    return 0 if not result['problems'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
