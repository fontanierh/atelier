"""The cockpit frame must preserve handedness, supported reach and the wheel's leg space."""
import importlib.util
import math
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location('kart_cockpit', Path(__file__).resolve().parents[1] / 'assets/vehicles/kart/cockpit.py')
cockpit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cockpit)


def test_child_and_adult_keep_normalized_reach():
    layout = cockpit.load()
    for length in (.595, .70, .793):
        assert length / cockpit.fit(length) == pytest.approx(layout['reference_leg_length'])
    # Clamping would silently put a different-sized character in the same kart.
    for unsupported in (.1, 2):
        with pytest.raises(AssertionError):
            cockpit.fit(unsupported)


@pytest.mark.parametrize('steer', [-.3, 0, .3])
def test_grips_stay_on_the_rim_at_steering_extremes(steer):
    layout = cockpit.load()
    for side in (0, 1):
        at, forward, radial, tangent = cockpit.grip(side, steer)
        assert math.dist(at, layout['steering']) == pytest.approx(layout['steering_radius'])
        for direction in (forward, radial, tangent):
            assert math.hypot(*direction) == pytest.approx(1)
        assert sum(a * b for a, b in zip(forward, tangent)) == pytest.approx(0, abs=1e-8)
        assert sum(a * b for a, b in zip(radial, tangent)) == pytest.approx(0, abs=1e-8)
        # The former runtime bug crossed left/right hands while elbows and legs stayed on their own sides.
        assert at[1] > 0 if side == 0 else at[1] < 0


def test_forward_wheel_sits_above_the_leg_targets():
    layout = cockpit.load()
    at, _, _, _ = cockpit.grip(0)
    assert at[2] > layout['knee'][2]
    assert layout['steering'][2] > layout['knee'][2] + .05
    assert layout['steering'][0] > .1
    # The original .55 m hub/.15 m rim crossed the .40 m knee plane, before clothing thickness.
    assert not .55 - .15 > .40 + .04


def test_wheel_face_is_perpendicular_to_the_steering_shaft():
    layout = cockpit.load()
    _, forward, _, _ = cockpit.grip(0)
    shaft = tuple(a - b for a, b in zip(layout['steering_column_base'], layout['steering']))
    length = math.hypot(*shaft)
    assert sum(a * b / length for a, b in zip(forward, shaft)) == pytest.approx(1)
    assert layout['steering_tilt_degrees'] == pytest.approx(50)


@pytest.mark.parametrize('opposed', [False, True])
def test_phalanges_wrap_without_crossing_the_rubber(opposed):
    point = (.028, .012)
    radius = .0185
    for length in (.030, .022, .016):
        direction = cockpit.wrap_direction(point, radius, opposed)
        assert math.hypot(*direction) == pytest.approx(1)
        # Nearest point anywhere along this bone, rather than just its endpoints.
        along = min(length, max(0, -sum(a * b for a, b in zip(point, direction))))
        nearest = tuple(a + along * b for a, b in zip(point, direction))
        assert math.hypot(*nearest) >= radius - .0001
        point = tuple(a + length * b for a, b in zip(point, direction))
