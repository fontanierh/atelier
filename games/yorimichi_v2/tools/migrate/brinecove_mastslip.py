"""Brine Cove signal mast and stone shipyard slip as their own objects, cut out of their residual tiles
(docs/inventory/exceptions.md, the two Brine Cove rows; docs/inventory/brinecove-objects.md for the donor boundaries).

Both objects are straight-line constructor code, not loops, so the loop-header replay of brinecove_market.py cannot
find them. This tool replays the owning constructor in pure Python at the donor's recorded RNG position and tags each
face by the source block that made it:

- `signal-mast`: the block of `procedural/market.py` market() from its `# Signal mast` comment to the `# Well.` comment
  (the mast, crossyard, rigging, bunting and crow's nest; 250 faces, all in the Market tiles at 3,4 and 4,4).
- `shipyard-slip`: every face `brinecove/landmarks.py` `_slipway()` makes: the stone block, kerbs and wet centre strip,
  and the wood sleepers and ground ways. The object is whole. Batch 1 already cut part of the wood into `shipyard-yard`
  (the same radius rule reproduces its 9,558 triangles), so `plan` reports those triangles as taken from the yard: the
  yard keeps only what is left of its own geometry.

Every generated face is then matched to the donor GLB triangle with the same float32 positions (brinecove_market.py's
face index), so each triangle gets its generating object or none. Nothing is measured by distance; the donor generator is
read, never modified. The donor GLB tiles are read by name and triangle only: the Market tiles are piece-split
(`SM_BC_Market_3_4_Piece*`), so every GLB file whose name starts with a tile stem is matched, whatever its piece suffix.

    python3 games/yorimichi_v2/tools/migrate/brinecove_mastslip.py paths [--donor DONOR_BUILD] [--json]
    python3 games/yorimichi_v2/tools/migrate/brinecove_mastslip.py plan  --donor DONOR_BUILD [--json]

`paths` reads only generator source and (with --donor) the donor's GLB file names. It prints every path, lock and
scope a claim needs for the two objects: the new records, the residual tile records they trim, the expectation file
`split-mastslip.json`, the region objects and the runtime lock. `--json` prints {"paths": [...], "scopes": [...],
"locks": [...]}. A claim must cover that whole set; the apply machinery refuses any write it does not cover.

`plan` also needs the donor GLB triangles. It prints each object's triangles per donor tile (piece names included), its
bounds and the trimmed remainder's counts, and refuses unless every donor triangle is matched exactly once. It writes
nothing; the apply step is the shared brinecove_split_apply machinery, which this tool does not run.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brinecove_market as market  # noqa: E402  (glb_point, face_index, owners_of, donor_source)
import brinecove_split as split  # noqa: E402
import recover  # noqa: E402

GAME_REL = 'games/yorimichi_v2'
REGION = 'w09-brinecove'
RUNTIME_LOCK = 'runtime-data.lock.json'
RUNTIME = 'Data/brinecove/runtime.json'
ENVIRONMENT = 'w00-island'          # the actor saves also write the environment region's manifest (brinecove-split.md)
TILE = 256.0
EXPECTED_NAME = 'split-mastslip.json'
PIECE_LIMIT = 32768                  # build.py's MIXED_TRIANGLE_LIMIT: a larger tile is cut into _PieceN models

MARKET_FILE = ('brinecove', 'procedural', 'market.py')
HARBOR_FILE = ('brinecove', 'procedural', 'harbor.py')
LANDMARKS_FILE = ('brinecove', 'landmarks.py')
MAST_HEADER = "# Signal mast, crossyard, rigging, bunting and a crow's nest."
MAST_END = '# Well.'


class MastSlipError(RuntimeError):
    pass


OBJECTS = {
    'signal-mast': dict(component='Market', module='market', tile_prefix='Market'),
    'shipyard-slip': dict(component='Harbor', module='harbor', tile_prefix='Harbor'),
}
PREFIX_OF = {name: spec['tile_prefix'] for name, spec in OBJECTS.items()}
YARD = 'shipyard-yard'          # batch 1's object that holds part of the slipway's wood (split.OBJECTS)
YARD_TRIANGLES = 9558           # its saved triangle count (split-batch1.json)


def soft_prefixes() -> tuple:
    """The generator's SOFT material prefixes, read from build.py (which imports bpy, so it cannot be imported here)."""
    tree = ast.parse((HERE.parents[2] / 'yorimichi' / 'world' / 'regions' / 'brinecove' / 'build.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'SOFT' for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise MastSlipError('build.py has no SOFT tuple')


def block_lines(source: str) -> tuple[int, int]:
    """First and last source line of the signal mast block inside market(), found by its comment text."""
    lines = source.splitlines()
    head = [i for i, line in enumerate(lines, 1) if line.strip() == MAST_HEADER]
    if len(head) != 1:
        raise MastSlipError(f'signal mast header found {len(head)} times in the donor market module')
    end = [i for i, line in enumerate(lines, 1) if i > head[0] and line.strip() == MAST_END]
    if not end:
        raise MastSlipError('no "# Well." comment after the signal mast block')
    return head[0] + 1, end[0] - 1


def _under(frame_path: str, parts: tuple) -> bool:
    return frame_path.replace('\\', '/').endswith('/'.join(parts))


def owner_rule(name: str, source: str):
    """@cc [owner:fontanierh,label:correctness] brinecove-mastslip-owner-rule
    (frame, material) -> owner name or None. The frame is the face's maker; the walk goes outward to the constructor.
    A face belongs to the mast only inside the source block between its comment headers, and to the slip only when
    _slipway() made it and it is stone; any other face is nobody's, so it stays in the residual tile."""
    if name == 'signal-mast':
        first, last = block_lines(source)

        def mast(frame, mat):
            while frame is not None:
                if _under(frame.f_code.co_filename, MARKET_FILE):
                    return 'signal-mast' if first <= frame.f_lineno <= last else None
                frame = frame.f_back
            return None
        return mast

    def slip(frame, mat):
        while frame is not None:
            if frame.f_code.co_name == '_slipway' and _under(frame.f_code.co_filename, LANDMARKS_FILE):
                return 'shipyard-slip'
            if _under(frame.f_code.co_filename, HARBOR_FILE):
                return None
            frame = frame.f_back
        return None
    return slip


def _forget():
    for name in [n for n in sys.modules if n == 'brinecove' or n.startswith('brinecove.') or n == 'random_stream']:
        del sys.modules[name]


def replay(src: Path, name: str) -> dict:
    """Run the donor constructor that makes object `name` at its recorded RNG position. Returns the Builder's lists, the
    owner of every face (None for faces of other objects) and the donor's tile origin (region.OUTER)."""
    import importlib
    spec = OBJECTS[name]
    module = spec['module']
    source = (src / 'world' / 'regions' / 'brinecove' / 'procedural' / f'{module}.py').read_text()
    rule = owner_rule(name, source)
    old_flag, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    added = [str(src / 'world'), str(src / 'world' / 'regions')]
    sys.path[:0] = added
    _forget()
    try:
        from random_stream import positioned
        params = json.loads((src / 'assets' / 'brinecove' / 'export-parameters' / f'{spec["component"]}.json').read_text())
        state = importlib.import_module('brinecove.procedural.random_state')
        state.RNG.setstate(positioned(params['seed'], params['prefix_words']).getstate())
        mod = importlib.import_module(f'brinecove.procedural.{module}')
        geom = importlib.import_module('brinecove.geom')
        region = importlib.import_module('brinecove.region')
        owner: list = []
        original = geom.Builder.face

        def face(self, points, mat, uvs=None, normals=None):
            before = len(self.faces)
            original(self, points, mat, uvs, normals)
            owner.extend([rule(sys._getframe(1), mat)] * (len(self.faces) - before))

        geom.Builder.face = face
        try:
            builder = getattr(mod, module)()
        finally:
            geom.Builder.face = original
        if len(owner) != len(builder.faces):
            raise MastSlipError('face ownership lost count; the builder changed faces outside Builder.face')
        return {'verts': builder.verts, 'faces': builder.faces, 'mats': builder.mats, 'owner': owner,
                'outer': tuple(region.OUTER)}
    finally:
        for path in added:
            sys.path.remove(path)
        _forget()
        sys.dont_write_bytecode = old_flag


def tile_of(built: dict, face: tuple) -> tuple[int, int]:
    """The donor tile (x, y) a generated face is cut into, by its centre (build.py's split())."""
    ox0, oy0 = built['outer'][0], built['outer'][1]
    pts = [built['verts'][i] for i in face]
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return int((cx - ox0) // TILE), int((cy - oy0) // TILE)


def summary(built: dict) -> dict:
    """{owner: {'faces', 'triangles', 'tiles': {tile stem: triangles}, 'materials'}} for every owner but None. The tile stem
    is the generator's (no piece suffix; a Soft stem keeps `_Soft`)."""
    soft = soft_prefixes()
    out: dict = {}
    for face, owner, mat in zip(built['faces'], built['owner'], built['mats']):
        if owner is None:
            continue
        x, y = tile_of(built, face)
        stem = f'{PREFIX_OF[owner]}_{x}_{y}' + ('_Soft' if mat.startswith(soft) else '')
        info = out.setdefault(owner, {'faces': 0, 'triangles': 0, 'tiles': defaultdict(int), 'materials': set()})
        info['faces'] += 1
        info['triangles'] += len(face) - 2
        info['tiles'][stem] += len(face) - 2
        info['materials'].add(mat)
    for info in out.values():
        info['tiles'] = dict(sorted(info['tiles'].items()))
        info['materials'] = sorted(info['materials'])
    return out


def record_id(name: str) -> str:
    return f'prop/brinecove/{name}'


def part_mesh(name: str) -> str:
    return 'SM_BC_' + ''.join(part.title() for part in name.split('-'))


def tile_record(stem: str) -> str:
    """A residual tile's record ID, by the split tools' own convention (recover.ident)."""
    return 'prop/brinecove/' + recover.ident(stem)


def ranges(ordinals) -> list[list[int]]:
    """Sorted ordinals as half-open [start, end) ranges, the form the carve selection files use."""
    out: list[list[int]] = []
    for i in sorted(set(ordinals)):
        if out and out[-1][1] == i:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return out


def donor_stems(donor: Path | None) -> list[str]:
    """Every donor GLB stem (piece suffixes included) of the Market and Harbor tiles, from the file names only."""
    if donor is None:
        return []
    glb = Path(donor) / 'brinecove' / 'glb'
    stems = set()
    for prefix in sorted(set(PREFIX_OF.values())):
        for path in glb.glob(f'SM_BC_{prefix}_*.glb'):
            stems.add(path.stem[len('SM_BC_'):])
    return sorted(stems)


def expand(tile: str, stems: list[str]) -> list[str]:
    """The GLB stems of one generator tile: the tile itself, or its _PieceN slices when the build cut it."""
    return [s for s in stems if s == tile or re.fullmatch(re.escape(tile) + r'_Piece\d+', s)] or [tile]


def claim_set(donor: Path | None, summaries: dict, result: dict | None = None) -> dict:
    """The complete claim set for the two objects (a superset of what apply writes): folders end with '/', plus the
    scopes and the lock. Residual tile records come from the donor GLB names when --donor is given."""
    paths, scopes = set(), set()
    stems = donor_stems(donor)
    for name in OBJECTS:
        record = record_id(name)
        paths.add(f'{GAME_REL}/assets/{record}/')
        paths.add(f'{GAME_REL}/assets/{record}/asset.toml')
        paths.add(f'{GAME_REL}/assets/{record}/src/{part_mesh(name)}.glb')
        scopes.add((f'asset/{record}', 'shared/brinecove/' + name))
        scopes.add((f'object/brinecove/{name}', f'region/{REGION}'))
    if result is not None:
        # exact: the GLB files the plan trims (each carve it changes), not every piece of the generator's tile
        tiles = sorted(result['trimmed'])
        glb_stems = tiles
    else:
        tiles = sorted({t for name in OBJECTS for t in summaries.get(name, {}).get('tiles', {})})
        glb_stems = [g for tile in tiles for g in expand(tile, stems)]
    for glb_stem in glb_stems:
        record = tile_record(glb_stem)
        paths.add(f'{GAME_REL}/assets/{record}/asset.toml')
        paths.add(f'{GAME_REL}/assets/{record}/src/{carve_name(glb_stem)}')
        scopes.add((f'asset/{record}', 'shared/brinecove/' + record.rsplit('/', 1)[1]))
    # batch 1's shipyard-yard part gives up the slipway's wood: its record and its expectation change too
    paths.add(f'{GAME_REL}/assets/prop/brinecove/shipyard-yard/')
    scopes.add(('asset/prop/brinecove/shipyard-yard', 'shared/brinecove/shipyard-yard'))
    paths.add(f'{GAME_REL}/world/regions/{REGION}/split-batch1.json')
    paths.add(f'{GAME_REL}/world/regions/{REGION}/{EXPECTED_NAME}')
    paths.add(f'{GAME_REL}/world/regions/{REGION}/objects.toml')
    paths.add(f'{GAME_REL}/{RUNTIME_LOCK}')
    scopes.add(f'region/{REGION}')
    scopes.add(f'region/{ENVIRONMENT}')
    return {'paths': sorted(paths),
            'scopes': sorted(s if isinstance(s, str) else ' or '.join(s) for s in scopes),
            'locks': [f'{GAME_REL}/{RUNTIME_LOCK}'],
            'residual_tiles': tiles,
            'donor_glb_stems': stems if donor else None}


def carve_name(stem: str) -> str:
    return f'SM_BC_{stem}.carve.json'


def carved_kept(game: Path, stem: str) -> set | None:
    """The triangle ordinals a tile's existing carve keeps (its remainder before this batch), or None if it was never
    carved. Earlier batches' carves are the base: this batch removes its objects from what they left."""
    path = game / 'assets' / tile_record(stem) / 'src' / f'SM_BC_{stem}.carve.json'
    if not path.is_file():
        return None
    return {i for a, b in json.loads(path.read_text())['kept'] for i in range(a, b)}


def yard_ordinals(glb: Path) -> dict:
    """{tile stem: set of ordinals} that batch 1's radius rule cut into shipyard-yard (split.compute, unchanged)."""
    radial = split.compute(glb, {YARD: split.OBJECTS[YARD]})
    return {stem: set(owned.get(YARD, [])) for stem, owned in radial['owned'].items()}


def plan(donor: Path, src: Path, game: Path = HERE.parents[1]) -> dict:
    """Match every donor GLB triangle of the Market and Harbor tiles to the generated faces, then account each object
    against the tile's existing carve (the remainder left by earlier batches). Per object: triangles per GLB file as
    half-open ordinal ranges, bounds, the triangles still in the remainder and those taken from shipyard-yard. Per
    trimmed file: kept before and after. The yard's count before and after. Raises unless every triangle is matched
    by exactly one face, every mast triangle is still in its tile's remainder, and every slip triangle is either in the
    remainder or in batch 1's shipyard-yard part. Writes nothing."""
    glb = donor / 'brinecove' / 'glb'
    combined = {'verts': [], 'faces': [], 'mats': [], 'owner': []}
    for name in OBJECTS:
        built = replay(src, name)
        base = len(combined['verts'])
        combined['verts'] += built['verts']
        combined['faces'] += [tuple(i + base for i in f) for f in built['faces']]
        combined['mats'] += built['mats']
        combined['owner'] += built['owner']
    index = market.face_index(combined)
    yards = yard_ordinals(glb)
    out = {'objects': {name: {'triangles': 0, 'from_residual': 0, 'from_shipyard_yard': 0, 'files': {}, 'min': None,
                              'max': None} for name in OBJECTS},
           'trimmed': {}, 'shipyard_yard': {'before': YARD_TRIANGLES, 'removed': 0, 'after': YARD_TRIANGLES,
                                             'files': {}}}
    for stem in donor_stems(donor):
        model = split.read_glb(glb / f'SM_BC_{stem}.glb')
        tris = list(split.triangles(model))
        owners = market.owners_of(tris, index)
        kept = carved_kept(game, stem)
        if kept is None:
            kept = set(range(len(tris)))
        taken = defaultdict(list)
        for ordinal, owner in enumerate(owners):
            if owner in OBJECTS:
                taken[owner].append(ordinal)
        if not taken:
            continue
        removed_now = 0
        for name, members in taken.items():
            residual = [i for i in members if i in kept]
            from_yard = [i for i in members if i not in kept]
            foreign = [i for i in from_yard if i not in yards.get(stem, set())]
            if name == 'signal-mast' and from_yard:
                raise MastSlipError(f'{stem}: {len(from_yard)} mast triangles already taken by an earlier batch')
            if foreign:
                raise MastSlipError(f'{stem}: {len(foreign)} {name} triangles are neither in the remainder nor in '
                                    f'{YARD}')
            lo, hi = split.bounds(tris, members)
            item = out['objects'][name]
            item['triangles'] += len(members)
            item['from_residual'] += len(residual)
            item['from_shipyard_yard'] += len(from_yard)
            item['files'][stem] = ranges(members)
            item['min'] = list(lo) if item['min'] is None else [min(a, b) for a, b in zip(item['min'], lo)]
            item['max'] = list(hi) if item['max'] is None else [max(a, b) for a, b in zip(item['max'], hi)]
            removed_now += len(residual)
            if from_yard:
                out['shipyard_yard']['files'][stem] = len(from_yard)
                out['shipyard_yard']['removed'] += len(from_yard)
        before = len(kept)
        out['trimmed'][stem] = {'kept_before': before, 'removed': removed_now, 'kept_after': before - removed_now}
    out['shipyard_yard']['after'] = YARD_TRIANGLES - out['shipyard_yard']['removed']
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=('paths', 'plan'))
    parser.add_argument('--donor', type=Path, help='the donor build/yorimichi folder (paths: GLB names; plan: GLB triangles)')
    parser.add_argument('--donor-src', type=Path, help='the donor games/yorimichi folder (default: next to --donor)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--game', type=Path, default=HERE.parents[1], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        donor = args.donor.resolve() if args.donor else None
        src = market.donor_source(donor, args.donor_src) if donor else None
        if args.command == 'plan':
            if donor is None or src is None:
                parser.error('plan needs --donor (the donor GLB triangles)')
            print(json.dumps(plan(donor, src, args.game.resolve()), indent=2, default=list))
            return 0
        if src is None:
            # paths without a donor reads only the generator (for the object list and tile names)
            src = args.game.resolve().parent / 'yorimichi'
        summaries: dict = {}
        for name in OBJECTS:
            summaries.update(summary(replay(src, name)))
        result = plan(donor, src, args.game.resolve()) if donor else None
        info = claim_set(donor, summaries, result)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print('# claim paths (a trailing / is a folder: every file in it)')
            print('\n'.join(info['paths']))
            print('# scopes')
            print('\n'.join(info['scopes']))
            print('# locks: ' + ', '.join(info['locks']))
            print('# residual tiles: ' + ', '.join(info['residual_tiles']))
            if info['donor_glb_stems'] is None:
                print('# piece names need --donor: the Market tiles are cut into _PieceN models')
        return 0
    except (MastSlipError, market.MarketError) as error:
        print(f'mast/slip split failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
