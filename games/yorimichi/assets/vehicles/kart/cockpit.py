"""One authored cockpit frame for the generated kart, fitted previews and runtime staging."""
import json
import math
from pathlib import Path

SOURCE = Path(__file__).with_suffix('.json')


def load():
    """@cc [owner:fontanierh,label:correctness] kart-cockpit-frame
    Mesh generation, driver fitting and staged runtime layout MUST consume this same metre frame.
    Unreal consumers MUST mirror Y and convert lengths to centimetres exactly once.
    """
    data = json.loads(SOURCE.read_text())
    assert data['schema'] == 1
    for key in ('seat', 'pelvis', 'steering', 'foot', 'knee', 'elbow', 'foot_forward', 'body_half_extents', 'steering_column_base'):
        assert len(data[key]) == 3 and all(math.isfinite(v) for v in data[key]), key
    assert 0 < data['scale_range'][0] <= data['scale_range'][1] < 2
    assert data['reference_leg_length'] > 0 and data['steering_radius'] > 0
    assert len(data['wheel_positions']) == 4
    assert all(len(v) == 3 and all(math.isfinite(n) for n in v) for v in data['wheel_positions'])
    assert data['wheel_radius'] > 0 and data['wheel_width'] > 0
    hub, base = data['steering'], data['steering_column_base']
    assert hub[1] == base[1] and base[0] > hub[0] and hub[2] > base[2]
    data['steering_tilt_degrees'] = math.degrees(math.atan2(hub[2] - base[2], base[0] - hub[0]))
    # The old dashboard crossed the legs. The open cockpit has no transverse solid here.
    # Exact clothed leg clearance is checked on the evaluated pose: the tilted wheel's
    # low point lies between/behind the knees, so a shared horizontal height plane is too coarse.
    assert data['steering'][2] > data['knee'][2] + .05
    return data


def fit(leg_length, data=None):
    """Uniform scale keeps a child's and an adult's normalized leg reach in the same cockpit."""
    data = load() if data is None else data
    assert math.isfinite(leg_length) and leg_length > 0
    low, high = data['scale_range']
    scale = leg_length / data['reference_leg_length']
    assert low <= scale <= high, ('rider outside verified cockpit range', scale)
    return scale


def grip(side, steer=0.0, data=None):
    """Rim contact, forward, radial and upward tangent in the authored Blender frame.

    steer is the runtime front-wheel angle (radians, right positive). Reflecting UE's
    X-axis wheel rotation into Blender reverses its angle; tilt about Y keeps its sign.
    """
    data = load() if data is None else data
    assert side in (0, 1) and math.isfinite(steer)
    sign = 1 if side == 0 else -1
    elev = math.radians(data['grip_elevation_degrees'])
    spin, tilt = steer * 2.5, math.radians(data['steering_tilt_degrees'])

    def rotate(v):
        x, y, z = v
        y, z = y * math.cos(spin) - z * math.sin(spin), y * math.sin(spin) + z * math.cos(spin)
        return (x * math.cos(tilt) + z * math.sin(tilt), y, -x * math.sin(tilt) + z * math.cos(tilt))

    forward = rotate((1, 0, 0))
    radial = rotate((0, sign * math.cos(elev), math.sin(elev)))
    tangent = rotate((0, -sign * math.sin(elev), math.cos(elev)))
    at = tuple(c + r * data['steering_radius'] for c, r in zip(data['steering'], radial))
    return at, forward, radial, tangent


def wrap_direction(point, radius, opposed=False):
    """A finger segment tangent to the inflated rim cross-section; the thumb wraps oppositely."""
    x, y = point
    distance = math.hypot(x, y)
    assert distance >= radius - 1e-6, ('finger joint starts inside the grip', distance, radius)
    sine = min(.999, radius / max(radius + .0001, distance))
    cosine = math.sqrt(1 - sine * sine)
    sign = -1 if opposed else 1
    return (-x / distance * cosine - sign * y / distance * sine,
            -y / distance * cosine + sign * x / distance * sine)
