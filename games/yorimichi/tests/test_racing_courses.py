"""Committed racecourses must match both their schema and the actual venue surface."""
import io
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import build as recipes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from racing import courses  # noqa: E402
from belmonte import source, planting  # noqa: E402


def course_leaf():
    path = courses.DATA.parent / 'stage_courses.py'
    spec = importlib.util.spec_from_file_location('stage_courses', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_course_leaf_preserves_original_bytes(tmp_path):
    leaf = course_leaf()
    original = courses.DATA.read_bytes()
    # Valid noncanonical whitespace must survive just as it does under original copy2.
    raw = b' \r\n' + original.replace(b'\n', b'\r\n') + b'\t\r\n'
    course = tmp_path / 'input.json'
    course.write_bytes(raw)
    output = tmp_path / 'output' / 'belmonte_courses.json'

    def destination(name):
        assert name == 'belmonte_courses.json'
        output.parent.mkdir()
        return output

    leaf.run(SimpleNamespace(input=lambda slot: {'courses': course, 'venue': courses.SCENE,
                                                'surface': courses.surface_inputs()[0]}[slot],
                             output=destination))
    assert output.read_bytes() == raw
    assert courses.load_bytes(raw) == courses.load()


@pytest.mark.parametrize('bad', [b'{}', b'{broken json', b'[]',
                                b'\xef\xbb\xbf{}', '{}'.encode('utf-16')])
def test_invalid_course_leaf_never_requests_output(tmp_path, bad):
    leaf = course_leaf()
    course = tmp_path / 'input.json'
    course.write_bytes(bad)
    requested = []

    def forbidden_output(name):
        requested.append(name)
        raise AssertionError('invalid preflight reached output staging')

    with pytest.raises(ValueError):
        leaf.run(SimpleNamespace(input=lambda slot: {'courses': course, 'venue': courses.SCENE,
                                                    'surface': courses.surface_inputs()[0]}[slot],
                                 output=forbidden_output))
    assert requested == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ['input.json']


def test_course_declaration_is_pure_complete_and_independent(monkeypatch):
    recipe_path = courses.DATA.parents[2] / 'build_v2.py'
    spec = importlib.util.spec_from_file_location('yorimichi_build_v2', recipe_path)
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)

    def forbidden(*args, **kwargs):
        raise AssertionError('declaration discovery touched filesystem state')

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_bytes', forbidden)
        patch.setattr(Path, 'read_text', forbidden)
        patch.setattr(Path, 'mkdir', forbidden)
        first = recipe.declaration()
        second = recipe.declaration()
    unit = first['units'][0]
    assert unit['id'] == 'data.stage.racing_courses'
    assert unit['params'] == {}
    assert {i['source']['path'] for i in unit['inputs']} == {
        str(p.relative_to(courses.GAME.parents[1])) for p in [courses.DATA, courses.SCENE, *courses.surface_inputs()]}
    assert set(unit['code']) == set(recipe.COURSE_CODE)
    assert unit['outputs'][0]['files'] == [{
        'path': 'belmonte_courses.json',
        'install_path': 'games/yorimichi/unreal/Content/Data/racing/belmonte_courses.json'}]
    unit['code'].clear()
    assert second['units'][0]['code']
    assert recipe.staged_inputs()['surface'] == 'inputs/venue/meshes/SM_BM_BHip_Course.glb'


def test_committed_lap_lengths_and_finish():
    data = courses.load()
    assert data['tracks']['turf']['length_m'] == 1799.841
    assert data['tracks']['sand']['length_m'] == 1703.707
    assert data['tracks']['turf']['finish_s'] == 240.


@pytest.mark.parametrize('change', [
    lambda d: d.update(version=True),
    lambda d: d.update(frame='Unreal centimetres'),
    lambda d: d.update(source={}),
    lambda d: d['tracks'].pop('sand'),
    lambda d: d['tracks']['turf'].update(closed=False),
    lambda d: d['tracks']['turf'].update(points=[[0., 0., 0.]] * 3),
    lambda d: d['tracks']['turf']['points'][0].__setitem__(0, float('nan')),
    lambda d: d['tracks']['turf']['points'][0].__setitem__(0, True),
    lambda d: d['tracks']['turf'].update(finish_s=-1.),
    lambda d: d['tracks']['turf'].update(length_m=1800.),
    lambda d: d['tracks']['turf'].update(lane_width_m=1.9),
    lambda d: d['tracks']['turf']['points'].reverse(),
    lambda d: [p.__setitem__(2, p[2] + 100.) for p in d['tracks']['turf']['points']],
    lambda d: [p.__setitem__(0, p[0] + 100.) for p in d['tracks']['turf']['points']],
    lambda d: d['tracks']['turf'].update(lane_width_m=-100.),
    lambda d: d['tracks']['turf']['points'][0].__setitem__(0, 10**1000),
])
def test_invalid_course_data_is_rejected(tmp_path, change):
    data = json.loads(courses.DATA.read_text())
    change(data)
    path = tmp_path / 'courses.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        courses.load(path)


def test_every_racing_lane_stays_on_the_committed_course():
    scene = source.manifest()
    model = next(m for m in scene['meshes'] if m['name'] == 'SM_BM_BHip_Course')
    placed = next(p for p in scene['placements'] if p['asset'] == model['source_asset'])
    transform = placed['transform']
    faces = source.triangles(source.LIBRARY / model['path']) * [100., -100., 100.] * transform['scale']
    faces = (planting.rotate(transform['rotation_xyzw'], faces) + transform['translation_cm']) / [100., -100., 100.]
    surface = source.Surface(faces)
    for name, track in courses.load()['tracks'].items():
        points = np.asarray(track['points'])
        ends = np.roll(points, -1, axis=0)
        lengths = np.linalg.norm(ends[:, :2] - points[:, :2], axis=1)
        cumulative = np.r_[0., np.cumsum(lengths)]
        s = np.arange(0., cumulative[-1], 2.)
        segment = np.searchsorted(cumulative, s, side='right') - 1
        fraction = (s - cumulative[segment]) / lengths[segment]
        centres = points[segment] + (ends[segment] - points[segment]) * fraction[:, None]
        tangent = (ends[segment, :2] - points[segment, :2]) / lengths[segment, None]
        outward = np.c_[tangent[:, 1], -tangent[:, 0]]
        # Six runners, from the inner to outer lane, in the existing rail corridor.
        for offset in np.linspace(-10., -.5, 6):
            xy = centres[:, :2] + outward * offset
            ground = surface.height(xy[:, 0], xy[:, 1])
            assert np.isfinite(ground).all(), f'{name} lane {offset}: missing committed course surface'
            np.testing.assert_allclose(ground, centres[:, 2], atol=.05)


def test_invalid_courses_fail_before_staging_writes(tmp_path, monkeypatch):
    recipe = recipes.load_recipe('yorimichi')
    runtime = recipe.runtime_data
    bad = tmp_path / 'courses.json'
    bad.write_text('{}')
    destination = tmp_path / 'Data'
    monkeypatch.setattr(runtime, 'RACING_COURSES', bad)
    monkeypatch.setattr(runtime.paths, 'content_data', lambda game: destination)
    with pytest.raises(ValueError):
        runtime.stage_data(SimpleNamespace(game='yorimichi', out=tmp_path), io.StringIO())
    assert not destination.exists()


def test_staging_tracks_all_course_inputs(tmp_path):
    recipe = recipes.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    step = next(s for s in recipe.steps(ctx) if s.name == 'data.stage')
    runtime = recipe.runtime_data
    assert runtime.staged_source(tmp_path, 'racing/belmonte_courses.json') == courses.DATA
    assert courses.DATA in step.inputs
    assert runtime.RACING_VALIDATOR in step.inputs
    assert courses.SCENE in step.inputs
    assert all(p in step.inputs for p in courses.surface_inputs())
    from atelier import gltf
    assert courses.SOURCE_READER in step.inputs
    assert Path(gltf.__file__) in step.inputs
    target = recipe.GAME / 'unreal/Content/Data/racing/belmonte_courses.json'
    assert target not in step.outputs
    leaf = next(s for s in recipe.steps(ctx) if s.name == 'data.stage.racing_courses')
    assert leaf.controller is not None
    assert leaf.outputs == [target]
    assert leaf.name in step.after
    assert leaf.name not in step.needs  # Ordering is not an invented output-content bridge.
    assert 'racing/belmonte_courses.json' not in runtime.staged(tmp_path)


def test_off_venue_course_fails_before_staging_writes(tmp_path, monkeypatch):
    runtime = recipes.load_recipe('yorimichi').runtime_data
    data = json.loads(courses.DATA.read_text())
    for point in data['tracks']['turf']['points']:
        point[2] += 100.
    bad = tmp_path / 'courses.json'
    bad.write_text(json.dumps(data))
    destination = tmp_path / 'Data'
    monkeypatch.setattr(runtime, 'RACING_COURSES', bad)
    monkeypatch.setattr(runtime.paths, 'content_data', lambda game: destination)
    with pytest.raises(ValueError, match='venue surface'):
        runtime.stage_data(SimpleNamespace(game='yorimichi', out=tmp_path), io.StringIO())
    assert not destination.exists()


def test_corrupt_venue_mesh_is_rejected_before_parsing(tmp_path):
    scene = tmp_path / 'source.json'
    scene.write_bytes(courses.SCENE.read_bytes())
    model_path = courses.surface_inputs(scene)[0]
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b'changed geometry')
    with pytest.raises(ValueError, match='mesh differs'):
        courses.load(scene=scene)


def test_surface_validation_follows_the_authored_venue_placement(tmp_path):
    scene = json.loads(courses.SCENE.read_text())
    model, _, original_path = courses.venue(courses.SCENE)
    placement = next(p for p in scene['placements'] if p['asset'] == model['source_asset'])
    placement['transform']['translation_cm'][0] += 1000.
    scene_path = tmp_path / 'source.json'
    scene_path.write_text(json.dumps(scene))
    model_path = tmp_path / model['path']
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(original_path.read_bytes())
    data = json.loads(courses.DATA.read_text())
    data['source']['venue_scene_sha256'] = hashlib.sha256(scene_path.read_bytes()).hexdigest()
    data_path = tmp_path / 'courses.json'
    data_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='venue'):
        courses.load(data_path, scene_path)
    for track in data['tracks'].values():
        for point in track['points']:
            point[0] += 10.
    data_path.write_text(json.dumps(data))
    assert courses.load(data_path, scene_path)['tracks'] == data['tracks']
