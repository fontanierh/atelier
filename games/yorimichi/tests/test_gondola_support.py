"""Whole support footprints include ground vertices outside the footprint."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from gondola_kit_fixture import gondola_modules
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))


def test_support_ceiling_clips_the_complete_triangle_and_preserves_the_peak():
    with gondola_modules('solid',pure=False):
        support=importlib.import_module('gondola.support')
    triangles=np.array([[[-50,-50,0],[50,-50,100],[0,50,50]]],float)
    footprint=[[-1,-1],[1,-1],[1,1],[-1,1]]
    # z=x+50 across the entire footprint; no terrain vertex lies inside it.
    assert support.ground_ceiling(triangles,footprint)==pytest.approx(51.)
    assert support.ground_ceiling(triangles,footprint[::-1])==pytest.approx(51.)


def test_support_without_any_owned_triangle_refuses():
    with gondola_modules('solid',pure=False):
        support=importlib.import_module('gondola.support')
    with pytest.raises(ValueError,match='No owned terrain'):
        support.ground_ceiling(np.array([[[10,10,0],[11,10,0],[10,11,0]]]),[[0,0],[1,0],[1,1],[0,1]])


def test_vertical_ground_edge_is_preserved_as_a_clearance_obstacle():
    with gondola_modules('solid',pure=False):
        support=importlib.import_module('gondola.support')
    triangle=np.array([[[0,-10,0],[0,10,0],[0,0,15]]],float)
    assert support.ground_ceiling(triangle,[[-1,-1],[1,-1],[1,1],[-1,1]])==15.
