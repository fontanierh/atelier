"""Regressions for the continuous coast, occupied ground and exported waterline."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
import shorelines as S  # noqa: E402


def test_planting_samples_the_asymmetric_refined_faces_instead_of_the_curved_formula(monkeypatch):
    from belmonte.source import Surface
    monkeypatch.setattr(S,'field',lambda x,y:(np.zeros_like(x),np.zeros_like(x)))
    monkeypatch.setattr(S,'reach',lambda x,y:np.full_like(x,1000.))
    xs,ys=np.array([0.,10.]),np.array([0.,14.])
    z=np.array([[1.,2.],[3.,8.]])
    shape=lambda x,y,base:base+.2*x*x-.07*y*y
    vertices,faces=S.grid_mesh(xs,ys,z,shape=shape)
    triangles=np.asarray(vertices)[np.asarray([(p[0],p[k],p[k+1]) for p in faces for k in range(1,len(p)-1)])]
    surface=Surface(triangles)
    x,y=np.array([2.5,7.,3.,9.]),np.array([3.5,4.,12.,13.])
    sampled=S.sample_grid_mesh(xs,ys,z,x,y,shape=shape)
    np.testing.assert_allclose(sampled,surface.height(x,y),rtol=0,atol=1.e-10)
    u,v=x/10.,y/14.
    base=np.where(u>=v,1.+u+v*6.,1.+u*5.+v*2.)
    assert np.max(abs(sampled-shape(x,y,base)))>.2
    import pytest
    with pytest.raises(ValueError,match='outside'):
        S.sample_grid_mesh(xs,ys,z,[11.],[4.],shape=shape)


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


def test_entire_occupied_belmonte_footprint_keeps_its_ground():
    from belmonte.layout import BOUNDS
    x, y = np.meshgrid(np.linspace(BOUNDS[0], BOUNDS[2], 41),
                       np.linspace(BOUNDS[1], BOUNDS[3], 41))
    base = 210.+.01*(x-550.)+.005*(y-4500.)
    np.testing.assert_array_equal(S.height(x, y, base), base)


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
        # Include the full country transition, whose low foreground now
        # extends farther inland than the former narrow cliff strip.
        x = np.linspace(1500., 3200., 3401)
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
    p = np.asarray(vertices)
    f = np.array([(face[0],face[k],face[k+1]) for face in faces for k in range(1,len(face)-1)])
    assert len(f) > 100
    assert not np.any(np.all(np.abs(p[f, 2]) < .001, axis=1))
    normals = np.cross(p[f[:, 1]]-p[f[:, 0]], p[f[:, 2]]-p[f[:, 0]])
    assert np.all(normals[:, 2] > 0.)
    assert np.max(np.abs(p[:, 2])) > 1.


def test_harbor_piers_and_canal_approach_remain_over_water():
    x, y = np.meshgrid(np.arange(480., 841., 60.), [-136., -160., -200.])
    assert np.max(S.height(x, y, 3.)) < -.2
    assert S.height(848., -145., 3.) < -1.


def test_west_harbor_approach_has_no_extruded_beach_tip_ridge():
    # The former seaward control at x=380 made this floor rise toward a cusp
    # before falling into the basin. Grazing rays jumped over that ridge,
    # producing a straight shallow/deep boundary despite continuous meshes.
    x = np.linspace(300., 420., 481)
    for y in [-200., -210.]:
        z = S.height(x, np.full_like(x, y), -8.)
        assert np.max(np.diff(z)) < 0.
        assert np.max(z) < -5.   # The approach remains clear beneath boats.
    x, y = np.meshgrid(np.arange(280., 440.01, .5), np.arange(-260., -149.99, .5))
    z = S.height(x, y, -8.)
    assert np.isfinite(z).all()
    assert np.max(np.abs(np.diff(z, axis=0))/.5) < .6
    assert np.max(np.abs(np.diff(z, axis=1))/.5) < .6


def test_harbor_basin_and_arrival_edge_keep_their_established_depths():
    # Witnesses outside the retracted x=300..420 corner retain genuine basin
    # relief, rather than flattening all bathymetry to hide depth-driven color.
    x = np.array([300., 420., 600., 900.])
    y = np.array([-210., -190., -190., -210.])
    np.testing.assert_allclose(S.height(x, y, np.full_like(x, -8.)),
                               [-9.89242375370834, -11.928572415293704,
                                -11.880000000027236, -27.874896326561235], atol=1e-10)


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
    monkeypatch.setattr(terrain, 'old_height', lambda x,y: np.zeros_like(x))
    vertices, faces = S.grid_mesh(xs, ys, z)
    p = np.asarray(vertices)
    assert len(faces) > 100
    np.testing.assert_allclose(p[:,2], terrain.country_height(p[:,0],p[:,1]), atol=1e-10)


def eastern_waterline(y):
    lo, hi = np.full_like(np.asarray(y, float), 2500.), np.full_like(np.asarray(y, float), 3200.)
    for _ in range(32):
        middle = (lo+hi)/2.
        distance, _ = S.field(middle, y)
        lo, hi = np.where(distance > 0., middle, lo), np.where(distance <= 0., middle, hi)
    return (lo+hi)/2.


def test_country_foreground_stays_low_and_breaks_into_knolls():
    # The rejected native ground reached about 100 m just 500 m behind the
    # sand. A low foreground must survive the actual 225 m plateau scale.
    for y in [4680., 5810.]:
        d = np.arange(150., 501., 5.)
        x = eastern_waterline(y)-d
        base = 225.*S.smooth((3000.-x)/750.)
        z = S.height(x, y, base)
        assert np.max(z[d <= 300.]) < 38.
        assert z[-1] < 70.
    # The named valley mouth is intentionally quiet ground. Its two wooded
    # ridge shoulders must rise independently on either side, rather than
    # relying on tiny ripples within the floor to imply an entire landscape.
    y = np.array([4310., 4670., 5080.])
    x = eastern_waterline(y)-350.
    z = S.height(x, y, 225.)
    assert z[1] < 25.
    assert np.min(z[[0, 2]]) > 45.
    assert np.min(z[[0, 2]])-z[1] > 30.


def test_eastern_rock_wall_is_interrupted_by_physical_pocket_beaches():
    for y in [560., 1050., 3000.]:
        waterline = float(eastern_waterline(y))
        x = np.arange(waterline-90., waterline+30., .25)
        z = S.height(x, y, 180.)
        _, rock = S.field(waterline, y)
        assert rock < .01
        assert np.count_nonzero((z > .2) & (z < 3.))*.25 >= 25.
    centre = float(eastern_waterline(560.))
    banks = np.mean(eastern_waterline(np.array([400., 720.])))
    assert centre < banks-100.
    for y in [400., 720.]:
        _, rock = S.field(eastern_waterline(y), y)
        assert rock > .85


def test_local_landforms_preserve_complete_interpolated_rail_clearance():
    import json
    p = np.array([[r['x'], r['y']] for r in json.loads(S.RAIL_LINE.read_text())['samples']])
    q = np.concatenate([p[:-1]*(1.-t)+p[1:]*t for t in [0., .25, .5, .75, 1.]])
    angle = np.arange(16)*np.pi/8.
    x = (q[:,0,None]+20.*np.cos(angle)).ravel()
    y = (q[:,1,None]+20.*np.sin(angle)).ravel()
    base = 225.+.001*x+.002*y
    np.testing.assert_array_equal(S.landforms(x,y,base),base)
    np.testing.assert_array_equal(S.height(x,y,base),base)


def test_local_landforms_keep_waterline_seabed_and_outside_region_unchanged():
    x,y = np.meshgrid(np.arange(-3200.,3401.,40.),np.arange(-300.,7101.,40.))
    d,_ = S.field(x,y)
    before = .01*x+.02*y
    after = S.landforms(x,y,before)
    country,headland = S.landform_regions(x,y)
    fixed = (d <= 0.) | ((country == 0.) & (headland == 0.)) | (d >= S.reach(x,y))
    np.testing.assert_array_equal(after[fixed],before[fixed])
    assert S.reach(-2600.,4700.) == S._profile_reach(-2600.,4700.)
    assert S.reach(35.,-150.) == 260.


def test_eastern_crags_have_sloping_crests_and_a_recessed_gully():
    # The formerly broad roofs now peak at different x/y positions.
    x=np.array([2870.,2870.,2912.,2912.]);y=np.array([224.,280.,408.,470.])
    z=S.height(x,y,180.)
    assert min(z[0],z[2])>45.
    assert S.height(2910.,330.,180.)<12.
    assert z[0]-z[1]>15. and z[2]-z[3]>15.


def test_expanded_country_grid_refines_the_new_inland_landform(monkeypatch):
    from belmonte import terrain
    xs=np.array([1600.,1750.,1900.]);ys=np.array([4500.,4550.])
    base=np.array([[225.,210.,200.],[235.,220.,205.]])
    monkeypatch.setattr(terrain,'country_grid',lambda:(xs,ys,base))
    monkeypatch.setattr(terrain,'old_height',lambda x,y:np.zeros_like(x))
    vertices,faces=S.grid_mesh(xs,ys,base)
    p=np.asarray(vertices)
    assert len(faces)>100
    np.testing.assert_allclose(p[:,2],terrain.country_height(p[:,0],p[:,1]),atol=1e-10)


def test_apron_outer_east_edge_uses_the_same_shaped_country_height(monkeypatch):
    from belmonte import terrain,layout,source
    x0,y0,x1,y1=layout.BOUNDS
    vertices=np.array([[x0,y0,210.],[x1,y0,210.],[x1,y1,210.],[x0,y1,210.]])-layout.ORIGIN
    class FixedTown:
        faces=vertices[[[0,1,2],[0,2,3]]]
        def height(self,x,y):
            return np.full_like(x,210.-layout.ORIGIN[2])
    monkeypatch.setattr(source,'terrain',lambda *, natural=False:FixedTown())
    monkeypatch.setattr(terrain,'country_grid',lambda:(np.array([-3200.,3200.]),np.array([3200.,7000.]),np.full((2,2),225.)))
    monkeypatch.setattr(terrain,'old_height',lambda x,y:np.full_like(x,225.))
    monkeypatch.setattr(terrain.H,'north_height',lambda x,y,**kw:S.height(x,y,np.full_like(x,225.)))
    mesh,_=terrain.collar();p=np.asarray(mesh.p)+layout.ORIGIN
    outer=np.isclose(p[:,0],terrain.OUTER[2])
    assert outer.any()
    np.testing.assert_allclose(p[outer,2],terrain.country_height(p[outer,0],p[outer,1]),atol=1e-10)
    inner=np.isclose(p[:,0],x1)&(p[:,1]>=y0)&(p[:,1]<=y1)
    np.testing.assert_allclose(p[inner,2],210.,atol=1e-10)


def test_new_rocky_toe_does_not_keep_an_old_front_ridge():
    # This shoulder has its new wedge farther inland. Starting the new blend
    # after the old cliff had risen left a narrow old wall in front of it.
    d=np.arange(0.,46.,.25)
    for y in [140.,720.]:
        x=eastern_waterline(y)-d
        z=S.height(x,y,180.)
        assert np.max(z)<4.1
        assert np.min(np.diff(z))>=-1e-7


def test_asymmetric_refinement_preserves_parent_saddle_inside_every_triangle():
    from belmonte.terrain import grid_height
    xs=np.array([1850.,1917.]);ys=np.array([4100.,4150.])
    z=np.array([[0.,16.],[7.,-9.]])
    vertices,faces=S.grid_mesh(xs,ys,z,shape=lambda x,y,base:base)
    p=np.asarray(vertices)
    triangles=np.array([(face[0],face[k],face[k+1]) for face in faces for k in range(1,len(face)-1)])
    assert len(triangles)>200  # 12x9 children, including diagonal intersections
    for weights in [[.2,.3,.5],[.61,.31,.08]]:
        q=np.einsum('tvc,v->tc',p[triangles],weights)
        np.testing.assert_allclose(q[:,2],grid_height(xs,ys,z,q[:,0],q[:,1]),atol=2e-11)
    normals=np.cross(p[triangles[:,1]]-p[triangles[:,0]],p[triangles[:,2]]-p[triangles[:,0]])
    assert np.all(normals[:,2]>0.)


def test_initial_inserted_knots_keep_original_parent_breaklines(monkeypatch):
    from belmonte.terrain import grid_height
    from belmonte.source import Surface
    original_x=np.array([-1044.2105263158,-976.8421052632])
    original_y=np.array([437.8947368421,505.2631578947])
    original_z=np.array([[0.,0.],[0.,100.]])
    xs=np.array([original_x[0],-1015.,original_x[1]])
    ys=np.array([original_y[0],470.,500.,original_y[1]])
    xx,yy=np.meshgrid(xs,ys)
    z=grid_height(original_x,original_y,original_z,xx,yy)
    parents=(original_x,original_y,original_z)
    monkeypatch.setattr(S,'field',lambda x,y:(np.zeros_like(x),np.zeros_like(x)))
    for step in [6.,1000.]:
        vertices,faces=S.grid_mesh(xs,ys,z,step=step,shape=lambda x,y,base:base,parents=parents)
        p=np.asarray(vertices);tri=np.array([(f[0],f[k],f[k+1]) for f in faces for k in range(1,len(f)-1)])
        assert (np.cross(p[tri[:,1]]-p[tri[:,0]],p[tri[:,2]]-p[tri[:,0]])[:,2]>0.).all()
        for weights in [[.21,.37,.42],[.61,.31,.08]]:
            q=np.einsum('tvc,v->tc',p[tri],weights)
            np.testing.assert_allclose(q[:,2],grid_height(*parents,q[:,0],q[:,1]),atol=2e-10)
        qx,qy=np.array([-1003.7894736842,-982.1052631579]),np.array([501.3157894737,500.])
        expected=grid_height(*parents,qx,qy)
        np.testing.assert_allclose(Surface(p[tri]).height(qx,qy),expected,atol=2e-10)
        np.testing.assert_allclose(S.sample_grid_mesh(xs,ys,z,qx,qy,step=step,shape=lambda x,y,base:base,parents=parents),expected,atol=2e-10)


def test_rail_lattice_edges_conform_to_the_neighboring_coastal_grid(monkeypatch):
    from belmonte.source import Surface
    monkeypatch.setattr(S,'field',lambda x,y:(np.zeros_like(x),np.zeros_like(x)))
    xs,ys=np.array([0.,100.,170.]),np.array([0.,80.,140.])
    z=np.array([[0.,4.,7.],[3.,12.,8.],[5.,10.,2.]])
    shape=lambda x,y,b:b+.001*y*y+.0003*x*x
    parents=(xs,ys,z);refinement={(0,0):7}
    v,f=S.grid_mesh(xs,ys,z,step=40.,shape=shape,parents=parents,parent_refinement=refinement)
    p=np.asarray(v);tri=np.array([(f[0],f[k],f[k+1]) for f in f for k in range(1,len(f)-1)])
    assert (np.cross(p[tri[:,1]]-p[tri[:,0]],p[tri[:,2]]-p[tri[:,0]])[:,2]>1e-10).all()
    for axis,value,lo,hi in [(0,100.,0.,80.),(1,80.,0.,100.)]:
        left=p[tri][np.max(p[tri][:,:,axis],axis=1)<=value+1e-9]
        right=p[tri][np.min(p[tri][:,:,axis],axis=1)>=value-1e-9]
        t=np.linspace(lo+.01,hi-.01,123);q=np.full_like(t,value)
        a,b=(q,t) if axis==0 else (t,q)
        np.testing.assert_allclose(Surface(left).height(a,b),Surface(right).height(a,b),atol=1e-10)
    x,y=np.array([21.,99.,101.,55.]),np.array([15.,51.,51.,81.])
    np.testing.assert_allclose(S.sample_grid_mesh(xs,ys,z,x,y,step=40.,shape=shape,parents=parents,parent_refinement=refinement),Surface(p[tri]).height(x,y),atol=1e-10)


def test_original_rail_planner_prevents_the_observed_open_track_burial(monkeypatch):
    import farhills_grid as F
    from train import earthworks as E
    from belmonte.source import Surface
    # Actual original parent cell around committed s4780. Other coastal faces
    # reproduce the global density statistic that buried this open-track point.
    xs=np.array([2458.9473684210525,2526.315789473684])
    ys=np.array([2324.210526315789,2391.578947368421])
    z=np.array([[241.8931884765625,241.39047241210938],[238.57815551757812,237.49505615234375]])
    monkeypatch.setattr(F,'source_grid',lambda **kwargs:(xs,ys,z))
    monkeypatch.setattr(S,'field',lambda x,y:(np.full_like(x,2000.),np.zeros_like(x)))
    F.rail_refinement.cache_clear()
    try:refinement=F.rail_refinement()
    finally:F.rail_refinement.cache_clear()
    assert refinement[(0,0)]>=20
    results=[]
    for density in [None,refinement]:
        v,f=S.grid_mesh(xs,ys,z,shape=lambda x,y,b:b,parents=(xs,ys,z),parent_refinement=density)
        k=len(v);v.extend([(1250.,300.,35.),(1272.,300.,35.),(1250.,322.,35.)])
        f.extend([(k,k+1,k+2)]*40)
        v,f,_=E.polygons(v,f,4.)
        results.append(float(Surface(np.asarray(v)[np.asarray(f)]).height(2487.02,2381.92)))
    rail=213.87
    assert results[0]>rail+.5
    assert results[1]<rail-.5


def test_country_landform_starts_after_the_existing_south_join():
    from belmonte import layout
    x=np.linspace(1575.,layout.BOUNDS[2]+layout.APRON,121);y=np.full_like(x,layout.SOUTH_JOIN)
    base=np.full_like(x,225.)
    np.testing.assert_array_equal(S.landforms(x,y,base),base)


def test_collar_deformation_keeps_actual_rail_support_triangles(monkeypatch):
    from belmonte import terrain,layout,source
    x0,y0,x1,y1=layout.BOUNDS
    vertices=np.array([[x0,y0,210.],[x1,y0,210.],[x1,y1,210.],[x0,y1,210.]])-layout.ORIGIN
    class Town:
        faces=vertices[[[0,1,2],[0,2,3]]]
        def height(self,x,y):return np.full_like(x,210.-layout.ORIGIN[2])
    monkeypatch.setattr(source,'terrain',lambda *, natural=False:Town())
    monkeypatch.setattr(terrain,'country_grid',lambda:(np.array([-3200.,3200.]),np.array([3200.,7000.]),np.full((2,2),225.)))
    monkeypatch.setattr(terrain,'old_height',lambda x,y:np.full_like(x,225.))
    monkeypatch.setattr(terrain.H,'north_height',lambda x,y,**kw:S.profile_height(x,y,np.full_like(x,225.)))
    mesh,_=terrain.collar()
    changed=source.Surface(np.array(mesh.p)[np.array(mesh.i).reshape(-1,3)])
    monkeypatch.setattr(S,'landforms',lambda x,y,z:z)
    baseline,_=terrain.collar()
    original=source.Surface(np.array(baseline.p)[np.array(baseline.i).reshape(-1,3)])
    # The actual town approach at s7090 lies just outside the occupied east rim.
    centre=np.array([1576.5864282864918,4335.5548417948075])
    angles=np.linspace(0.,2.*np.pi,32,endpoint=False)
    q=np.vstack([centre+r*np.c_[np.cos(angles),np.sin(angles)] for r in [0.,10.,20.]])
    q=q[q[:,0]>x1+.001]
    x,y=q[:,0]-layout.ORIGIN[0],q[:,1]-layout.ORIGIN[1]
    assert np.isfinite(changed.height(x,y)).all()
    np.testing.assert_array_equal(changed.height(x,y),original.height(x,y))


def test_complete_seam_stitches_coastal_knots_without_a_railway(monkeypatch):
    from hippodrome.build import Mesh
    from train import earthworks
    from belmonte.source import Surface
    monkeypatch.setattr(earthworks,'line',lambda:None)
    left,right=Mesh(),Mesh()
    left.quad([-10.,0.,0.],[0.,0.,0.],[0.,10.,0.],[-10.,10.,0.])
    right.quad([0.,0.,0.],[10.,0.,0.],[10.,5.,1.],[0.,5.,1.])
    right.quad([0.,5.,1.],[10.,5.,1.],[10.,10.,0.],[0.,10.,0.])
    assert earthworks.stitch([left,right],[0.,0.,0.],[(0,0.)])==0
    assert earthworks.stitch([left,right],[0.,0.,0.],[(0,0.)],whole_seam=True)>0
    a,b=[Surface(np.array(m.p)[np.array(m.i).reshape(-1,3)]) for m in [left,right]]
    y=np.linspace(0.,10.,101);x=np.zeros_like(y)
    np.testing.assert_allclose(a.height(x,y),b.height(x,y),atol=1e-12)


def test_rock_shoulder_has_unequal_crests_recessed_face_and_connected_toe():
    c=dict(x=0.,y=0.,rx=100.,ry=70.,angle=0.,height=50.)
    # The old affine roof rose monotonically into another broad flat slab.
    u=np.array([-.8,-.2,0.,.25,.8])
    z=S.wedge(u*100.,np.full_like(u,-.18*70.),c)
    assert z[3]>max(z[0],z[-1])+25.
    assert z[1]>z[2]+10.  # a distinct saddle between unequal crests
    x=np.linspace(-105.,105.,141);y=np.full_like(x,.30*70.)
    face=S.wedge(x,y,c)
    assert np.min(face)>0.  # the recessed face retains connected lower support
    recess=float(S.wedge(-.166*100.,.30*70.,c))
    assert recess<min(float(S.wedge(-.4*100.,.30*70.,c)),float(S.wedge(.12*100.,.30*70.,c)))-15.
    assert S.wedge(130.,0.,c)==0.  # bounded footprint
