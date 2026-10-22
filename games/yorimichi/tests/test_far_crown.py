import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / 'world/far_crown.py'


@pytest.fixture
def crown(monkeypatch):
    spec = importlib.util.spec_from_file_location('far_crown_under_test', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ellipsoid(radii, centre=(0., 0., 5.), n=400, seed=1):
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(n, 3)); d /= np.linalg.norm(d, axis=1, keepdims=True)
    return np.array(centre) + d * np.array(radii)


def signed_volumes(vertices, faces, centre):
    tri = vertices[faces] - centre
    return np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2]))


@pytest.mark.parametrize('radii', [(4., 4., 3.), (1.2, 1.2, 7.5), (10., 9., 3.)])
def test_bipyramid_is_twelve_outward_triangles_in_the_cards_box(crown, monkeypatch, radii):
    points = ellipsoid(radii)
    monkeypatch.setattr(crown, '_hull_volume', lambda p: 4 / 3 * np.pi * np.prod(radii) * .9)
    vertices, faces, scale = crown.bipyramid(points, 1e9)
    assert vertices.shape == (8, 3) and faces.shape == (12, 3)
    centre = (points.min(0) + points.max(0)) / 2
    assert (signed_volumes(vertices, faces, centre) > 0).all()
    # Measured in the box frame: a tall, thin crown (cypress) gets no sideways spikes.
    extent = (vertices.max(0) - vertices.min(0)) / (points.max(0) - points.min(0))
    assert (extent < 1.7).all() and scale > 1.


def test_bipyramid_caps_growth_at_the_importer_tolerance(crown, monkeypatch):
    points = ellipsoid((4., 4., 3.))
    monkeypatch.setattr(crown, '_hull_volume', lambda p: 1e6)   # would grow without bound
    vertices, _, _ = crown.bipyramid(points, 9.)
    assert np.linalg.norm(vertices.max(0) - vertices.min(0)) == pytest.approx(9.)
