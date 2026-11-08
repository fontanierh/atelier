"""Write Crater Park's editing units (assets/adopted/craterpark/units.json) for its ownership split (DECISIONS D08).

    uv run python games/yorimichi_v2/tools/migrate/craterpark_units.py [--check]
    uv run python games/yorimichi_v2/tools/migrate/craterpark_units.py --measure GEOMETRY.npz   # refresh the ledger

What the packages are. The shipped park is the owner's editor document (games/yorimichi/tools/craterpark_editor/
shipped.json, craterpark-editor/1: 57 pieces such as bowls, ramps, runs, decks, kickers, landings). The generator
(world/regions/craterpark/v2/editor_generate.py) compiles it to one mesh whose faces carry a feature name (`p9`,
`p9_supports`, `editor_coping_004`, `crater_floor`, ...), and v2/split.py cuts that into render meshes by (role,
material, 64 m tile), `SM_CP_<role>_<material>_<tx>_<tz>`, and into collision sections `UC_CP_original_<k>` cut again
by v2/atomic_inputs.py into 32768-triangle `_PieceNNN` packages. No package name says which feature it came from, so
`craterpark_ownership.json` (this folder; written by --measure from the generator's own geometry.npz, which
reproduces the adopted names exactly) records it:

  - render mesh -> owner feature: the feature (a piece with its supports, tower and shrine; a coping rail goes to the
    piece it rides on, found by the nearest piece surface; the crater floor) that holds most of the mesh's faces.
    930 of 1123 meshes hold one feature only. The others lie on a tile edge and also hold faces of a neighbour
    (listed in the ledger under `mixed`); they belong to the larger share.
  - collision piece -> owner feature, only when one feature holds at least 95 % of its triangles, else `mixed`.
    Sections are z-ordered over the whole park, so most pieces mix many features (see the ledger).

Units. Each piece is one unit (`p9-mega-55-m-mega`): its render meshes, its pure collision pieces and the material
instances and textures only it uses. The crater floor (the volcano's ground inside the crater, cut by the park) is
bounded area units of 4 x 4 tiles. Collision pieces no single feature holds are `collision-mixed`. A material instance
several units share goes to its surface family (`shared-materials-<family>`), a texture to the family of the
instances using it. The parent materials are `materials-base`, which is also the generator unit. The cap cloud is
`cloud`.

Sources (repository paths; adopt.py --repartition copies them into each record and pins their sha256).
`materials-base` lists the generator: the region scripts and the editor compiler, the shipped park document and the
terrain it was drawn on, the texture, shrine and import scripts, the source library and the pictures its AI paintings
were made from. A texture unit lists the painting (and the original texture) it was finished from; the tower unit the
shrine models. Every other unit references `materials-base`. The same adopted records and ledger always give the same
file.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
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
D = 'games/yorimichi/'
ASSETS = D + 'assets/craterpark/'
OUT = GAME / 'assets' / 'adopted' / 'craterpark' / 'units.json'
LEDGER = GAME / 'assets' / 'adopted' / 'craterpark' / 'craterpark_ownership.json'
ROOT = '/Game/CraterPark/'
SHIPPED = DONOR / 'tools' / 'craterpark_editor' / 'shipped.json'
PURE = .95              # share of a collision piece's triangles one feature must hold to own it
BLOCK = 4               # tiles (64 m) per side of a crater-floor area unit
GENERATOR = 'materials-base'
FLOOR = 'crater_floor'
SUFFIX = re.compile(r'_(?:supports|tower|shrine)$')
MESH = re.compile(r'^SM_CP_(?:original|coping)_(?:material_\d+|coping_steel)_(m?\d+)_(m?\d+)(?:_\d+)?$')
PIECE = re.compile(r'^UC_CP_original_\d+_Piece\d+$')
# Generator files outside the region folder (donor build steps world.craterpark, unreal.craterpark, textures).
GENERATOR_FILES = ('craterpark_atomic_build.py', 'tools/craterpark_textures.py', 'tools/craterpark_shrine_props.py',
                   'tools/craterpark_editor/shipped.json', 'tools/craterpark_editor/export_terrain.py',
                   'unreal/Scripts/import_craterpark.py', 'unreal/Scripts/import_megapark.py',
                   'unreal/Scripts/park_atomic_native.py', 'world/yori.py', 'world/source_registry.py',
                   'assets/source-library.json', 'assets/craterpark/materials.json', 'assets/craterpark/provenance.json')
GENERATOR_FOLDERS = ('world/regions/craterpark', 'tools/craterpark_editor/data')
CLOUD = ('world/regions/craterpark/cloud.py', 'world/regions/craterpark/cloud_build.py',
         'unreal/Scripts/crater_cloud_material.py')
# Surface family of the textures a material shows, where the source texture's own name is no help.
FAMILY = {'stair_brick': 'brick', 'side_bank': 'concrete', 'ramp_planks': 'wood', 'ramp_fascia': 'wood',
          'brick_coping': 'brick', 'masonite': 'wood', 'ramp_boards': 'wood'}


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def block(n: int) -> str:
    return str(n).replace('-', 'm')


def base(feature: str) -> str:
    """p183_tower -> p183: supports, tower and shrine belong to their piece."""
    return SUFFIX.sub('', feature)


def textures_module():
    sys.path.insert(0, str(DONOR / 'world'))
    spec = importlib.util.spec_from_file_location('craterpark_textures', DONOR / 'tools' / 'craterpark_textures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------ --measure
def measure(npz: Path) -> dict:
    import numpy as np
    sys.path.insert(0, str(DONOR / 'world' / 'regions'))
    geometry = np.load(npz)
    index = json.loads(str(geometry['index']))
    renders = index['render']

    def per_face(i):
        table = renders[i]['features']
        return [base(table[k]) for k in geometry[f'r{i}_feature']]

    # coping rails ride a piece: the feature whose surface lies nearest, by vote of sampled rail vertices
    labelled, owner_of_vertex = [], []
    for i, e in enumerate(renders):
        if e['role'] == 'coping':
            continue
        vertices, faces = geometry[f'r{i}_V'], geometry[f'r{i}_F']
        names = per_face(i)
        step = max(1, len(faces) // 400)
        for j in range(0, len(faces), step):
            if names[j] != FLOOR:
                labelled.append(vertices[faces[j]].mean(0)); owner_of_vertex.append(names[j])
    labelled = np.asarray(labelled)
    rails = collections.defaultdict(list)
    for i, e in enumerate(renders):
        if e['role'] == 'coping':
            vertices, faces = geometry[f'r{i}_V'], geometry[f'r{i}_F']
            names = [x for x in geometry[f'r{i}_feature']]
            for j in range(0, len(faces), max(1, len(faces) // 50)):
                if e['features'][names[j]].startswith('editor_coping'):
                    rails[e['features'][names[j]]].append(vertices[faces[j]].mean(0))
    rides = {}
    for rail, points in sorted(rails.items()):
        votes = collections.Counter()
        for p in points:
            votes[owner_of_vertex[int(np.argmin(((labelled - p) ** 2).sum(1)))]] += 1
        rides[rail] = votes.most_common(1)[0][0]
    owner, mixed, materials = {}, {}, collections.defaultdict(set)
    for i, e in enumerate(renders):
        faces = geometry[f'r{i}_feature']
        count = collections.Counter()
        for k in faces:
            name = e['features'][k]
            count[rides.get(name, base(name))] += 1
        owner[e['name']] = count.most_common(1)[0][0]
        if len(count) > 1:
            mixed[e['name']] = sorted(k for k in count if k != owner[e['name']])
        materials[owner[e['name']]].update(e['materials'])
    # collision pieces: match every triangle to the render face it was cut from
    def key(t):
        return np.round(t.reshape(len(t), 9) * 1e5).astype('i8')
    lookup = {}
    for i, e in enumerate(renders):
        if e['role'] == 'coping':
            continue
        triangles = geometry[f'r{i}_V'][geometry[f'r{i}_F']]
        for k, f in zip(map(bytes, key(triangles)), per_face(i)):
            lookup[k] = f
    collision = {}
    for i, e in enumerate(index['collision']):
        triangles = geometry[f'c{i}']
        keys = [bytes(x) for x in key(triangles)]
        for start in range(0, len(keys), 32768):
            share = collections.Counter(lookup.get(k, '?') for k in keys[start:start + 32768])
            name = e['name'] if len(keys) <= 32768 else f'{e["name"]}_Piece{start // 32768:03d}'
            top, n = share.most_common(1)[0]
            collision[name] = {'owner': top if n >= PURE * sum(share.values()) else 'mixed',
                               'triangles': sum(share.values()), 'features': dict(share.most_common(4))}
    return {'about': 'Crater Park package ownership measured from the generator (craterpark_units.py --measure): '
                     'render mesh -> owner feature, collision piece -> owner feature or mixed, the materials each '
                     'owner uses',
            'shipped_rev': json.loads(SHIPPED.read_text()).get('rev'),
            'coping_rides': rides, 'render': dict(sorted(owner.items())), 'mixed': dict(sorted(mixed.items())),
            'collision': dict(sorted(collision.items())),
            'materials': {k: sorted(v) for k, v in sorted(materials.items())}}


# ------------------------------------------------------------------------------------------------ units
def donor_files(folder: str) -> list[str]:
    return [D + p.relative_to(DONOR).as_posix() for p in sorted((DONOR / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != '.DS_Store']


def existing(paths) -> list[str]:
    return [p for p in paths if (REPO / p).is_file()]


def build(game: Path) -> dict:
    ledger = json.loads(LEDGER.read_text())
    shipped = json.loads(SHIPPED.read_text())
    pieces = {p['id']: p for p in shipped['pieces']}
    ct = textures_module()
    specs = {m['id']: m for m in json.loads((DONOR / 'assets/craterpark/materials.json').read_text())}
    specs['coping_steel'] = {'id': 'coping_steel', 'texture': None, 'finish': 'metal'}
    packages = sorted(o.package for a in records.discover(game)[0] if a.id.startswith('adopted/craterpark/')
                      for o in a.outputs)
    if any(not p.startswith(ROOT) for p in packages):
        raise ValueError('an adopted/craterpark record owns a package outside /Game/CraterPark')

    def unit_name(feature: str) -> str:
        if feature == FLOOR:
            raise ValueError('floor is an area unit')
        if feature not in pieces:
            raise ValueError(f'ledger names feature {feature}, which shipped.json does not')
        return f'{feature}-{slug(pieces[feature]["name"])}'

    unit: dict[str, str] = {}
    info: dict[str, dict] = {}
    counts = collections.Counter()
    for package in packages:
        name = package.rsplit('/', 1)[1]
        if package.startswith(ROOT + 'Meshes/'):
            if name.startswith('SM_CP_'):
                feature = ledger['render'].get(name)
                if feature is None:
                    raise ValueError(f'{name} is not in the ownership ledger')
                if feature == FLOOR:
                    tile = MESH.match(name)
                    if not tile:
                        raise ValueError(f'{name} names no tile')
                    x, z = (int(v.replace('m', '-')) // BLOCK for v in tile.groups())
                    unit[package] = f'crater-floor-{block(x)}-{block(z)}'
                else:
                    unit[package] = unit_name(feature)
            elif PIECE.match(name):
                row = ledger['collision'].get(name)
                if row is None:
                    raise ValueError(f'{name} is not in the ownership ledger')
                owner = row['owner']
                unit[package] = 'collision-mixed' if owner in ('mixed', FLOOR) else unit_name(owner)
            else:
                raise ValueError(f'{name} fits no Crater Park unit')
        elif package.startswith(ROOT + 'Cloud/'):
            unit[package] = 'cloud'
        elif name.startswith('M_CP_'):
            unit[package] = GENERATOR
        elif not name.startswith(('MI_CP_', 'T_CP_')):
            raise ValueError(f'{name} fits no Crater Park unit')
    for package in packages:
        if package.startswith(ROOT + 'Meshes/'):
            counts[unit[package]] += 1

    # which units' meshes show each material
    users = collections.defaultdict(set)
    for owner, ids in ledger['materials'].items():
        if owner == FLOOR:
            continue
        for mat in ids:
            users[mat].add(unit_name(owner))
    floor_materials = set(ledger['materials'].get(FLOOR, []))
    # the area units of the floor use the floor's materials: one per block, all of them; a material the floor shares
    # with a piece is shared, so mark it with a floor pseudo-user
    for mat in floor_materials:
        users[mat].add('crater-floor')

    # surface family of a material (shared materials) and the texture it shows
    keys = {}
    for slug_, row in ct.SURFACES.items():
        keys[row[0]] = slug_
    for slug_, row in ct.DECALS.items():
        keys[row[0]] = slug_
    for slug_, row in ct.UV_PAINTINGS.items():
        keys[row[0]] = slug_
    for key in ct.BOOST_PAINTS:
        keys[key] = Path(key).stem
    keys[ct.LETTERS] = Path(ct.LETTERS).stem
    for slug_ in ('bell_pavilion', 'nobori', 'stone_lantern', 'torii'):
        keys[ct.SHRINE_TEXTURE.format(slug=slug_)] = 'shrine_' + slug_

    def texture_of(mat: str):
        spec = specs[mat]
        if spec.get('texture'):
            return keys[spec['texture']]
        return mat if mat in ct.WORLD_ALIGNED else None

    def family(mat: str) -> str:
        spec = specs[mat]
        if spec.get('finish') == 'metal':
            return 'steel'
        if spec.get('finish') == 'lacquer':
            return 'lacquer'
        if mat in ct.WORLD_ALIGNED:
            return 'world'
        if not spec.get('texture'):
            return 'flat'
        if spec['texture'].startswith('shrine/'):
            return 'shrine'
        stem = keys[spec['texture']]
        found = re.search(r'sur_([a-z]+)_', spec.get('sourceTextureName') or '')
        return FAMILY.get(stem) or (found.group(1) if found else stem)

    for package in packages:
        name = package.rsplit('/', 1)[1]
        if name.startswith('MI_CP_'):
            mat = name[len('MI_CP_'):]
            owners = users.get(mat, set())
            unit[package] = next(iter(owners)) if len(owners) == 1 and 'crater-floor' not in owners else \
                f'shared-materials-{family(mat)}'
    # a single-owner material owned by the floor goes to the floor's shared unit
    for package in packages:
        name = package.rsplit('/', 1)[1]
        if name.startswith('MI_CP_') and users.get(name[len('MI_CP_'):]) == {'crater-floor'}:
            unit[package] = 'shared-materials-floor'
    stem_unit = {}
    stem_family = {}
    for package in packages:
        name = package.rsplit('/', 1)[1]
        if name.startswith('MI_CP_'):
            mat = name[len('MI_CP_'):]
            stem = texture_of(mat)
            if stem:
                stem_unit.setdefault(stem, set()).add(unit[package])
                stem_family[stem] = family(mat)
    for package in packages:
        name = package.rsplit('/', 1)[1]
        if name.startswith('T_CP_'):
            stem = name[len('T_CP_'):]
            if stem not in stem_unit:
                raise ValueError(f'texture {name} is shown by no material instance')
            owners = stem_unit[stem]
            if len(owners) == 1 and not next(iter(owners)).startswith('shared-'):
                unit[package] = next(iter(owners))
            else:
                unit[package] = f'shared-textures-{stem_family[stem]}'

    # ------------------------------------------------------------------ unit descriptions
    names = collections.Counter(unit.values())
    for name in sorted(names):
        info[name] = {'about': ''}
    for feature, piece in pieces.items():
        name = f'{feature}-{slug(piece["name"])}'
        if name in info:
            line = piece.get('line')
            info[name]['about'] = (f'Crater Park {piece["type"]} "{piece["name"]}" (piece {feature}, line {line}): its '
                                   'render meshes (with its supports and coping), the collision pieces it fills, and '
                                   'the material instances and textures only it uses')
    for name in info:
        if name.startswith('crater-floor-'):
            x, z = (int(v.replace('m', '-')) for v in name[len('crater-floor-'):].split('-'))
            info[name]['about'] = (f"Crater Park crater floor, area block ({x}, {z}): the volcano's ground inside the "
                                   f'crater, cut by the park, 64 m tiles x {BLOCK * x} to {BLOCK * x + BLOCK - 1}, '
                                   f'z {BLOCK * z} to {BLOCK * z + BLOCK - 1} (render meshes only)')
    fixed = {
        GENERATOR: 'Crater Park parent materials, and the generator that made every Crater Park package (the region and '
                   'editor scripts, the shipped park document and its terrain, the texture, shrine and import scripts)',
        'collision-mixed': 'Crater Park collision pieces of the z-ordered sections that no single feature fills '
                           f'(under {int(PURE * 100)} % of their triangles from one feature); the ownership ledger '
                           'lists their features',
        'cloud': 'Crater Park lenticular cap cloud materials (cloud.py shells, ACraterCloud)'}
    for name, about in fixed.items():
        if name in info:
            info[name]['about'] = about
    for name in info:
        if name.startswith('shared-materials-'):
            info[name]['about'] = f'Crater Park material instances several units share, surface family {name.split("-", 2)[2]}'
        elif name.startswith('shared-textures-'):
            info[name]['about'] = f'Crater Park textures several units share, surface family {name.split("-", 2)[2]}'
    unnamed = sorted(n for n, i in info.items() if not i['about'])
    if unnamed:
        raise ValueError(f'units without a description: {unnamed[:3]}')

    # ------------------------------------------------------------------ sources
    def painting(slug_: str) -> list[str]:
        return existing([f'{ASSETS}restyle/{slug_}.jpg', f'{ASSETS}restyle/{slug_}.json'])

    def texture_sources(stem: str) -> list[str]:
        out = []
        if stem in ct.SURFACES:
            painted = ct.REPAINTED.get(stem, (stem,))[0]
            out += painting(painted) + existing([ASSETS + ct.SURFACES[stem][0]])
        elif stem in ct.DECALS:
            out += painting(stem) + existing([ASSETS + 'concepts/editor/prado-plan.png'])
        elif stem in ct.UV_PAINTINGS:
            out += painting(stem)
        elif stem == Path(ct.LETTERS).stem:
            out += painting('concrete')
        elif stem.startswith('shrine_'):
            out += []
        elif stem in ct.WORLD_ALIGNED:
            slug_ = ct.WORLD_ALIGNED[stem][0]
            if slug_.startswith('megapark:'):
                out += existing([f'{D}assets/megapark/restyle/{slug_.split(":")[1]}.{e}' for e in ('jpg', 'json')])
            else:
                out += painting(slug_)
        else:
            for key, (painted, _) in ct.BOOST_PAINTS.items():
                if Path(key).stem == stem:
                    out += painting(painted)
        return out

    sources: dict[str, set] = collections.defaultdict(set)
    gaps = []
    for package in packages:
        name = package.rsplit('/', 1)[1]
        if name.startswith('T_CP_'):
            stem = name[len('T_CP_'):]
            found = texture_sources(stem)
            if not found and not stem.startswith('shrine_'):
                gaps.append(name)
            sources[unit[package]].update(found)
    # the tower's shrine models (Tripo outputs and their prompts)
    for slug_ in ('bell_pavilion', 'nobori', 'stone_lantern', 'torii'):
        for p in sorted((DONOR / 'assets/craterpark/shrine' / slug_).glob('*')):
            if p.is_file():
                sources[unit[next(q for q in packages if q.endswith('T_CP_shrine_' + slug_))]].add(
                    D + p.relative_to(DONOR).as_posix())
    for name in CLOUD:
        sources['cloud'].add(D + name)
    generator = set(D + f for f in GENERATOR_FILES) | {f for folder in GENERATOR_FOLDERS for f in donor_files(folder)}
    # pictures the paintings were made from (STYLES crops, the Prado plan and layout)
    for path, _ in ct.STYLES.values():
        generator.add(D + Path(path).relative_to(DONOR).as_posix() if Path(path).is_relative_to(DONOR)
                      else 'games/' + Path(path).relative_to(DONOR.parent).as_posix())
    generator.add(ASSETS + 'concepts/editor/prado-graphics-layout.jpg')
    for slug_ in ('rock',):
        generator.update(existing([f'{D}assets/megapark/restyle/{slug_}.json']))
    generator = {g for g in generator if (REPO / g).is_file()}
    missing = sorted(g for g in generator if not (REPO / g).is_file())
    sources[GENERATOR].update(generator)
    for name, row in info.items():
        if sources.get(name):
            row['sources'] = sorted(sources[name])
        if name != GENERATOR:
            row['references'] = [f'adopted/craterpark/{GENERATOR}']
    if gaps or missing:
        raise ValueError(f'sources missing: {gaps[:3]} {missing[:3]}')
    return {'about': 'Crater Park editing units for tools/migrate/adopt.py (written by tools/migrate/craterpark_units.py)',
            'units': dict(sorted(info.items())), 'packages': dict(sorted(unit.items()))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    parser.add_argument('--measure', type=Path, help="refresh the ownership ledger from the generator's geometry.npz")
    args = parser.parse_args(argv)
    if args.measure:
        LEDGER.write_text(json.dumps(measure(args.measure), indent=1) + '\n')
        print(f'{LEDGER.relative_to(REPO)} written')
        return 0
    text = json.dumps(build(GAME), indent=1) + '\n'
    if args.check:
        same = OUT.is_file() and OUT.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    OUT.write_text(text)
    counts = collections.Counter(json.loads(text)['packages'].values())
    print(f'{OUT.relative_to(REPO)}: {sum(counts.values())} packages in {len(counts)} units; largest '
          + ', '.join(f'{u} {n}' for u, n in counts.most_common(4)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
