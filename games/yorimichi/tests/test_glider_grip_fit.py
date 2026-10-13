"""A rigid bar fits a narrow character without concealing a perpendicular grip miss."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def fit(enabled, target_span=50., perpendicular=0., source_span=80.):
    source = Path(__file__).resolve().parents[1] / 'unreal/Scripts/import_adventure_moveset.py'
    names = {'sub', 'add', 'mul', 'dot', 'cross', 'apply', 'apply_t', 'compose', 'compose_t', 'glider'}
    nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    identity = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    scope = {'math': math, 'BODY': 1., 'FIT': {'glider': {'fit_grip_span': enabled}},
             'transform': lambda rotation, position, scale: (rotation, position, scale),
             'U': SimpleNamespace(MathLibrary=SimpleNamespace(make_relative_transform=lambda t, _: t))}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    class Rig:
        def __init__(self, span, offset):
            self.span, self.offset = span, offset
        def body(self):
            return identity
        def hand(self, side):
            return identity, 10.
        def at(self, name):
            sign = 1. if name.endswith('R') else -1.
            return [sign * self.offset / 2., sign * self.span / 2., 100.]
        def rotation(self, name):
            return identity
        def transform(self, name):
            return None
    return scope['glider'](Rig(source_span, 0.), Rig(target_span, perpendicular), {'hand': 'Weapon_R'}, 1.)


def test_narrow_grip_fits_bar_but_keeps_canopy_angle_and_midpoint():
    original, miss = fit(False)
    assert miss == [15., 15.] and original[2] == 1.
    fitted, miss = fit(True)
    assert miss == [0., 0.]
    assert fitted[0] == original[0]
    assert fitted[2] == .625
    # The pivot remains the fitted right grip, so its scaled left end also meets the left hand.
    assert fitted[1] == [0., 25., 100.]


def test_perpendicular_miss_is_retained_and_bad_spans_refused():
    _, miss = fit(True, perpendicular=14.)
    assert miss == [7., 7.]  # Still fails the unchanged native 6 cm gate.
    with pytest.raises(AssertionError, match='reference glider grip span'):
        fit(True, source_span=0.)
    with pytest.raises(AssertionError, match='invalid glider grip scale'):
        fit(True, target_span=-50.)
