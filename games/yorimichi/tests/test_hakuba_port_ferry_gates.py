"""The ferry's boarding gates hang at their openings' hinges on the deck, not at the ship's waterline origin.

`FY_BoardingGate` is built about its hinge at the sill, with its rail running along +X across the opening. Standing it
at the ship's origin, as the hull is stood, buried it at the waterline some 7 m below the deck.
"""
import json
import math
import sys
from pathlib import Path

import pytest

PORT = Path(__file__).resolve().parents[1] / 'hakuba_port'
sys.path.insert(0, str(PORT))
import regions  # noqa: E402

# The ship's two boarding openings as its build records them: ship metres, +X bow, the centre on the sill.
OPENINGS = [
    {'side': 'starboard', 'centre': [15.2, -5.6, 6.939], 'width': 2.2, 'outward': [0, -1, 0]},
    {'side': 'port', 'centre': [15.2, 5.6, 6.939], 'width': 2.2, 'outward': [0, 1, 0]},
]


def build(tmp_path, centre, heading):
    """A ferry build holding only what the adapter reads, with the ship berthed at `centre`, turned `heading`."""
    ship = tmp_path / 'ferry'
    (ship / 'terminals').mkdir(parents=True)
    (ship / 'manifest.json').write_text(json.dumps({'materials': {}, 'boarding_openings': OPENINGS}))
    terminal = {'frame': 'world', 'anchor': [0.0, 0.0, 0.0], 'meshes': []}
    (ship / 'terminals' / 'manifest.json').write_text(json.dumps(
        {'materials': {}, 'terminals': {'hidamari': terminal, 'brinecove': terminal}}))
    (ship / 'terminals' / 'site.json').write_text(json.dumps(
        {'hidamari': {'berth': {'centre': centre, 'heading_deg': heading}}, 'brinecove': {'origin_m': [0.0, 0.0]}}))
    return tmp_path


def on_map(centre, heading, point):
    turn = math.radians(heading)
    x, y = point
    return centre[0] + x * math.cos(turn) - y * math.sin(turn), centre[1] + x * math.sin(turn) + y * math.cos(turn)


@pytest.mark.parametrize('centre, heading', [([855.0, -145.0], 180.0), ([10.0, 20.0], 37.0)])
def test_gates_hang_at_their_openings_hinges(tmp_path, centre, heading):
    region = regions.ferry(build(tmp_path, centre, heading))
    gates = [instances for name, _, instances in region.groups if name == 'ferry-boarding-gate']
    assert len(gates) == 1 and len(gates[0]) == len(OPENINGS)
    for opening, (x, y, z, yaw, scale) in zip(OPENINGS, gates[0]):
        cx, cy, sill = opening['centre']
        run = opening['width'] - 0.2
        # The hinge stands on the opening's sill, at the after end of the rail's run across it.
        assert (x, y) == pytest.approx(on_map(centre, heading, (cx - run / 2, cy)), abs=1e-9)
        assert z == pytest.approx(sill) and z > 6.0
        assert scale == 1.0
        # The rail's free end: across the opening when shut, outboard when swung open.
        end = (x + run * math.cos(math.radians(yaw)), y + run * math.sin(math.radians(yaw)))
        if opening['side'] == 'starboard':
            out_x, out_y, _ = opening['outward']
            outboard = on_map(centre, heading, (cx - run / 2 + out_x * run, cy + out_y * run))
            assert end == pytest.approx(outboard, abs=1e-9)
        else:
            assert end == pytest.approx(on_map(centre, heading, (cx + run / 2, cy)), abs=1e-9)
    # The rest of the ship stands at its origin on the berth.
    hull = [instances for name, _, instances in region.groups if name == 'ferry-hull']
    assert hull == [[[*centre, 0.0, heading, 1.0]]]
