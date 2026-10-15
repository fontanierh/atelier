"""Editor-park coping: a grindable steel lip wherever a riding surface meets its deck, never on a launch ramp."""
from pathlib import Path
import sys
import types

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2 import editor_coping as ec  # noqa: E402

RIDE, DECK = [0.863, 0.762, 0.674], [0.874, 0.51, 0.322]


def strip(x, z0, z1, colour, y=0.):
    """A flat strip of quads from x[0] to x[-1], z0 to z1, every vertex in `colour`."""
    V, F = [], []
    for i, xi in enumerate(x):
        V += [(xi, y, z0), (xi, y, z1)]
        if i:
            a = 2 * (i - 1)
            F += [(a, a + 1, a + 3), (a, a + 3, a + 2)]
    return np.array(V, 'f8'), np.array(F), np.tile(colour, (len(V), 1))


def piece(kind='run', length=40., info=None):
    x = np.arange(0., length + .1, 1.)
    parts = [strip(x, -5., 5., RIDE), strip(x, 5., 6.5, DECK)]
    V, F, C, base = [], [], [], 0
    for v, f, c in parts:
        V.append(v), F.append(f + base), C.append(c)
        base += len(v)
    stations = [dict(d=float(d), x=float(d), y=0., z=0.) for d in x]
    meta = dict(id='p1', type=kind, stations=stations, info=info or {})
    return types.SimpleNamespace(mesh=types.SimpleNamespace(V=np.concatenate(V), F=np.concatenate(F)),
                                 colors=np.concatenate(C), metadata=meta)


def test_lip_runs_along_the_ride_deck_edge_and_points_into_the_ride():
    (points, into), = ec.piece_lips(piece())
    assert np.allclose(points[:, 2], 5.) and np.isclose(np.ptp(points[:, 0]), 40.)
    assert np.allclose(into, [0., 0., -1.])


def test_jump_kicker_and_capped_run_tail_have_no_coping():
    (points, _), = ec.piece_lips(piece('jump', info={'lip': {'i': 15}}))
    assert points[:, 0].min() >= 15.
    (points, _), = ec.piece_lips(piece('run', length=60.), cap=.5)
    assert points[:, 0].max() <= 60. - ec.KICK_REACH


def test_build_makes_a_grind_rail_per_lip():
    meshes, rails, summary = ec.build([piece()], {})
    assert summary['rails'] == 1 and len(meshes) == 1
    top = rails[0].points
    assert np.allclose(top[:, 2], 5. - (ec.coping_mod.REVEAL - ec.coping_mod.RADIUS), atol=1e-6)
    assert np.all(np.linalg.norm(np.diff(top, axis=0), axis=1) <= .5 + 1e-9)
