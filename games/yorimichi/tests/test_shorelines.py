"""Regressions for the continuous coast, occupied ground and exported waterline."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
import shorelines as S  # noqa: E402


def test_inland_town_and_railway_terrain_is_unchanged():
    x = np.array([-475., 550., 1574., 2450., 2490., 1231., -700.])
    y = np.array([3900., 4500., 5692., 1550., 2220., 301., 2400.])
    base = np.array([210., 250., 230., 180., 240., 32., 120.])
    np.testing.assert_array_equal(S.height(x, y, base), base)


def test_entire_committed_railway_and_tunnel_cover_are_preserved():
    import json
    rows = json.loads(S.RAIL_LINE.read_text())['samples']
    p = np.array([[r['x'], r['y'], r['ground_z']] for r in rows])
    tangent = np.gradient(p[:, :2], axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.c_[-tangent[:, 1], tangent[:, 0]]
    for offset in [-20., 0., 20.]:
        xy = p[:, :2]+normal*offset
        np.testing.assert_array_equal(S.height(xy[:, 0], xy[:, 1], p[:, 2]), p[:, 2])
    # The preserved spiral becomes one rocky headland whose outer edge is
    # submerged inside the existing terrain extent, rather than an open wall.
    y = np.linspace(1400., 2600., 241)
    assert np.max(S.height(np.full_like(y, 3200.), y, 300.)) < -1.


def test_existing_road_and_quay_top_are_protected():
    x, y = np.meshgrid(np.linspace(-300., 1420., 79), [-125., -100., -90., 0.])
    base = 2.4+.04*(y+125.)
    # The quay's new submerged ground begins below its coping; its top is retained.
    mask = ~((x >= 420.) & (x <= 900.) & (y == -125.))
    np.testing.assert_array_equal(S.height(x, y, base)[mask], base[mask])
    np.testing.assert_array_equal(S.height(x, np.maximum(y, -124.), base), base)


def test_old_zero_height_country_aprons_are_submerged():
    y = np.linspace(3700., 7100., 90)
    for x in [-3200., -3100., 3100., 3200.]:
        h = S.height(np.full_like(y, x), y, np.zeros_like(y))
        assert np.max(h) < -.5
    x = np.linspace(-3200., 3200., 130)
    assert np.max(S.height(x, np.full_like(x, 7100.), 0.)) < -5.


def test_profile_has_dry_land_and_a_continuous_underwater_toe():
    for y in [800., 2400., 4600., 6000.]:
        x = np.linspace(2500., 3200., 1401)
        z = S.height(x, np.full_like(x, y), 180.)
        assert z.min() <= -15.
        assert z.max() > 30.
        assert np.count_nonzero((z > .2) & (z < 3.)) > 2
        assert np.max(np.abs(np.diff(z))) < 4.


def test_reference_bays_have_broad_walkable_sand_between_rocky_points():
    x = np.arange(2500., 3200., .25)
    for y in [4680., 5810.]:
        z = S.height(x, np.full_like(x, y), 80.)
        dry = (z > .2) & (z < 3.)
        assert np.count_nonzero(dry)*.25 >= 45.
        assert np.max(abs(np.gradient(z, .25)[dry])) < .20
    # The point between those bays has an actual elevated rock shelf.
    y = np.full_like(x, 5250.)
    distance, rock = S.field(x, y)
    assert rock[np.argmin(abs(distance))] > .9
    z = S.height(x, y, 80.)
    assert np.max(z[(distance > 25.) & (distance < 38.)]) > 10.


def test_country_export_has_no_sea_level_quads_and_faces_up():
    xs = np.array([2800., 3000., 3200.]); ys = np.array([4500., 4550.])
    vertices, faces = S.grid_mesh(xs, ys, np.zeros((2, 3)))
    p = np.asarray(vertices); f = np.asarray(faces)
    assert len(f) > 100
    assert not np.any(np.all(np.abs(p[f, 2]) < .001, axis=1))
    normals = np.cross(p[f[:, 1]]-p[f[:, 0]], p[f[:, 3]]-p[f[:, 0]])
    assert np.all(normals[:, 2] > 0.)
    assert np.max(np.abs(p[:, 2])) > 1.


def test_harbor_piers_and_canal_approach_remain_over_water():
    x, y = np.meshgrid(np.arange(480., 841., 60.), [-136., -160., -200.])
    assert np.max(S.height(x, y, 3.)) < -.2
    assert S.height(848., -145., 3.) < -1.


def test_spawn_beach_clears_the_existing_skate_pier_frontage():
    from skatepark.pier_site import ORIGIN, HALF_X, HALF_Y
    from skatepark.layout import ENTRANCE_X
    x = np.linspace(ORIGIN[0]-HALF_X, ORIGIN[0]+HALF_X, 171)
    y = np.full_like(x, ORIGIN[1]+HALF_Y)
    # The path's last ring joins this fixed deck. A raised beach here buries
    # the pier and makes its terrain-clearing, grade-limited path infeasible.
    assert np.max(S.height(x, y, 8.)) < ORIGIN[2]-.05
    # Keep the raised approach bench under the fixed deck run-in. Flattening
    # it to the country-bay profile made the unmodified path exceed 11% grade.
    entrance = S.height(ORIGIN[0]+ENTRANCE_X, ORIGIN[1]+HALF_Y, 8.)
    assert ORIGIN[2]-.5 < entrance < ORIGIN[2]-.05


def test_arrival_cove_has_a_thirty_metre_dry_sand_strip():
    y = np.arange(-220., -125., .25)
    z = S.height(np.full_like(y, 35.), y, 8.)
    assert 25. <= np.count_nonzero((z > .2) & (z < 3.))*.25 <= 35.


def test_shore_vegetation_clearance_and_palette_are_finite():
    x, y = np.meshgrid(np.linspace(-3200., 3200., 151), np.linspace(-300., 7100., 101))
    z = S.height(x, y, 200.)
    colour = S.colours(x, y, z, np.ones_like(z), [.055, .11, .035])
    assert colour.shape == (*x.shape, 3)
    assert np.isfinite(colour).all() and np.all((colour >= 0.) & (colour <= 1.))
    d, _ = S.field(x, y)
    assert not S.vegetation(x[d < 0.], y[d < 0.]).any()


def test_harbor_and_open_sea_partition_the_surface_without_an_overlap():
    vertices,faces=S.sea_mesh()
    p=np.asarray(vertices);f=np.asarray(faces)
    assert np.all(p[:,2]==0.)
    rectangles=[(*p[ids[0],:2],*p[ids[2],:2]) for ids in f]+[S.HARBOR_RECT]
    area=sum((x1-x0)*(y1-y0) for x0,y0,x1,y1 in rectangles)
    assert area==(48000.)**2
    for i,(x0,y0,x1,y1) in enumerate(rectangles):
        for a0,b0,a1,b1 in rectangles[i+1:]:
            assert max(0.,min(x1,a1)-max(x0,a0))*max(0.,min(y1,b1)-max(y0,b0))==0.


def test_beach_clearance_preserves_town_planting_and_the_separate_islet():
    rows=[[0.,-170.,2.,0.,1.],[600.,-112.,3.,0.,1.],[-150.,-530.,82.,0.,1.]]
    instances={'Tree_Maple_A':rows.copy(),'SW_Stand':rows.copy()}
    assert S.clear_vegetation(instances)==1
    assert instances['Tree_Maple_A']==rows[1:]
    assert instances['SW_Stand']==rows


def test_refined_country_vertices_match_the_public_ground_sampler(monkeypatch):
    from belmonte import terrain
    xs=np.array([2650.,2800.,3000.]);ys=np.array([4400.,4500.])
    z=np.array([[90.,230.,35.],[180.,80.,25.]])
    monkeypatch.setattr(terrain,'country_grid',lambda:(xs,ys,z))
    monkeypatch.setattr(terrain,'old_height',lambda x,y:np.zeros_like(x))
    vertices,_=S.grid_mesh(xs,ys,z)
    p=np.asarray(vertices)
    np.testing.assert_allclose(p[:,2],terrain.country_height(p[:,0],p[:,1]),atol=1e-10)


def test_city_and_main_coastal_rims_share_exported_edge_heights(monkeypatch):
    from hidamari import layout
    axis=np.linspace(-300.,300.,301);x,y=np.meshgrid(axis,axis)
    monkeypatch.setattr(layout,'H',S.height(x,y,8.+.02*y))
    monkeypatch.setattr(layout.street_height,'start',[300.,70.],raising=False)
    city_x=np.arange(300.,1421.,4.);city_y=np.arange(-300.,501.,4.)
    monkeypatch.setattr(layout,'terrain_axes',lambda:(city_x,city_y))
    ys=np.unique(np.r_[np.linspace(-300.,-125.,101),city_y[city_y<=-125.]])
    east=layout.coastal_backdrop_height(1420.,ys,-6.)
    np.testing.assert_allclose(east,np.interp(ys,city_y,layout.height(1420.,city_y)),atol=1e-12)
    west=layout.coastal_backdrop_height(-300.,ys,-6.)
    np.testing.assert_allclose(west,np.interp(ys,axis,layout.H[:,0]),atol=1e-12)
    # The internal x300 seam cannot attract exterior terrain, and the repair
    # ends below occupied streets and the inland railway's final earthworks.
    np.testing.assert_allclose(layout.coastal_backdrop_height(300.,-150.,3.),S.height(300.,-150.,3.))
    np.testing.assert_allclose(layout.coastal_backdrop_height(1440.,460.,32.),32.)
    assert abs(float(layout.coastal_backdrop_height(1420.001,-135.,-6.))-float(np.interp(-135.,city_y,layout.height(1420.,city_y))))<.1

    # Refinement also inserts vertices between the edge knots. Their heights
    # stay on the same straight fine-edge segments after export.
    coarse_y=np.unique(np.r_[ys,city_y[(city_y>=-300.)&(city_y<=-125.)]])
    vertices,_=S.grid_mesh([1420.,1490.],coarse_y,np.full((len(coarse_y),2),-6.),shape=layout.coastal_backdrop_height)
    p=np.asarray(vertices);edge=p[np.isclose(p[:,0],1420.)]
    np.testing.assert_allclose(edge[:,2],np.interp(edge[:,1],city_y,layout.height(1420.,city_y)),atol=1e-12)


def test_country_backshore_reaches_high_ground_without_a_short_wall():
    # A 225 m countryside compressed into the old 260 m strip produced the
    # rejected native wall. Exercise that actual height scale across both bays.
    x = np.arange(1500., 3200., .5)
    for y in [4680., 5810.]:
        d, rock = S.field(x, y)
        base = 225.*S.smooth((3000.-x)/750.)
        z = S.height(x, y, base)
        backshore = (d > 100.) & (d < 600.)
        assert np.max(abs(np.gradient(z, .5)[backshore])) < .55
        assert np.max(z[(d > 100.) & (d < 220.)]) < 30.
        np.testing.assert_array_equal(z[d >= S.reach(x,y)], base[d >= S.reach(x,y)])
    assert S.reach(35., -150.) == 260.


def test_wider_country_refinement_matches_ground_beyond_old_coast_band(monkeypatch):
    from belmonte import terrain
    xs = np.array([1850., 2050., 2250.]); ys = np.array([4500., 4550.])
    z = np.array([[200., 230., 180.], [190., 210., 165.]])
    monkeypatch.setattr(terrain, 'country_grid', lambda: (xs, ys, z))
    vertices, faces = S.grid_mesh(xs, ys, z)
    p = np.asarray(vertices)
    assert len(faces) > 100
    np.testing.assert_allclose(p[:,2], terrain.country_height(p[:,0],p[:,1]), atol=1e-10)
