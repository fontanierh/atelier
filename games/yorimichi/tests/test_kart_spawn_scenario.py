"""The spawn search finds a real narrow spot, not a missing-ground probe.

The old predicate wanted two of four 2.5 m side traces to miss the terrain, which never happens on the continuous
village ground. This loads the scenario with a synthetic terrain and checks the replacement definition: a flat shelf
closed on both sides by at least a step, found beyond the old 18 m grid, while a uniform slope is not narrow.
"""
import importlib.util
import math
import sys
import types
from pathlib import Path

SCENARIO = Path(__file__).resolve().parents[1] / 'scenarios' / 'kart_spawn.py'
ROOT = str(Path(__file__).resolve().parents[3])
BASE_X, BASE_Y = -25542.0, 10140.0


class Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class Hit:
    def __init__(self, x, y, z, nz=1.0):
        self.point = Vec(x, y, z)
        self.normal = Vec(0.0, 0.0, nz)

    def to_tuple(self):
        return (None, None, None, None, None, self.point, None, self.normal)


class Terrain:
    def __init__(self):
        self.height = lambda x, y: 1000.0
        self.walls = []   # (x, y, radius) vertical obstacle posts


def load(tmp_path, monkeypatch, terrain):
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(tmp_path))

    def line_trace(world, start, end, *args):
        if start.z > end.z:
            return Hit(start.x, start.y, terrain.height(start.x, start.y))
        for wx, wy, radius in terrain.walls:
            dx, dy = end.x - start.x, end.y - start.y
            length = math.hypot(dx, dy)
            if length == 0.0:
                continue
            along = ((wx - start.x) * dx + (wy - start.y) * dy) / length
            across = abs(-(wx - start.x) * dy + (wy - start.y) * dx) / length
            if 0.0 < along <= length and across <= radius:
                return Hit(start.x + dx * along / length, start.y + dy * along / length, start.z, nz=0.0)
        return None

    unreal = types.ModuleType('unreal')
    unreal.Vector = Vec
    unreal.TraceTypeQuery = types.SimpleNamespace(ECC_VISIBILITY=0)
    unreal.DrawDebugTrace = types.SimpleNamespace(NONE=0)
    unreal.SystemLibrary = types.SimpleNamespace(line_trace_single=line_trace)
    unreal.LiveLibrary = types.SimpleNamespace(player=lambda: object(), game_world=lambda: object())
    unreal.MegaParkValidation = types.SimpleNamespace(restore_player_camera=lambda: None)
    unreal.log = lambda message: None
    unreal.log_error = lambda message: None

    live = types.ModuleType('live')
    live.ROOT = ROOT
    live.L = types.SimpleNamespace(game_world=lambda: object())
    live.behave = lambda name, fn: None
    live.stop = lambda name=None: None

    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'live', live)
    spec = importlib.util.spec_from_file_location('kart_spawn_scenario', SCENARIO)
    module = importlib.util.module_from_spec(spec)
    module.live, module.unreal = live, unreal
    spec.loader.exec_module(module)
    return module


def shelf(x, y):
    """Flat ground with a bank 120 cm up to the north and a drop 80 cm down to the south, west of x = -28200."""
    if x <= -28200.0:
        if y >= BASE_Y + 120.0:
            return 1120.0
        if y <= BASE_Y - 120.0:
            return 920.0
    return 1000.0


def test_narrow_finds_a_closed_shelf_beyond_the_old_grid(tmp_path, monkeypatch):
    terrain = Terrain()
    terrain.height = shelf
    module = load(tmp_path, monkeypatch, terrain)
    point, detail = module.find_narrow()
    assert point is not None and detail is not None
    assert abs(point.x - BASE_X) > 1800.0           # outside the old 18 m grid
    assert abs(point.x + 28200.0) < 150.0 and abs(point.y - BASE_Y) < 150.0
    assert detail['axis'] == 'y'
    assert detail['deltas_cm'][0] < -45.0 and detail['deltas_cm'][1] > 90.0


def test_uniform_slope_is_not_narrow(tmp_path, monkeypatch):
    terrain = Terrain()
    terrain.height = lambda x, y: 1000.0 + 0.2 * (y - BASE_Y)   # 50 cm each way, no closed side
    module = load(tmp_path, monkeypatch, terrain)
    assert module.narrow_at(BASE_X, BASE_Y) is None
    assert module.find_narrow() == (None, None)


def test_a_wall_closes_a_flat_side(tmp_path, monkeypatch):
    terrain = Terrain()
    terrain.height = lambda x, y: 1000.0 + (200.0 if y >= BASE_Y + 120.0 else 0.0)   # bank north
    terrain.walls = [(BASE_X, BASE_Y - 160.0, 30.0)]                            # rail south within reach
    module = load(tmp_path, monkeypatch, terrain)
    found = module.narrow_at(BASE_X, BASE_Y)
    assert found is not None and found[1]['axis'] == 'y'
