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

DONOR_BUILD is the donor's `build/yorimichi` folder; the generator sources are read from `games/yorimichi` two levels up
(override with --donor-src). The apply, check and claim machinery is `brinecove_split_apply.py`, used unchanged with
its expectation file pointed at `split-market.json`.
"""
from __future__ import annotations

import argparse
import ast
import itertools
import json
import struct
import sys
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
COMPONENT_OF = {'market-': 'Market', 'town-lower-': 'TownLower', 'town-upper-': 'TownUpper'}


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
        if asset is not None and asset.sources and asset.sources[0].sha256 == donor_sha:
            settings = dict(asset.recipe['settings'])
            if len(settings['slot_materials']) != len(model['materials']):
                raise apply_.SplitError(f'{stem}: the record binds {len(settings["slot_materials"])} slots, '
                                        f'the donor mesh has {len(model["materials"])}')
            tiles[stem] = {'record': asset.id, 'owner': asset.owner, 'references': list(asset.references),
                           'package': asset.outputs[0].package, 'settings': settings,
                           'material_package': dict(zip(model['materials'], settings['slot_materials']))}
        elif stem in saved:
            tiles[stem] = {**saved[stem]['original'], 'record': saved[stem]['record'], 'package': saved[stem]['package']}
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
            name = apply_.mesh_name(obj, soft)
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
                                'slots': [apply_.slot_of(tiles, [stem], m) for m in used]}
        else:
            remainders[stem] = None
    return {'tiles': tiles, 'parts': parts, 'remainders': remainders, 'stage': stage, 'prior': done['prior']}


def check(game: Path, donor: Path | None, batch: str, src: Path | None = None) -> list[str]:
    """apply's repository checks for this batch, plus the vertex-level proof when the donor is given: donor tile =
    this batch's parts + its remainder + the earlier batches' parts of the same tile."""
    apply_ = set_batch(batch)
    problems = apply_.check(game, None)
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
    files += [game / 'assets' / t['record'] / 'src' / f'SM_BC_{s}.glb' for s, t in exp['tiles'].items() if t['remainder']]
    for other in prior_files(region, f'split-{batch}.json'):          # earlier batches' parts cut from the same tiles
        old = json.loads(other.read_text())
        files += [game / 'assets' / rid / 'src' / f'{p["mesh"]}.glb' for rid, p in old['parts'].items()
                  if set(p['tiles']) & set(exp['tiles'])]
    for f in files:
        if not f.is_file() or records.is_lfs_pointer(f):
            return problems + [f'{f.name}: not hydrated, the donor proof is skipped']
        pieces.append(list(split.triangles(split.read_glb(f))))
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
    parser.add_argument('command', choices=('plan', 'paths', 'apply', 'check', 'list'))
    parser.add_argument('--batch', default='market1', help='batch name; its expectation is split-<batch>.json')
    parser.add_argument('--only', help='comma-separated object names instead of the batch\'s own list')
    parser.add_argument('--donor', type=Path, help='the donor build/yorimichi folder')
    parser.add_argument('--donor-src', type=Path, help='the donor games/yorimichi folder (default: next to --donor)')
    parser.add_argument('--components', default='Market', help='list: Market, TownLower, TownUpper (comma-separated)')
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--claim', help='the active claim (task ID) that must cover the touched set')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--game', type=Path, default=HERE.parents[1], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    apply_ = set_batch(args.batch)
    game = args.game.resolve()
    try:
        if args.command == 'check':
            problems = check(game, args.donor.resolve() if args.donor else None, args.batch)
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
        stage = (args.stage or apply_.DEFAULT_STAGE.with_name('brinecove-' + args.batch)).resolve()
        plan = build(game, donor, src, stage, args.batch, selection(args.batch, args.only))
        if args.command == 'plan':
            print(apply_.report(plan))
            if args.json:
                print(json.dumps(summary(plan), indent=2))
        elif args.command == 'paths':
            info = apply_.touched(game, plan)
            scopes = sorted(s if isinstance(s, str) else ' or '.join(s) for s in info['scopes'])
            if args.json:
                print(json.dumps({'apply': info['paths'], 'scopes': scopes}, indent=2))
            else:
                print('# apply: write, create or (for the package files, by the import) overwrite')
                print('\n'.join(info['paths']))
        else:
            print(apply_.report(plan))
            done = apply_.run_step(game, plan, args.claim)
            print(f'apply: wrote {len(done["written"])}')
    except (MarketError, apply_.SplitError, apply_.recover.RecoverError, apply_.records.RecordError, ValueError) as error:
        print(f'market split failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
