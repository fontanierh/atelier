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
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
import brinecove_market as market  # noqa: E402  (glb_point, face_index, owners_of, donor_source)
import brinecove_split as split  # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / 'tools' / 'content'))
import carve  # noqa: E402
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
    """
    @cc [owner:fontanierh,label:correctness] brinecove-mastslip-owner-rule
    (frame, material) -> owner name or None. The frame is the face's maker; the walk goes outward to the constructor.
    A face belongs to the mast only inside the source block between its comment headers. A face of `_slipway()` belongs
    to the slip whatever its material: the stone, the kerbs and the wood sleepers and ground ways are one object, so the
    slip is whole. Any other face is nobody's and stays in its residual tile.
    """
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
    # the yard's re-cut and batch 1's expectation (apply writes both), the new records' verified stamps, the runtime
    # file the groups go into, and the region objects that get the two new parts
    paths.add(f'{GAME_REL}/assets/{YARD_RECORD}/asset.toml')
    paths.add(f'{GAME_REL}/assets/{YARD_RECORD}/src/{YARD_SRC}')
    paths.add(f'{GAME_REL}/assets/{YARD_RECORD}/{YARD_CARVE}')
    paths.add(f'{GAME_REL}/world/regions/{REGION}/split-batch1.json')
    paths.add(f'{GAME_REL}/unreal/Content/{RUNTIME}')
    for name in OBJECTS:
        paths.add(f'{GAME_REL}/assets/{record_id(name)}/verified.json')
        paths.add(f'{GAME_REL}/assets/{record_id(name)}/src/{part_mesh(name)}.glb')
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


def donor_owned(donor: Path, src: Path) -> dict:
    """{stem: {'model', 'tris', 'owners'}} for every donor GLB of the Market and Harbor tiles: the GLB model, its
    triangles, and each triangle's owner (an object name or None). Raises unless every triangle is matched exactly once."""
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
    out = {}
    for stem in donor_stems(donor):
        model = split.read_glb(glb / f'SM_BC_{stem}.glb')
        tris = list(split.triangles(model))
        out[stem] = {'model': model, 'tris': tris, 'owners': market.owners_of(tris, index)}
    return out


def plan(donor: Path, src: Path, game: Path = HERE.parents[1]) -> dict:
    """Per object: triangles per donor GLB file (half-open ordinal ranges), bounds, the triangles still in the remainder and
    those taken from shipyard-yard; per trimmed file: kept before and after; the yard's count before and after. Raises
    unless every mast triangle is still in its tile's remainder and every slip triangle is in the remainder or the yard.
    Writes nothing."""
    files = donor_owned(donor, src)
    yards = yard_ordinals(donor / 'brinecove' / 'glb')
    out = {'objects': {name: {'triangles': 0, 'from_residual': 0, 'from_shipyard_yard': 0, 'files': {}, 'min': None,
                              'max': None} for name in OBJECTS},
           'trimmed': {}, 'shipyard_yard': {'before': YARD_TRIANGLES, 'removed': 0, 'after': YARD_TRIANGLES,
                                             'files': {}}}
    for stem, f in files.items():
        tris, owners = f['tris'], f['owners']
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


# --- the batch: two whole parts, their carves, and the yard re-cut (docs/inventory/brinecove-split.md) -----------------

BATCH = 'mastslip'
YARD_RECORD = 'prop/brinecove/shipyard-yard'
YARD_SRC = 'SM_BC_ShipyardYard.glb'
YARD_BEFORE = 9558         # the donor yard (batch 1's own cut, the original GLB)
YARD_AFTER = 9352          # 8,926 - 192 + 632 - 14 (the yard's Harbor_5_3 and Harbor_5_4 shares, batch 1)
BATCH1 = 'split-batch1.json'


def yard_key(corners) -> tuple:
    return tuple(sorted(split._key(p) for p in corners))


def yard_holds_slip(yard_tris: list, slip_keys: set) -> list[int]:
    """@cc [owner:fontanierh,label:correctness] brinecove-yard-holds-no-slip
    The yard part's ordinals that are still a slipway triangle. The re-cut is complete only when this is empty: the
    slip is whole in its own record, so any slip triangle left in shipyard-yard would be drawn twice."""
    return [n for n, (_, corners) in enumerate(yard_tris) if yard_key(corners) in slip_keys]


def yard_recut(game: Path, donor: Path, src: Path, files: dict, expected_removed: dict) -> dict:
    """The yard's new source GLB, its record, and the batch-1 expectation, with the slipway triangles removed.
    `expected_removed` maps each donor stem to the donor ordinals of slip ∩ yard. Their yard ordinals are found by
    welded corner positions (every donor triangle matches exactly one yard triangle, or the re-cut refuses)."""
    apply_ = market.set_batch(BATCH)
    yard_path = game / 'assets' / YARD_RECORD / 'src' / YARD_SRC
    yard_model = split.read_glb(yard_path)
    yard_tris = list(split.triangles(yard_model))
    index: dict = defaultdict(list)
    for n, (_, corners) in enumerate(yard_tris):
        index[yard_key(corners)].append(n)
    removed_yard = []
    for stem, donor_ords in expected_removed.items():
        for i in donor_ords:
            hits = index.get(yard_key(files[stem]['tris'][i][1]), [])
            if len(hits) != 1:
                raise MastSlipError(f'{stem} triangle {i}: {len(hits)} matching yard triangles, expected exactly one')
            removed_yard.append(hits[0])
    if len(set(removed_yard)) != len(removed_yard):
        raise MastSlipError('two slip triangles match the same yard triangle')
    if not removed_yard:
        raise MastSlipError('no slip triangle is in shipyard-yard: nothing to re-cut')
    data, used = apply_.recut_part(yard_model, removed_yard, 'SM_BC_ShipyardYard')
    kept_tris = [t for n, t in enumerate(yard_tris) if n not in set(removed_yard)]
    if len(kept_tris) != YARD_AFTER:
        raise MastSlipError(f'the yard keeps {len(kept_tris)} triangles, expected {YARD_AFTER}')
    lo, hi = split.bounds(yard_tris, [n for n in range(len(yard_tris)) if n not in set(removed_yard)])
    return {'bytes': data, 'used': used, 'removed_yard': sorted(removed_yard),
            'sha256': hashlib.sha256(data).hexdigest(), 'min': [round(v, 4) for v in lo],
            'max': [round(v, 4) for v in hi]}


def yard_about_text(objects_text: str, triangles: int) -> str:
    """The objects.toml description of the yard, with the triangle count of the derived mesh."""
    return re.sub(r'(id = "object/brinecove/shipyard-yard"\n(?:.*\n)*?about = "[^"]*?)\(9558 triangles\)',
                  lambda m: m.group(1) + f'({triangles} triangles)', objects_text, count=1)


def yard_asset_text(base: str, selection_sha: str) -> str:
    """The yard record's asset.toml as a carved record: the donor's original stays the first pinned source, the selection
    is the second, [derive] names both (tools/content/carve.py), and the recipe counts the derived mesh's triangles."""
    m = re.search(r'(?m)^\[\[sources\]\]\npath = "src/SM_BC_ShipyardYard\.glb"\nsha256 = "[0-9a-f]{64}"\n', base)
    if m is None:
        raise MastSlipError('the yard asset.toml does not pin its original GLB as its first source')
    text = (base[:m.end()] + f'\n[[sources]]\npath = "src/SM_BC_ShipyardYard.carve.json"\nsha256 = "{selection_sha}"\n'
            + base[m.end():])
    text = re.sub(r'(?m)^triangles = \d+$', f'triangles = {YARD_AFTER}', text)
    return carve.with_derive(text, 'src/SM_BC_ShipyardYard.glb', 'src/SM_BC_ShipyardYard.carve.json')


YARD_CARVE = 'src/SM_BC_ShipyardYard.carve.json'
YARD_ORIGINAL = 'src/SM_BC_ShipyardYard.glb'
YARD_ORIGINAL_SHA = '4e9d5402b8207f45a2753cefcb73b62df61658f0861220cd96da1d273e29ebcc'   # main's pin, batch 1's own cut


def yard_original_path(yard_dir: Path) -> Path:
    """The yard record's pinned original GLB inside its folder (YARD_ORIGINAL already names src/)."""
    return yard_dir / YARD_ORIGINAL


def yard_selection(total: int, removed_yard) -> str:
    """The yard's selection file: the original's triangles the derived yard keeps (removed_yard are the slip's)."""
    gone = set(removed_yard)
    return carve.selection_text(total, [i for i in range(total) if i not in gone])


def yard_problems(folder: Path, expected_sha: str, slip_keys: set) -> list[str]:
    """@cc [owner:fontanierh,label:correctness] brinecove-yard-through-carve
    The yard record is checked through its carve only: the derived mesh (tools/content/carve.py's own derivation from the
    pinned original and the selection) must be the expected bytes, have the expected triangles, and hold no slip triangle.
    The committed src/ folder never holds the derived mesh."""
    problems: list[str] = []
    try:
        asset = tomllib.loads((folder / 'asset.toml').read_text())
    except (OSError, ValueError) as error:
        return [f'the yard asset.toml does not parse: {error}']
    sources = {Path(x['path']).name: x['sha256'] for x in asset.get('sources', [])}
    derive = asset.get('derive', {})
    if derive.get('kind') != carve.DERIVE_KIND or derive.get('original') != YARD_ORIGINAL or derive.get('selection') != YARD_CARVE:
        return ['the yard asset.toml has no [derive] carve of its original and selection']
    for name in (YARD_ORIGINAL, YARD_CARVE):
        data = (folder / name).read_bytes() if (folder / name).is_file() else b''
        if not data or hashlib.sha256(data).hexdigest() != sources.get(Path(name).name):
            problems.append(f'{name} is missing or differs from its pinned sha256')
    if problems:
        return problems
    try:
        derived = carve.derive(folder, derive)
    except carve.CarveError as error:
        return [f'the yard carve does not derive: {error}']
    if hashlib.sha256(derived).hexdigest() != expected_sha:
        problems.append('the derived yard differs from the expected bytes')
    tris = list(split.triangles(carve.parse_glb(derived, YARD_ORIGINAL)))
    if len(tris) != YARD_AFTER:
        problems.append(f'the derived yard has {len(tris)} triangles, expected {YARD_AFTER}')
    holds = yard_holds_slip(tris, slip_keys)
    if holds:
        problems.append(f'the derived yard still holds {len(holds)} slip triangle(s)')
    return problems


def build_plan(game: Path, donor: Path, src: Path, stage: Path) -> tuple[dict, dict]:
    """The plan in apply's shape (tiles, parts, remainders), built from the donor GLBs and each tile's existing carve.
    Returns (plan, files). A part takes every triangle of its object in the tile, including the triangles that
    shipyard-yard holds (the whole slip); a remainder keeps the carve's kept triangles minus the objects."""
    apply_ = market.set_batch(BATCH)
    records = apply_.records
    region = game / 'world' / 'regions' / apply_.REGION
    files = donor_owned(donor, src)
    yards = yard_ordinals(donor / 'brinecove' / 'glb')
    owned, prior, models, tris = {}, {}, {}, {}
    for stem, f in files.items():
        mine = {n: [i for i, o in enumerate(f['owners']) if o == n] for n in OBJECTS}
        taken = {i for v in mine.values() for i in v}
        if not taken:
            continue
        kept = carved_kept(game, stem)
        n = len(f['tris'])
        if kept is None:
            kept = set(range(n))
        # the refusal plan() makes: a triangle an earlier batch already took is not this batch's to take again
        for name, members in mine.items():
            for i in members:
                if i in kept:
                    continue
                if name == 'signal-mast' or i not in yards.get(stem, set()):
                    where = 'an earlier batch' if name == 'signal-mast' else f'neither the remainder nor {YARD}'
                    raise MastSlipError(f'{stem}: a {name} triangle is in {where}; refusing to take it again')
        rest = [i for i in sorted(kept) if i not in taken]
        prior[stem] = sum(1 for i in range(n) if i not in kept and i not in taken)
        if len(rest) + len(taken) + prior[stem] != n:
            raise MastSlipError(f'{stem}: the remainder, the objects and the earlier batches do not partition the tile')
        owned[stem] = {**mine, '': rest}
        models[stem], tris[stem] = f['model'], f['tris']
    saved: dict = {}
    for path in [region / BATCH1] + market.prior_files(region, f'split-{BATCH}.json'):
        if path.is_file():
            for stem, tile in json.loads(path.read_text()).get('tiles', {}).items():
                saved.setdefault(stem, tile)
    tiles = {}
    for stem in owned:
        model = models[stem]
        asset_path = game / 'assets' / apply_.tile_record(stem) / 'asset.toml'
        asset = records.load_asset(asset_path) if asset_path.is_file() else None
        donor_sha = records.sha256_file(donor / 'brinecove' / 'glb' / f'SM_BC_{stem}.glb')
        if asset is None or not asset.sources or asset.sources[0].sha256 != donor_sha:
            raise MastSlipError(f'{stem}: its record does not pin the donor GLB')
        if stem in saved:
            tiles[stem] = {**saved[stem]['original'], 'record': saved[stem]['record'], 'package': saved[stem]['package'],
                           'source': {'name': Path(asset.sources[0].path).name, 'sha256': donor_sha}}
        else:
            settings = dict(asset.recipe['settings'])
            tiles[stem] = {'record': asset.id, 'owner': asset.owner, 'references': list(asset.references),
                           'package': asset.outputs[0].package, 'settings': settings,
                           'material_package': apply_.material_packages(model['materials'], settings['slot_materials']),
                           'source': {'name': Path(asset.sources[0].path).name, 'sha256': donor_sha}}
        tiles[stem]['triangles'] = len(tris[stem]) - prior[stem]
    parts = {}
    for obj in OBJECTS:
        stems = [s for s in owned if owned[s][obj]]
        if not stems:
            continue
        merged = split.merge_models([(models[s], owned[s][obj]) for s in stems])
        members = list(range(sum(1 for _ in split.triangles(merged))))
        mesh = market.part_mesh(obj, False)
        path = stage / 'parts' / f'{mesh}.glb'
        path.parent.mkdir(parents=True, exist_ok=True)
        used = split.write_subset(merged, members, path)
        lo, hi = split.bounds(list(split.triangles(merged)), members)
        parts[(obj, False)] = {
            'object': obj, 'soft': False, 'record': apply_.record_id(obj, False), 'mesh': mesh,
            'package': apply_.MESHES + mesh, 'file': path, 'sha256': apply_.sha_of(path), 'triangles': len(members),
            'materials': used, 'share': {s: len(owned[s][obj]) for s in stems},
            'slots': [apply_.slot_of(tiles, stems, m) for m in used], 'min': [round(v, 4) for v in lo],
            'max': [round(v, 4) for v in hi], 'tiles': stems, 'tile': tiles[stems[0]]}
    remainders = {}
    for stem in owned:
        rest = owned[stem]['']
        path = stage / 'rest' / f'SM_BC_{stem}.glb'
        path.parent.mkdir(parents=True, exist_ok=True)
        used = split.write_subset(models[stem], rest, path)
        remainders[stem] = {'file': path, 'sha256': apply_.sha_of(path), 'triangles': len(rest), 'materials': used,
                            'slots': [apply_.slot_of(tiles, [stem], m) for m in used], 'kept': sorted(rest),
                            'total': len(tris[stem])}
    market.check_packages(game, parts)
    plan = {'tiles': tiles, 'parts': parts, 'remainders': remainders, 'stage': stage, 'prior': prior,
            'selection': list(OBJECTS), 'stale': [], 'resave': []}
    return plan, files


def apply(game: Path, donor: Path, src: Path, stage: Path, claim: str) -> dict:
    """Write the batch under the claim: the two records and their sources, each tile's carve (kept minus the objects),
    the region objects, the runtime file and lock (apply's compute), and the yard re-cut and batch-1 expectation.
    Journaled in one step: a failure restores every file. Authorizes the complete touched set first."""
    apply_ = market.set_batch(BATCH)
    apply_.Journal(game).recover(claim)     # an interrupted run is restored (and authorized) before anything is read
    plan, files = build_plan(game, donor, src, stage)
    expect_before = json.loads((game / apply_.EXPECTED).read_text()) if (game / apply_.EXPECTED).is_file() else {}
    if expect_before.get('parts'):
        raise MastSlipError('this batch is already applied; run check, do not apply it again')
    ops = apply_.compute(game, plan)
    writes = dict(ops['writes'])
    expected_removed = {}
    yards = yard_ordinals(donor / 'brinecove' / 'glb')
    for stem, f in files.items():
        slip = {i for i, o in enumerate(f['owners']) if o == 'shipyard-slip'}
        both = sorted(slip & yards.get(stem, set()))
        if both:
            expected_removed[stem] = both
    yard_dir = game / 'assets' / YARD_RECORD
    original = yard_original_path(yard_dir).read_bytes()
    if hashlib.sha256(original).hexdigest() != YARD_ORIGINAL_SHA:
        raise MastSlipError('the yard GLB is not main\'s original (it is already carved): run yard-carve, not apply')
    recut = yard_recut(game, donor, src, files, expected_removed)
    selection = yard_selection(YARD_BEFORE, recut['removed_yard']).encode()
    writes[f'assets/{YARD_RECORD}/{YARD_CARVE}'] = selection
    writes[f'assets/{YARD_RECORD}/asset.toml'] = yard_asset_text(
        (yard_dir / 'asset.toml').read_text(), hashlib.sha256(selection).hexdigest()).encode()
    objects_rel = f'world/regions/{apply_.REGION}/objects.toml'
    objects_text = writes.get(objects_rel)   # apply's compute holds the new objects.toml as bytes
    objects_text = (game / objects_rel).read_text() if objects_text is None else objects_text.decode()
    writes[objects_rel] = yard_about_text(objects_text, YARD_AFTER).encode()
    expect = json.loads(writes[apply_.EXPECTED].decode()) if apply_.EXPECTED in writes else json.loads(
        (game / apply_.EXPECTED).read_text())
    expect['yard'] = yard_expectation(expected_removed, recut, selection)
    writes[apply_.EXPECTED] = (json.dumps(expect, indent=2, sort_keys=True) + '\n').encode()
    all_ops = {'writes': writes, 'deletes': ops['deletes']}
    info = apply_.touched(game, plan, False, all_ops)
    extra = {f'{GAME_REL}/assets/{YARD_RECORD}/{YARD_CARVE}', f'{GAME_REL}/assets/{YARD_RECORD}/asset.toml',
             f'{GAME_REL}/{objects_rel}'}
    paths = sorted(set(info['paths']) | extra)
    scopes = set(info['scopes']) | {(f'asset/{YARD_RECORD}', f'shared/brinecove/{YARD_RECORD.rsplit("/", 1)[1]}'),
                                    f'region/{apply_.REGION}'}
    apply_.authority.authorize(paths, claim, 'Brine Cove mast and slip apply', scopes=scopes)
    return apply_.execute(game, all_ops, scopes=scopes)


def yard_expectation(expected_removed: dict, recut: dict, selection: bytes) -> dict:
    """The mast/slip expectation's yard section: the yard's derived sha, its carve, and the removed ordinals per source file
    (donor ordinals and the yard part's own ordinals), so check can prove removed = slip ∩ yard."""
    return {'record': YARD_RECORD, 'before': YARD_BEFORE, 'after': YARD_AFTER, 'sha256': recut['sha256'],
            'carve': {'original': YARD_ORIGINAL, 'original_sha256': YARD_ORIGINAL_SHA, 'selection': YARD_CARVE,
                      'selection_sha256': hashlib.sha256(selection).hexdigest()},
            'removed_donor': {s: ranges(v) for s, v in expected_removed.items()},
            'removed_yard': ranges(recut['removed_yard'])}


def check(game: Path, donor: Path, src: Path) -> list[str]:
    """Problems with the applied batch, proved from the committed files and the donor: the yard, read through its carve
    (yard_problems), holds no slip triangle; its recorded re-cut is exactly slip ∩ yard; batch 1 still describes its own
    cut (the original yard GLB); and the parts match their expectation."""
    apply_ = market.set_batch(BATCH)
    expect_path = game / apply_.EXPECTED
    if not expect_path.is_file():
        return [f'{apply_.EXPECTED} is missing: apply has not run']
    expect = json.loads(expect_path.read_text())
    yard = expect.get('yard')
    if not yard:
        return ['the expectation has no yard section: apply has not run']
    problems: list[str] = []
    batch1 = json.loads((game / 'world' / 'regions' / apply_.REGION / BATCH1).read_text())
    if batch1['parts'][YARD_RECORD]['sha256'] != YARD_ORIGINAL_SHA:
        problems.append('batch 1 does not describe its own cut: its yard part is not the original GLB')
    files = donor_owned(donor, src)
    yards = yard_ordinals(donor / 'brinecove' / 'glb')
    slip_keys = set()
    recorded = yard.get('removed_donor', {})
    for stem, f in files.items():
        slip = {i for i, o in enumerate(f['owners']) if o == 'shipyard-slip'}
        slip_keys |= {yard_key(f['tris'][i][1]) for i in slip}
        want = sorted(slip & yards.get(stem, set()))
        have = [i for a, b in recorded.get(stem, []) for i in range(a, b)]
        if want != sorted(have):
            problems.append(f'{stem}: the re-cut records {len(have)} removed triangles, slip ∩ yard is {len(want)}')
    problems += yard_problems(game / 'assets' / YARD_RECORD, yard['sha256'], slip_keys)
    for record, part in expect.get('parts', {}).items():
        path = game / 'assets' / record / 'src' / f'{part["mesh"]}.glb'
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != part['sha256']:
            problems.append(f'{record}: its source GLB is missing or differs from the expectation')
    return problems


def git_bytes(ref: str, rel: str) -> bytes:
    """A file's bytes at a commit, its LFS object read from the local store (the working tree is not needed)."""
    raw = subprocess.run(['git', 'show', f'{ref}:{rel}'], check=True, capture_output=True, cwd=REPO).stdout
    if raw.startswith(b'version https://git-lfs'):
        raw = subprocess.run(['git', 'lfs', 'smudge', '--', rel], input=raw, check=True, capture_output=True,
                             cwd=REPO).stdout
    return raw


def yard_carve_paths() -> dict:
    """The exact touched set of yard-carve (repository-relative paths and the claim scopes)."""
    yard = f'{GAME_REL}/assets/{YARD_RECORD}'
    paths = [f'{yard}/{YARD_ORIGINAL}', f'{yard}/{YARD_CARVE}', f'{yard}/asset.toml',
             f'{GAME_REL}/world/regions/{REGION}/{BATCH1}', f'{GAME_REL}/world/regions/{REGION}/{EXPECTED_NAME}']
    scopes = [f'asset/{YARD_RECORD} or shared/brinecove/{YARD_RECORD.rsplit("/", 1)[1]}', f'region/{REGION}']
    return {'paths': sorted(paths), 'scopes': scopes}


def yard_carve(game: Path, claim: str, base_ref: str = 'origin/main') -> dict:
    """Move an applied yard (the recut GLB) to its carved form, from the current committed state: restore the original
    GLB from base_ref, write the selection and the carved asset.toml, put batch 1's expectation back as base_ref has it,
    and renew the mast/slip expectation's yard carve. The derived bytes must be the recorded ones. Journaled and claim-
    authorized like apply; the touched set is yard_carve_paths()."""
    apply_ = market.set_batch(BATCH)
    apply_.Journal(game).recover(claim)     # restore an interrupted run before reading the expectation
    yard_dir = f'{GAME_REL}/assets/{YARD_RECORD}'
    original = git_bytes(base_ref, f'{yard_dir}/{YARD_ORIGINAL}')
    if hashlib.sha256(original).hexdigest() != YARD_ORIGINAL_SHA:
        raise MastSlipError(f'{base_ref}: the yard GLB is not the original pinned by batch 1')
    base_asset = git_bytes(base_ref, f'{yard_dir}/asset.toml').decode()
    batch1 = git_bytes(base_ref, f'{GAME_REL}/world/regions/{REGION}/{BATCH1}')
    expect_path = game / apply_.EXPECTED
    expect = json.loads(expect_path.read_text())
    yard = expect.get('yard')
    if not yard:
        raise MastSlipError('no yard section in the expectation: apply has not run')
    total = sum(1 for _ in split.triangles(carve.parse_glb(original, YARD_ORIGINAL)))
    removed = [i for a, b in yard['removed_yard'] for i in range(a, b)]
    selection = yard_selection(total, removed).encode()
    kept = [i for i in range(total) if i not in set(removed)]
    derived = carve.remainder_bytes(original, Path(YARD_ORIGINAL).name, kept, total)
    if hashlib.sha256(derived).hexdigest() != yard['sha256']:
        raise MastSlipError('the carve of the original does not derive the recorded yard bytes; nothing written')
    yard['carve'] = {'original': YARD_ORIGINAL, 'original_sha256': YARD_ORIGINAL_SHA, 'selection': YARD_CARVE,
                     'selection_sha256': hashlib.sha256(selection).hexdigest()}
    writes = {
        f'assets/{YARD_RECORD}/{YARD_ORIGINAL}': original,
        f'assets/{YARD_RECORD}/{YARD_CARVE}': selection,
        f'assets/{YARD_RECORD}/asset.toml': yard_asset_text(base_asset, hashlib.sha256(selection).hexdigest()).encode(),
        f'world/regions/{REGION}/{BATCH1}': batch1,
        apply_.EXPECTED: (json.dumps(expect, indent=2, sort_keys=True) + '\n').encode(),
    }
    exact = yard_carve_paths()
    scopes = {(f'asset/{YARD_RECORD}', f'shared/brinecove/{YARD_RECORD.rsplit("/", 1)[1]}'), f'region/{REGION}'}
    apply_.authority.authorize(exact['paths'], claim, 'Brine Cove yard carve', scopes=scopes)
    return apply_.execute(game, {'writes': writes, 'deletes': []}, scopes=scopes)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=('paths', 'plan', 'apply', 'check', 'yard-carve'))
    parser.add_argument('--base-ref', default='origin/main',
                        help='yard-carve: the commit whose original yard GLB, asset.toml and batch 1 are restored')
    parser.add_argument('--stage', type=Path, default=HERE.parents[3] / 'build' / 'yorimichi_v2' / 'brinecove-mastslip',
                        help='apply: the staging folder for the new GLBs (outside the repository by default)')
    parser.add_argument('--claim', help='apply: the active claim (task ID) that must cover the touched set')
    parser.add_argument('--donor', type=Path, help='the donor build/yorimichi folder (paths: GLB names; plan: GLB triangles)')
    parser.add_argument('--donor-src', type=Path, help='the donor games/yorimichi folder (default: next to --donor)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--game', type=Path, default=HERE.parents[1], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        donor = args.donor.resolve() if args.donor else None
        src = market.donor_source(donor, args.donor_src) if donor else None
        if args.command == 'yard-carve':
            if not args.claim:
                parser.error('yard-carve needs --claim TASK (its touched set is printed by `paths`)')
            done = yard_carve(args.game.resolve(), args.claim, args.base_ref)
            print(f'yard-carve: wrote {len(done["written"])}')
            return 0
        if args.command in ('plan', 'apply', 'check'):
            if donor is None or src is None:
                parser.error(f'{args.command} needs --donor (the donor GLB triangles)')
        if args.command == 'plan':
            print(json.dumps(plan(donor, src, args.game.resolve()), indent=2, default=list))
            return 0
        if args.command == 'check':
            problems = check(args.game.resolve(), donor, src)
            print('\n'.join(problems))
            print(f'{"FAIL" if problems else "OK"}: {len(problems)} problem(s)')
            return 1 if problems else 0
        if args.command == 'apply':
            if not args.claim:
                parser.error('apply needs --claim TASK (the claim that covers the touched set)')
            done = apply(args.game.resolve(), donor, src, args.stage.resolve(), args.claim)
            print(f'apply: wrote {len(done["written"])}, deleted {len(done["deleted"])}')
            return 0
        if src is None:
            # paths without a donor reads only the generator (for the object list and tile names)
            src = args.game.resolve().parent / 'yorimichi'
        summaries: dict = {}
        for name in OBJECTS:
            summaries.update(summary(replay(src, name)))
        result = None
        if donor:
            try:
                result = plan(donor, src, args.game.resolve())
            except MastSlipError:
                # applied already: plan() runs on the un-carved remainder only. The applied expectation names the tiles.
                expect_path = args.game.resolve() / market.set_batch(BATCH).EXPECTED
                if not expect_path.is_file() or not json.loads(expect_path.read_text()).get('tiles'):
                    raise
                result = {'trimmed': {stem: {} for stem in json.loads(expect_path.read_text())['tiles']}}
        info = claim_set(donor, summaries, result)
        info['yard_carve'] = yard_carve_paths()     # the exact touched set of `yard-carve`
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print('# claim paths (a trailing / is a folder: every file in it)')
            print('\n'.join(info['paths']))
            print('# scopes')
            print('\n'.join(info['scopes']))
            print('# locks: ' + ', '.join(info['locks']))
            print('# residual tiles: ' + ', '.join(info['residual_tiles']))
            print('# yard-carve (exact touched set; claim these for `yard-carve --claim TASK`)')
            print('\n'.join(info['yard_carve']['paths']))
            print('# yard-carve scopes: ' + ' ; '.join(info['yard_carve']['scopes']))
            if info['donor_glb_stems'] is None:
                print('# piece names need --donor: the Market tiles are cut into _PieceN models')
        return 0
    except (MastSlipError, market.MarketError) as error:
        print(f'mast/slip split failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
