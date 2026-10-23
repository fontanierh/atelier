"""Crown placement queries the final product without reconstructing its surface."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GAME/'world'))
import yori  # noqa: E402,F401
from terrain_product import Mesh  # noqa: E402
from hidamari.forest_backdrop import crown_support  # noqa: E402


@pytest.mark.parametrize('name,points',[
    ('inserted_parent_saddle',[[5.,4.]]),
    ('asymmetric_curved_sampling',[[5.,6.],[7.,9.]]),
    ('rail_lattice_transition',[[9.,4.],[17.,4.]]),
])
def test_crown_height_and_slope_use_existing_final_triangles(name,points):
    from belmonte.source import Surface
    case=json.loads(Path(__file__).with_name('fixtures').joinpath('terrain-r8.json').read_text())['cases'][name]
    mesh=Mesh.from_polygons(case['vertices'],case['triangles'])
    before=[a.copy() for a in (mesh.vertices,mesh.indices,mesh.offsets)]
    x,y=np.asarray(points).T
    # Independent existing triangle query over the frozen nonlinear/asymmetric
    # surfaces. The stencil may cross facets: its slope is not a face normal.
    triangles=Surface(mesh.vertices[mesh.triangles()])
    expected=triangles.height(np.r_[x,x+2.,x-2.,x,x],
                              np.r_[y,y,y,y+2.,y-2.]).reshape(5,-1)
    height,slope=crown_support(mesh,x,y)
    np.testing.assert_allclose(height,expected[0],rtol=0.,atol=1e-12)
    np.testing.assert_allclose(slope,np.hypot((expected[1]-expected[2])/4.,
                                             (expected[3]-expected[4])/4.),rtol=0.,atol=1e-12)
    for old,new in zip(before,(mesh.vertices,mesh.indices,mesh.offsets)):
        np.testing.assert_array_equal(old,new)


def test_crown_stencil_missing_final_support_fails_instead_of_using_analytic_ground():
    mesh=Mesh.from_polygons([[0.,0.,0.],[4.,0.,1.],[0.,4.,2.]],[[0,1,2]])
    with pytest.raises(ValueError,match='FarHills/final has no triangle support'):
        crown_support(mesh,[1.],[1.])


def test_city_producer_reads_final_product_before_grounding_crowns(tmp_path):
    from atelier import build,build_products
    recipe=build.load_recipe('yorimichi')
    graph=build_products.Graph(recipe.steps(SimpleNamespace(game='yorimichi',out=tmp_path,uproject=None)))
    assert 'terrain.FarHills.final' in graph.by_name['world.hidamari.layout_data'].reads
    names=[s.name for s in graph.select(['world.hidamari'])]
    assert names.index('world.layout') < names.index('world.farhills') < names.index('world.hidamari')
