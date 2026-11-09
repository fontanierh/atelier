"""Brine Cove ships as separate objects, assigned by the generator's own object boundaries (docs/inventory/brinecove-ships.md).

The donor bakes the galleon Nightjar and the sloop into the fused tiles SM_BC_Ships_4_2 / _4_3 / _5_3 (and the hull of all three
ships into the hero model `galleon-hull`, four cell meshes that each hold all three transforms). This tool:

1. runs the donor's own `procedural/ship.py` `ship()` once per `layout.SHIPS` entry, exactly as `procedural/ships.py` does,
   in pure Python (no Blender, no Unreal), and records every vertex each ship emits;
2. gives each exported tile triangle to the ship whose generator vertices all three corners coincide with (same material,
   same ground position within 2 mm). No radius, no connected-component guess: the generator's ship is the boundary;
3. proves the result: a ship's triangle count must equal the generator's own count, every triangle of the three tiles
   must belong to exactly one ship, and the tiles' remainder must be empty (they hold only these two ships);
4. splits the hero hull's runtime groups per instance (one transform per group, same mesh cells, nothing re-exported).

It reuses brinecove_split.py (GLB reader, writer, partition proof) and brinecove_split_apply.py (records, journal, claim
preflight, runtime/objects.toml edits for the parts). The apply/retire pair works exactly like batch 1: preflight, claim
check, journal, write; `apply` never deletes; `retire` refuses unless `check` passes.

    CMD="uv run python games/yorimichi_v2/tools/migrate/brinecove_ships.py"
    $CMD plan   --donor DONOR_BUILD [--generator DIR] [--stage DIR]
    $CMD paths  --donor DONOR_BUILD [--json]
    $CMD apply  --donor DONOR_BUILD --claim TASK
    $CMD check  [--donor DONOR_BUILD]
    $CMD retire --donor DONOR_BUILD --claim TASK
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import importlib
import json
import re
import sys
import tomllib
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brinecove_split as split  # noqa: E402
import brinecove_split_apply as apply  # noqa: E402
import records  # noqa: E402
import recover  # noqa: E402
import towns  # noqa: E402

GAME, REGION, GAME_REL = apply.GAME, apply.REGION, apply.GAME_REL
SplitError = apply.SplitError
EXPECTED = f'world/regions/{REGION}/split-ships.json'
TILES = ('Ships_4_2', 'Ships_4_3', 'Ships_5_3')                    # the fused tiles that hold the Nightjar and the sloop
OBJECTS = {                                                       # object -> the donor ship (layout.SHIPS name) and its tiles
    'galleon-nightjar': dict(ship='galleon-nightjar', tiles=('Ships_4_2', 'Ships_4_3')),
    'sloop-east': dict(ship='sloop-east', tiles=('Ships_4_3', 'Ships_5_3')),
}
# layout.SHIPS order = the order of the transforms in every hero hull cell group (hero_placements.placements).
HULL_SHIPS = ('galleon-adventure', 'galleon-nightjar', 'sloop-east')
HULL_OBJECT = {'galleon-nightjar': 'galleon-nightjar', 'sloop-east': 'sloop-east', 'galleon-adventure': 'galleon-adventure-hull'}
HULL_MODEL = 'adopted/brinecove/hero-galleon-hull'
HULL_PREFIX = 'SM_BC_Hero_GalleonHull_cell_'
RETIRED_OBJECTS = ('object/brinecove/ships-nightjar-sloop', 'object/brinecove/hero-galleon-hull')
HERO_OBJECT = 'object/brinecove/hero-galleon-hull'
CELL = 0.01          # spatial hash cell, metres
TOLERANCE = 0.002    # a GLB corner (float32) matches a generator vertex (float64) within 2 mm on the ground plane
HULL_TOLERANCE_CM = 1.0


# --- the generator -----------------------------------------------------------------------------------------------------

def region_dir_of(donor: Path) -> Path:
    """The donor checkout's Brine Cove package folder parent: DONOR/../../games/yorimichi/world/regions."""
    return donor.resolve().parents[1] / 'games' / 'yorimichi' / 'world' / 'regions'


@contextlib.contextmanager
def donor_modules(region: Path):
    """Import the donor's `brinecove` package from `region` for the duration, then forget it again. The package needs
    `atelier.paths.build_root` (a path only); a stub stands in when the real package is not importable."""
    if not (region / 'brinecove' / 'procedural' / 'ship.py').is_file():
        raise SplitError(f'{region}: no brinecove/procedural/ship.py (pass --generator the donor world/regions folder)')
    saved_path, saved_flag = list(sys.path), sys.dont_write_bytecode
    before = set(sys.modules)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(region))
    try:
        try:
            importlib.import_module('atelier.paths')
        except ImportError:
            pkg = types.ModuleType('atelier')
            paths = types.ModuleType('atelier.paths')
            paths.build_root = lambda *a, **k: Path('/nonexistent')
            sys.modules['atelier'], sys.modules['atelier.paths'] = pkg, paths
        yield
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_flag
        for name in set(sys.modules) - before:
            if name == 'brinecove' or name.startswith('brinecove.') or name in ('atelier', 'atelier.paths'):
                del sys.modules[name]


def ground_point(p) -> tuple[float, float]:
    """A generator vertex (x, y, z) on the GLB ground plane: glTF is (x, z up, -y)."""
    return (float(p[0]), -float(p[1]))


def load_generator(region: Path) -> dict:
    """{'ships': {name: {'spec': (x, y, yaw, scale, sails), 'triangles': n, 'vertices': [(material, gx, gz)]}},
    'has_hull': bool}: what `procedural/ships.py` builds for every `layout.SHIPS` entry, one Builder per ship."""
    with donor_modules(region):
        from brinecove import layout as L
        from brinecove.geom import Builder, distinct_corners
        from brinecove.procedural import hero_presence
        from brinecove.procedural.ship import ship
        out = {}
        for name, x, y, yaw, scale, sails in L.SHIPS:
            b = Builder(name)
            ship(b, x, y, -1.1, yaw, scale, sails=sails, unfinished=False,
                 canvas='sail_dark' if name.startswith('galleon') else 'sail')       # the call in procedural/ships.py
            vertices, tris = [], 0
            for face, mat in zip(b.faces, b.mats):
                pts = [b.verts[i] for i in face]
                corners = distinct_corners(pts)
                if corners is None:
                    continue
                tris += len(corners) - 2
                vertices += [('BC_' + mat,) + ground_point(pts[k]) for k in corners]
            out[name] = {'spec': (x, y, yaw, scale, sails), 'triangles': tris, 'vertices': vertices}
        return {'ships': out, 'has_hull': bool(hero_presence.HAS_HULL)}


# --- assignment by generator vertices (pure) ----------------------------------------------------------------------------

def vertex_index(ships: dict[str, list]) -> dict:
    """{(cell_x, cell_z): [(ship, material, x, z)]} of every generator vertex of every ship."""
    index = collections.defaultdict(list)
    for name, vertices in ships.items():
        for mat, x, z in vertices:
            index[(round(x / CELL), round(z / CELL))].append((name, mat, x, z))
    return index


def owners_of(index: dict, mat: str, x: float, z: float) -> set[str]:
    """The ships with a vertex of this material at this ground position (within TOLERANCE)."""
    cx, cz = round(x / CELL), round(z / CELL)
    found = set()
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for name, m, vx, vz in index.get((cx + dx, cz + dz), ()):
                if m == mat and abs(vx - x) <= TOLERANCE and abs(vz - z) <= TOLERANCE:
                    found.add(name)
    return found


def triangle_owner(index: dict, mat: str, corners) -> tuple[str | None, bool]:
    """(ship, ambiguous): the one ship all three corners belong to; None when no ship owns the triangle."""
    common = None
    for p in corners:
        mine = owners_of(index, mat, p[0], p[2])      # glTF (x, y up, z): the ground plane is (x, z)
        common = mine if common is None else common & mine
        if not common:
            return None, False
    return (next(iter(common)), False) if len(common) == 1 else (None, True)


def make_assigner(index: dict, objects: dict[str, dict], problems: list[str]):
    """The assigner brinecove_split.compute takes: per tile, each triangle goes to the object whose ship owns it."""
    ship_object = {o['ship']: name for name, o in objects.items()}

    def assigner(stem, tris, comps, allowed):
        out: dict[str, list[int]] = {name: [] for name in allowed}
        out[''] = []
        for t, (mat, corners) in enumerate(tris):
            ship, ambiguous = triangle_owner(index, mat, corners)
            if ambiguous:
                problems.append(f'{stem}: triangle {t} is owned by more than one ship')
            name = ship_object.get(ship)
            out[name if name in allowed else ''].append(t)
        return out
    return assigner


# --- the hero hull, one group per instance (pure) -----------------------------------------------------------------------

def instance_of(transform: dict, ships: dict[str, tuple]) -> str:
    """The ship a hero hull transform belongs to: its translation_cm is (x * 100, -y * 100) of the layout entry."""
    tx, ty = transform['translation_cm'][:2]
    for name, (x, y) in ships.items():
        if abs(tx - x * 100) <= HULL_TOLERANCE_CM and abs(ty + y * 100) <= HULL_TOLERANCE_CM:
            return name
    raise SplitError(f'hull transform at {tx}, {ty} cm matches no ship')


def is_hull(group: dict) -> bool:
    return towns.mesh_name(group).startswith(HULL_PREFIX)


def split_hull_groups(data: dict, ships: dict[str, tuple]) -> dict:
    """The runtime file with every hero hull cell group holding one transform. A cell group keeps its place and its first
    transform (the Adventure's); the other instances become new groups of the same mesh appended at the end, ordered by
    ship and cell, so no group before them changes position (plant group keys are positional, towns.group_keys).
    A rerun finds single-transform groups and changes nothing."""
    order = {name: i for i, name in enumerate(ships)}
    groups, extra = [], []
    for g in data['groups']:
        if is_hull(g) and len(g['transforms']) > 1:
            first, *rest = g['transforms']
            groups.append({**g, 'transforms': [first]})
            extra += [(order[instance_of(t, ships)], len(extra), {**g, 'transforms': [t]}) for t in rest]
        else:
            groups.append(g)
    return {**data, 'groups': groups + [g for _, _, g in sorted(extra, key=lambda e: e[:2])]}


def hull_keys(data: dict, ships: dict[str, tuple]) -> dict[str, list[str]]:
    """{ship: [group key of each of its hull cell groups]} of a runtime file whose hulls are already split."""
    keys = towns.group_keys(data)
    out = {name: [] for name in ships}
    for key, g in zip(keys, data['groups']):
        if is_hull(g):
            if len(g['transforms']) != 1:
                raise SplitError(f'{key}: hull group holds {len(g["transforms"])} transforms, run apply first')
            out[instance_of(g['transforms'][0], ships)].append(key)
    return out


# --- objects.toml and runtime edits -------------------------------------------------------------------------------------

def object_entries(plan: dict, keys: dict[str, list[str]]) -> list[dict]:
    """objects.toml entries: the Nightjar and the sloop (rig part + its hull cells) and the Adventure's hull alone."""
    entries = []
    for obj in sorted(OBJECTS):
        part = plan['parts'][(obj, False)]
        ship = OBJECTS[obj]['ship']
        entries.append({'id': f'object/brinecove/{obj}', 'groups': [part['mesh']] + keys[ship],
                        'models': [part['record'], HULL_MODEL],
                        'about': f'the {obj.replace("-", " ")}: rig and flags cut from the fused ship tiles '
                                 f'({part["triangles"]} triangles, by the generator\'s ship boundary) and its own hero hull instance'})
    entries.append({'id': 'object/brinecove/galleon-adventure-hull', 'groups': keys['galleon-adventure'],
                    'models': [HULL_MODEL],
                    'about': 'the galleon Adventure\'s hero hull instance (its rig, deck and guns are object/brinecove/galleon-adventure)'})
    return entries


def block_id(block: str) -> str | None:
    m = re.search(r'(?m)^id = "([^"]+)"', block)
    return m.group(1) if m else None


def edit_objects_toml(text: str, entries: list[dict], remove: tuple[str, ...]) -> str:
    """objects.toml with the entries (re)written in the hand-written head and the `remove` objects gone from head and tail."""
    head, found, tail = text.partition(apply.MARKER)
    if not found:
        raise SplitError('objects.toml has no generated-part marker')
    split_at = lambda s: re.split(r'(?m)^(?=\[\[objects\]\]\n)', s)       # noqa: E731
    new = {e['id']: apply.entry_text(e) for e in entries}
    pre, *blocks = split_at(head)
    blocks = [b for b in blocks if block_id(b) not in new and block_id(b) not in remove]
    head = pre + ''.join(b if b.endswith('\n\n') else b.rstrip('\n') + '\n\n' for b in blocks) + '\n'.join(new[k] for k in sorted(new)) + '\n'
    tail = ''.join(b for b in split_at(tail) if block_id(b) not in remove)
    return head + found + tail


def edited_runtime(data: dict, plan: dict, ships: dict[str, tuple], retire: bool = False) -> dict:
    """The hull split, then the parts and remainders (batch 1's edit, which re-appends the parts each run). Splitting first
    keeps the new hull groups before the parts, so a rerun leaves every group where it is (the positional keys hold)."""
    return apply.edit_runtime(split_hull_groups(data, ships), plan, retire=retire)


# --- the plan ----------------------------------------------------------------------------------------------------------

def hull_ships(gen: dict) -> dict[str, tuple]:
    return {n: (gen['ships'][n]['spec'][0], gen['ships'][n]['spec'][1]) for n in HULL_SHIPS}


def build(game: Path, donor: Path, stage: Path, region: Path | None = None) -> dict:
    """Split the three ship tiles by the generator's ships; the apply plan plus the generator facts."""
    gen = load_generator(region or region_dir_of(donor))
    if not gen['has_hull']:
        raise SplitError('the donor generator has no hero hull: the tile ships would include a procedural hull')
    problems: list[str] = []
    index = vertex_index({n: [(m, x, z) for m, x, z in s['vertices']] for n, s in gen['ships'].items()})
    plan = apply.build(game, donor, stage, OBJECTS, assigner=make_assigner(index, OBJECTS, problems))
    plan['generator'] = {n: s['triangles'] for n, s in gen['ships'].items()}
    plan['ships'] = hull_ships(gen)
    for obj, o in OBJECTS.items():
        got = plan['parts'][(obj, False)]['triangles']
        if got != plan['generator'][o['ship']]:
            problems.append(f'{obj}: {got} triangles in the tiles, the generator emits {plan["generator"][o["ship"]]}')
    for stem in TILES:
        if plan['remainders'].get(stem) is not None:
            problems.append(f'{stem}: {plan["remainders"][stem]["triangles"]} triangles belong to no generator ship')
    if (obj_soft := [k for k in plan['parts'] if k[1]]):
        problems.append(f'unexpected Soft parts {obj_soft}')
    if problems:
        raise SplitError('the generator assignment does not hold: ' + '; '.join(problems[:4]))
    return plan


def expected(plan: dict) -> dict:
    out = apply.expected(plan)
    out['about'] = ('Expected result of tools/migrate/brinecove_ships.py (docs/inventory/brinecove-ships.md): the Nightjar and the '
                    'sloop parts cut by the generator\'s ship boundary, and the retired ship tiles.')
    out['generator_triangles'] = plan['generator']
    out['hull'] = {'model': HULL_MODEL, 'objects': HULL_OBJECT,
                   'ships': {n: list(xy) for n, xy in plan['ships'].items()}}
    return out


def retired_records(game: Path) -> list[tuple[str, str]]:
    """(record id, owner scope) of the placements `retire` deletes."""
    return [(i, f'region/{REGION}') for i in RETIRED_OBJECTS]


def touched(game: Path, plan: dict, retire: bool = False) -> dict:
    """Repository-relative paths and claim scopes of a step. Apply: the parts' records and packages, objects.toml, this
    tool's expectation, the runtime file and its lock. Retire: the three ship tile records and packages, the two retired
    placement records and their actor packages, objects.toml / objects.saved.json, the runtime file and its lock."""
    region = f'region/{REGION}'
    paths, scopes = set(), {region}
    add = lambda rel: paths.add(f'{GAME_REL}/{rel}')   # noqa: E731
    if not retire:
        for p in plan['parts'].values():
            scopes.add((f'asset/{p["record"]}', 'shared/brinecove/' + p['record'].rsplit('/', 1)[1]))
            for rel in (f'assets/{p["record"]}/asset.toml', f'assets/{p["record"]}/src/{p["mesh"]}.glb',
                        f'assets/{p["record"]}/verified.json', *apply.package_rels(game, p['package'])):
                add(rel)
        for rel in (f'world/regions/{REGION}/objects.toml', EXPECTED, f'unreal/Content/{apply.RUNTIME}', apply.LOCK):
            add(rel)
        return {'paths': sorted(paths), 'scopes': scopes}
    for stem in TILES:
        tile = plan['tiles'][stem]
        scopes.add((f'asset/{tile["record"]}', tile['owner']))
        folder = game / 'assets' / tile['record']
        for path in sorted(folder.rglob('*')) if folder.is_dir() else []:
            if path.is_file():
                add(path.relative_to(game).as_posix())
        for rel in apply.package_rels(game, tile['package']):
            add(rel)
    for rid, owner in retired_records(game):
        scopes.add((f'asset/{rid}', owner))
        folder = game / 'assets' / rid
        for path in sorted(folder.rglob('*')) if folder.is_dir() else []:
            if path.is_file():
                add(path.relative_to(game).as_posix())
        if (folder / 'asset.toml').is_file():
            for output in records.load_asset(folder / 'asset.toml').outputs:
                for rel in apply.package_rels(game, output.package):
                    add(rel)
    for rel in (f'world/regions/{REGION}/objects.toml', f'world/regions/{REGION}/objects.saved.json',
                f'unreal/Content/{apply.RUNTIME}', apply.LOCK):
        add(rel)
    return {'paths': sorted(paths), 'scopes': scopes}


def objects_step_paths(plan: dict) -> list[str]:
    """What the controller's later `objects.py` run creates for the new placements (its own claim): the placement records
    and the saved-objects file. The actor packages under __ExternalActors__ are named by Unreal at save time."""
    ids = [e for e in HULL_OBJECT.values()]
    return sorted([f'{GAME_REL}/assets/object/brinecove/{i}/asset.toml' for i in ids] +
                  [f'{GAME_REL}/world/regions/{REGION}/objects.saved.json'])


def compute(game: Path, plan: dict, retire: bool = False) -> dict:
    """Every output of a step in memory: {'writes': {rel: bytes}, 'deletes': [rel]}. Reads only."""
    writes, deletes = {}, []
    runtime = apply.runtime_input(game)
    region = game / 'world' / 'regions' / REGION

    def put(rel: str, data: bytes):
        path = game / rel
        if not path.is_file() or path.read_bytes() != data:
            writes[rel] = data

    new_runtime = edited_runtime(runtime, plan, plan['ships'], retire=retire)
    keys = hull_keys(new_runtime, plan['ships'])
    toml = (region / 'objects.toml').read_text()
    if not retire:
        for gen in [apply.part_generated(p) for p in plan['parts'].values()]:
            text, name = apply.record_files(gen)
            put(f'assets/{gen.id}/asset.toml', text.encode())
            put(f'assets/{gen.id}/src/{name}', gen.source.read_bytes())
        # The old hero placement lists the four hull groups under their plain mesh names, which no longer exist as keys.
        toml = edit_objects_toml(toml, object_entries(plan, keys), (HERO_OBJECT,))
        put(EXPECTED, (json.dumps(expected(plan), indent=2, sort_keys=True) + '\n').encode())
    else:
        toml = edit_objects_toml(toml, object_entries(plan, keys), RETIRED_OBJECTS)
        retired_ids = {rid for rid, _ in retired_records(game)}
        for stem in TILES:
            tile = plan['tiles'][stem]
            others = [a.id for a in (records.load_asset(q) for q in records.record_paths(game))
                      if tile['record'] in a.references + a.input_dependencies and a.id not in retired_ids]
            if others:
                raise SplitError(f'{tile["record"]} is retired but {others} still reference it')
        deletes += [p[len(GAME_REL) + 1:] for p in touched(game, plan, True)['paths']
                    if (game / p[len(GAME_REL) + 1:]).is_file()
                    and not p.endswith(('objects.toml', 'objects.saved.json', apply.RUNTIME, apply.LOCK))]
        saved = region / 'objects.saved.json'
        if saved.is_file():
            body = json.loads(saved.read_text())
            if any(i in body.get('objects', {}) for i in RETIRED_OBJECTS):
                body['objects'] = {k: v for k, v in body['objects'].items() if k not in RETIRED_OBJECTS}
                put(f'world/regions/{REGION}/objects.saved.json', (json.dumps(body, indent=2, sort_keys=True) + '\n').encode())
    put(f'world/regions/{REGION}/objects.toml', toml.encode())
    if new_runtime != runtime:
        data = json.dumps(new_runtime, separators=(',', ':')).encode()
        put(f'unreal/Content/{apply.RUNTIME}', data)
        put(apply.LOCK, apply.lock_text(game, data).encode())
    return {'writes': writes, 'deletes': deletes}


def run_step(game: Path, plan: dict, claim: str | None, *, retire: bool = False, lockable=apply.lockable_present,
             echo=print) -> dict:
    recovered = apply.Journal(game).recover(claim)    # authorizes the journal's own paths and scopes first
    if recovered:
        echo(f'restored {len(recovered)} file(s) from an interrupted run')
    ops = compute(game, plan, retire)
    info = touched(game, plan, retire)
    try:
        apply.authority.authorize(info['paths'], claim, 'Brine Cove ships ' + ('retire' if retire else 'apply'),
                                  scopes=info['scopes'])
    except apply.authority.Unauthorized as error:
        raise SplitError(str(error)) from None
    return apply.execute(game, ops, lockable=lockable)


# --- check -------------------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def ships_expectation():
    """batch 1's `check` reads the module-level expectation file name; point it at this tool's file for the call."""
    old = apply.EXPECTED
    apply.EXPECTED = EXPECTED
    try:
        yield
    finally:
        apply.EXPECTED = old


def check(game: Path, donor: Path | None = None, retired: bool = False) -> list[str]:
    """Batch 1's proofs (counts, bounds, hashes, drawn once, the donor union) on the ship parts and tiles, plus the hull."""
    with ships_expectation():
        problems = apply.check(game, donor, retired)
    exp = json.loads((game / EXPECTED).read_text())
    ships = {n: tuple(xy) for n, xy in exp['hull']['ships'].items()}
    region = game / 'world' / 'regions' / REGION
    listed = {i['id']: i for i in tomllib.loads((region / 'objects.toml').read_text()).get('objects', [])}
    for obj in OBJECTS:
        if exp['parts'][f'prop/brinecove/{obj}']['triangles'] != exp['generator_triangles'][OBJECTS[obj]['ship']]:
            problems.append(f'{obj}: part triangles differ from the generator count')
    path = game / 'unreal' / 'Content' / apply.RUNTIME
    if not path.is_file() or records.is_lfs_pointer(path):
        return problems + [f'{apply.RUNTIME} not hydrated: hull checks skipped']
    data = json.loads(path.read_text())
    try:
        keys = hull_keys(data, ships)
    except SplitError as error:
        return problems + [str(error)]
    for ship, ks in keys.items():
        obj = f'object/brinecove/{HULL_OBJECT[ship]}'
        names = listed.get(obj, {})
        have = [names['group']] if 'group' in names else list(names.get('groups', []))
        if len(ks) != 4 or [k for k in ks if k not in have]:
            problems.append(f'{obj}: hull keys {ks} are not all groups of the object ({have}); rerun apply')
    count = sum(len(g['transforms']) for g in data['groups'] if is_hull(g))
    if count != 12:
        problems.append(f'hull transforms: {count} in the runtime file, expected 12 (3 ships x 4 cells)')
    if HERO_OBJECT in listed:
        problems.append(f'{HERO_OBJECT} still lists the shared hull groups')
    if retired and (game / 'assets' / HERO_OBJECT).exists():
        problems.append(f'{HERO_OBJECT} is not retired')
    return problems


# --- command line ------------------------------------------------------------------------------------------------------

def report(plan: dict) -> str:
    lines = [apply.report(plan), 'generator triangles per ship: ' + ', '.join(f'{n} {t}' for n, t in plan['generator'].items())]
    lines.append('hull: one group per instance (4 cells each) of ' + HULL_MODEL + ' for ' + ', '.join(HULL_SHIPS))
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=('plan', 'paths', 'apply', 'retire', 'check'))
    parser.add_argument('--donor', type=Path, help='the donor build/yorimichi folder')
    parser.add_argument('--generator', type=Path, help='the donor games/yorimichi/world/regions folder (default: beside --donor)')
    parser.add_argument('--stage', type=Path, default=apply.DEFAULT_STAGE / 'ships')
    parser.add_argument('--claim', help='the active claim (task ID) that must cover the touched set')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--game', type=Path, default=GAME, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    game = args.game.resolve()
    try:
        if args.command == 'check':
            problems = check(game, args.donor)
            print('\n'.join(problems))
            print(f'{"FAIL" if problems else "OK"}: {len(problems)} problem(s)')
            return 1 if problems else 0
        if args.donor is None:
            parser.error('--donor is required')
        plan = build(game, args.donor.resolve(), args.stage.resolve(), args.generator)
        retire = args.command == 'retire'
        if args.command == 'plan':
            print(report(plan))
        elif args.command == 'paths':
            info, gone = touched(game, plan, False), touched(game, plan, True)
            scopes = sorted(s if isinstance(s, str) else ' or '.join(s) for s in info['scopes'] | gone['scopes'])
            extra = objects_step_paths(plan)
            if args.json:
                print(json.dumps({'apply': info['paths'], 'retire': gone['paths'], 'objects_step': extra, 'scopes': scopes}, indent=2))
            else:
                print('# apply: write, create or (package files, by the import) overwrite')
                print('\n'.join(info['paths']))
                print('# objects.py step (its own claim): placement records and saved-objects file')
                print('\n'.join(extra))
                print('# retire: delete (after the import, objects.py and a passing check)')
                print('\n'.join(gone['paths']))
        else:
            if retire:
                problems = check(game, args.donor, retired=False)
                if problems:
                    raise SplitError('refusing to retire before the import and check pass: ' + '; '.join(problems[:3]))
            print(report(plan))
            done = run_step(game, plan, args.claim, retire=retire)
            print(f'{args.command}: wrote {len(done["written"])}, deleted {len(done["deleted"])}')
    except (SplitError, recover.RecoverError, records.RecordError, ValueError) as error:
        print(f'ships failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
