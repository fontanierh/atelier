"""Owner selection, missing coverage and explicit trail contact regressions."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
from gondola.terrain import Ground
from terrain_product import Mesh
from terrain_query import Surface


def plane(owner, z, bounds=(-10, -10, 10, 10)):
    a, b, c, d = bounds
    return Surface(Mesh.from_polygons([(a,b,z),(c,b,z),(c,d,z),(a,d,z)], [[0,1,2],[0,2,3]]),
                   owner=owner, stage='final')


def ground(**overrides):
    fields = dict(city=plane('city', 10), mountain=plane('mountain', 20),
                  valley=plane('valley', 40), apron=plane('apron', 30),
                  trail=plane('trail', 1, (1,-1,2,1)),
                  city_bounds=(-5,-5,5,0), mountain_bounds=(-5,0,5,3),
                  valley_bounds=(-2,5,2,10), apron_bounds=(-5,3,5,10))
    return Ground(**(fields | overrides))


def test_seams_choose_north_owner_without_comparing_height():
    xy = [[0,-1e-6],[0,0],[0,1e-6],[0,3-1e-6],[0,3],[0,3+1e-6],
          [0,5-1e-6],[0,5],[0,5+1e-6]]
    z, owners = ground().base(xy)
    assert owners.tolist() == ['city','mountain','mountain','mountain','apron','apron','apron','valley','valley']
    assert z.tolist() == [10,20,20,20,30,30,30,40,40]


def test_trail_owns_covered_walking_contact_even_if_lower_than_base():
    query = [[1.5,-.5],[2.5,-.5]]
    z, owners = ground().contact(query)
    assert z.tolist() == [1,10]
    assert owners.tolist() == ['trail','city']
    assert ground().base(query)[0].tolist() == [10,10]


def test_missing_owned_triangle_never_falls_back_to_present_neighbour():
    query = ground(mountain=plane('mountain', 20, (-5,1,5,3)))
    with pytest.raises(ValueError, match='no triangle support'):
        query.base([[0,.5]])


def test_trail_contact_remains_valid_above_a_base_hole_but_support_is_still_missing():
    query = ground(city=plane('city',10,(-5,-5,0,0)))
    z,owners = query.contact([[1.5,-.5]])
    assert z.tolist()==[1] and owners.tolist()==['trail']
    with pytest.raises(ValueError,match='no triangle support'):
        query.base([[1.5,-.5]])


@pytest.mark.parametrize('xy', [[[6,-1]], [[6,1]], [[6,4]], [[0,11]]])
def test_outside_declared_footprints_refused_even_if_mesh_extends_there(xy):
    with pytest.raises(ValueError, match='outside declared'):
        ground().base(xy)


def test_apron_selected_outside_valley_instead_of_extending_valley_mesh():
    z, owners = ground().base([[3,6]])
    assert z.tolist() == [30] and owners.tolist() == ['apron']


def test_bad_seam_declaration_refused():
    with pytest.raises(ValueError, match='share their authored seams'):
        ground(city_bounds=(-5,-5,5,.1))
