"""Source recovery for adopted/hippodrome/meshes, the 14 Interchange sub-objects of the Hippodrome GLB imports (plan first).

    uv run python games/yorimichi_v2/tools/migrate/hippodrome_meshes.py              # plan and checks; writes nothing
    uv run python games/yorimichi_v2/tools/migrate/hippodrome_meshes.py --paths      # every path and scope a claim needs
    uv run python games/yorimichi_v2/tools/migrate/hippodrome_meshes.py --claim TASK # the one journaled write

The donor's import_hippodrome.py imported each course GLB into /Game/Hippodrome/Meshes/<mesh>. Interchange made one
material instance per glTF material and one texture per embedded image there; the donor then restyled the four painted
props' instances (`restyle`, lines 116-124): cleared their parameters, reparented them to M_HD_Structure and set
BaseColorTexture back to the embedded image. The 14 packages are:

- 4 textures `SM_HD_<Part>/Color_<uuid>`: each is the one JPEG its prop GLB embeds. The GLB is already committed and
  pinned in the prop record's src/ (prop/hippodrome/<part>), so the image bytes are read from there, copied into the new
  texture record's src/ and pinned by sha256. Settings: sRGB, TC_Default, TEXTUREGROUP_World (the committed bytes name
  the last two), wrap (glTF's default, no sampler).
- 4 material instances `SM_HD_<Part>/HD_<Part>`: one material-instance record each, parent M_HD_Structure and
  BaseColorTexture its texture, as `restyle` left them. Each prop's slot material is its instance, so the prop record's
  input_dependencies move from the adopted record to the instance record.
- 6 course instances (`HD_Grass`, `HD_Dirt` twice, `HD_Stone` twice, `HD_Rail`) under SM_HD_Ground, Lane, LaneSkirt,
  Rails, Skirt and Track. Nothing uses them: those prop records' slots name the M_HD_<surface> masters, and no tracked
  file other than their own packages and the adopted record names them. They are donor leftovers and are retired.

The write deletes the adopted record and its verified.json (no package is left in it) and the six retired packages'
files. The eight new records are unimported until tools/import/run.py rebuilds and reads back their packages.
States: `unmoved` (the adopted record lists exactly the 14) and `moved` (it is gone, the eight records exist and the six
packages are off disk); any other state is refused, and a rerun after the move changes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import authority  # noqa: E402
import records  # noqa: E402
sys.path.insert(0, str(HERE))
import brinecove_split_apply as apply  # noqa: E402  (Journal and execute: the journaled write every migrate step uses)
from belmontetrain_lods import scanned  # noqa: E402  (the tracked files the referencer proof reads)
from belmontetrain_materials import image_bytes, read_glb, texture_packages  # noqa: E402

GAME_REL = 'games/yorimichi_v2'
ADOPTED = 'adopted/hippodrome/meshes'
ADOPTED_REL = f'assets/{ADOPTED}'
MESHES = '/Game/Hippodrome/Meshes'
STRUCTURE = '/Game/Hippodrome/Materials/M_HD_Structure'
STRUCTURE_RECORD = 'master/hippodrome/structure'
PARTS = {'finish-post': 'FinishPost', 'grandstand': 'Grandstand', 'judges-tower': 'JudgesTower', 'tote-board': 'ToteBoard'}
UNUSED = {f'{MESHES}/{mesh}/{name}': prop for mesh, name, prop in (
    ('SM_HD_Ground', 'HD_Grass', 'ground'), ('SM_HD_Lane', 'HD_Dirt', 'lane'), ('SM_HD_LaneSkirt', 'HD_Stone', 'lane-skirt'),
    ('SM_HD_Rails', 'HD_Rail', 'rails'), ('SM_HD_Skirt', 'HD_Stone', 'skirt'), ('SM_HD_Track', 'HD_Dirt', 'track'))}
EXTENSIONS = ('.uasset', '.uexp', '.ubulk', '.umap')
# Package lists of an earlier editor read (docs/inventory): the retired lines leave them.
READ_LISTS = ('docs/inventory/small-families-hippodrome-meshes.txt', 'docs/inventory/small-families-hippodrome-packages.txt')
SCOPES = sorted({'shared/hippodrome/meshes', *(f'shared/hippodrome/{part}' for part in PARTS),
                 *(f'shared/hippodrome/materials/{part}' for part in PARTS),
                 *(f'shared/hippodrome/textures/{part}' for part in PARTS)})


class PlanError(RuntimeError):
    pass


def texture_id(part: str) -> str:
    return f'texture/hippodrome/{part}-color'


def material_id(part: str) -> str:
    return f'material/hippodrome/{part}'


def prop_rel(part: str) -> str:
    return f'assets/prop/hippodrome/{part}/asset.toml'


def package_rels(game: Path, package: str) -> list[str]:
    stem = game / 'unreal' / 'Content' / package[len('/Game/'):]
    return [(stem.parent / (stem.name + ext)).relative_to(game).as_posix() for ext in EXTENSIONS
            if (stem.parent / (stem.name + ext)).is_file()]


def plan(game: Path) -> dict:
    """{part: {glb, image, sha, texture, instance}} read from each prop record's committed, pinned GLB."""
    out = {}
    for part, name in PARTS.items():
        prop = records.load_asset(game / prop_rel(part))
        glbs = [s for s in prop.sources if s.path == f'src/SM_HD_{name}.glb']
        path = game / prop_rel(part).rsplit('/', 1)[0] / f'src/SM_HD_{name}.glb'
        if len(glbs) != 1 or records.is_lfs_pointer(path) or records.sha256_file(path) != glbs[0].sha256:
            raise PlanError(f'{prop.id}: its GLB is not one hydrated source matching its pin')
        doc, body = read_glb(path)
        materials, textures = doc.get('materials', []), texture_packages(doc)
        if len(materials) != 1 or len(textures) != 1 or materials[0]['name'] != f'HD_{name}':
            raise PlanError(f'{path.name}: not one material HD_{name} with one texture')
        if materials[0]['pbrMetallicRoughness'].get('baseColorTexture', {}).get('index') != 0:
            raise PlanError(f'{path.name}: the material does not take its one texture as base colour')
        image_name, image = textures[0]
        if doc['images'][image].get('mimeType') != 'image/jpeg':
            raise PlanError(f'{path.name}: the embedded image is not a JPEG')
        data = image_bytes(doc, body, image)
        out[part] = {'glb': path.name, 'image': data, 'sha': hashlib.sha256(data).hexdigest(),
                     'texture': f'{MESHES}/SM_HD_{name}/{image_name}', 'instance': f'{MESHES}/SM_HD_{name}/HD_{name}',
                     'source': f'{image_name}.jpg'}
        if prop.recipe['settings']['slot_materials'] != [out[part]['instance']]:
            raise PlanError(f'{prop.id}: its slot material is not {out[part]["instance"]}')
    return out


def expected_packages(rows: dict) -> set[str]:
    return {r[k] for r in rows.values() for k in ('texture', 'instance')} | set(UNUSED)


def texture_text(part: str, row: dict) -> str:
    return '\n'.join([
        f'# Recovered from the donor import (tools/migrate/hippodrome_meshes.py): the base colour image the donor',
        f'# {row["glb"]} embeds, which Interchange imported as {row["texture"].rsplit("/", 1)[1]}. The image is committed',
        '# in src/ and pinned by sha256; the record is imported by the V2 editor and verified by tools/import/run.py.',
        'schema = 1', f'id = "{texture_id(part)}"', 'kind = "texture"', 'authority = "generated"',
        f'owner = "shared/hippodrome/textures/{part}"',
        'provenance = "donor build of games/yorimichi at the V2 source baseline (docs/DECISIONS.md D01, D02); pinned by sha256"',
        'license = "owner-published (docs/DECISIONS.md D05 group 1)"',
        '', '[[sources]]', f'path = "src/{row["source"]}"', f'sha256 = "{row["sha"]}"',
        '', '[recipe]', 'importer = "texture"', 'version = 1', '', '[recipe.settings]',
        'srgb = true', 'compression = "TC_DEFAULT"', 'lod_group = "TEXTUREGROUP_WORLD"', 'address = "wrap"',
        '', '[[outputs]]', f'package = "{row["texture"]}"', ''])


def material_text(part: str, row: dict) -> str:
    return '\n'.join([
        '# Recovered from the donor import (tools/migrate/hippodrome_meshes.py): import_hippodrome.py restyle (lines',
        '# 116-124) cleared the imported instance, reparented it to M_HD_Structure and set BaseColorTexture to the image',
        '# its GLB embeds. The importer (tools/import/run.py) writes it in place and reads every value back.',
        'schema = 1', f'id = "{material_id(part)}"', 'kind = "material-instance"', 'authority = "generated"',
        f'owner = "shared/hippodrome/materials/{part}"',
        'provenance = "donor games/yorimichi/unreal/Scripts/import_hippodrome.py at the V2 source baseline (docs/DECISIONS.md D01, D02), restyle lines 116-124"',
        'license = "owner-published (docs/DECISIONS.md D05 group 1)"',
        f'input_dependencies = ["{STRUCTURE_RECORD}", "{texture_id(part)}"]',
        '', '[recipe]', 'importer = "material-instance"', 'version = 2', '', '[recipe.settings]',
        f'parent = "{STRUCTURE}"', f'textures = {{ BaseColorTexture = "{row["texture"]}" }}', 'scalars = {}', 'vectors = {}',
        '', '[[outputs]]', f'package = "{row["instance"]}"', ''])


def state(game: Path, rows: dict) -> str:
    adopted = game / ADOPTED_REL / 'asset.toml'
    made = [(game / f'assets/{rid}/asset.toml').is_file() for part in PARTS for rid in (texture_id(part), material_id(part))]
    if adopted.is_file() and not any(made):
        listed = {o.package for o in records.load_asset(adopted).outputs}
        if listed == expected_packages(rows):
            return 'unmoved'
        raise PlanError(f'{ADOPTED} lists {sorted(listed ^ expected_packages(rows))[:3]} beyond the planned 14; refused')
    if not adopted.is_file() and all(made) and not any(package_rels(game, p) for p in UNUSED):
        return 'moved'
    raise PlanError(f'{ADOPTED} is half-moved: adopted record present {adopted.is_file()}, records {sum(made)} of 8')


def byte_check(game: Path, rows: dict) -> list[str]:
    """Problems with the planned facts against the committed package bytes (hydrated, not LFS pointers)."""
    problems = []
    for part, row in rows.items():
        for package, needles in ((row['instance'], [STRUCTURE.encode(), row['texture'].encode()]),
                                 (row['texture'], [b'TC_Default', b'TEXTUREGROUP_World'])):
            rels = package_rels(game, package)
            if not rels or records.is_lfs_pointer(game / rels[0]):
                problems.append(f'{package}: no hydrated package to check')
                continue
            data = b''.join((game / rel).read_bytes() for rel in rels)
            problems += [f'{package} does not name {n.decode()}' for n in needles if n not in data]
    return problems


def build_writes(game: Path, rows: dict) -> dict:
    """The one write: {'writes': {game-relative path: bytes}, 'deletes': [game-relative path]}."""
    writes, deletes = {}, []
    for part, row in rows.items():
        writes[f'assets/{texture_id(part)}/asset.toml'] = texture_text(part, row).encode()
        writes[f'assets/{texture_id(part)}/src/{row["source"]}'] = row['image']
        writes[f'assets/{material_id(part)}/asset.toml'] = material_text(part, row).encode()
        text = (game / prop_rel(part)).read_text()
        line = f'input_dependencies = ["{ADOPTED}"]'
        if text.count(line) != 1:
            raise PlanError(f'{prop_rel(part)}: its input_dependencies are not the one adopted record')
        writes[prop_rel(part)] = text.replace(line, f'input_dependencies = ["{material_id(part)}"]').encode()
    for rel in READ_LISTS:
        lines = (game / rel).read_text().splitlines(keepends=True)
        kept = [line for line in lines if line.strip() not in UNUSED]
        if kept != lines:
            writes[rel] = ''.join(kept).encode()
    deletes += [f'{ADOPTED_REL}/{name}' for name in ('asset.toml', 'verified.json') if (game / ADOPTED_REL / name).is_file()]
    for package in UNUSED:
        deletes += package_rels(game, package)
    return {'writes': writes, 'deletes': sorted(deletes)}


def proof(game: Path, ops: dict) -> list[str]:
    """@cc [owner:fontanierh,label:safety] hippodrome-unused-instances-unreferenced
    The six course instances MUST NOT be deleted while any tracked file other than their own packages names one, as
    UTF-8 or UTF-16, in the form it will have after the write (deleted files are not read). A Git LFS pointer among the
    scanned files cannot be proven clean, so it refuses."""
    forms = {p: (p.lower().encode(), p.lower().encode('utf-16-le')) for p in UNUSED}
    gone = set(ops['deletes'])
    problems, pointers = [], []
    for rel in scanned(game):
        if rel in gone or not (game / rel).is_file():
            continue
        if records.is_lfs_pointer(game / rel):
            pointers.append(rel)
            continue
        low = (ops['writes'][rel] if rel in ops['writes'] else (game / rel).read_bytes()).lower()
        hits = [p for p, (a, b) in forms.items() if a in low or b in low]
        if hits:
            problems.append(f'{rel} names {hits[0]}')
    if pointers:
        problems.insert(0, f'{len(pointers)} Git LFS pointer file(s), e.g. {pointers[0]}: cannot prove the instances '
                           'are unreferenced; fetch the real files and rerun')
    return problems


def claimed_paths(ops: dict) -> list[str]:
    return sorted(set(ops['writes']) | set(ops['deletes']))


def materialize(game: Path, claim: str, *, lockable=apply.lockable_present, echo=print) -> str:
    apply.Journal(game).recover(claim)
    rows = plan(game)
    if state(game, rows) == 'moved':
        echo('materialize: already moved; nothing written')
        return 'moved'
    problems = byte_check(game, rows)
    ops = build_writes(game, rows)
    problems += proof(game, ops)
    if problems:
        raise PlanError('refused, nothing changed: ' + '; '.join(problems[:5]))
    try:
        authority.authorize([f'{GAME_REL}/{rel}' for rel in claimed_paths(ops)], claim,
                            'Hippodrome mesh sub-object sources', scopes=SCOPES)
    except authority.Unauthorized as error:
        raise PlanError(str(error)) from None
    apply.execute(game, ops, scopes=SCOPES, lockable=lockable)
    if state(game, rows) != 'moved':
        raise PlanError('the write did not leave the move complete; restore from the journal and report')
    echo(f'materialize: 4 texture and 4 material-instance records written; {len(UNUSED)} unused instances retired')
    return 'moved'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--paths', action='store_true', help='print the claim paths and scopes')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write')
    args = parser.parse_args(argv)
    try:
        if args.claim:
            materialize(args.game, args.claim)
            return 0
        rows = plan(args.game)
        current = state(args.game, rows)
        print(f'state: {current}')
        if current == 'unmoved':
            ops = build_writes(args.game, rows)
            problems = byte_check(args.game, rows) + proof(args.game, ops)
            print(json.dumps({part: {k: v for k, v in row.items() if k != 'image'} for part, row in rows.items()}, indent=1))
            print(f'checks: {len(problems)} problem(s)' + ''.join(f'\n  {p}' for p in problems))
            if args.paths:
                for rel in claimed_paths(ops):
                    print(f'path {GAME_REL}/{rel}')
                print('scopes: ' + ' '.join(SCOPES))
    except (PlanError, records.RecordError, authority.Unauthorized) as error:
        print(f'hippodrome_meshes: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
