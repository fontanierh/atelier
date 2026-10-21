import numpy as np
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
from gondola.clearance import riding_clearance


def check(triangles,profile=None,**kwargs):
    if profile is None:
        profile = np.array([[0,30],[5,30],[10,30]])
    return riding_clearance(np.asarray(triangles,float),[0,0],[1,0],profile,
                            lateral=1,half_length=.5,drop=0,**kwargs)


def test_vertical_face_is_an_obstacle_without_any_nonvertical_ground_hit():
    tri = [[[5,-.5,0],[5,.5,0],[5,0,16]]]
    result = check(tri)
    assert result['triangles_tested']==1
    assert result['minimum_m']==pytest.approx(14)


def test_large_triangle_crossing_strip_is_kept_when_all_vertices_are_outside():
    tri = [[[-10,-10,16],[20,-10,16],[5,20,16]]]
    assert check(tri)['minimum_m']==pytest.approx(14)


def test_high_vertex_outside_corridor_is_clipped_at_actual_edge_height():
    tri = [[[4,0,0],[6,0,0],[5,10,100]]]
    assert check(tri)['minimum_m']==pytest.approx(20)


def test_cabin_length_inflates_obstacle_interval_to_include_low_rope_knot():
    tri = [[[5.4,-.1,10],[5.5,.1,10],[5.6,-.1,10]]]
    p = np.array([[0,30],[5,20],[10,30]])
    assert check(tri,p)['minimum_m']==pytest.approx(10)


def test_bbox_overlap_does_not_invent_triangle_contact_outside_strip():
    tri = [[[9,20,100],[20,0,100],[20,20,100]]]
    assert check(tri)['triangles_tested']==0


def test_sag_knot_inside_triangle_interval_is_used_instead_of_only_endpoints():
    tri = [[[2,-.5,12],[8,-.5,12],[5,.5,12]]]
    p = np.array([[0,40],[5,25],[10,40]])
    assert check(tri,p)['minimum_m']==pytest.approx(13)



def test_l3_committed_fit_clears_the_rim_approach_crest():
    """Datums/crest from the failed final-owner probe; placement comes from source."""
    from gondola.line import centre_profile
    from gondola.validation import PARAMETERS
    from regions.gondola.layout import LINES,STATIONS
    line=next(row for row in LINES if row['id']=='L3')
    length=np.linalg.norm(np.array(STATIONS['floor_rim']['mouth'])-STATIONS['floor']['mouth'])
    d=PARAMETERS.derived(PARAMETERS.DEFAULTS)
    crest=np.array([[[183.37,-4.3,702.361],[189.97,4.3,702.361],[189.97,-4.3,702.361]]])
    def clearance(height,lift):
        profile=centre_profile([(.6,655.1621877479114,False),
                                (line['towers'][0][0],660.5034018391225,True),
                                (line['towers'][1][0],687.9759026165713+height,True),
                                (length-.6,693.5030226726246+lift+d['rope_height_above_platform'],False)])
        return riding_clearance(crest,[0,0],[1,0],profile,lateral=4.3,half_length=1.15,
                                drop=d['grip_to_floor']+PARAMETERS.DEFAULTS['cabin_floor_depth'])['minimum_m']
    assert clearance(20.,0.)<0
    assert clearance(line['towers'][-1][1],STATIONS['floor_rim']['platform_lift_m'])>.03
