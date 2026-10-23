"""Rock shading and crown edits stay on the owned exposed headland faces."""
import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
import coastal_surface as C  # noqa: E402
import coastal_dressing as D  # noqa: E402


def test_observed_cliff_face_is_selected_but_its_meadow_and_beach_are_not():
    # Actual native06 face centroid; changing just its slope or height must
    # leave smooth crowns and sand on their existing material/normal path.
    x,y=2893.099,160.935
    assert C.rock_faces(x,y,21.338,.725)
    assert not C.rock_faces(x,y,21.338,.95)
    assert not C.rock_faces(x,y,1.5,.725)
    assert not C.rock_faces(x,y,-2.,.725)


def test_meadow_caps_keep_upper_shoulders_green_and_steep_faces_stone():
    import shorelines as S
    assert S.meadow_caps(2900.,440.,45.,.9) > .99
    assert S.meadow_caps(2900.,440.,45.,.3) == 0.
    assert S.meadow_caps(2900.,440.,1.5,.9) == 0.
    assert not C.rock_faces(2950.,250.,50.,.8)
    # The unchanged observed steep foreground face retains its exact stone path.
    assert C.rock_faces(2893.099,160.935,21.338,.725)
    x=np.array([1231.,550.,-150.,2850.]);y=np.array([301.8,4500.,-175.,2000.])
    np.testing.assert_array_equal(S.meadow_caps(x,y,50.,.95),np.zeros(4))
    for nz in [.579999,.580001]:
        assert S.meadow_caps(2900.,440.,45.,nz) < 1.e-8


def test_meadow_caps_leave_the_entire_west_country_palette_unchanged():
    import shorelines as S
    x,y=np.meshgrid(np.linspace(-3190.,-2200.,100),np.linspace(3500.,6500.,100))
    assert not S.meadow_caps(x,y,50.,.95).any()
    # With no cap the complete paint path retains its former wet/stone/sand mix.
    z=np.full_like(x,50.);nz=np.full_like(x,.95)
    oldcap=S.meadow_caps
    try:
        original=S.paint(x,y,z,nz)
        S.meadow_caps=lambda *args:np.zeros_like(x)
        without=S.paint(x,y,z,nz)
    finally:S.meadow_caps=oldcap
    for a,b in zip(original,without):np.testing.assert_array_equal(a,b)


def test_shared_backdrop_grid_keeps_the_original_export_construction(tmp_path,monkeypatch):
    from hidamari import forest_backdrop as F,layout as H
    from belmonte import terrain as B
    axis=np.linspace(-3200.,3200.,96);xx,yy=np.meshgrid(axis,axis)
    raw=(.01*xx+.02*yy).astype('f4');city=raw.astype(float)+3.
    monkeypatch.setattr(yori,'OUT',tmp_path);np.save(tmp_path/'farhills.npy',raw)
    monkeypatch.setattr(H,'backdrop_grid',lambda:city.copy())
    monkeypatch.setattr(H,'terrain_axes',lambda:([300.,1420.],[-300.,-180.,-100.,500.]))
    monkeypatch.setattr(H,'north_height',lambda x,y,carved=False:np.full_like(x,-40.))
    monkeypatch.setattr(F.mountains,'contains',lambda x,y:(x<0.)&(y>0.))
    monkeypatch.setattr(F.park_trail,'in_approach',lambda x,y:np.zeros_like(x,dtype=bool))
    fine_y=np.unique(np.r_[np.linspace(-300.,300.,301),H.terrain_axes()[1]])
    fine_y=fine_y[(fine_y>=-300.)&(fine_y<=-100.)]
    xs=np.unique(np.r_[axis,-300.,300.,1420.]);ys=np.unique(np.r_[axis,fine_y,-300.,300.,500.])
    qx,qy=np.meshgrid(xs,ys)
    for enabled in [False,True]:
        expected=city.copy() if enabled else raw.copy()
        if enabled:
            mask=F.mountains.contains(xx,yy)|F.park_trail.in_approach(xx,yy)
            expected[mask]=np.minimum(expected[mask],H.north_height(xx,yy,carved=False)[mask]-25.)
            expected=B.old_backdrop(expected,xx,yy)
        actual=F.mesh_grid(301,city=enabled)
        for a,b in zip(actual,[xs,ys,B.grid_height(axis,axis,expected,qx,qy)]):
            np.testing.assert_array_equal(a,b)


def test_other_coasts_town_and_rail_cover_never_get_the_headland_slot():
    x=np.array([2850.,1231.,550.,-150.,2900.,-2900.])
    y=np.array([2000.,301.8,4500.,-175.,5000.,5000.])
    assert not C.rock_faces(x,y,np.full_like(x,30.),np.full_like(x,.3)).any()
    assert not C.crown_zone(x,y,np.full_like(x,30.)).any()


def test_rock_face_palette_is_finite_and_warm_without_changing_geometry():
    x,y,z=np.array([2893.099,2912.]),np.array([160.935,408.]),np.array([21.338,40.])
    before=[v.copy() for v in (x,y,z)]
    colours=C.face_colour(x,y,z,np.array([.725,.4]))
    assert colours.shape==(2,3) and np.isfinite(colours).all()
    assert ((colours>=0.)&(colours<=1.)).all()
    assert (colours[:,0]>colours[:,2]).all()
    for actual,original in zip((x,y,z),before):np.testing.assert_array_equal(actual,original)


def test_coastal_crown_postfilter_preserves_all_outside_transforms_and_other_objects():
    rows={'Tree_Maple_A':[[2923.85,248.81,32.26,310.6,2.11],
                          [2100.,4800.,40.,72.,2.11],
                          [1231.,301.8,32.,25.,2.]],
          'SW_Boulder_A':[[2923.85,248.81,32.26,310.6,10.]],
          'Bush_Ochre_A':[[2923.85,248.81,32.26,310.6,1.5]]}
    original=copy.deepcopy(rows)
    D.shape_crowns(rows)
    assert rows['Tree_Maple_A'][-2:]==original['Tree_Maple_A'][-2:]
    assert rows['SW_Boulder_A']==original['SW_Boulder_A']
    assert rows['Bush_Ochre_A']==original['Bush_Ochre_A']
    for row in rows['Tree_Maple_A'][:-2]:
        assert row[:4]==original['Tree_Maple_A'][0][:4] and row[4]<1.3


def test_city_forest_leaves_steep_observed_rock_clear_and_protected_ground_unchanged():
    # Native06 ray850/500: actual exposed face normal.z=.675. The same
    # decision must not affect occupied rail ground, another coast, or dry sand.
    x=np.array([2952.841,1231.,2900.,2952.841])
    y=np.array([467.498,301.8,5000.,467.498])
    z=np.array([20.51,32.,40.,1.5])
    keep,resize=C.forest_crowns(x,y,z,np.array([1.09,1.09,1.09,1.09]))
    np.testing.assert_array_equal(keep,[False,True,True,True])
    np.testing.assert_array_equal(resize[1:],[1.,1.,1.])


def test_rock_texture_identity_and_linear_normalization_match_committed_source():
    from PIL import Image
    path=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('shoreline_rock_look',path/'unreal/Scripts/coast_rock_look.py')
    look=importlib.util.module_from_spec(spec);spec.loader.exec_module(look)
    texture=path/'assets'/look.TEXTURE
    assert hashlib.sha256(texture.read_bytes()).hexdigest()==look.TEXTURE_SHA256
    with Image.open(texture) as image:srgb=np.asarray(image.convert('RGB'),float)/255.
    linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
    measured=float(linear.mean(axis=(0,1))@np.array([.2126,.7152,.0722]))
    assert abs(measured-look.LINEAR_LUMINANCE)<1e-10


def test_real_recipe_tracks_surface_selection_for_export_and_owned_planting(tmp_path):
    from atelier import build
    recipe=build.load_recipe('yorimichi')
    ctx=SimpleNamespace(game='yorimichi',out=tmp_path,uproject=tmp_path/'Yorimichi.uproject')
    steps={s.name:s for s in recipe.steps(ctx)}
    helper=recipe.WORLD/'coastal_surface.py'
    for name in ['world.layout','world.farhills','world.hidamari.layout_data']:
        assert helper in steps[name].inputs,name
    assert recipe.SCRIPTS/'forest_ground.py' in steps['unreal.island'].inputs
    assert recipe.SCRIPTS/'import_island_world.py' in steps['unreal.island'].inputs
    assert recipe.SCRIPTS/'coast_rock_look.py' in steps['unreal.island'].inputs
    assert recipe.ASSETS/'environment/textures/volcanic-rock.jpg' in steps['unreal.island'].inputs
