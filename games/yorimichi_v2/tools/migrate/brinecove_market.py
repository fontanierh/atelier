"""Brine Cove market stalls and town houses as individual objects, cut by the generator's own object boundaries.

The stalls are jittered by the shared `RNG` and overlap the bazaar clutter, so no radius or distance rule can separate
them. This tool therefore replays the donor's owning constructors (`procedural/market.py` `market()`,
`procedural/lower_town.py`, `procedural/upper_town.py`) in pure Python with the exact RNG stream position the donor
export used (`assets/brinecove/export-parameters/<Component>.json`), and records which object each generated face
belongs to: a face made inside the loop body of a stall (the stall, its barrel and its crate) or of a building lot
(foundation, stilts, ladders, walls, roof) is that object's. Every generated triangle is then matched to the donor GLB
triangle with the same float32 vertex positions, so each donor triangle gets the object that generated it, or none
(the remainder). Nothing is measured by distance; the donor generator is not modified and its output is read only.

    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py plan  --donor DONOR_BUILD [--only a,b]
    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py paths --donor DONOR_BUILD [--only a,b] [--json]
    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py apply --donor DONOR_BUILD --claim TASK [--only a,b]
    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py check [--donor DONOR_BUILD]
    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py list  --donor DONOR_BUILD
    python3 games/yorimichi_v2/tools/migrate/brinecove_market.py retire --batch B|a,b|all --retire-stage groups|placements|records --claim T --donor DONOR_BUILD

`--batch all` (or a comma list) runs a stage for several batches in one call; `placements` deletes each affected placement
once for the whole set and prints the ids to save again.

DONOR_BUILD is the donor's `build/yorimichi` folder; the generator sources are read from `games/yorimichi` two levels up
(override with --donor-src). The apply, check and claim machinery is `brinecove_split_apply.py`, used unchanged with
its expectation file pointed at `split-market.json`.
"""
from __future__ import annotations

import argparse
import ast
import itertools
import re
import json
import struct
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brinecove_split as split  # noqa: E402

EXPECTED_NAME = 'split-market.json'
PRIOR_EXPECTED = ('split-batch1.json',)      # earlier batches that already took triangles out of the same donor tiles

# One entry per loop whose body makes whole objects. `component` is the donor constructor (module = function name);
# `loop` is the loop header's source text; `key` is evaluated on the frame's locals when a face is made inside the body.
SCOPES = (
    dict(component='Market', module='market', loop='for i, (x, y, w, d, cloth) in enumerate(L.MARKET_STALLS):',
         key="'stall-%02d' % (i + 1)"),
    dict(component='Market', module='market', loop='for x, cloth in ((-76, \'canvas_red\'), (58, \'canvas_teal\')):',
         key="'south-%s' % ('west' if x < 0 else 'east')"),
    # Town houses: a lot's foundation, stilts and ladders come before its houses in the same loop body, so the whole body
    # (and every house `split_lot` cuts the lot into) is one object, named by the layout key.
    dict(component='TownLower', module='lower_town', loop='for spec in L.DENSE_LOTS:', key='spec[0]'),
    dict(component='TownLower', module='lower_town', loop='for spec in L.SHORE_BUILDINGS:', key='key'),
    dict(component='TownUpper', module='upper_town', loop='for spec in L.DENSE_LOTS:', key='spec[0]'),
    dict(component='TownUpper', module='upper_town', loop='for spec in L.HILLSIDE_BUILDINGS:', key='key'),
)


class MarketError(RuntimeError):
    pass


# --- replaying the donor constructor with face ownership ---------------------------------------------------------------

def donor_source(donor: Path, override: Path | None = None) -> Path:
    """The donor's `games/yorimichi` folder: next to its build folder unless given."""
    root = Path(override) if override else Path(donor).resolve().parents[1] / 'games' / 'yorimichi'
    if not (root / 'world' / 'regions' / 'brinecove' / 'kit.py').is_file():
        raise MarketError(f'{root}: not the donor generator (no world/regions/brinecove/kit.py); pass --donor-src')
    return root


def loop_ranges(source: str, scopes) -> list[tuple[int, int, dict]]:
    """(first line, last line, scope) of each scope's loop body, found by the loop header's text in the module source."""
    tree = ast.parse(source)
    lines = source.splitlines()
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            header = ' '.join(lines[node.lineno - 1].split())
            for scope in scopes:
                if header == ' '.join(scope['loop'].split()):
                    found.append((node.body[0].lineno, node.end_lineno, scope))
    missing = [s['loop'] for s in scopes if not any(f[2] is s for f in found)]
    if missing:
        raise MarketError(f'loop header(s) not found in the donor module: {missing}')
    return found


def _forget():
    for name in [n for n in sys.modules if n == 'brinecove' or n.startswith('brinecove.') or n == 'random_stream']:
        del sys.modules[name]


def replay(src: Path, component: str, scopes=SCOPES) -> dict:
    """Run the donor constructor of `component` at its recorded RNG position and return
    {'verts', 'faces', 'mats', 'owner': [object name or None per face]} (the Builder's own lists)."""
    scopes = [s for s in scopes if s['component'] == component]
    if not scopes:
        raise MarketError(f'no object scopes for {component}')
    module = scopes[0]['module']
    old_flag, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    added = [str(src / 'world'), str(src / 'world' / 'regions')]
    sys.path[:0] = added
    _forget()                    # another donor checkout (or a test's) may already have put its modules in sys.modules
    try:
        import importlib
        from random_stream import positioned
        params = json.loads((src / 'assets' / 'brinecove' / 'export-parameters' / f'{component}.json').read_text())
        random_state = importlib.import_module('brinecove.procedural.random_state')
        random_state.RNG.setstate(positioned(params['seed'], params['prefix_words']).getstate())
        mod = importlib.import_module(f'brinecove.procedural.{module}')
        geom = importlib.import_module('brinecove.geom')
        ranges = loop_ranges(Path(mod.__file__).read_text(), scopes)
        code = mod.__file__
        owner: list = []
        original = geom.Builder.face

        def face(self, points, mat, uvs=None, normals=None):
            before = len(self.faces)
            original(self, points, mat, uvs, normals)
            name = None
            frame = sys._getframe(1)
            while frame is not None:
                if frame.f_code.co_filename == code:
                    for first, last, scope in ranges:
                        if first <= frame.f_lineno <= last:
                            name = eval(scope['key'], {}, dict(frame.f_locals))     # noqa: S307  (constant scope table)
                    break
                frame = frame.f_back
            owner.extend([name] * (len(self.faces) - before))

        geom.Builder.face = face
        try:
            builder = getattr(mod, module)()
        finally:
            geom.Builder.face = original
        if len(owner) != len(builder.faces):
            raise MarketError('face ownership lost count; the builder changed faces outside Builder.face')
        return {'verts': builder.verts, 'faces': builder.faces, 'mats': builder.mats, 'owner': owner}
    finally:
        for path in added:
            sys.path.remove(path)
        _forget()
        sys.dont_write_bytecode = old_flag


# --- matching generated faces to donor triangles -------------------------------------------------------------------------

def _f32(v: float) -> float:
    return struct.unpack('f', struct.pack('f', v))[0]


def glb_point(p) -> tuple:
    """A generator point (x, y, z with z up) as the donor GLB stores it (glTF y up, float32)."""
    return (_f32(p[0]), _f32(p[2]), _f32(-p[1]))


def face_index(built: dict) -> dict:
    """{sorted triple of GLB points: {owners}} over every corner triple of every generated face (any triangulation)."""
    index: dict = defaultdict(set)
    verts, mats = built['verts'], built['mats']
    for f, owner in zip(built['faces'], built['owner']):
        pts = [glb_point(verts[i]) for i in f]
        for triple in itertools.combinations(range(len(pts)), 3):
            index[tuple(sorted(pts[i] for i in triple))].add(owner)
    return index


def owners_of(tris: list, index: dict) -> list:
    """For each GLB triangle (material, corners) its generating object (None: none) or raise on a missing or ambiguous match."""
    out = []
    for n, (_, corners) in enumerate(tris):
        owners = index.get(tuple(sorted(tuple(c) for c in corners)))
        if owners is None:
            raise MarketError(f'triangle {n} has no generated face')
        if len(owners) != 1:
            raise MarketError(f'triangle {n} is generated by more than one object: {sorted(map(str, owners))}')
        out.append(next(iter(owners)))
    return out


# --- the objects ---------------------------------------------------------------------------------------------------------

def object_name(component: str, key: str) -> str:
    """The V2 object id (after `object/brinecove/`) of a generator object."""
    if component == 'Market':
        return 'market-' + (key if key.startswith('stall') else 'stall-' + key)
    if component in ('TownLower', 'TownUpper'):
        return 'town-' + component[4:].lower() + '-' + key.lower().replace('_', '-')
    raise MarketError(f'no naming for component {component}')


# Small importable batches: stalls whose triangles all lie in one hard tile (no Soft part), so a batch changes few tiles.
BATCHES = {
    'market1': tuple(f'market-stall-{n:02d}' for n in (1, 2, 6, 7, 8, 9)),
    'market2': tuple(f'market-stall-{n:02d}' for n in (3, 4, 5, 10, 11, 12, 13, 14)),
    'market3': tuple(f'market-stall-{n:02d}' for n in (15, 16, 17, 18, 19)) + ('market-stall-south-east', 'market-stall-south-west'),
    # lots whose houses all sit in one hard tile
    'town1': ('town-lower-hall--1-2-1', 'town-lower-back-e2-0', 'town-lower-back-w1-0', 'town-lower-mid-e1-1',
              'town-lower-rum-e2-0', 'town-lower-rum-e2-1', 'town-lower-back-w4-0'),
}
# Every other town lot, grouped by the 256 m cell its triangles mostly lie in so that a hard tile and a Soft tile are
# remade by as few batches as possible (6 tiles are cut by two of these batches, the rest by one; town1, already queued, shares 6 more). Apply in order: town2 ... town9.
# Lot names are the object names without the town-lower- / town-upper- prefix.
TOWN_LOTS = {
    'town2': ('town-lower-', (
        'back-e1-0', 'back-e1-1', 'back-e1-2', 'back-e2-1', 'back-e2-2', 'back-e3-0', 'back-e3-1', 'back-e3-2',
        'hall-1-0-0', 'hall-1-0-1', 'hall-1-1-0', 'hall-1-1-1', 'hall-1-2-0', 'hall-1-2-1', 'mid-e1-0',
        'mid-e2-0', 'mid-e2-1', 'mid-e2-2', 'mid-e3-0', 'mid-e3-1', 'rum-e1-0', 'rum-e1-1', 'rum-e2-2',
        'rum-e3-0', 'rum-e4-0',
    )),
    'town3': ('town-lower-', (
        'back-e4-0', 'back-e4-1', 'back-e5-0', 'back-e5-1', 'back-e5-2', 'cliff-e1-0', 'cliff-e1-1', 'mid-e4-0',
        'mid-e4-1', 'rum-e3-1', 'rum-e4-1', 'rum-e4-2', 'rum-e5-0', 'rum-e5-1', 'rum-e5-2', 'rum-e6-0',
        'rum-e6-1', 'rum-e6-2', 'slope-1-0-1-0', 'slope-1-0-1-1', 'slope-1-0-2-0', 'slope-1-0-2-1',
        'slope-1-1-2-0', 'slope-1-1-2-1', 'slope-1-1-3-0', 'slope-1-1-3-1', 'slope-1-2-1-0', 'slope-1-2-1-1',
        'slope-1-2-2-0', 'slope-1-2-2-1', 'slope-1-2-3-1',
    )),
    'town4': ('town-lower-', (
        'back-w1-1', 'back-w1-2', 'back-w2-0', 'back-w2-1', 'back-w2-2', 'back-w3-0', 'back-w3-1', 'back-w4-1',
        'back-w5-0', 'back-w5-1', 'back-w5-2', 'hall--1-0-0', 'hall--1-0-1', 'hall--1-1-0', 'hall--1-1-1',
        'hall--1-2-0', 'mid-w1-0', 'mid-w1-1', 'mid-w1-2', 'mid-w2-0', 'mid-w2-1', 'mid-w3-0', 'mid-w3-1',
        'mid-w3-2', 'mid-w4-0', 'mid-w4-1', 'rum-w2-0', 'rum-w2-1', 'rum-w2-2', 'rum-w3-0', 'rum-w3-1',
        'rum-w3-2', 'rum-w4-0', 'rum-w4-1', 'rum-w4-2', 'rum-w5-0', 'rum-w5-1', 'rum-w6-0', 'rum-w6-1',
        'shore-e1', 'shore-e2', 'shore-e3', 'shore-e4', 'shore-e5', 'shore-e6',
    )),
    'town5': ('town-lower-', (
        'cliff-w1-0', 'cliff-w1-1', 'rum-w1-0', 'rum-w1-1', 'rum-w1-2', 'shore-w1', 'shore-w2', 'shore-w3',
        'shore-w4', 'shore-w5', 'shore-w6', 'slope--1-0-1-0', 'slope--1-0-1-1', 'slope--1-0-2-0',
        'slope--1-0-2-1', 'slope--1-1-0-0', 'slope--1-1-0-1', 'slope--1-1-1-0', 'slope--1-1-1-1',
        'slope--1-1-2-0', 'slope--1-1-2-1', 'slope--1-2-0-0', 'slope--1-2-0-1', 'slope--1-2-1-0',
        'slope--1-2-1-1', 'slope--1-2-2-0', 'slope--1-2-2-1', 'slope--1-2-3-0',
    )),
    'town6': ('town-upper-', (
        'cliff-w2-0', 'cliff-w2-1', 'edge-0-0', 'edge-0-1', 'edge-1-0', 'edge-1-1', 'edge-2-0', 'edge-2-1',
        'edge-3-0', 'edge-3-1', 'edge-4-0', 'edge-4-1', 'edge-5-0', 'edge-5-1', 'slope--1-0-4-0',
        'slope--1-0-4-1', 'slope--1-0-5-0', 'slope--1-0-5-1', 'slope--1-2-3-1', 'slope--1-2-4-0',
        'slope--1-2-4-1', 'terrace-w1-0', 'terrace-w1-1', 'terrace-w1-2', 'terrace-w2-0', 'terrace-w2-1',
        'terrace-w3-0', 'terrace-w3-1', 'terrace-w3-2', 'terrace-w4-0', 'terrace-w4-1', 'terrace-w5-0',
        'terrace-w5-1',
    )),
    'town7': ('town-upper-', (
        'crest-e1-0', 'crest-e1-1', 'crest-e1-2', 'crest-e2-0', 'crest-e2-1', 'crest-e3-0', 'crest-e3-1',
        'crest-e3-2', 'crest-e4-0', 'crest-e4-1', 'hill-e1', 'hill-e2', 'hill-e3', 'hill-e4', 'ridge-10-0',
        'ridge-10-1', 'ridge-11-0', 'ridge-11-1', 'ridge-12-0', 'ridge-12-1', 'ridge-13-0', 'ridge-13-1',
        'ridge-14-0', 'ridge-14-1', 'ridge-15-0', 'ridge-15-1', 'ridge-8-0', 'ridge-8-1', 'ridge-9-0',
        'ridge-9-1',
    )),
    'town8': ('town-upper-', (
        'crest-w1-0', 'crest-w1-1', 'crest-w1-2', 'crest-w2-0', 'crest-w2-1', 'hill-w1', 'hill-w2', 'hill-w3',
        'ridge-0-0', 'ridge-0-1', 'ridge-1-0', 'ridge-1-1', 'ridge-2-0', 'ridge-2-1', 'ridge-3-0', 'ridge-3-1',
        'ridge-4-0', 'ridge-4-1', 'ridge-6-0', 'ridge-6-1', 'ridge-7-0', 'ridge-7-1', 'slope--1-1-5-0',
        'slope--1-1-5-1', 'slope--1-2-5-0', 'slope--1-2-5-1',
    )),
    'town9': ('town-upper-', (
        'edge-10-0', 'edge-10-1', 'edge-11-0', 'edge-11-1', 'edge-6-0', 'edge-6-1', 'edge-7-0', 'edge-7-1',
        'edge-8-0', 'edge-8-1', 'edge-9-0', 'edge-9-1', 'slope-1-0-4-0', 'slope-1-0-4-1', 'slope-1-0-5-0',
        'slope-1-0-5-1', 'slope-1-1-4-0', 'slope-1-1-4-1', 'slope-1-1-5-0', 'slope-1-1-5-1', 'slope-1-2-3-0',
        'slope-1-2-4-0', 'slope-1-2-4-1', 'slope-1-2-5-0', 'slope-1-2-5-1', 'terrace-e1-0', 'terrace-e1-1',
        'terrace-e2-0', 'terrace-e2-1', 'terrace-e2-2', 'terrace-e3-0', 'terrace-e3-1', 'terrace-e4-0',
        'terrace-e4-1', 'terrace-e4-2', 'terrace-e5-0', 'terrace-e5-1', 'terrace-e6-0', 'terrace-e6-1',
        'terrace-e6-2',
    )),
}
BATCHES.update({name: tuple(prefix + lot for lot in lots) for name, (prefix, lots) in TOWN_LOTS.items()})

COMPONENT_OF = {'market-': 'Market', 'town-lower-': 'TownLower', 'town-upper-': 'TownUpper'}
ALL_OBJECTS = frozenset(o for names in BATCHES.values() for o in names)


def part_mesh(obj: str, soft: bool) -> str:
    """The part's mesh name. apply.mesh_name drops a negative coordinate's minus (town-lower-hall--1-2-1 ->
    SM_BC_TownLowerHall121, saved by town1), so the non-negative twin of a negative object takes a P before its
    coordinates (town-lower-hall-1-2-1 -> SM_BC_TownLowerHallP121); the two never share a package."""
    apply_ = _apply()
    if '--' not in obj and re.sub(r'-(\d)', r'--\1', obj, count=1) in ALL_OBJECTS:
        return apply_.mesh_name(re.sub(r'-(\d)', r'-p\1', obj, count=1), soft)
    return apply_.mesh_name(obj, soft)


def check_packages(game: Path, parts: dict) -> None:
    """@cc [owner:fontanierh,label:safety] brinecove-part-package-unique
    A split part MUST NOT share its package with another part of the plan or with another committed record: an import
    would overwrite that record's accepted package (town2's hall-1-2-1 overwrote town1's hall--1-2-1)."""
    apply_ = _apply()
    seen: dict[str, str] = {}
    for p in parts.values():
        if seen.setdefault(p['package'], p['record']) != p['record']:
            raise apply_.SplitError(f'{p["record"]} and {seen[p["package"]]} both name the package {p["package"]}')
    for path in sorted((game / 'assets').rglob('asset.toml')):
        data = tomllib.loads(path.read_text())
        for output in data.get('outputs', []):
            owner = seen.get(output['package'])
            if owner is not None and owner != data['id']:
                raise apply_.SplitError(f'{owner} would overwrite {data["id"]}\'s package {output["package"]}')


def component_of(obj: str) -> str:
    for prefix, component in COMPONENT_OF.items():
        if obj.startswith(prefix):
            return component
    raise MarketError(f'unknown object {obj}')


def tile_stems(glb_dir: Path, component: str) -> list[str]:
    return sorted(p.stem[len('SM_BC_'):] for p in Path(glb_dir).glob(f'SM_BC_{component}_*.glb'))


def generated_owners(glb_dir: Path, src: Path, component: str) -> dict:
    """{'models', 'tris', 'owner'}: per donor tile of the component, its model, triangles and the generating object name
    ('market-stall-03', or None) of every triangle ordinal. Raises unless every donor triangle is matched exactly once."""
    built = replay(src, component)
    named = dict(built)
    named['owner'] = [None if o is None else object_name(component, o) for o in built['owner']]
    index = face_index(named)
    out = {'models': {}, 'tris': {}, 'owner': {}}
    for stem in tile_stems(glb_dir, component):
        model = split.read_glb(Path(glb_dir) / f'SM_BC_{stem}.glb')
        tris = list(split.triangles(model))
        try:
            out['owner'][stem] = owners_of(tris, index)
        except MarketError as error:
            raise MarketError(f'{stem}: {error}') from None
        out['models'][stem], out['tris'][stem] = model, tris
    return out


def prior_files(region: Path, own: str) -> list[Path]:
    return sorted(p for p in Path(region).glob('split-*.json') if p.name != own)


def prior_objects(region: Path, own: str) -> set[str]:
    """Objects earlier batches already cut out of the donor tiles (batch 1 and any other split-*.json)."""
    names: set[str] = set()
    for path in prior_files(region, own):
        names |= {part['object'] for part in json.loads(path.read_text())['parts'].values()}
    return names


def compute(glb_dir: Path, src: Path, names: list[str], priors: set[str]) -> dict:
    """The split in `split.compute`'s shape: owned[tile] = {object: [ordinals], '': [remainder ordinals]}.
    Triangles of objects in `priors` are left out of every list (an earlier batch took them); `prior_count[tile]`
    counts them, so remainder + parts + prior = the donor tile."""
    out = {'models': {}, 'tris': {}, 'owned': {}, 'prior': {}, 'problems': []}
    radius = {n: split.OBJECTS[n] for n in priors if n in split.OBJECTS}
    radial = split.compute(glb_dir, radius) if radius else {'owned': {}, 'tris': {}}
    for component in sorted({component_of(n) for n in names}):
        gen = generated_owners(glb_dir, src, component)
        for stem, owners in gen['owner'].items():
            tris = gen['tris'][stem]
            taken = set()
            for obj in priors:
                if obj in radius:
                    taken |= set(radial['owned'].get(stem, {}).get(obj, ()))
                else:
                    taken |= {i for i, o in enumerate(owners) if o == obj}
            owned = {n: [] for n in names}
            owned[''] = []
            for i, o in enumerate(owners):
                if i in taken:
                    if o in names:
                        out['problems'].append(f'{stem}: triangle {i} of {o} is already taken by an earlier batch')
                    continue
                owned[o if o in names else ''].append(i)
            if not any(owned[n] for n in names):
                continue
            parts = [[tris[t] for t in m] for m in owned.values()]
            parts.append([tris[t] for t in sorted(taken)])
            out['problems'] += [f'{stem}: {p}' for p in split.verify_partition(tris, parts)]
            out['models'][stem], out['tris'][stem], out['owned'][stem] = gen['models'][stem], tris, owned
            out['prior'][stem] = len(taken)
    return out


# --- the plan: apply's plan shape, built from the provenance split ---------------------------------------------------------

def _apply():
    import brinecove_split_apply as apply_
    return apply_


def set_batch(batch: str):
    """Point the shared apply machinery at this batch's own expectation file (no other state is shared)."""
    apply_ = _apply()
    apply_.EXPECTED = f'world/regions/{apply_.REGION}/split-{batch}.json'
    return apply_


def build(game: Path, donor: Path, src: Path, stage: Path, batch: str, names: list[str]) -> dict:
    """Split the donor tiles into the stage folder and return the whole plan (same shape as brinecove_split_apply.build)."""
    apply_ = set_batch(batch)
    records, recover = apply_.records, apply_.recover
    region = game / 'world' / 'regions' / apply_.REGION
    own = f'split-{batch}.json'
    glb_dir = donor / 'brinecove' / 'glb'
    done = compute(glb_dir, src, names, prior_objects(region, own))
    if done['problems']:
        raise apply_.SplitError('the partition does not hold: ' + '; '.join(done['problems'][:3]))
    stage.mkdir(parents=True, exist_ok=True)
    saved: dict = {}
    for path in [region / own] + prior_files(region, own):       # the first run of a tile kept its original
        if path.is_file():
            for stem, tile in json.loads(path.read_text())['tiles'].items():
                saved.setdefault(stem, tile)
    tiles = {}
    for stem, model in done['models'].items():
        asset_path = game / 'assets' / apply_.tile_record(stem) / 'asset.toml'
        asset = records.load_asset(asset_path) if asset_path.is_file() else None
        donor_sha = records.sha256_file(glb_dir / f'SM_BC_{stem}.glb')
        if asset is not None and asset.sources and asset.sources[0].sha256 == donor_sha and stem in saved:
            # Carved by an earlier batch (derived form): the fused original's facts are the ones that split saved; the
            # record's settings are its remainder's.
            tiles[stem] = {**saved[stem]['original'], 'record': saved[stem]['record'], 'package': saved[stem]['package'],
                           'source': {'name': Path(asset.sources[0].path).name, 'sha256': donor_sha}}
        elif asset is not None and asset.sources and asset.sources[0].sha256 == donor_sha:
            settings = dict(asset.recipe['settings'])
            tiles[stem] = {'record': asset.id, 'owner': asset.owner, 'references': list(asset.references),
                           'package': asset.outputs[0].package, 'settings': settings,
                           'material_package': apply_.material_packages(model['materials'], settings['slot_materials']),
                           'source': {'name': Path(asset.sources[0].path).name, 'sha256': donor_sha}}
        elif stem in saved or asset is not None:
            raise apply_.SplitError(f'{stem}: carved in the old form, its remainder is the committed source; run '
                                    'tools/migrate/brinecove_sources.py --claim TASK first')
        else:
            raise apply_.SplitError(f'{stem}: the record neither pins the donor mesh nor appears in an earlier split-*.json')
        tiles[stem]['triangles'] = len(done['tris'][stem]) - done['prior'][stem]
    parts, remainders = {}, {}
    for obj in names:
        for soft in (False, True):
            stems = [s for s in done['models'] if split.is_soft(s) == soft and done['owned'][s].get(obj)]
            if not stems:
                continue
            merged = split.merge_models([(done['models'][s], done['owned'][s][obj]) for s in stems])
            members = list(range(sum(1 for _ in split.triangles(merged))))
            name = part_mesh(obj, soft)
            path = stage / 'parts' / f'{name}.glb'
            path.parent.mkdir(parents=True, exist_ok=True)
            used = split.write_subset(merged, members, path)
            lo, hi = split.bounds(list(split.triangles(merged)), members)
            lead = tiles[stems[0]]
            for s in stems:
                for key in ('collision', 'full_precision_uvs'):
                    if tiles[s]['settings'].get(key) != lead['settings'].get(key):
                        raise apply_.SplitError(f'{obj}: its tiles {stems} disagree on {key}')
            parts[(obj, soft)] = {
                'object': obj, 'soft': soft, 'record': apply_.record_id(obj, soft), 'mesh': name,
                'package': apply_.MESHES + name, 'file': path, 'sha256': apply_.sha_of(path), 'triangles': len(members),
                'materials': used, 'share': {s: len(done['owned'][s][obj]) for s in stems},
                'slots': [apply_.slot_of(tiles, stems, m) for m in used], 'min': [round(v, 4) for v in lo],
                'max': [round(v, 4) for v in hi], 'tiles': stems, 'tile': lead}
    for stem, owned in done['owned'].items():
        rest = owned.get('', [])
        if rest:
            path = stage / 'rest' / f'SM_BC_{stem}.glb'
            path.parent.mkdir(parents=True, exist_ok=True)
            used = split.write_subset(done['models'][stem], rest, path)
            remainders[stem] = {'file': path, 'sha256': apply_.sha_of(path), 'triangles': len(rest), 'materials': used,
                                'slots': [apply_.slot_of(tiles, [stem], m) for m in used],
                                'kept': sorted(rest), 'total': len(done['tris'][stem])}
        else:
            remainders[stem] = None
    check_packages(game, parts)
    return {'tiles': tiles, 'parts': parts, 'remainders': remainders, 'stage': stage, 'prior': done['prior']}


def check(game: Path, donor: Path | None, batch: str, retired: bool = False, groups: bool = False) -> list[str]:
    """apply's repository checks for this batch, plus the vertex-level proof when the donor is given: donor tile =
    this batch's parts + its remainder + the earlier batches' parts of the same tile.
    `groups`: the groups stage is done (emptied tiles have no runtime group); `retired`: the records stage is done too."""
    apply_ = set_batch(batch)
    problems = apply_.check(game, None)            # apply's own `retired` mode also tests the ships' actor: not used
    if retired or groups:
        exp = json.loads((game / apply_.EXPECTED).read_text())
        gone = [s for s, t in exp['tiles'].items() if t['remainder'] is None]
        problems = [p for p in problems if not any(p.startswith(f'SM_BC_{s} appears 0 times') for s in gone)]
        data = json.loads((game / 'unreal' / 'Content' / apply_.RUNTIME).read_text())
        names = apply_.group_names(data)
        for s in gone:
            if retired and (game / 'assets' / exp['tiles'][s]['record'] / 'asset.toml').exists():
                problems.append(f'{exp["tiles"][s]["record"]}: should be retired (empty remainder)')
            if f'SM_BC_{s}' in names:
                problems.append(f'retired tile SM_BC_{s} is still in the runtime file')
    if donor is None:
        return problems
    records = apply_.records
    exp = json.loads((game / apply_.EXPECTED).read_text())
    region = game / 'world' / 'regions' / apply_.REGION
    glb_dir = donor / 'brinecove' / 'glb'
    sources, pieces = [], []
    for stem in exp['tiles']:
        sources += list(split.triangles(split.read_glb(glb_dir / f'SM_BC_{stem}.glb')))
    files = [game / 'assets' / rid / 'src' / f'{p["mesh"]}.glb' for rid, p in exp['parts'].items()]
    for other in prior_files(region, f'split-{batch}.json'):          # earlier batches' parts cut from the same tiles
        old = json.loads(other.read_text())
        files += [game / 'assets' / rid / 'src' / f'{p["mesh"]}.glb' for rid, p in old['parts'].items()
                  if set(p['tiles']) & set(exp['tiles'])]
    for f in files:
        if not f.is_file() or records.is_lfs_pointer(f):
            return problems + [f'{f.name}: not hydrated, the donor proof is skipped']
        pieces.append(list(split.triangles(split.read_glb(f))))
    for s, t in exp['tiles'].items():                                   # the remainders are derived, never read from src
        if t['remainder']:
            asset = records.load_asset(game / 'assets' / t['record'] / 'asset.toml')
            if asset.derive is None:
                return problems + [f'{t["record"]}: carved in the old form, the donor proof is skipped']
            try:
                pieces.append(list(split.triangles(apply_.carve.remainder_model(asset.folder, asset.derive))))
            except (OSError, ValueError, apply_.carve.CarveError):
                return problems + [f'{t["record"]}: original or selection not hydrated, the donor proof is skipped']
    # earlier parts may also cover tiles outside this batch; keep only triangles that the donor tiles above contain
    source_set = {tuple(sorted(split._key(p) for p in c)) for _, c in sources}
    pieces = [[t for t in piece if tuple(sorted(split._key(p) for p in t[1])) in source_set] for piece in pieces]
    problems += [f'donor: {p}' for p in split.verify_partition(sources, pieces)]
    return problems


def summary(plan: dict) -> dict:
    """The batch as data: per object its record, part file, triangles, bounds and tiles; per tile the remainder."""
    return {'parts': {p['record']: {'file': p['file'].name, 'sha256': p['sha256'], 'triangles': p['triangles'],
                                    'share': p['share'], 'min': p['min'], 'max': p['max'], 'materials': p['materials']}
                      for p in sorted(plan['parts'].values(), key=lambda p: p['record'])},
            'tiles': {s: {'record': plan['tiles'][s]['record'], 'before': plan['tiles'][s]['triangles'],
                          'after': None if r is None else r['triangles']} for s, r in sorted(plan['remainders'].items())}}


# --- emptied tiles: retire ----------------------------------------------------------------------------------------------------
# Town lots can take every triangle of a tile. `apply` keeps such a tile's record, package and runtime group until the
# parts are imported and checked (otherwise the old tile would be drawn twice); `retire` then removes them.

def drop_group(text: str, mesh: str) -> str:
    """objects.toml text without the group `mesh`: removed from `groups = [...]`; an object left with no group is dropped."""
    blocks = re.split(r'(?m)^(?=\[\[objects\]\]\n)', text)
    out = []
    for block in blocks:
        if f'"{mesh}"' not in block or not block.startswith('[[objects]]'):
            out.append(block)
            continue
        lines, keep = block.split('\n'), True
        for n, line in enumerate(lines):
            if line.startswith('group = '):
                keep = json.loads(line[len('group = '):]) != mesh
            elif line.startswith('groups = '):
                groups = [g for g in json.loads(line[len('groups = '):]) if g != mesh]
                keep = bool(groups)
                lines[n] = 'groups = ' + json.dumps(groups)
        if keep:
            out.append('\n'.join(lines))
    return ''.join(out)


def drop_saved_group(body: dict, mesh: str) -> dict:
    """objects.saved.json body without the group `mesh`; an object left with no group is removed."""
    objects = {}
    for oid, item in body.get('objects', {}).items():
        groups = item.get('groups')
        if groups is not None and mesh in groups:
            groups = [g for g in groups if g != mesh]
            if not groups:
                continue
            item = {**item, 'groups': groups}
        objects[oid] = item
    return {**body, 'objects': objects}


def emptied(plan: dict) -> list[str]:
    return sorted(stem for stem, rem in plan['remainders'].items() if rem is None)


def affected_placements(game: Path, plan: dict) -> list[str]:
    """Saved placements that must be deleted with their records and saved again by `migrate/objects.py` (an object cannot
    change its groups after it was saved). @cc [owner:fontanierh,label:correctness] brinecove-placements-survive-groups
    Found two ways: the objects.toml entries that list a group of an emptied tile (before the groups stage), and the object
    records that reference an emptied tile's record. The groups stage removes the groups from objects.toml but never from a
    record, so after it the second way is the only one that still finds the placements."""
    apply_ = _apply()
    stems = emptied(plan)
    if not stems:
        return []
    listed = apply_.tomllib.loads((game / 'world' / 'regions' / apply_.REGION / 'objects.toml').read_text()).get('objects', [])
    meshes = {f'SM_BC_{s}' for s in stems}
    ids = {i['id'] for i in listed if meshes & ({i['group']} if 'group' in i else set(i.get('groups', [])))}
    tile_records = {plan['tiles'][s]['record'] for s in stems}
    for path in apply_.records.record_paths(game):
        asset = apply_.records.load_asset(path)
        if asset.id.startswith('object/') and tile_records & set(asset.references + asset.input_dependencies):
            ids.add(asset.id)
    return sorted(ids)


def placement_ids(game: Path, plans: list) -> list[str]:
    """The affected placements of several (batch, plan) pairs, each id once: a placement that lists tiles of two batches
    is deleted and saved again once."""
    return sorted({oid for _, plan in plans for oid in affected_placements(game, plan)})


def groups_retired(game: Path, plan: dict) -> bool:
    """True when the groups stage has run for this plan: no emptied tile's group is left in objects.toml, objects.saved.json
    or the runtime file (the tile records may still exist)."""
    apply_ = _apply()
    region = game / 'world' / 'regions' / apply_.REGION
    meshes = {f'SM_BC_{s}' for s in emptied(plan)}
    text = (region / 'objects.toml').read_text()
    saved = json.loads((region / 'objects.saved.json').read_text()) if (region / 'objects.saved.json').is_file() else None
    names = apply_.group_names(json.loads((game / 'unreal' / 'Content' / apply_.RUNTIME).read_text()))
    return not any(drop_group(text, m) != text or (saved is not None and drop_saved_group(saved, m) != saved) or m in names
                   for m in meshes)


def placements_touched(game: Path, ids: list[str]) -> dict:
    """Stage `placements`: each affected placement's record folder files and the actor packages its record lists as outputs
    (the same approach as brinecove_ships.touched with retire=True). A placement already deleted contributes nothing."""
    apply_ = _apply()
    region = f'region/{apply_.REGION}'
    paths, scopes = set(), {region}
    for oid in ids:
        folder = game / 'assets' / oid
        owner = region
        if (folder / 'asset.toml').is_file():
            asset = apply_.records.load_asset(folder / 'asset.toml')
            owner = asset.owner
            for output in asset.outputs:
                for rel in apply_.package_rels(game, output.package):
                    paths.add(f'{apply_.GAME_REL}/{rel}')
        scopes.add((f'asset/{oid}', owner))
        for path in sorted(folder.rglob('*')) if folder.is_dir() else []:
            if path.is_file():
                paths.add(f'{apply_.GAME_REL}/{path.relative_to(game).as_posix()}')
    return {'paths': sorted(paths), 'scopes': scopes}


def retire_touched(game: Path, plan: dict, stage: str = 'groups') -> dict:
    """Stage `groups`: objects.toml, objects.saved.json, runtime file and lock. Stage `records`: the emptied tiles'
    records and package files."""
    apply_ = _apply()
    region = f'region/{apply_.REGION}'
    paths, scopes = set(), {region}
    add = lambda rel: paths.add(f'{apply_.GAME_REL}/{rel}')       # noqa: E731
    if not emptied(plan):
        return {'paths': [], 'scopes': scopes}
    if stage == 'groups':
        for rel in (f'world/regions/{apply_.REGION}/objects.toml', f'world/regions/{apply_.REGION}/objects.saved.json',
                    f'unreal/Content/{apply_.RUNTIME}', apply_.LOCK):
            add(rel)
        return {'paths': sorted(paths), 'scopes': scopes}
    for stem in emptied(plan):
        tile = plan['tiles'][stem]
        scopes.add((f'asset/{tile["record"]}', tile['owner']))
        folder = game / 'assets' / tile['record']
        for path in sorted(folder.rglob('*')) if folder.is_dir() else []:
            if path.is_file():
                add(path.relative_to(game).as_posix())
        for rel in apply_.package_rels(game, tile['package']):
            add(rel)
    return {'paths': sorted(paths), 'scopes': scopes}


def retire_compute(game: Path, plan: dict, stage: str = 'groups') -> dict:
    """{'writes', 'deletes'} of a retire stage (see retire_touched)."""
    apply_ = _apply()
    records = apply_.records
    stems = emptied(plan)
    writes, deletes = {}, []
    if not stems:
        return {'writes': writes, 'deletes': deletes}
    region = game / 'world' / 'regions' / apply_.REGION
    if stage == 'records':
        for stem in stems:
            tile = plan['tiles'][stem]
            others = [a.id for a in (records.load_asset(q) for q in records.record_paths(game))
                      if tile['record'] in a.references + a.input_dependencies]
            if others:
                raise apply_.SplitError(f'{tile["record"]} is still referenced by {others}: delete those placements\' actors '
                                        'and records and save them again with migrate/objects.py first')
        return {'writes': {}, 'deletes': sorted(p[len(apply_.GAME_REL) + 1:] for p in retire_touched(game, plan, stage)['paths']
                                                  if (game / p[len(apply_.GAME_REL) + 1:]).is_file())}
    runtime = apply_.runtime_input(game)
    text = (region / 'objects.toml').read_text()
    saved = json.loads((region / 'objects.saved.json').read_text()) if (region / 'objects.saved.json').is_file() else None
    for stem in stems:
        text = drop_group(text, f'SM_BC_{stem}')
        if saved is not None:
            saved = drop_saved_group(saved, f'SM_BC_{stem}')
    new = {f'world/regions/{apply_.REGION}/objects.toml': text.encode()}
    if saved is not None:
        new[f'world/regions/{apply_.REGION}/objects.saved.json'] = (json.dumps(saved, indent=2, sort_keys=True) + '\n').encode()
    new_bytes = json.dumps(apply_.edit_runtime(runtime, plan, retire=True), separators=(',', ':')).encode()
    new[f'unreal/Content/{apply_.RUNTIME}'] = new_bytes
    new[apply_.LOCK] = apply_.lock_text(game, new_bytes).encode()
    writes = {k: v for k, v in new.items() if not (game / k).is_file() or (game / k).read_bytes() != v}
    return {'writes': writes, 'deletes': []}


def retire(game: Path, plan: dict, claim: str | None, batch: str, stage: str = 'groups', donor: Path | None = None,
           echo=print) -> dict:
    """Retire the emptied tiles of an applied, imported and checked batch in two stages (refuses before the check passes):
    `groups` drops their groups from the placements and the runtime file; after the affected placements were deleted and
    saved again, `records` deletes the tile records and packages."""
    apply_ = _apply()
    problems = check(game, donor, batch, retired=(stage == 'records'))
    if problems:
        raise apply_.SplitError('refusing to retire before the import and check pass: ' + '; '.join(problems[:3]))
    set_batch(batch).require_applied_plan(game, plan)   # the checked batch, not a fresh selection under its name
    ops = retire_compute(game, plan, stage)
    info = retire_touched(game, plan, stage)
    try:
        apply_.authority.authorize(info['paths'], claim, 'Brine Cove market/town retire ' + stage, scopes=info['scopes'])
    except apply_.authority.Unauthorized as error:
        raise apply_.SplitError(str(error)) from None
    if stage == 'groups':
        echo('placements to delete (actor and record) and save again with migrate/objects.py: ' +
             ', '.join(affected_placements(game, plan)))
    return apply_.execute(game, ops, scopes=info['scopes'])


def retire_placements(game: Path, plans: list, claim: str | None, donor: Path | None = None, echo=print) -> dict:
    """Stage `placements` for every (batch, plan) pair in one claimed, journaled step: the affected placements' record folders
    and actor packages, each placement once. Refuses unless each batch's groups stage is done and its check passes (the
    emptied tile records still exist). Batches with nothing emptied are skipped. Idempotent: a placement already deleted
    is no longer found, so a rerun deletes nothing (keep the list the first run printed for the re-save)."""
    apply_ = _apply()
    active = [(batch, plan) for batch, plan in plans if emptied(plan)]
    if not active:
        return {'written': [], 'deleted': []}
    for batch, plan in active:
        problems = check(game, donor, batch, groups=True)
        if problems:
            raise apply_.SplitError(f'{batch}: refusing to delete placements before the check passes: ' + '; '.join(problems[:3]))
        set_batch(batch).require_applied_plan(game, plan)
        if not groups_retired(game, plan):
            raise apply_.SplitError(f'{batch}: the groups stage is not done; run retire --retire-stage groups first')
    ids = placement_ids(game, active)
    echo('placements to save again with migrate/objects.py: ' + (', '.join(ids) or 'none'))
    info = placements_touched(game, ids)
    ops = placements_compute(game, info)
    if not ops['deletes']:
        return {'written': [], 'deleted': []}
    try:
        apply_.authority.authorize(info['paths'], claim, 'Brine Cove market/town retire placements', scopes=info['scopes'])
    except apply_.authority.Unauthorized as error:
        raise apply_.SplitError(str(error)) from None
    return apply_.execute(game, ops, scopes=info['scopes'])


def placements_compute(game: Path, info: dict) -> dict:
    """{'writes', 'deletes'} of the placements stage: the existing files of the placements' touched set."""
    prefix = len(_apply().GAME_REL) + 1
    deletes = sorted(p[prefix:] for p in info['paths'] if (game / p[prefix:]).is_file())
    return {'writes': {}, 'deletes': deletes}


def batch_names(arg: str) -> list[str]:
    """`all` (every market and town batch in apply order) or a comma list of batch names, each once."""
    names = list(BATCHES) if arg == 'all' else list(dict.fromkeys(b.strip() for b in arg.split(',') if b.strip()))
    unknown = [b for b in names if b not in BATCHES]
    if not names or unknown:
        raise MarketError(f'unknown batch {", ".join(unknown) or "(none)"}; known: {", ".join(BATCHES)}, or all')
    return names


def touched_all(game: Path, plans: list) -> dict:
    """The union over (batch, plan) pairs of every stage's paths and scopes, and the placements to save again."""
    apply_ = _apply()
    out = {'apply': set(), 'scopes': set(), 'retire_groups': set(), 'retire_records': set()}
    for batch, plan in plans:
        set_batch(batch)
        info = apply_.touched(game, plan)
        out['apply'] |= set(info['paths'])
        out['scopes'] |= set(info['scopes'])
        for stage, key in (('groups', 'retire_groups'), ('records', 'retire_records')):
            step = retire_touched(game, plan, stage)
            out[key] |= set(step['paths'])
            out['scopes'] |= set(step['scopes'])
    ids = placement_ids(game, plans)
    placed = placements_touched(game, ids)
    out['retire_placements'] = placed['paths']
    out['scopes'] |= placed['scopes']
    out['placements'] = ids
    return {'apply': sorted(out['apply']), 'retire_groups': sorted(out['retire_groups']),
            'retire_records': sorted(out['retire_records']), 'retire_placements': out['retire_placements'],
            'placements': ids, 'scopes': sorted(s if isinstance(s, str) else ' or '.join(s) for s in out['scopes'])}


def selection(batch: str, only: str | None) -> list[str]:
    if only:
        names = only.split(',')
    elif batch in BATCHES:
        names = list(BATCHES[batch])
    else:
        raise MarketError(f'unknown batch {batch}; known: {", ".join(BATCHES)} (or pass --only)')
    for n in names:
        component_of(n)
    return names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=('plan', 'paths', 'apply', 'retire', 'check', 'list'))
    parser.add_argument('--batch', default='market1', help='batch name, a comma list of names, or all (every market and town batch)')
    parser.add_argument('--only', help='comma-separated object names instead of the batch\'s own list (one batch only)')
    parser.add_argument('--donor', type=Path, help='the donor build/yorimichi folder')
    parser.add_argument('--donor-src', type=Path, help='the donor games/yorimichi folder (default: next to --donor)')
    parser.add_argument('--components', default='Market', help='list: Market, TownLower, TownUpper (comma-separated)')
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--claim', help='the active claim (task ID) that must cover the touched set')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--retire-stage', choices=('groups', 'placements', 'records'), default='groups',
                        help='retire: groups, then placements (delete and re-save them), then records')
    parser.add_argument('--retired', action='store_true', help='check: the emptied tiles are already retired')
    parser.add_argument('--game', type=Path, default=HERE.parents[1], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    apply_ = _apply()
    game = args.game.resolve()
    try:
        names = batch_names(args.batch)
        if args.command == 'check':
            donor = args.donor.resolve() if args.donor else None
            problems = [p if len(names) == 1 else f'{b}: {p}' for b in names for p in check(game, donor, b, args.retired)]
            print('\n'.join(problems))
            print(f'{"FAIL" if problems else "OK"}: {len(problems)} problem(s)')
            return 1 if problems else 0
        if args.donor is None:
            parser.error('--donor is required')
        donor = args.donor.resolve()
        src = donor_source(donor, args.donor_src)
        if args.command == 'list':
            for component in args.components.split(','):
                gen = generated_owners(donor / 'brinecove' / 'glb', src, component)
                count: dict = defaultdict(lambda: defaultdict(int))
                for stem, owners in gen['owner'].items():
                    for o in owners:
                        if o:
                            count[o][stem] += 1
                for obj in sorted(count):
                    print(f'{obj:26} {sum(count[obj].values()):6} tris  {dict(count[obj])}')
            return 0
        if len(names) > 1 and args.only:
            parser.error('--only takes one batch')
        if args.command == 'apply' and len(names) > 1:
            parser.error('apply takes one batch; run the batches one at a time, in order')
        plans = []
        for batch in names:
            if args.stage is None:
                stage = apply_.DEFAULT_STAGE.with_name('brinecove-' + batch)
            else:
                stage = args.stage if len(names) == 1 else args.stage / batch
            plans.append((batch, build(game, donor, src, stage.resolve(), batch, selection(batch, args.only))))
        if args.command == 'plan':
            for batch, plan in plans:
                print(apply_.report(plan))
            if args.json:
                print(json.dumps(summary(plans[0][1]) if len(plans) == 1 else {b: summary(p) for b, p in plans}, indent=2))
        elif args.command == 'paths':
            info = touched_all(game, plans)
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                for title, key in (('# apply: write, create or (for the package files, by the import) overwrite', 'apply'),
                                   ('# retire --retire-stage groups: edit placements and runtime (after a passing import and check)',
                                    'retire_groups'),
                                   ('# retire --retire-stage placements: delete the affected placements (records and actors)',
                                    'retire_placements'),
                                   ('# retire --retire-stage records: delete the emptied tiles (after their placements were saved again)',
                                    'retire_records')):
                    print(title)
                    print('\n'.join(info[key]))
                print('# placements to delete and save again between the stages: ' + ', '.join(info['placements']))
        elif args.command == 'retire':
            for batch, plan in plans:
                print(f'# {batch}')
                print(apply_.report(plan))
            if args.retire_stage == 'placements':
                done = retire_placements(game, plans, args.claim, donor)
            else:
                done = {'written': [], 'deleted': []}
                for batch, plan in plans:
                    if not emptied(plan):
                        print(f'{batch}: no emptied tile, nothing to retire')
                        continue
                    step = retire(game, plan, args.claim, batch, args.retire_stage, donor)
                    done['written'] += step['written']
                    done['deleted'] += step['deleted']
            print(f'retire: wrote {len(done["written"])}, deleted {len(done["deleted"])}')
        else:
            if len(plans) != 1:
                parser.error('apply takes one batch')
            print(apply_.report(plans[0][1]))
            done = apply_.run_step(game, plans[0][1], args.claim)
            print(f'apply: wrote {len(done["written"])}')
    except (MarketError, apply_.SplitError, apply_.recover.RecoverError, apply_.records.RecordError, ValueError) as error:
        print(f'market split failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
