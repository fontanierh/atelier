"""Belmonte north of the volcano, in the same metre frame as the island.

The imported scene keeps its own local origin and scale. The northern apron joins
the existing foothills without changing their samples. The eastern railway is an
environmental corridor; train service and Haras mechanics are outside this region.
"""
import numpy as np

ORIGIN = np.array([550., 3900., 210.])
SOURCE_BOUNDS = (-1024.5, -600.5, 1023.5, 1191.5)
BOUNDS = tuple(value + ORIGIN[i % 2] for i, value in enumerate(SOURCE_BOUNDS))
SOUTH_JOIN = 3000.
APRON = 180.
# The route leaves Hidamari's yard, rounds the volcano's eastern flank and
# approaches Belmonte from its southern countryside. No train gameplay is added.
RAILWAY = [(1231.4, 301.45), (1440., 460.), (1900., 880.),
           (2450., 1550.), (2490., 2220.), (2360., 2860.),
           (2040., 3250.), (1730., 3550.), (1350., 3780.)]
RAIL_END_Z = 213.


def contains(x, y, margin=0.):
    return ((np.asarray(x) >= BOUNDS[0] - margin) & (np.asarray(x) <= BOUNDS[2] + margin)
            & (np.asarray(y) >= BOUNDS[1] - margin) & (np.asarray(y) <= BOUNDS[3] + margin))


def native_origin():
    return [float(ORIGIN[0] * 100), float(-ORIGIN[1] * 100), float(ORIGIN[2] * 100)]
