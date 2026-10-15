"""Editor-park supports: basalt towers under high pieces, timber bents under low ones, never above a ramp."""
from pathlib import Path
import sys
import types

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2 import dsl, editor_supports as es  # noqa: E402


def sheet(pid, y, length=60., width=18., x0=0., z0=0.):
    """A flat run along +x at height y, as the bridge would hand it over (vertices plus stations)."""
    xs, zs = np.meshgrid(np.arange(0, length + .1, 1.), np.arange(-width / 2, width / 2 + .1, 1.))
    V = np.stack([x0 + xs.ravel(), np.full(xs.size, y), z0 + zs.ravel()], 1)
    stations = [dict(d=float(d), x=x0 + d, y=y, z=z0, h=0., a=0., w=width - 2, wl={'h': 0., 'R': 1.}, wr={'h': 0., 'R': 1.},
                     deck=1.) for d in np.arange(0, length + .1, 1.)]
    return types.SimpleNamespace(mesh=types.SimpleNamespace(V=V), metadata=dict(id=pid, type='run', stations=stations))


GRID = dict(x0=-60., z0=-60., G=2., nx=150, nz=150)
FLAT = np.zeros(150 * 150, 'f4')


def vertices(parts, material=None):
    keep = [p for p in parts if material is None or (p.material == dsl.MATERIAL[material]).all()]
    return np.concatenate([p.V for p in keep]) if keep else np.zeros((0, 3))


def test_high_piece_stands_on_basalt_towers_under_its_underside():
    parts, summary = es.build([sheet('p1', 30., length=120.)], FLAT, GRID)
    assert summary['pieces'] == {'p1': 'basalt'} and summary['towers'] >= 2 and summary['columns'] > 10
    V = vertices(parts, es.BASALT)
    assert V[:, 1].max() <= 30. + es.EMBED + 1e-6
    assert V[:, 1].min() >= -es.SINK - 1e-6
    assert all(p.role[0] == dsl.ROLE[dsl.SIDE] for p in parts)


def test_low_piece_stands_on_timber_bents():
    parts, summary = es.build([sheet('p1', 5.)], FLAT, GRID)
    assert summary['pieces'] == {'p1': 'timber'} and summary['bents'] >= 5 and summary['towers'] == 0
    assert len(vertices(parts, es.TIMBER)) and len(vertices(parts, es.FOOTING))
    assert vertices(parts)[:, 1].max() <= 5. + 1e-6


def test_no_column_passes_through_a_piece_below():
    high, low = sheet('high', 40.), sheet('low', 10., length=20., x0=20.)
    parts, _ = es.build([high, low], FLAT, GRID)
    V = vertices(parts, es.BASALT)
    over_low = (V[:, 0] > 20.5) & (V[:, 0] < 39.5) & (np.abs(V[:, 2]) < 8.5)
    assert not (V[over_low, 1] > 10.).any(), 'a tower column runs through the lower piece'


def test_supports_are_deterministic():
    a, _ = es.build([sheet('p1', 30.)], FLAT, GRID)
    b, _ = es.build([sheet('p1', 30.)], FLAT, GRID)
    assert np.array_equal(vertices(a), vertices(b))
