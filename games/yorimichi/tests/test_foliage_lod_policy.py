"""Split foliage preserves the current main LOD policy without launching Blender."""
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]


@pytest.fixture
def exporter(monkeypatch, tmp_path):
    generators = SimpleNamespace(**{name: object() for name in
        ('tree_broad', 'tree_maple', 'tree_ginkgo', 'tree_pine', 'tree_cedar', 'bush', 'bush_flower')})
    for name, module in {
        'bpy': SimpleNamespace(), 'mathutils': SimpleNamespace(Vector=tuple),
        'asset_mesh': SimpleNamespace(), 'foliage_geometry': generators,
        'asset_catalog': SimpleNamespace(FOLIAGE=(), SPEC_ROOT=GAME / 'assets/foliage'),
        'yori': SimpleNamespace(OUT=tmp_path),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    spec = importlib.util.spec_from_file_location('split_foliage_lod_policy', GAME / 'world/build_foliage_lods.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, generators


class RecordedMesh:
    def __init__(self):
        self.cards, self.tubes = [], []

    def card(self, center, size, *args):
        self.cards.append((center, size))

    def tube(self, *args, **kwargs):
        self.tubes.append(kwargs['n'])


def test_all_ten_tree_specs_keep_the_current_cadence_and_extra_far_lod():
    specs = [json.loads(path.read_text()) for path in (GAME / 'assets/foliage').glob('Tree_*.json')]
    assert len(specs) == 10
    for spec in specs:
        conifer = spec['generator'] in ('tree_pine', 'tree_cedar')
        assert spec['screen_sizes'] == ([1., .18, .07, .025, .012] if conifer else [1., .22, .09, .035, .012])
        assert spec['strides'] == ([3, 8, 16, 32] if conifer else [3, 9, 27, 54])
    all_specs = [json.loads(path.read_text()) for path in (GAME / 'assets/foliage').glob('*.json')]
    assert len(all_specs) == 18 and sum(len(spec['screen_sizes']) for spec in all_specs) == 74


@pytest.mark.parametrize('generator,strides', [('tree_broad', (3, 9, 27, 54)), ('tree_cedar', (3, 8, 16, 32))])
@pytest.mark.parametrize('level', [1, 2, 3, 4])
def test_tree_cards_keep_stride_and_current_coverage_cap(exporter, generator, strides, level):
    module, generators = exporter
    mesh = module.lod_mesh_type(RecordedMesh, getattr(generators, generator), (0, 0, 0), (1, 1, 1), level, strides)()
    stride = strides[level - 1]
    for number in range(stride * 2):
        mesh.card(number, (2., 4.), 0, 0, None, None, None)
    cap = 3.6 if level == 4 else 3.0 if generator == 'tree_broad' or level == 3 else 2.2
    scale = min(math.sqrt(stride), cap)
    assert mesh.cards == [(0, (2 * scale, 4 * scale)), (stride, (2 * scale, 4 * scale))]


@pytest.mark.parametrize('generator', ['tree_broad', 'tree_cedar'])
@pytest.mark.parametrize('level,retained', [(1, [5, 5, 5]), (2, [3, 3]), (3, [3, 3]), (4, [3])])
def test_only_the_current_tree_interior_branches_are_dropped(exporter, generator, level, retained):
    module, generators = exporter
    mesh = module.lod_mesh_type(RecordedMesh, getattr(generators, generator), (0, 0, 0), (1, 1, 1),
                                level, (3, 8, 16, 32))()
    for sides in (5, 6, 8, 10):
        mesh.tube(n=sides)
    assert mesh.tubes == retained


@pytest.mark.parametrize('generator', ['bush', 'bush_flower'])
def test_non_tree_generators_keep_their_branches(exporter, generator):
    module, generators = exporter
    mesh = module.lod_mesh_type(RecordedMesh, getattr(generators, generator), (0, 0, 0), (1, 1, 1), 2, (3, 8))()
    for sides in (5, 6, 8, 10):
        mesh.tube(n=sides)
    assert mesh.tubes == [3, 3, 3, 3]
