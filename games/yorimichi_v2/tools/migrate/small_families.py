"""@cc [owner:fontanierh,label:correctness] yorimichi-v2-single-writer
Source closure plan for the small open families (docs/inventory/exceptions.md, "Source closure still to classify").

Plan mode, the default, reads the committed adopted records, their verified bytes and, when --donor is given, the donor
checkout (read-only). It writes nothing:

    uv run python games/yorimichi_v2/tools/migrate/small_families.py [--game PATH] [--donor PATH] [--json]
    uv run python games/yorimichi_v2/tools/migrate/small_families.py --donor PATH --paths
    uv run python games/yorimichi_v2/tools/migrate/small_families.py --donor PATH --claim TASK   # the one journaled write

`--paths` prints the claim paths, the owner scopes, and the lock paths (LFS-lockable files, such as the copied `src/` GLBs
and PNGs, are listed as `lock`, the rest as `path`). `--claim TASK` is the one journaled write: the new records and their
`src/` copies, the adopted records' outputs moved out, and the referencing records rewritten. It covers only the
determined rows in CLAIM_FAMILIES (the Hippodrome loose meshes and the plaza textures). The tree house textures are not
claimable: the texture recipe cannot express their settings yet. The donor is read only.

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
from dataclasses import dataclass, field
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402
import authority  # noqa: E402
import subprocess  # noqa: E402
import brinecove_split_apply as apply  # noqa: E402  (the journaled write every migrate step uses)
import recover  # noqa: E402  (_toml, _drop_outputs)

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

MASTER_NOTE = ' Loaded by the read as materials, not instances (report_materials cannot read them), so their parameters are unread. Classified, not blocked: a generator-built master keeps its editor-authority record, and its saved package is the only byte-level original of an editor-scripted generator.'
# adopted record -> (family, origin, donor evidence, status, blocker or note)
REGISTRY = {
    'adopted/hippodrome/loose_files': ('hippodrome', 'generated static mesh (GLB, region/glb)',
        'donor world/regions/hippodrome/build.py via unreal/Scripts/import_hippodrome.py:161-177', 'planned',
        'static-mesh recipe needs the GLB copied to src/ and a native import; object records still reference this record'),
    'adopted/hippodrome/materials': ('hippodrome', 'generator master materials M_HD_Structure and M_HD_<surface>',
        'import_hippodrome.py:32-33 (SURFACES), :60-61 (M_HD_Structure)', 'need-read',
        'generator-built masters; loaded, parameters unread.'+MASTER_NOTE),
    'adopted/hippodrome/meshes': ('hippodrome', 'Interchange sub-objects of the loose GLB imports',
        'import_hippodrome.py:102-103 (Meshes/<name> folder per GLB)', 'blocked',
        'referenced by the four loose meshes (18 files under unreal/Content name Hippodrome/Meshes/); retire only after a loose re-import'),
    'adopted/japan/treehouse/surface-flat': ('treehouse', 'generated texture T_TH_flat and MI_TH_flat',
        'import_treehouse.py:3-4 and :39-46 (sRGB, max size 1024, WORLD group); build/yorimichi/treehouse/textures/flat.png', 'planned',
        'claimable once docs/inventory/treehouse-textures-read.json confirms the three settings; the glass PNG has the same sha256'),
    'adopted/japan/treehouse/surface-glass': ('treehouse', 'generated texture T_TH_glass and MI_TH_glass',
        'import_treehouse.py:3-4 and :39-46; build/yorimichi/treehouse/textures/glass.png', 'planned',
        'glass.png and flat.png are byte-identical in the donor; the two textures differ in V2 (8297 and 8303 bytes), so the import settings are not yet established'),
    'adopted/japan/treehouse/surface-pane': ('treehouse', 'generated MI_TH_pane (parent M_TH_Light)',
        'treehouse generator (adopted/japan/treehouse/generator); parent M_TH_Light', 'need-read',
        'material instance without its own texture; parameters need a native read'),
    'adopted/japan/treehouse/surface-rope': ('treehouse', 'generated texture T_TH_rope and MI_TH_rope',
        'import_treehouse.py:3-4 and :39-46; build/yorimichi/treehouse/textures/rope.png', 'planned',
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
        'board_dissolve_material.py:11-15', 'need-read', 'generator-built master; loaded, parameters unread.'+MASTER_NOTE),
    'adopted/skatepark/materials': ('skatepark', 'generator masters M_Pier_<surface>',
        'import_skatepark.py:137-173 (M_Pier_ and T_Pier_ textures)', 'need-read',
        'generator-built masters; not yet read; their textures are owned by texture/skatepark records.'+MASTER_NOTE),
    'adopted/belmonte/shared-metal-glass': ('belmonte', 'generator-built MI_BM_<hash>',
        'world/regions/belmonte/material_preparation.py:21 (name from sha256 of the path)', 'need-read',
        'parent M_Belmonte is owned by adopted/belmonte/generator'),
    'adopted/belmonte/shared-water': ('belmonte', 'generator-built MI_BM_<hash>',
        'world/regions/belmonte/material_preparation.py:21', 'need-read', 'as shared-metal-glass'),
    'adopted/fx': ('fx', 'generator masters and instances (sprite materials)',
        'unreal/Scripts/import_combat_fx.py:82-87 (sprite_material, instance)', 'need-read',
        'the T_FX_* textures are owned by texture/fx records; the masters are script-built'),
    'adopted/japan/textures/plaza-harbor': ('plaza', 'textures imported from two tracked donor PNGs',
        'arcade_material.py:5-12 (T_Arcade_<name>) and harbor_material.py:24-27 (T_Harbor_<name>), both from world/regions/hidamari/textures/{paving,timber}.png',
        'planned', 'T_Arcade and T_Harbor packages of each name have equal sizes (2219461 and 1833653 bytes), so one import of each PNG is consistent; the PNGs are tracked in the donor source (paving sha256 0cf002e5..., timber d71b181a...)'),
    'adopted/japan/assets/bike': ('bike', 'generated wheel static meshes (Blender bike build)',
        'import_bike.py:36-46 (manifest parts, FBX per part under build/yorimichi/bike/assets)', 'blocked',
        'Bike.blend, the generator, is not tracked in the donor (git ls-files finds no .blend under the bike build): the FBX has no recorded generator, so it cannot be pinned. M_Bike is owned by adopted/japan/materials/base-materials'),
    'adopted/swordcamp/materials': ('swordcamp', 'generator masters M_SwordCamp and M_RoninBody',
        'import_swordcamp.py:47-51 (M_SwordCamp), :117-122 (M_RoninBody); atlas import :29-39', 'need-read',
        'generator-built masters; not yet read; the atlas T_SwordCampAtlas is owned by texture/swordcamp/atlas.'+MASTER_NOTE),
    'adopted/japan/hidamari/surface-flat': ('hidamari', 'generated MI_HD_flat (parent M_HDCity)',
        'city_material.py (hidamari generator), tools/hidamari_textures.py', 'need-read',
        'parent M_HDCity and T_HD_plaster are owned by adopted/japan/hidamari records'),
    'adopted/racing': ('racing', 'generator master M_RacingTv',
        'racing_tv_material.py:12-16', 'need-read', 'generator-built master; loaded, parameters unread.'+MASTER_NOTE),
    'adopted/seethrough': ('seethrough', 'generator material parameter collection MPC_SeeThrough',
        'see_through.py:47 and :246-253', 'blocked', 'no importer for parameter collections'),
    'adopted/skateruntime': ('skateruntime', 'generated RuntimeData data asset (31 MB)',
        'build.py:1813 (RuntimeData output); unreal/Scripts/skate_ride/verify_data.py:15', 'blocked',
        'no importer for data assets; the cooked data is the only copy in the editor'),
}
# The spec's families that name more than one registry family (their native lists cover all of them).
FAMILY_GROUPS = {'hidamari': ('hidamari', 'racing', 'seethrough', 'skateruntime')}
FAMILY_ORDER = ('megapark', 'hippodrome', 'treehouse', 'skatepark', 'belmonte', 'fx', 'plaza', 'bike', 'swordcamp', 'hidamari',
                'racing', 'seethrough', 'skateruntime')


class FamilyError(RuntimeError):
    pass


PlanError = FamilyError
REPO = GAME.parents[1]
GAME_REL = 'games/yorimichi_v2'


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


# --- the claim: the Hippodrome loose meshes and the plaza textures ------------------------------------------------------------
# Donor files are generated (hippodrome GLBs) or authored and tracked (plaza PNGs in the donor's source tree). Both are
# committed under src/ with their sha256 and the owner-published license (docs/DECISIONS.md D05 group 1), as the Japan leaf
# and plant records are. The tree house textures are not claimable: the texture recipe cannot express their settings.
CLAIM_FAMILIES = ('hippodrome', 'plaza', 'treehouse')
LICENSE = 'owner-published (docs/DECISIONS.md D05 group 1)'
PROVENANCE = 'donor build of games/yorimichi at the V2 source baseline (docs/DECISIONS.md D01, D02); pinned by sha256'
GLB_DIR = 'build/yorimichi/hippodrome/region/glb'
PNG_DIR = 'games/yorimichi/world/regions/hidamari/textures'
TREE_DIR = 'build/yorimichi/treehouse/textures'
TREE_CLAIM = {   # the tree house textures (import_treehouse.py:3-4 and :39-46): package -> (slug, donor PNG, adopted record)
    '/Game/Japan/Treehouse/Textures/T_TH_flat': ('flat', 'flat.png', 'adopted/japan/treehouse/surface-flat'),
    '/Game/Japan/Treehouse/Textures/T_TH_glass': ('glass', 'glass.png', 'adopted/japan/treehouse/surface-glass'),
    '/Game/Japan/Treehouse/Textures/T_TH_rope': ('rope', 'rope.png', 'adopted/japan/treehouse/surface-rope'),
}
TREE_SETTINGS = {'srgb': True, 'max_texture_size': 1024, 'lod_group': 'TEXTUREGROUP_WORLD'}
# The tree house textures are claimable only once the texture read (report_textures.py, its JSON) confirms these settings.
TREE_READ = 'docs/inventory/treehouse-textures-read.json'
# The plaza textures: the read shows the saved packages' full settings. The importer states all five: the donor scripts
# set sRGB only, and the saved compression (TC_EDITOR_ICON) and mirrored addressing are what the packages carry.
PLAZA_SETTINGS = {'srgb': True, 'max_texture_size': 1024, 'lod_group': 'TEXTUREGROUP_WORLD',
                  'compression': 'TC_EDITOR_ICON', 'address': 'mirror'}
PLAZA_READ = 'docs/inventory/plaza-textures-read.json'
PLAZA_TEXTURES = (   # the four plaza packages (PLAZA_CLAIM) by their read key
    '/Game/Japan/Textures/T_Arcade_paving', '/Game/Japan/Textures/T_Arcade_timber',
    '/Game/Japan/Textures/T_Harbor_paving', '/Game/Japan/Textures/T_Harbor_timber')
PINS = {   # donor-relative path -> sha256 (the region GLBs equal the exports; the plaza PNGs are tracked donor sources)
    f'{GLB_DIR}/SM_HD_FinishPost.glb': '123ab4602df5111d1df5345185183557b6488595ff9d5c3d58aebf57c9e9b3b4',
    f'{GLB_DIR}/SM_HD_Grandstand.glb': '92add5b3492eb839b9c6909d055c1d54d9692070e546a3429b2af9fd6ed9ae8f',
    f'{GLB_DIR}/SM_HD_JudgesTower.glb': 'ebfe7c40abbd75f5b9c4153ef8c1c48f215b1cc077773ee4b2758a19576188e5',
    f'{GLB_DIR}/SM_HD_ToteBoard.glb': '8086362ef6c65c6457f9ed6c7ca87e89edcfc2fef9856e089b4d375862e589d9',
    f'{PNG_DIR}/paving.png': '0cf002e567a081c1e32ff1c9ae56d70f3bd91d1d728d9f32fe358d2dda3df264',
    f'{PNG_DIR}/timber.png': 'd71b181a3d0df569f0c83ab2f5ffc0142bbeff3e2d542f2ddd4c1d5e3fb28311',
    f'{TREE_DIR}/flat.png': '10b379bb6586c9e928bec14701c904b488d4677577857642a9a6a8e514fdd3a7',
    f'{TREE_DIR}/glass.png': '10b379bb6586c9e928bec14701c904b488d4677577857642a9a6a8e514fdd3a7',
    f'{TREE_DIR}/rope.png': '13d328aea5ed6186c14ef7a0fc4972f0c3a05160d0b6b5c00cd6af952b722021',
}
HIPPO_CLAIM = {   # adopted/hippodrome/loose_files package -> (record slug, donor GLB name); static-mesh, lane's form
    '/Game/Hippodrome/SM_HD_FinishPost': ('finish-post', 'SM_HD_FinishPost'),
    '/Game/Hippodrome/SM_HD_Grandstand': ('grandstand', 'SM_HD_Grandstand'),
    '/Game/Hippodrome/SM_HD_JudgesTower': ('judges-tower', 'SM_HD_JudgesTower'),
    '/Game/Hippodrome/SM_HD_ToteBoard': ('tote-board', 'SM_HD_ToteBoard'),
}
PLAZA_CLAIM = {   # adopted/japan/textures/plaza-harbor package -> (record slug, donor PNG); both import with srgb true
    '/Game/Japan/Textures/T_Arcade_paving': ('arcade-paving', 'paving.png'),
    '/Game/Japan/Textures/T_Arcade_timber': ('arcade-timber', 'timber.png'),
    '/Game/Japan/Textures/T_Harbor_paving': ('harbor-paving', 'paving.png'),
    '/Game/Japan/Textures/T_Harbor_timber': ('harbor-timber', 'timber.png'),
}
CLAIM_ADOPTED = ('adopted/hippodrome/loose_files', 'adopted/japan/textures/plaza-harbor')


@dataclass
class NewRecord:
    id: str
    kind: str
    owner: str
    references: list
    sources: list     # (record-relative path, sha256, donor file)
    settings: dict
    outputs: list
    adopted: str      # the adopted record that gives up this package
    about: str
    inputs: list = field(default_factory=list)   # input_dependencies: the adopted records whose packages it binds


ADDRESS_MODES = {'TA_WRAP': 'wrap', 'TA_MIRROR': 'mirror'}   # report_textures.py's names -> a record's address setting


def read_view(row):
    """A read row in the records' setting vocabulary: address_x and address_y must agree and name a mode the importer
    states; any other address leaves the key out, so no setting can match it."""
    if row is None:
        return None
    view = dict(row)
    x, y = row.get('address_x'), row.get('address_y')
    if x is not None and x == y and x in ADDRESS_MODES:
        view['address'] = ADDRESS_MODES[x]
    return view


def read_status(game: Path, read_rel: str, packages, settings: dict) -> tuple:
    """(confirmed, reason): a texture family is claimable when the read file holds, for every package, each setting the
    records state, as report_textures.py reads them back."""
    path = game / read_rel
    if not path.is_file():
        return False, f'{read_rel} is missing: the texture read has not confirmed the settings'
    read = json.loads(path.read_text())
    for package in packages:
        row = read_view(read.get(package))
        if row is None:
            return False, f'{package} is not in {read_rel}'
        for key, want in settings.items():
            if row.get(key) != want:
                return False, f'{package}: {key} reads back {row.get(key)!r}, not {want!r}'
    return True, f'the settings are confirmed by {read_rel}'


def treehouse_status(game: Path) -> tuple:
    return read_status(game, TREE_READ, TREE_CLAIM, TREE_SETTINGS)


def plaza_status(game: Path) -> tuple:
    return read_status(game, PLAZA_READ, PLAZA_TEXTURES, PLAZA_SETTINGS)


def claim_records(donor: Path, game: Path) -> list:
    """The new records. Every donor file the plan needs is checked against its pin first; a mismatch refuses the plan.
    The tree house and plaza records are included only when their read gates confirm them (treehouse_status, plaza_status)."""
    tree_ok, _ = treehouse_status(game)
    plaza_ok, _ = plaza_status(game)
    needed = [rel for rel in PINS if rel.startswith(GLB_DIR)
              or (plaza_ok and rel.startswith(PNG_DIR)) or (tree_ok and rel.startswith(TREE_DIR))]
    for rel in needed:
        path = donor / rel
        if not path.is_file():
            raise PlanError(f'{rel}: missing in the donor')
        if sha256_file(path) != PINS[rel]:
            raise PlanError(f'{rel}: not its pinned sha256')
    report = json.loads((donor / 'build/yorimichi/hippodrome/import-report.json').read_text())
    out = []
    for package, (slug, name) in HIPPO_CLAIM.items():
        rel = f'{GLB_DIR}/{name}.glb'
        out.append(NewRecord(
            id=f'prop/hippodrome/{slug}', kind='static-mesh', owner=f'shared/hippodrome/{slug}',
            references=['adopted/hippodrome/materials'], inputs=['adopted/hippodrome/meshes'],
            sources=[(f'src/{name}.glb', PINS[rel], donor / rel)],
            # The read (docs/inventory/small-families-reads/hippodrome-meshes.json): one slot, bound to the mesh's own
            # material instance, which the adopted meshes record owns; one LOD; complex collision as simple.
            settings={'slot_materials': [hippo_slot(name)],
                      'triangles': int(report[name]['triangles']), 'collision': 'complex'},
            outputs=[package], adopted='adopted/hippodrome/loose_files',
            about=f'{name}: the donor region GLB of one hippodrome course piece'))
    if plaza_ok:
        for package, (slug, png) in PLAZA_CLAIM.items():
            rel = f'{PNG_DIR}/{png}'
            name = package.rsplit('/', 1)[1]
            out.append(NewRecord(
                id=f'texture/japan/{slug}', kind='texture', owner=f'shared/japan/{slug}', references=[],
                sources=[(f'src/{name}.png', PINS[rel], donor / rel)], settings=dict(PLAZA_SETTINGS),
                outputs=[package], adopted='adopted/japan/textures/plaza-harbor',
                about=f'{name}: the donor PNG {png}, imported with the saved packages\' settings (the plaza read)'))
    if tree_ok:
        for package, (slug, png, adopted) in TREE_CLAIM.items():
            rel = f'{TREE_DIR}/{png}'
            name = package.rsplit('/', 1)[1]
            out.append(NewRecord(
                id=f'texture/japan/treehouse-{slug}', kind='texture', owner=f'shared/japan/treehouse-{slug}',
                references=[], sources=[(f'src/{name}.png', PINS[rel], donor / rel)], settings=dict(TREE_SETTINGS),
                outputs=[package], adopted=adopted,
                about=f'{name}: the donor PNG {png}, imported sRGB at max size 1024 in the WORLD group (import_treehouse.py:39-46)'))
    return out


def hippo_slot(name: str) -> str:
    """The loose mesh's material instance in the adopted meshes folder (SM_HD_<x> -> .../SM_HD_<x>/HD_<x>)."""
    part = name[len('SM_HD_'):]
    return f'/Game/Hippodrome/Meshes/{name}/HD_{part}'


def record_text(rec: NewRecord) -> str:
    lines = [f'# Recovered from the donor (tools/migrate/small_families.py): {rec.about}.',
             '# The donor file is committed in src/ and pinned by sha256; the record is imported by the V2 editor and',
             '# verified by tools/import/run.py, never edited by hand.',
             'schema = 1', f'id = "{rec.id}"', f'kind = "{rec.kind}"', 'authority = "generated"', f'owner = "{rec.owner}"',
             f'license = "{LICENSE}"', f'provenance = "{PROVENANCE}"']
    if rec.references:
        lines.append('references = [' + ', '.join(f'"{r}"' for r in rec.references) + ']')
    if rec.inputs:   # a top-level key: it must come before the first [[sources]] table
        lines.append('input_dependencies = [' + ', '.join(f'"{r}"' for r in rec.inputs) + ']')
    for path, sha, _ in rec.sources:
        lines += ['', '[[sources]]', f'path = "{path}"', f'sha256 = "{sha}"']
    lines += ['', '[recipe]', f'importer = "{rec.kind}"', 'version = 1', '', '[recipe.settings]']
    lines += [f'{key} = {recover._toml(value)}' for key, value in rec.settings.items()]
    lines += ['']
    for package in rec.outputs:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


def _owner_of(text: str) -> str:
    match = re.search(r'(?m)^owner = "([^"]+)"$', text)
    return match.group(1) if match else ''


def claim_ops(game: Path, donor: Path) -> dict:
    """The one write: {'writes': {rel: bytes}, 'deletes': [rel]}. The new records and their src/ copies. An adopted record
    that gives up every package is deleted with its verified.json; one that keeps some (a tree house surface keeps its
    instance) loses the moved outputs from its asset.toml and their entries from its verified.json. The units.json of each
    folder drops the moved packages, and a record that references a fully moved record names the new records."""
    recs = claim_records(donor, game)
    writes, deletes, moved, new_ids = {}, [], {}, {}
    for rec in recs:
        folder = 'assets/' + rec.id
        writes[f'{folder}/asset.toml'] = record_text(rec).encode()
        for rel, _, file in rec.sources:
            writes[f'{folder}/{rel}'] = file.read_bytes()
        moved.setdefault(rec.adopted, set()).update(rec.outputs)
        new_ids.setdefault(rec.adopted, []).append(rec.id)
    full, partial = set(), set()
    for adopted_id, packages in sorted(moved.items()):
        rel = f'assets/{adopted_id}/asset.toml'
        text = (game / rel).read_text()
        listed = {o.package for o in records.load_asset(game / rel).outputs}
        if not packages <= listed:
            raise PlanError(f'{adopted_id}: the plan moves {sorted(packages - listed)}, which it does not list')
        verified = game / f'assets/{adopted_id}/verified.json'
        if listed == packages:
            full.add(adopted_id)
            deletes.append(rel)
            if verified.is_file():
                deletes.append(f'assets/{adopted_id}/verified.json')
            continue
        partial.add(adopted_id)
        writes[rel] = recover._drop_outputs(text, packages).encode()
        if not verified.is_file():
            raise PlanError(f'{adopted_id}: keeps some packages but has no verified.json to edit')
        vtext = verified.read_text()
        data = json.loads(vtext)
        if json.dumps(data, indent=2, sort_keys=True) + '\n' != vtext:
            raise PlanError(f'{adopted_id}/verified.json is not in the form adoption writes; edit it by hand')
        files = data.get('files', {})
        for package in packages:
            for ext in ('.uasset', '.umap', '.uexp', '.ubulk'):
                files.pop('unreal/Content/' + package[len('/Game/'):] + ext, None)
        writes[f'assets/{adopted_id}/verified.json'] = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    all_moved = {package for packages in moved.values() for package in packages}
    for folder_rel in sorted({i.rsplit('/', 1)[0] for i in moved}):
        units_rel = f'assets/{folder_rel}/units.json'
        if not (game / units_rel).is_file():
            continue
        text = (game / units_rel).read_text()
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
        if rel in writes or any(rel == f'assets/{i}/asset.toml' for i in full):
            continue
        text = path.read_text()
        match = re.search(r'(?m)^references = \[(.*)\]$', text)
        if not match:
            continue
        refs = re.findall(r'"([^"]+)"', match.group(1))
        if not any(r in full for r in refs):
            continue
        others = text[:match.start()] + text[match.end():]
        if any(f'"{r}"' in others for r in refs if r in full):
            raise PlanError(f'{rel} names a moved record outside its references line; refused')
        kept = []
        for r in refs:
            kept += sorted(new_ids[r]) if r in full else [r]
        line = 'references = [' + ', '.join(f'"{r}"' for r in sorted(set(kept))) + ']'
        writes[rel] = (text[:match.start()] + line + text[match.end():]).encode()
    return {'writes': writes, 'deletes': sorted(set(deletes))}


def claim_scopes(game: Path, ops: dict) -> list:
    owners = set()
    for rel, data in ops['writes'].items():
        if rel.endswith('asset.toml'):
            owners.add(_owner_of(data.decode()))
    for rel in ops['deletes']:
        if rel.endswith('asset.toml'):
            owners.add(_owner_of((game / rel).read_text()))
    return sorted(o for o in owners if o)


def locked_paths(game_rels: list) -> set:
    """The repository-relative paths Git LFS marks lockable (their src copies and binaries)."""
    out = subprocess.run(['git', 'check-attr', 'lockable', '--', *game_rels], cwd=REPO, text=True,
                         stdout=subprocess.PIPE, check=True).stdout
    return {line.split(':')[0] for line in out.splitlines() if line.endswith(': lockable: set')}


def print_paths(game: Path, donor: Path) -> None:
    for family, (confirmed, reason) in (('tree house', treehouse_status(game)), ('plaza', plaza_status(game))):
        print(f'note: {family} textures {"claimed" if confirmed else "not claimed"}: {reason}')
    ops = claim_ops(game, donor)
    paths = sorted(set(ops['writes']) | set(ops['deletes']))
    full = [f'{GAME_REL}/{rel}' for rel in paths]
    locks = locked_paths(full)
    for rel in full:
        print(('lock ' if rel in locks else 'path ') + rel)
    print('scopes: ' + ' '.join(claim_scopes(game, ops)))


def materialize(game: Path, donor: Path, claim: str, *, echo=print) -> None:
    apply.Journal(game).recover(claim)
    ops = claim_ops(game, donor)
    scopes = claim_scopes(game, ops)
    paths = sorted(set(ops['writes']) | set(ops['deletes']))
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in paths], claim,
                            'Yorimichi V2 small families (hippodrome loose meshes, plaza textures)', scopes=scopes)
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=scopes)
    echo(f'materialize: {len(claim_records(donor, game))} record(s) written; {len(paths)} path(s) under {claim}')



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--donor', type=Path, default=None, help='a donor checkout (read-only); donor evidence is skipped without it')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--paths', action='store_true', help='print the claim paths (lock or path), then the scopes')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write for the claimable rows')
    args = parser.parse_args(argv)
    if args.claim or args.paths:
        if args.donor is None:
            print('small_families: --paths and --claim need --donor', file=sys.stderr)
            return 1
        try:
            if args.claim:
                materialize(args.game, args.donor, args.claim)
            else:
                print_paths(args.game, args.donor)
            return 0
        except (FamilyError, records.RecordError, apply.SplitError) as error:
            print(f'small_families: {error}', file=sys.stderr)
            return 1
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
