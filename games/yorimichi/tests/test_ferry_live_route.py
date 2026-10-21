"""The physical companionway drive reaches both deck joins in ship-local coordinates."""
import ast
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

import numpy as np
import pytest


def route_function():
    path = Path(__file__).resolve().parents[1] / 'scenarios/ferry_roundtrip_live.py'
    tree = ast.parse(path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'companionway_route')
    namespace = {'math': math}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['companionway_route']


@pytest.mark.parametrize('side', [-1, 1])
def test_companionway_route_crosses_both_joins_and_returns(side):
    deck = {'main_deck': {'x': [-40., 40.], 'z': [6., 7.]},
            'boat_deck': {'z': {'x': [-40., 40.], 'z': [10., 11.]}},
            'stair': {'y': [-1.7, -.7], 'foot_x': -26., 'foot_z': 6.2,
                      'top_x': -22., 'top_z': 10.225, 'tread': .28}}
    start = [15.2, side*4.5, 6.69]
    route = route_function()(deck, start)
    foot, top = deck['stair']['foot_x']-.28, deck['stair']['top_x']
    stair_points = [p for p in route if foot <= p[0] <= top and abs(p[1]+1.2) < 1e-10]
    assert route[0] == start
    assert stair_points[0] == pytest.approx([foot, -1.2, 6.2])
    assert stair_points[-1] == pytest.approx([top, -1.2, 10.225])
    assert all(0 < b[0]-a[0] <= .5 for a, b in zip(stair_points, stair_points[1:]))
    assert route[-1] == pytest.approx([-21.2, -1.2, 10.+(40.-21.2)/80.])
    assert route[-1][0] > top+.5  # Must walk onto the upper deck, beyond the nosing.
    return_route = list(reversed(route))
    assert return_route[0] == route[-1] and return_route[-1] == start
    assert max(p[2] for p in route) - min(p[2] for p in route) > 3.9


def test_companionway_approach_clears_actual_generated_collision():
    root = Path(__file__).resolve().parents[1]
    build = Path(os.environ.get('ATELIER_BUILD_ROOT', root.parents[1] / 'build'))
    layout = build / 'yorimichi/ferry/deck_layout.json'
    if not layout.is_file():
        pytest.skip('requires the generated ferry deck; run after world.ferry_ship')
    deck = json.loads(layout.read_text())
    sys.path.insert(0, str(root / 'world'))
    spec = importlib.util.spec_from_file_location('ferry_walk_route_test', root / 'assets/vehicles/ferry/walk.py')
    walker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(walker)
    main = deck['main_deck']
    xs, widths, zs = (np.asarray(main[k]) for k in ('x', 'half_width', 'z'))
    surface = walker.Deck('companionway approach', -29., 18., -5.6, 5.6,
                          lambda X, Y: np.abs(Y) <= np.interp(X, xs, widths)-.02,
                          lambda X, Y: np.interp(X, xs, zs), {'main deck'}).rasterise(deck['proxies'])
    for side in (-1, 1):
        route = route_function()(deck, [15.2, side*4.5, float(np.interp(15.2, xs, zs))])
        foot = next(i for i, p in enumerate(route) if p[0] == deck['stair']['foot_x']-deck['stair']['tread'])
        for a, b in zip(route[:foot], route[1:foot+1]):
            count = max(2, math.ceil(math.dist(a[:2], b[:2])/.025))
            for point in np.linspace(a, b, count):
                i, j = surface.cell(*point[:2])
                assert surface.walk[i, j], (side, point.tolist(), float(surface.dist[i, j]))
