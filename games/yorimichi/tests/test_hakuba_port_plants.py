"""A region's plant keeps its source height only where it is off Hakuba's ground or seated on a ported prop.

Belmonte's and Brinecove's plants once kept their source height whenever it stood well above Hakuba's ground, so
hundreds hung 0.3–5.6 m in the air over nothing; the bound applies under the prop's surface as well as over it.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hakuba_port'))
import plants  # noqa: E402


def test_plants_keep_height_only_on_a_prop():
    ground = np.array([0.0, 0.0, 0.0, 0.0, np.nan, 0.0])
    z = np.array([5.0, 5.0, 10.0, 10.0, 7.0, 1.0])
    surface = np.array([np.nan, 5.3, 14.0, 9.7, np.nan, np.nan])
    # Over no prop, seated on one, 4 m under one, seated just under one's surface, off the ground, near the ground.
    assert plants.keeps_height(z, ground, surface).tolist() == [False, True, False, True, True, False]
