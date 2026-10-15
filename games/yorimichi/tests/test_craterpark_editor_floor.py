"""Editor-park crater floor: basalt crags, snow drifts, moss, shrubs and conifers round the pieces, deterministic and
clear of the riding."""
import math
from pathlib import Path
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2 import dsl, editor_floor as ef  # noqa: E402

GRID = dict(x0=-150., z0=-150., G=2., nx=150, nz=150)
_x = GRID['x0'] + (np.arange(150) + .5) * 2.
_X, _Z = np.meshgrid(_x, _x)
GROUND = (1.5 * np.sin(_X / 23.) * np.cos(_Z / 31.)).astype('f4').ravel()     # a gently rolling floor


def sheet(pid, y, length=60., width=12., x0=0., z0=0., kind='run'):
    """A flat run along +x at height y over (x0, z0), as the bridge would hand it over (a sheet plus stations)."""
    xs, zs = np.meshgrid(np.arange(0, length + .1, 2.), np.arange(-width / 2, width / 2 + .1, 3.))
    V = np.stack([x0 + xs.ravel(), np.full(xs.size, y), z0 + zs.ravel()], 1)
    nz, nx = xs.shape
    i = (np.arange(nz - 1)[:, None] * nx + np.arange(nx - 1)[None]).ravel()
    F = np.concatenate([np.stack([i, i + nx, i + 1], 1), np.stack([i + 1, i + nx, i + nx + 1], 1)])
    stations = [] if kind == 'bowl' else [
        dict(d=float(d), x=x0 + d, y=y, z=z0, h=0., a=0., w=width - 2, wl={'h': 0., 'R': 1.}, wr={'h': 0., 'R': 1.},
             deck=0.) for d in np.arange(0, length + .1, 1.)]
    return types.SimpleNamespace(mesh=types.SimpleNamespace(V=V, F=F),
                                 metadata=dict(id=pid, type=kind, stations=stations))


def scene():
    """A high run, a low run whose end meets the ground (a run-out), and a bowl sunk in the floor."""
    return [sheet('high', 12., length=80., x0=-60., z0=-40.),
            sheet('low', 1., length=40., x0=-20., z0=30.),
            sheet('bowl', -3., length=30., width=24., x0=40., z0=-60., kind='bowl')]


def floor_site():
    """The rolling floor inside a round crater wall whose foot is 135 m from the middle (the corners are up the wall)."""
    site = ef.Site.flat(GROUND, GRID)
    site.foot = lambda x, z: 135. - np.hypot(x, z)
    return site


@pytest.fixture(scope='module')
def built():
    return ef.build(scene(), GROUND, GRID, floor_site())


def vertices(parts):
    return np.concatenate([p.V for p in parts])


def plan_distance(parts, pieces, cell=.5):
    """Each dressing vertex's plan distance (m) to the nearest piece surface (a fine chamfer grid); the bowl apart."""
    out = {}
    for name, group in (('pieces', [p for p in pieces if p.metadata['type'] != 'bowl']),
                        ('bowl', [p for p in pieces if p.metadata['type'] == 'bowl'])):
        P = np.concatenate([ef._samples(np.asarray(p.mesh.V, 'f8'), np.asarray(p.mesh.F), .4) for p in group])
        n = int(300 / cell)
        f = np.full((n, n), np.inf)
        i = ((P[:, 0] - GRID['x0']) / cell).astype(int)
        j = ((P[:, 2] - GRID['z0']) / cell).astype(int)
        f[j, i] = 0.
        shifts = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
        for _ in range(int(12 / cell)):
            p = np.pad(f, 1, constant_values=np.inf)
            f = np.minimum.reduce([f] + [p[1 + a:1 + a + n, 1 + b:1 + b + n] + math.hypot(a, b) * cell
                                         for a, b in shifts])
        V = vertices(parts)
        out[name] = f[np.clip(((V[:, 2] - GRID['z0']) / cell).astype(int), 0, n - 1),
                      np.clip(((V[:, 0] - GRID['x0']) / cell).astype(int), 0, n - 1)]
    return out


def test_every_kind_is_placed_on_a_budget(built):
    parts, summary = built
    for kind in ('crags', 'spires', 'rocks', 'stones', 'conifers', 'shrubs', 'tufts', 'cushions', 'snow_m2', 'moss_m2'):
        assert summary[kind] > 0, kind
    assert summary['triangles'] == sum(len(p.F) for p in parts) < 100000
    assert set(summary['by_material']) == {ef.ROCK, ef.SNOW, ef.GRASS, ef.MOSS, ef.OLIVE, ef.SHRUB, ef.GOLD,
                                           ef.CONIFER}
    assert all(m in dsl.MATERIAL for m in summary['by_material'])


def test_snow_lies_in_broad_fields_over_its_share_of_the_open_floor(built):
    parts, summary = built
    assert abs(summary['snow_share'] - ef.SNOW_COVER) < .08, summary['snow_share']
    snow = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.SNOW][0]
    # one welded sheet: its faces connect into a few big fields, not hundreds of blobs
    parent = list(range(len(snow.V)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b, c in snow.F:
        for u, v in ((a, b), (b, c)):
            parent[root(u)] = root(v)
    fields = {root(i) for i in np.unique(snow.F)}
    assert len(fields) < summary['snow_m2'] / 150., (len(fields), summary['snow_m2'])


def test_crags_are_big_dark_and_gather_at_the_wall_conifers_stylised(built):
    parts, _ = built
    site = floor_site()
    rock = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.ROCK][0]
    over = rock.V[:, 1] - site.ground(rock.V[:, 0], rock.V[:, 2])
    assert 8. < over.max() <= 15.5, 'the biggest crags stand 8 to 15 m'
    tall = rock.V[over > 3.]
    foot = site.foot(tall[:, 0], tall[:, 2])
    band = (foot < ef.BAND) & (foot > -ef.WALL_UP)
    # crag rock stands far thicker in the wall's band than out on the floor (per square metre of plan)
    plan = np.stack(np.meshgrid(np.arange(-149., 150.), np.arange(-149., 150.)), -1).reshape(-1, 2)
    f = site.foot(plan[:, 0], plan[:, 1])
    share = ((f < ef.BAND) & (f > -ef.WALL_UP)).mean()
    assert band.mean() / share > 3 * (1 - band.mean()) / (1 - share)
    tree = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.CONIFER][0]
    over = tree.V[:, 1] - site.ground(tree.V[:, 0], tree.V[:, 2])
    assert 3.5 < over.max() <= 9.5


def test_snow_drifts_are_never_fragments(built):
    parts, _ = built
    snow = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.SNOW][0]
    parent = list(range(len(snow.V)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b, c in snow.F:
        parent[root(b)] = root(a)
        parent[root(c)] = root(a)
    T = snow.V[snow.F][:, :, [0, 2]]
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    comp = np.array([root(a) for a in snow.F[:, 0]])
    sizes = np.bincount(np.unique(comp, return_inverse=True)[1], area)
    assert sizes.min() >= 60. * .9, sizes.min()


def test_no_nan_and_valid_faces(built):
    parts, _ = built
    for p in parts:
        assert np.isfinite(p.V).all() and np.isfinite(p.N).all() and np.isfinite(p.UV).all()
        assert p.F.min() >= 0 and p.F.max() < len(p.V)


def test_rocks_are_solid_the_rest_drawn_only(built):
    parts, _ = built
    for p in parts:
        material = dsl.MATERIALS[int(p.material[0])]
        assert p.role[0] == dsl.ROLE[dsl.SIDE if material in ef.SOLID else dsl.COPING]
        assert dsl.RENDER_ROLE.get(dsl.ROLES[p.role[0]]) is not None, 'drawn'


def test_deterministic():
    a, sa = ef.build(scene(), GROUND, GRID, floor_site(), bake=False)
    b, sb = ef.build(scene(), GROUND, GRID, floor_site(), bake=False)
    assert sa == sb
    assert np.array_equal(vertices(a), vertices(b))


def test_clear_of_the_pieces_and_off_the_bowl(built):
    parts, _ = built
    d = plan_distance(parts, scene())
    # the field is a 1 m chamfer: allow a cell and its diagonal error
    assert d['pieces'].min() >= ef.CLEAR - 1., d['pieces'].min()
    assert d['bowl'].min() >= ef.BOWL_CLEAR - 1., d['bowl'].min()
    high = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.SNOW]
    assert high and plan_distance(high, scene())['pieces'].min() >= ef.CLEAR - 1., 'no snow on or by anything ridden'


def test_nothing_tall_near_an_end_and_the_run_out_kept_clear(built):
    parts, _ = built
    site = ef.Site.flat(GROUND, GRID)
    V = vertices(parts)
    over = V[:, 1] - site.ground(V[:, 0], V[:, 2])
    ends = np.array([(st[k]['x'], st[k]['z']) for p in scene() if (st := p.metadata['stations']) for k in (0, -1)])
    near = np.sqrt(((V[:, None, [0, 2]] - ends[None]) ** 2).sum(-1)).min(1)
    assert (over[near < ef.END_REACH] <= ef.LOW + .05).all()
    # the low run's end (x 20, z 30) meets the ground: its run-out along +x is empty
    run = (V[:, 0] > 20.5) & (V[:, 0] < 19.5 + ef.EXIT_LEN) & (np.abs(V[:, 2] - 30.) < 4.5 + ef.EXIT_SIDE)
    assert not run.any()


def test_rests_on_the_ground(built):
    parts, _ = built
    site = ef.Site.flat(GROUND, GRID)
    for p in parts:
        lo = p.V[:, 1] - site.ground(p.V[:, 0], p.V[:, 2])
        assert lo.min() < .05, 'every part touches or sinks into the ground'
        assert lo.min() > -4., 'none buried deep'
    snow = [p for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.SNOW][0]
    rise = snow.V[:, 1] - site.ground(snow.V[:, 0], snow.V[:, 2])
    assert rise.max() <= .25, 'snow lies low'


def test_the_dressing_bakes_its_own_occlusion(built):
    parts, _ = built
    ao = np.concatenate([p.AO for p in parts])
    assert len(ao) == len(vertices(parts)) and np.isfinite(ao).all() and ao.min() >= 0. and ao.max() <= 1.
    rock = np.concatenate([p.AO for p in parts if dsl.MATERIALS[int(p.material[0])] == ef.ROCK])
    assert (rock < .9).mean() > .02, 'rocks in a cluster shade one another'
