"""Selected placement never borrows the old block or a stale geometry artifact."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
sys.path.insert(0, str(GAME / 'world'))
from craterpark import placement  # noqa: E402
from craterpark.v2 import dsl, v4_config, v4_placement  # noqa: E402
from hidamari import mountains  # noqa: E402


@pytest.fixture
def selected(tmp_path, monkeypatch):
    path = tmp_path / 'design.json'
    doc = {'frame': {'lift': 680}, 'ground': {'dig': {'kind': 'depth', 'DEPTH': 65}},
           'site': {'buildable': [[0, 0], [20, 0], [20, 20], [0, 20]]},
           'tower': {'deck_y': 125, 'roll_ins': [{'pos': [10, 10], 'heading': 0}]}}
    path.write_text(json.dumps(doc))
    monkeypatch.setenv(v4_config.SWITCH, str(path))
    return path, doc


def test_selected_missing_design_cannot_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv(v4_config.SWITCH, str(tmp_path / 'missing.json'))
    monkeypatch.setattr(placement, '_legacy_ground_triangles', lambda: pytest.fail('legacy geometry called'))
    monkeypatch.setattr(v4_placement, 'geometry_path', lambda: tmp_path / 'missing-geometry.npz')
    with pytest.raises(OSError):
        placement.ground_triangles()
    with pytest.raises(OSError):
        placement.drop_in()
    with pytest.raises(OSError):
        placement.contains(0, 0)


def test_depth_changes_floor_without_changing_crest(selected, monkeypatch):
    assert mountains.caldera_floor() == pytest.approx(float(mountains.apron_height(mountains.VOLCANO[1])) + mountains.CREST - 65)
    monkeypatch.delenv(v4_config.SWITCH)
    assert mountains.caldera_floor() == pytest.approx(float(mountains.apron_height(mountains.VOLCANO[1])) + mountains.CREST - mountains.DEPTH)


def test_selected_envelope_and_spawn_use_native_design(selected, monkeypatch):
    monkeypatch.setattr(placement, 'native_to_island', lambda q: np.asarray(q)[..., [0, 2, 1]])
    assert placement.contains([10, 21], [10, 10]).tolist() == [True, False]
    assert placement.contains([10, 21], [10, 10], margin=2).tolist() == [True, True]
    monkeypatch.setattr(v4_placement, 'identity', lambda: ('fixture', 1, 1, 'sha'))
    monkeypatch.setattr(v4_placement, '_geometry', lambda *a: (None, None, {'lines': [
        {'spawn': {'location_cm': [1000, -1000, 12500], 'yaw_deg': 0}}]}))
    ground, camera = placement.drop_in()
    np.testing.assert_allclose(ground, [10, 10, 125])
    np.testing.assert_allclose(camera, [2, 10, 131])


def test_terrain_and_snow_cache_keys_include_selected_geometry(monkeypatch):
    key = ['one']
    calls = []
    monkeypatch.setattr(mountains, '_park_identity', lambda: tuple(key))
    monkeypatch.setattr(mountains, '_surface_grid', lambda sampler, identity: calls.append(('surface', identity)))
    monkeypatch.setattr(mountains, '_snow_grid', lambda sampler, identity: calls.append(('snow', identity)))
    sampler = lambda x,y: 0
    mountains.surface_grid(sampler)
    mountains.snow_grid(sampler)
    key[0] = 'two'
    mountains.surface_grid(sampler)
    mountains.snow_grid(sampler)
    assert calls == [('surface', ('one',)), ('snow', ('one',)), ('surface', ('two',)), ('snow', ('two',))]


def test_current_geometry_required_and_cache_invalidates(selected, monkeypatch, tmp_path):
    path, doc = selected
    artifact = tmp_path / 'geometry.npz'
    monkeypatch.setattr(v4_placement, 'geometry_path', lambda: artifact)
    monkeypatch.setattr(placement, 'native_to_island', lambda q: np.asarray(q))
    mesh = dsl.Mesh(np.array([[0., 0, 0], [0, 0, 1], [1, 0, 0], [1, 2, 0]]),
                    np.array([[0, 1, 2], [1, 2, 3]]),
                    role=np.array([dsl.ROLE[dsl.GROUND], dsl.ROLE[dsl.RIDING]]))
    index = {'render': [{}], 'v4': v4_config.provenance(), 'accepted': True,
             'validation': {'ran': True, 'ok': True, 'supports': {'ran': True, 'ok': True}}}
    np.savez(artifact, index=np.asarray(json.dumps(index)), **mesh.to_arrays('r0_'))
    assert placement.ground_triangles().shape == (1, 3, 3)
    assert placement.piece_triangles().shape == (1, 3, 3)
    # Replacing same-sized data and preserving mtime still invalidates caches.
    import os
    st=artifact.stat()
    mesh.V[:,1]+=1.
    np.savez(artifact,index=np.asarray(json.dumps(index)),**mesh.to_arrays('r0_'))
    os.utime(artifact,ns=(st.st_atime_ns,st.st_mtime_ns))
    assert artifact.stat().st_size==st.st_size
    np.testing.assert_allclose(placement.ground_triangles()[0,:,1],1.)
    index['accepted']=False
    np.savez(artifact,index=np.asarray(json.dumps(index)),**mesh.to_arrays('r0_'))
    with pytest.raises(ValueError,match='accepted structural and support'):
        placement.ground_triangles()
    index['accepted']=True
    index['validation']['supports']['ok']=False
    np.savez(artifact,index=np.asarray(json.dumps(index)),**mesh.to_arrays('r0_'))
    with pytest.raises(ValueError,match='accepted structural and support'):
        placement.ground_triangles()
    doc['tower']['deck_y'] = 126
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='current design provenance'):
        placement.ground_triangles()


def test_terrain_stamp_receives_distinct_selected_identity(selected, monkeypatch):
    sentinel = ('new-geometry', 1, 2, 'new-source')
    monkeypatch.setattr(v4_placement, 'identity', lambda: sentinel)
    monkeypatch.setattr(v4_placement, 'ground_grid', lambda: None)
    calls = []
    def stamp(natural, identity):
        calls.append(identity)
        q = np.ones((2, 2))
        return 0., 0., 1., q.astype(bool), q, q*0, q*12
    monkeypatch.setattr(placement, '_stamp', stamp)
    assert placement.terrain(.5, .5, 99., lambda x,y: 99.) == pytest.approx(12.)
    assert calls == [sentinel]
    monkeypatch.delenv(v4_config.SWITCH)
    placement.terrain(.5, .5, 99., lambda x,y: 99.)
    assert calls[-1] is None


def test_editor_ground_grid_is_followed_by_the_terrain(selected, monkeypatch, tmp_path):
    """An editor park draws no ground: the terrain takes its cut grid by weight, and its ground is the full-weight cells."""
    artifact = tmp_path / 'geometry.npz'
    monkeypatch.setattr(v4_placement, 'geometry_path', lambda: artifact)
    monkeypatch.setattr(placement, 'native_to_island', lambda q: np.asarray(q))
    monkeypatch.setattr(placement, 'island_to_native_xz', lambda x, y: (np.asarray(x, 'f8'), np.asarray(y, 'f8')))
    mesh = dsl.Mesh(np.array([[0., 30, 0], [0, 30, 1], [1, 30, 0]]), np.array([[0, 1, 2]]),
                    role=np.array([dsl.ROLE[dsl.RIDING]]))
    grid = {'x0': 0., 'z0': 0., 'G': 2., 'nx': 4, 'nz': 3, 'reach': 60., 'fade': 40.}
    heights = np.full((3, 4), -5., 'f4')
    weight = np.array([[1, 1, 1, 0], [1, 1, 1, 0], [1, 1, 1, 0]], 'f4')
    index = {'render': [{}], 'v4': v4_config.provenance(), 'editor_playtest': {'rev': 1}, 'ground_grid': grid}
    np.savez(artifact, index=np.asarray(json.dumps(index)), ground_height=heights, ground_weight=weight,
             **mesh.to_arrays('r0_'))
    natural = lambda x, y: np.full(np.shape(x), 700.)
    # the cell centres sit at 1, 3, 5, 7 (x) and 1, 3, 5 (z); weight 1 takes the cut ground (native -5 + 680)
    assert placement.terrain(3., 3., 700., natural) == pytest.approx(675.)
    assert placement.terrain(7., 3., 700., natural) == pytest.approx(700.)
    assert placement.terrain(6., 3., 700., natural) == pytest.approx(687.5)
    assert placement.terrain(-50., 3., 700., natural) == pytest.approx(700.)
    ground = placement.ground_triangles()
    assert ground.shape == (8, 3, 3) and (ground[..., 1] == -5.).all() and ground[..., 0].max() == 5.


def test_editor_ground_grid_weight_and_pit_clearance(monkeypatch):
    from types import SimpleNamespace
    from craterpark.v2 import editor_generate
    cut = np.zeros((40, 40)); cut[18:22, 18:22] = -10.          # a pit the bowl cut, 10 m under the layer
    monkeypatch.setattr(editor_generate.frontend, 'read_array', lambda directory, spec, columns: cut.reshape(-1, 1))
    scene = SimpleNamespace(metadata={'_dir': '', 'ground_grid': {'x0': 0., 'z0': 0., 'G': 2., 'nx': 40, 'nz': 40,
                                                                  'heights': None}})
    bowl = np.array([[40., -9.8, 40.]])                              # the bowl's floor, 0.2 m over the pit
    heights, weight = editor_generate.ground_grid(scene, bowl, np.zeros((40, 40)))
    assert heights[20, 20] == pytest.approx(-10.3)                  # kept PIT_CLEAR under the bowl
    assert heights[0, 0] == 0. and weight[19, 19] == 1.             # uncut ground untouched; full weight by the piece


def test_unsupported_depth_and_changed_frame_fail(selected):
    path, doc = selected
    doc['ground']['dig']['kind'] = 'dish'
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='kind=depth'):
        mountains.caldera_floor()
    doc['frame']['lift'] = 700
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='coordinate frame'):
        placement.drop_in()
