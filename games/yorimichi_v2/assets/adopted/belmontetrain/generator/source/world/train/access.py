"""Who fits aboard the Belmonte train and who may go where (plain Python, no bpy).

The playable characters come from their own definitions (assets/characters/pipeline/definition.py): their height
and capsule radius, the capsule's full height being twice its half height. Two kinds of check build on them:

- fit: every interior doorway and gangway clears the tallest player's capsule, and nothing hanging overhead (lamps
  and their cords, luggage racks and nets, the menu board) comes within that capsule anywhere a player can stand. The
  plan-view walking checks in layout.check() use a 0.28 m radius, wider than every player's capsule, so they already
  cover each player's width;
- access: the consist's junctions in train order. Two neighbours are joined when the ends facing each other are both
  gangways (or both footplates); a junction is open to passengers only between two coaches of the same passenger
  class. Every other joined junction keeps its gangway doors locked for passengers: second class stays on its own
  between stops, and the staff vehicles (locomotive, tender, baggage van, brake van) can't be reached from the
  passenger coaches, though staff can still walk through.
"""
import sys
from pathlib import Path

import numpy as np

from train import fittings as FT
from train import layout as L
from train.consist import BUILDERS, VEHICLES

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'assets' / 'characters' / 'pipeline'))
import definition  # noqa: E402

# who may board each vehicle: first class and the restaurant share a class; second class is on its own
ACCESS = {'locomotive': 'staff', 'tender': 'staff', 'baggage-van': 'staff', 'restaurant': 'first',
          'first-class': 'first', 'second-class': 'second', 'brake-van': 'staff'}
# Paul, 2026-10-16: every door opens for everyone, no locked doors. True brings back the class rules: second class on
# its own between stops, the staff vehicles shut to passengers behind locked gangway doors.
LOCKED_DOORS = False
HEAD_MARGIN = .05               # clearance kept above the tallest capsule (m)
OVERHEAD = ('Fittings_Lamps', 'Fittings_LampCords', 'Fittings_Racks', 'Fittings_RackNets', 'Fittings_MenuBoard')


def players():
    """The playable characters as (id, height m, capsule radius m, capsule height m), smallest first."""
    out = [(c.id, c.height, c.game['capsule_radius'] / 100, 2 * c.game['half_height'] / 100)
           for c in definition.movers() if c.playable]
    return sorted(out, key=lambda p: p[1])


def tallest():
    return max(p[3] for p in players())


def junctions():
    """The consist's neighbours, head first: (front id, rear id, the facing ends, joined, open to passengers).
    The head is at +x, so a vehicle's end A (-x) faces the next vehicle's end B (+x)."""
    out = []
    for front, rear in zip(VEHICLES, VEHICLES[1:]):
        a = BUILDERS[front['id']]().body.end_a
        b = BUILDERS[rear['id']]().body.end_b
        joined = a == b and a in ('gangway', 'footplate')
        cls = ACCESS[front['id']]
        open_ = joined and (not LOCKED_DOORS or cls != 'staff' and cls == ACCESS[rear['id']])
        out.append((front['id'], rear['id'], (a, b), joined, open_))
    return out


def passenger_groups():
    """The sets of vehicles a passenger can walk between, one per boarding class."""
    groups = {v['id']: {v['id']} for v in VEHICLES if not LOCKED_DOORS or ACCESS[v['id']] != 'staff'}
    for front, rear, _, _, open_ in junctions():
        if open_:
            merged = groups[front] | groups[rear]
            for v in merged:
                groups[v] = merged
    return sorted({frozenset(g) for g in groups.values()}, key=sorted)


def locked_gangways():
    """(vehicle id, door name) of every gangway door passengers may not open: both sides of a joined junction that
    isn't open to them."""
    out = []
    for front, rear, ends, joined, open_ in junctions():
        if joined and not open_ and ends[0] == 'gangway':
            out += [(front, 'gangway-door-a'), (rear, 'gangway-door-b')]
    return out


def check_access():
    bad = []
    # one open train (LOCKED_DOORS off): the class rules don't apply, only same-class neighbours must be joined
    groups = passenger_groups() if LOCKED_DOORS else []
    by_class = {}
    for g in groups:
        classes = {ACCESS[v] for v in g}
        if len(classes) > 1:
            bad.append(f'passengers can walk between classes: {sorted(g)}')
        by_class.setdefault(classes.pop(), []).append(g)
    for cls, gs in by_class.items():
        if len(gs) > 1:
            bad.append(f'{cls} class is split: {[sorted(g) for g in gs]}')
    for front, rear, ends, joined, _ in junctions():
        if ACCESS[front] == ACCESS[rear] != 'staff' and not joined:
            bad.append(f'{front} and {rear} share a class but no gangway joins them ({ends[0]} / {ends[1]})')
    return bad


def check_fit(c):
    """Doorways and overhead fittings against the tallest player's capsule, anywhere a player can stand."""
    bad = []
    for name, h in (('interior doorways', L.DOOR_H), ('gangways', L.GANGWAY_H)):
        if h < tallest() + HEAD_MARGIN:
            bad.append(f'{name} {h:.2f} m are lower than the tallest player plus {HEAD_MARGIN} m')
    parts = [p for p in FT.fittings(c) if p.name in OVERHEAD]
    if not parts:
        return bad
    lo = c.body.walk_limits()[0]
    pts = {p.name: np.array([q for face in p.faces for q in face[0]]) for p in parts}
    for who, _, radius, height in players():      # each player with its own capsule, where it can stand
        top = L.FLOOR_Z + height + HEAD_MARGIN
        grid, step = L.walkable_grid(c, radius)
        i, j = np.nonzero(grid)
        xs, ys = lo + (i + .5) * step, -L.IN + (j + .5) * step
        for name, p in pts.items():
            for x, y, z in p[p[:, 2] < top]:
                if ((xs - x) ** 2 + (ys - y) ** 2 < radius * radius).any():
                    bad.append(f'{name} at ({x:.2f}, {y:.2f}) hangs {z - L.FLOOR_Z:.2f} m above the floor, '
                               f'inside {who} ({height:.2f} m) standing there')
                    break
    return bad
