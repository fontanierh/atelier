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


IMPORTER = Path(__file__).resolve().parents[1] / 'unreal/Scripts/import_foliage_lods.py'


class FakeMeshes:
    def __init__(self, palettes, sizes):
        self.palettes, self.sizes = palettes, sizes

    def get_lod_screen_sizes(self, target):
        return self.sizes

    def get_lod_material_slot(self, target, level, section):
        return (level, section)

    def get_number_verts(self, target, level):
        return 8


class FakeMaterial:
    def __init__(self, path):
        self.path = path

    def get_path_name(self):
        return self.path


class FakeTarget:
    def __init__(self, palettes):
        self.palettes = palettes

    def get_name(self):
        return 'Tree_Forest_Pine'

    def get_num_lods(self):
        return len(self.palettes)

    def get_num_sections(self, level):
        return len(self.palettes[level])

    def get_material(self, slot):
        level, section = slot
        return FakeMaterial(self.palettes[level][section])

    def get_editor_property(self, name):
        assert name == 'static_materials'
        return []


@pytest.fixture
def importer(monkeypatch):
    import sys
    from types import SimpleNamespace
    for name, module in {'unreal': SimpleNamespace(), 'yori': SimpleNamespace(),
                         'foliage_material': SimpleNamespace(supports_lod_blend=lambda m: True),
                         'mesh_import': SimpleNamespace(import_mesh=None)}.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('import_foliage_lods_under_test', IMPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEAF = ['/Game/Japan/Materials/MI_Bark.MI_Bark', '/Game/Japan/Materials/MI_LeafPine.MI_LeafPine']
IMPOSTOR = sorted(['/Game/Japan/Materials/MI_Bark.MI_Bark',
                   '/Game/Japan/Materials/MI_Tree_Forest_Pine_Impostor.MI_Tree_Forest_Pine_Impostor'])
CROWN = ['/Game/Japan/FoliageLODs/MI_Tree_Forest_Pine_Crown.MI_Tree_Forest_Pine_Crown']


@pytest.mark.parametrize('palettes,impostor', [([LEAF, LEAF, LEAF, IMPOSTOR, CROWN], 'Tree_Forest_Pine_Impostor'),
                                               ([LEAF, LEAF, LEAF, LEAF, LEAF, CROWN], None)])
def test_crown_is_one_extra_level_after_the_authored_chain(importer, palettes, impostor):
    sizes = [1., .5, .2, .1, .05, .01][:len(palettes)]
    report = importer.verify_lods(FakeTarget(palettes), sizes, FakeMeshes(palettes, sizes), impostor,
                                  crown={'slot': 'Tree_Forest_Pine_Crown'}, folder='/Game/Japan/FoliageLODs')
    assert report['materials_by_lod'][-1] == CROWN


@pytest.mark.parametrize('palettes', [[LEAF, LEAF, LEAF, CROWN, IMPOSTOR], [LEAF, LEAF, LEAF, IMPOSTOR, IMPOSTOR]])
def test_crown_must_follow_the_impostor(importer, palettes):
    sizes = [1., .5, .2, .1, .05]
    with pytest.raises(AssertionError):
        importer.verify_lods(FakeTarget(palettes), sizes, FakeMeshes(palettes, sizes), 'Tree_Forest_Pine_Impostor',
                             crown={'slot': 'Tree_Forest_Pine_Crown'}, folder='/Game/Japan/FoliageLODs')


def test_each_tree_product_owns_its_crown_material(importer):
    import json
    from atelier import build
    catalog = build.load_recipe('yorimichi').foliage_build.catalog
    specs = Path(__file__).resolve().parents[1] / 'assets/foliage'
    crowned = [name for name in catalog.FOLIAGE
               if (specs / (name + '.json')).exists() and 'far_crown' in json.loads((specs / (name + '.json')).read_text())]
    assert crowned
    for name in crowned:
        # import_foliage.py passes the tree's own LOD folder; the native product retains that folder whole.
        path = importer.crown_path({'slot': name + '_Crown'}, '/Game/Japan/FoliageLODs/' + name)
        assert catalog.independently_owned(path), path
