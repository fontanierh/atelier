"""Analytic geometry fixtures for the standalone park comparison harness."""
import argparse
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from park_audit_geometry import BVH, closest, pairs, projected_overlap
from audit_craterpark import MeshSet, distance_report, overlap_report, topology_report, look_report, sample_faces, main


def options(**kwargs):
    values = dict(box=None, max_samples=0, max_pairs=0, tolerance=.01, plane_tolerance=.005,
                  angle_tolerance=.5, weld=1e-5, sliver_quality=.001, look_match_tolerance=.02)
    values.update(kwargs)
    return argparse.Namespace(**values)


def write_mesh(root, name, triangles, **attrs):
    root.mkdir(parents=True, exist_ok=True)
    triangles = np.asarray(triangles, 'f8').reshape(-1, 3, 3)
    np.savez(root/(name+'.npz'), positions=triangles.reshape(-1,3),
             triangles=np.arange(triangles.size//3).reshape(-1,3), **attrs)


UP = np.array([[0.,0.,0.], [0.,0.,1.], [1.,0.,0.]])


def test_closest_known_regions_and_degenerate():
    p = np.array([[.2,2,.2], [-1,0,0], [.8,0,.8]])
    d, q, w = closest(p, UP)
    np.testing.assert_allclose(d, [4,1,.18])
    np.testing.assert_allclose(q, [[.2,0,.2],[0,0,0],[.5,0,.5]])
    np.testing.assert_allclose(w.sum(axis=1), 1)
    d, q, _ = closest(np.array([2,1,0]), np.array([[0,0,0],[1,0,0],[1,0,0]]))
    assert d == 2
    np.testing.assert_allclose(q, [1,0,0])


def test_bvh_matches_exhaustive_nearest():
    rng = np.random.default_rng(123)
    t = rng.normal(size=(137,3,3))
    p = rng.normal(size=(101,3))*3
    d, f, w = BVH(t, leaf=5).nearest(p, chunk=13)
    exhaustive, _, _ = closest(p[:,None], t[None])
    np.testing.assert_allclose(d*d, exhaustive.min(axis=1), atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(p-np.sum(t[f]*w[:,:,None],axis=1),axis=1), d)


def test_empty_target_is_unmatched():
    d, f, _ = BVH(np.empty((0,3,3))).nearest(np.ones((2,3)))
    assert np.isinf(d).all() and (f == -1).all()


def test_exposure_hits_actual_triangle_and_excludes_self():
    t = np.array([UP, UP+[0,.5,0]])
    p = np.array([[.2,0,.2],[.2,.5,.2],[.9,0,.9],[.2,-2,.2]])
    assert BVH(t).exposed(p).tolist() == [False,True,True,True]


def test_bvh_pairs_unique_and_complete():
    rng = np.random.default_rng(8)
    lo = rng.random((71,3))*3
    hi = lo+rng.random((71,3))
    tree = BVH(lo=lo, hi=hi, leaf=3)
    actual = [tuple(sorted((int(i),int(j)))) for a,b in pairs(tree, epsilon=.01) for i,j in zip(a,b)]
    expected = {(i,j) for i in range(71) for j in range(i+1,71)
                if np.all(lo[i] <= hi[j]+.01) and np.all(lo[j] <= hi[i]+.01)}
    assert len(actual) == len(set(actual))
    assert set(actual) == expected


def test_overlap_area_reversed_winding_partial_and_shared_edge():
    t = np.repeat(UP[None], 3, axis=0)
    other = np.array([UP[::-1], UP+[.5,0,0], [[0,0,0],[1,0,0],[0,0,-1]]])
    area = projected_overlap(t, other, np.tile([0,1,0],(3,1)))
    np.testing.assert_allclose(area, [.5,.125,0])


def test_overlaps_within_and_between_meshes(tmp_path):
    write_mesh(tmp_path, 'SM_CP_a', [UP, UP+[0,.002,0]])
    write_mesh(tmp_path, 'SM_CP_b', [UP+[.5,0,0]])
    r = overlap_report(MeshSet(tmp_path,'render'), options())
    assert r['complete']
    assert r['within_mesh_pairs'] == 1
    assert r['between_mesh_pairs'] == 2
    assert r['pair_area_m2'] == pytest.approx(.75)


def test_pair_budget_is_explicitly_incomplete(tmp_path):
    write_mesh(tmp_path, 'SM_CP_a', [UP]*5)
    r = overlap_report(MeshSet(tmp_path,'render'), options(max_pairs=1))
    assert not r['complete']
    assert 'lower bounds' in r['stop_reason']


def test_topology_open_edges_t_junction_and_sliver(tmp_path):
    other = np.array([[.5,0,0],[.5,0,-1],[1,0,-1]])
    tiny = np.array([[2,0,0],[3,0,0],[2,0,.00001]])
    write_mesh(tmp_path,'SM_CP_a',[UP,other,tiny])
    r = topology_report(MeshSet(tmp_path,'render'),options())
    assert r['open_edges'] == 9
    assert r['t_junctions'] == 1
    assert r['sliver_faces'] == 1


def test_region_boundary_is_not_open_and_target_outside_is_used(tmp_path):
    # Two triangles form a square. First centroid selected, second centroid outside.
    second = np.array([[1,0,1],[1,0,0],[0,0,1]])
    write_mesh(tmp_path/'ref','UC_CP_a',[UP,second])
    reference = MeshSet(tmp_path/'ref','collision')
    r = topology_report(reference, options(box=[0,0,.5,.5]))
    assert r['open_edges'] == 2  # shared diagonal is not counted
    # Candidate is a single larger triangle: its centroid lies outside the filter.
    write_mesh(tmp_path/'cand','UC_CP_a',[UP*4])
    r = distance_report(reference,MeshSet(tmp_path/'cand','collision'),options(box=[0,0,.5,.5]))
    assert r['max'] == pytest.approx(0)
    assert r['sampled_within_tolerance']


def test_both_directions_detect_raised_and_missing_surface(tmp_path):
    write_mesh(tmp_path/'ref','UC_CP_a',[UP, UP+[5,0,0]])
    write_mesh(tmp_path/'cand','UC_CP_a',[UP+[0,.02,0]])
    ref, cand = MeshSet(tmp_path/'ref','collision'), MeshSet(tmp_path/'cand','collision')
    a, b = distance_report(ref,cand,options()), distance_report(cand,ref,options())
    assert a['max'] >= 5
    assert b['max'] == pytest.approx(.02)
    assert not a['sampled_within_tolerance'] and not b['sampled_within_tolerance']


def test_buried_faces_are_not_riding_samples(tmp_path):
    write_mesh(tmp_path/'ref','UC_CP_a',[UP,UP+[0,.5,0]])
    write_mesh(tmp_path/'cand','UC_CP_a',[UP+[0,.5,0]])
    r = distance_report(MeshSet(tmp_path/'ref','collision'),MeshSet(tmp_path/'cand','collision'),options())
    assert r['buried_samples'] == 7
    assert r['max'] == pytest.approx(0)


def test_look_interpolates_ao_and_normals(tmp_path):
    for path, ao, normal in ((tmp_path/'ref',.3,[0,1,0]),(tmp_path/'cand',.5,[1,0,0])):
        write_mesh(path,'SM_CP_a',[UP],corner_ao=np.full((1,3),ao),corner_normal=np.tile(normal,(1,3,1)))
    r = look_report(MeshSet(tmp_path/'ref','render'),MeshSet(tmp_path/'cand','render'),options())
    assert r['by_mesh']['SM_CP_a']['corner_ao']['max'] == pytest.approx(.2)
    assert r['by_mesh']['SM_CP_a']['corner_normal']['max'] == pytest.approx(90)


def test_cli_self_check_preserves_absolute_defects(tmp_path):
    import json
    root = tmp_path/'input'
    for name in ('SM_CP_a','UC_CP_a'):
        write_mesh(root,name,[UP,UP])
    (root/'build.json').write_text(json.dumps({'collision':[{'name':'UC_CP_a','triangles':3,'role':'original'}]}))
    output = tmp_path/'report.json'
    main([str(root),str(root),'--out',str(output),'--max-samples','0'])
    data = json.loads(output.read_text())
    assert data['complete']
    collision = data['domains']['collision']
    assert collision['reference_to_candidate']['max'] == pytest.approx(0)
    assert collision['candidate_to_reference']['max'] == pytest.approx(0)
    assert collision['reference_overlaps']['overlapping_pairs'] == 1
    assert collision['candidate_overlaps']['overlapping_pairs'] == 1
    assert collision['reference_counts']['UC_CP_a']['manifest_minus_npz'] == 1
    assert collision['reference_counts']['UC_CP_a']['role'] == 'original'


def test_dense_lattice_contains_corners_and_obeys_spacing(tmp_path):
    write_mesh(tmp_path,'UC_CP_a',[UP,UP*2])
    mesh = MeshSet(tmp_path,'collision')
    points, faces, bary, total = sample_faces(mesh,np.ones(2,bool),0,spacing=.5)
    assert total == 10+28  # ceil(sqrt(2)/.5)=3 and ceil(2sqrt(2)/.5)=6
    assert len(points) == total
    assert (bary >= 0).all()
    np.testing.assert_allclose(bary.sum(axis=1),1)
    for face in range(2):
        ps = points[faces==face]
        for corner in mesh.tri[face]:
            assert np.any(np.linalg.norm(ps-corner,axis=1) < 1e-12)
        assert len(np.unique(ps,axis=0)) == len(ps)
    result = distance_report(mesh,mesh,options(spacing=.5))
    assert result['full_spacing_coverage']
    assert result['sampling_fraction'] == 1


def test_dense_budget_never_claims_full_spacing(tmp_path):
    write_mesh(tmp_path,'UC_CP_a',[UP])
    mesh = MeshSet(tmp_path,'collision')
    result = distance_report(mesh,mesh,options(spacing=.05,max_samples=17))
    assert result['points_tested_for_exposure'] == 17
    assert not result['full_spacing_coverage']
    assert not result['stencil_complete']
    assert result['sampling_fraction'] < .1


def test_self_look_with_corner_discontinuities_is_exact_zero(tmp_path):
    t = np.array([UP,UP+[1,0,0]])
    write_mesh(tmp_path,'SM_CP_a',t,corner_ao=np.array([[0,.2,.4],[.8,.3,.1]]),
               corner_normal=np.array([[[.2,.9,.4]]*3,[[.4,.8,.3]]*3]))
    mesh = MeshSet(tmp_path,'render')
    result = look_report(mesh,mesh,options())['by_mesh']['SM_CP_a']
    assert result['corner_ao']['max'] == 0
    assert result['corner_normal']['max'] == 0
