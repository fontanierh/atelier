"""Write Belmonte's editing units (assets/adopted/belmonte/units.json) for its ownership split (audit A3).

    uv run python games/yorimichi_v2/tools/migrate/belmonte_units.py [--check]

Belmonte is a library of 288 models imported from the Haras valley project (games/yorimichi/assets/belmonte/source.json
pins the source revision and every model and texture checksum) plus two generated northern terrain meshes. Each
committed GLB is one source model; the V2 packages are named for it (`SM_BM_<Group>_<Model>`), with a
`_Collision` hull beside it and `_PieceN` slices where the build bounded an oversized model (model_pieces.py), so:

- one building, furniture model or country prop is one unit with its collision hull and pieces (`town-church`,
  `prop-bench`, `estate-3` for the villa, stables, grounds and accent of one estate, `hippodrome-salon`);
- repeated rendering batches stay grouped: the 56 terrain tiles are `terrain-<x>-<y>` (ground carved at build time),
  the 39 town blocks `block-<nn>`, and the civil paving, works, water, wall, rock and strata sets are family units;
- each material instance goes with its one object when only that object uses it (the estate accents, the cafe chair,
  the salon posters, the emblems), else to a shared unit by surface family (`shared-stone`, `shared-plaster`, ...);
  each texture goes with its materials, or to the shared family that uses it;
- `NorthCountry` and `NorthApron` have no committed model: the region generator builds them from the valley query data,
  so they only reference `generator`.

Sources are repository paths (adopt.py --repartition copies them into the record and pins hashes): an object unit its
GLB model(s) and, for sliced models, the whole parent GLB; a texture unit its source image; `generator` the region scripts, Unreal import
script, source.json, library and acquisition tools.
The 7.7 MB source.json (the pinned Haras revision, material settings and placements) lives once in `generator`, which
holds the generated base materials and which every other unit references.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
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
ASSETS = 'games/yorimichi/assets/belmonte/'
OUT = GAME / 'assets' / 'adopted' / 'belmonte' / 'units.json'
ROOT = '/Game/Belmonte/'
RUNTIME = GAME / 'unreal' / 'Content' / 'Data' / 'belmonte' / 'runtime.json'

# Model groups that make one structure or one family, longest prefix first: (regex on the model name, unit).
MERGE = [
    (r'BE_(\d)_(?:Accent|Grounds|Stables|Villa)$', r'estate-\1'),
    (r'BHip_(?:Salon|SalonGrounds|SalonHall)$', 'hippodrome-salon'),
    (r'BHip_(?:Stand|StandShell|StandGardens|StandTerrace)$', 'hippodrome-stand'),
    (r'BHip_(?:Stables|StableYard)$', 'hippodrome-stables'),
    (r'BH_(?:Osteria|Osteria_Taproom|OsteriaPergola)$', 'town-osteria'),
    (r'BC_Water_Ponte$|BC_Ponte$', 'civil-ponte'),
    (r'BC_Water_\d$', 'civil-water'),
    (r'BC_Mura_\d$', 'civil-mura'),
    (r'BC_GorgeStrata_\d$', 'civil-gorge-strata'),
    (r'BC_Pave_\d_\d$', 'civil-pave'),
    (r'BC_Works_\d_\d$', 'civil-works'),
    (r'BC_Rock_[ABC]$', 'civil-rocks'),
    (r'BP_StallGoods_[A-G]$', 'prop-stall-goods'),
    (r'BP_CrateProduce_[AB]$', 'prop-crate-produce'),
    (r'BP_StonePlanter_[AB]$', 'prop-stone-planter'),
    (r'HV_Emblem_\w+$', 'emblems'),
    (r'BT_Terrain_(\d)_(\d)$', r'terrain-\1-\2'),
    (r'BT_blk_(\d+)$', r'block-\1'),
    (r'BVV_Village_(\d)$', r'village-house-\1'),
]
PREFIX = {'AT': '', 'BC': 'civil', 'BE': 'estate', 'BH': 'town', 'BHip': 'hippodrome', 'BP': 'prop', 'BVV': 'village',
          'BT': 'terrain'}
GENERATED = {'north-country': 'SM_BM_NorthCountry', 'north-apron': 'SM_BM_NorthApron'}
# Shared material families by the surface a source material paints (source.json material name).
FAMILY = {'terrain_town': 'ground', 'turf': 'ground', 'sand': 'ground', 'gravel': 'ground', 'dirt': 'ground',
          'rock_town': 'ground', 'ashlar': 'stone', 'stone': 'stone', 'rubble': 'stone', 'piazza': 'stone',
          'cobble': 'stone', 'flag': 'stone', 'plaster': 'plaster', 'plaster_rough': 'plaster', 'wood': 'timber',
          'floor': 'timber', 'roof': 'roof', 'iron': 'metal-glass', 'glass_dark': 'metal-glass',
          'window_lit': 'metal-glass', 'vcol': 'metal-glass', 'farwall': 'metal-glass', 'water': 'water',
          'water_river': 'water'}
CARVED = {'terrain-4-3', 'terrain-5-2', 'terrain-5-3', 'terrain-6-2'}   # ground_names.VALLEY_CARVED_TILES
SLICE = re.compile(r'_Piece\d+')
GENERATOR_FILES = ('games/yorimichi/world/source_registry.py', 'games/yorimichi/assets/source-library.json',
                   'games/yorimichi/unreal/Scripts/import_belmonte.py')
GENERATOR_FOLDER = 'world/regions/belmonte'
LIBRARY_FILES = (ASSETS + 'source.json', ASSETS + 'README.md', 'games/yorimichi/tools/belmonte_extract.py',
                 'games/yorimichi/tools/belmonte_convert.py')
TUSCAN = ('games/yorimichi/assets/environment/textures/tuscan-ground.jpg',
          'games/yorimichi/assets/environment/textures/tuscan-ground.provenance.json')


def model_of(stem: str) -> str:
    """The committed model a mesh package is made from: collision hulls and slices fold into their render model."""
    return SLICE.sub('', stem[:-len('_Collision')] if stem.endswith('_Collision') else stem)


def unit_of_model(model: str) -> str:
    name = model[len('SM_BM_'):]
    for pattern, unit in MERGE:
        if re.fullmatch(pattern, name):
            return re.sub(pattern, unit, name)
    group, _, rest = name.partition('_')
    kebab = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|_', '-', rest).lower()
    return '-'.join(p for p in (PREFIX[group], kebab) if p)


def mesh_unit(stem: str) -> str:
    model = model_of(stem)
    for unit, owner in GENERATED.items():
        if model == owner:
            return unit
    return unit_of_model(model)


def hashed(text: str, prefix: str, ext: str = '') -> str:
    return prefix + hashlib.sha256(text.encode()).hexdigest()[:12] + ext


NORTH_ROOTS = ('world/regions/belmonte/north_pipeline.py', 'world/regions/belmonte/north_context.py',
               'world/regions/belmonte/north_apron.py', 'world/regions/belmonte/north_country.py',
               'world/regions/belmonte/terrain.py', 'world/surface_textures.py', 'belmonte_north_build.py',
               'belmonte_scene_build.py', 'world/yori.py', 'world/gen_world.py')
# The extra inputs of the donor's world.layout step (build.py), which writes world.json, heightmap.npy and farhills.npy:
# the layout modules of every region it places, the crater park scene and geometry, and the Belmonte railway corridor.
WORLD_INPUTS = ('world/regions/forest/ecotone.py', 'world/regions/forest/specs.py', 'world/regions/houses/layout.py',
                'world/torii_clearance.py', 'world/regions/village/layout.py', 'world/regions/mega/layout.py',
                'world/regions/southwest/layout.py', 'world/regions/skatepark/pier_site.py',
                'world/regions/forest_lake/layout.py', 'world/regions/zeppelin/layout.py',
                'world/regions/treehouse/layout.py', 'world/regions/treehouse/screen.py',
                'world/regions/megapark/placement.py', 'world/regions/megapark/forest.py',
                'world/regions/megapark/trail.py', 'world/regions/megapark/gate.py',
                'world/regions/hidamari/mountains.py', 'world/regions/hidamari/layout.py',
                'world/regions/hidamari_stable/layout.py', 'world/regions/hidamari/forest_backdrop.py',
                'world/farhills_grid.py', 'world/regions/craterpark/placement.py',
                'world/regions/craterpark/v2/v4_config.py', 'assets/craterpark/scene.json',
                'assets/craterpark/geometry', 'world/train/corridor.py', 'world/train/earthworks.py',
                'world/train/station_site.py', 'assets/vehicles/belmonte-train/line.json')


def north_inputs() -> list[str]:
    """Everything the northern terrain reads: its scripts, the modules they import (the same scanner the donor build
    uses for its step inputs), and the world.layout step that produces the heightmap, far hills and road anchor."""
    sys.path.insert(0, str(REPO / 'platform' / 'studio'))
    from atelier.build_inputs import local_imports
    roots = [DONOR / r for r in NORTH_ROOTS]
    found = set()
    for path in [*roots, *(DONOR / w for w in WORLD_INPUTS)]:
        if path.is_dir():
            found |= {p for p in path.rglob('*') if p.is_file()}
        elif path.is_file():
            found.add(path)
            if path.suffix == '.py':
                found |= {Path(p) for p in local_imports(path, (DONOR / 'world', DONOR / 'world' / 'regions'))}
        else:
            raise ValueError(f'{path} is missing')
    return sorted(f'games/yorimichi/{p.relative_to(DONOR).as_posix()}' for p in found
                  if DONOR in p.parents and '__pycache__' not in p.parts)


def donor_files(folder: str) -> list[str]:
    return [f'games/yorimichi/{p.relative_to(DONOR).as_posix()}' for p in sorted((DONOR / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts]


def build(game: Path) -> dict:
    packages = sorted(o.package for a in records.discover(game)[0] if a.id.startswith('adopted/belmonte/')
                      for o in a.outputs)
    if any(not p.startswith(ROOT) for p in packages):
        raise ValueError('an adopted/belmonte record owns a package outside /Game/Belmonte')
    data = json.loads((DONOR / 'assets/belmonte/source.json').read_text())
    runtime = json.loads(RUNTIME.read_text())
    glbs = {p.stem for p in (DONOR / 'assets/belmonte/meshes').glob('*.glb')}

    unit, models = {}, collections.defaultdict(set)
    for p in packages:
        if '/Meshes/' in p:
            stem = p.rsplit('/', 1)[1]
            unit[p] = mesh_unit(stem)
            models[unit[p]].add(model_of(stem))
    mesh_of = {p.rsplit('/', 1)[1]: unit[p] for p in unit}

    # Materials: which source material made each MI, which units draw with it, and the texture it carries.
    source = {}
    for path, entry in data['materials'].items():
        if path.endswith('MI_B_foliage'):
            continue
        texture = entry['textures'].get('BaseColor') or entry['textures'].get('DryColor')
        terrain, atlas = 'terrain_' in path, 'SalonPosters' in path or '/Atelier/' in path
        key = ('tuscan-ground' if terrain else texture) + (':atlas' if atlas else ':detail') if texture else None
        source[hashed(path, 'MI_BM_')] = (path.rsplit('/', 1)[1].split('.')[0].removeprefix('MI_B_'), texture, key)
    users = collections.defaultdict(set)
    for group in runtime['groups']:
        mesh = group['asset'].rsplit('/', 1)[1].split('.')[0]
        if mesh not in mesh_of:   # recovered as generated records (tools/migrate/recover.py): no unit of this map
            continue
        for material in group['materials']:
            users[material.rsplit('/', 1)[1].split('.')[0]].add(mesh_of[mesh])
    mat_unit = {}
    for p in packages:
        name = p.rsplit('/', 1)[1]
        if '/Materials/' not in p:
            continue
        if name not in source:   # M_Belmonte, M_BelmonteJoin, MI_BM_Ground: made by the build and import scripts
            mat_unit[name] = 'generator'
        elif len(users[name]) == 1:
            mat_unit[name] = next(iter(users[name]))
        else:
            family = FAMILY.get(source[name][0])
            mat_unit[name] = 'shared-' + family if family else 'shared-utility'
    for p in packages:
        if '/Materials/' in p:
            unit[p] = mat_unit[p.rsplit('/', 1)[1]]

    # Textures: with the units of the materials that carry them, else the shared family of those materials.
    by_key = {key: [m for m, (_, _, k) in source.items() if k == key and m in mat_unit] for key in
              {k for _, _, k in source.values() if k}}
    tex_name = {hashed(key, 'T_BM_'): key for key in by_key}
    image = {}
    for p in packages:
        if '/Textures/' not in p:
            continue
        name = p.rsplit('/', 1)[1]
        if name not in tex_name:
            raise ValueError(f'{name} matches no Belmonte material texture')
        owners = {mat_unit[m] for m in by_key[tex_name[name]]}
        shared = sorted(o for o in owners if o.startswith('shared-'))
        unit[p] = next(iter(owners)) if len(owners) == 1 else (shared or ['shared-utility'])[0]
        key = tex_name[name]
        if key.startswith('tuscan-ground'):
            image[name] = list(TUSCAN)
        else:
            texture = key.rsplit(':', 1)[0]
            image[name] = [ASSETS + data['textures'][texture]['file']]
    for p in packages:
        if p not in unit:
            raise ValueError(f'{p} fits no Belmonte unit')
    # A generated north unit exists only while its pieces are adopted; recovered pieces are generated records now.

    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        if name == 'generator':
            info[name] = {'about': 'Belmonte region generator and source library: the build scripts, Unreal import script '
                                   'and acquisition tools that made every Belmonte package, the pinned Haras revision '
                                   '(source.json: model and texture checksums, placements, material settings), and the '
                                   'generated base materials'}
        elif name.startswith('shared-'):
            info[name] = {'about': f'Belmonte shared {name[len("shared-"):]} materials and their textures'}
        elif name in GENERATED:
            info[name] = {'about': f'Belmonte {name} terrain: generated by the region scripts from the valley query '
                                   f'data ({counts[name]} bounded pieces); no committed model. Inputs: the island heightmap, far hills '
                                 f'and road anchor come from the world.layout step (world/gen_world.py and the region '
                                 f'layouts, hidamari, train earthworks, hippodrome and farhills_grid modules), all '
                                 f'listed in the generator sources'}
        elif name in models:
            members = sorted(models[name])
            glb = sorted({m for m in members if m in glbs} | {m + '_Collision' for m in members if m + '_Collision' in glbs})
            missing = [m for m in members if m not in glbs]
            if missing:
                raise ValueError(f'{name}: no committed model for {missing[:3]}')
            if name.startswith('terrain-'):
                about = f'Belmonte ground tile {name[len("terrain-"):]} (committed Haras terrain tile; carved at build time)'
                if name in CARVED:
                    about += ('; carved for the railway cutting and station by tools/belmonte_station_terrain.py, '
                              'which is not in the repository (open gap)')
            else:
                about = f'Belmonte {name} ({len(members)} model(s)) with its collision hulls, pieces and own materials'
            info[name] = {'about': about, 'sources': [f'{ASSETS}meshes/{g}.glb' for g in glb]}
        else:
            info[name] = {'about': f'Belmonte {name}'}
    # The sources an owned texture needs, on its unit.
    for p in packages:
        if p in unit and '/Textures/' in p:
            files = info[unit[p]].setdefault('sources', [])
            files.extend(f for f in image[p.rsplit('/', 1)[1]] if f not in files)
    for name, entry in info.items():
        if 'sources' in entry:
            entry['sources'] = sorted(entry['sources'])
    info['generator']['sources'] = sorted(set(GENERATOR_FILES) | set(LIBRARY_FILES) | set(donor_files(GENERATOR_FOLDER))
                                   | set(north_inputs()))
    for name, entry in info.items():
        if name != 'generator':
            entry['references'] = ['adopted/belmonte/generator']
    unit_map = dict(unit)
    return {'about': 'Belmonte editing units for tools/migrate/adopt.py (written by tools/migrate/belmonte_units.py)',
            'units': info, 'packages': unit_map}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    args = parser.parse_args(argv)
    result = build(GAME)
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        same = OUT.is_file() and OUT.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    OUT.write_text(text)
    counts = collections.Counter(result['packages'].values())
    print(f'{OUT.relative_to(REPO)}: {sum(counts.values())} packages in {len(counts)} package units '
          f'({len(result["units"])} units); largest ' + ', '.join(f'{u} {n}' for u, n in counts.most_common(5)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
