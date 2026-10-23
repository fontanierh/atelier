"""Shared coastal ground sampling parameters, independent from its mesh constructor."""
import math

from brinecove import layout as L

STEP = 4.0


def jag_point(p):
    """Break the sampled heightfield on steep faces: cliffs read as rock, not as a smooth sampled surface. Part of
    the landform the atlas signs (world/map/atlas.py), so it lives with the ground rather than the town kit."""
    px, py, pz = p
    amp = min(2.2, max(0.0, L.slope(px, py) - 0.42) * 2.4)
    if amp <= 0.0:
        return p
    wave = (math.sin(px * 0.11 + py * 0.07) * math.cos(py * 0.13 - px * 0.05)
            + 0.45 * math.sin(px * 0.27 + py * 0.19 + 1.3))
    return (px + math.cos(py * 0.17) * amp * 0.38,
            py + math.sin(px * 0.19) * amp * 0.38,
            pz + wave * amp)


def _axis(lo, hi, step):
    n = max(2, math.ceil((hi - lo) / step))
    return [lo + (hi - lo) * k / n for k in range(n + 1)]
