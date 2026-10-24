"""The replacement coastal unit uses declared content and the original projection."""
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
GAME = REPO / 'games/yorimichi'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def body():
    return load('v2_rim_body', GAME / 'world/regions/brinecove/stage_rim_v2.py')


class Context:
    def __init__(self, source, output, extra=False):
        self.inputs = {'far_final': source}
        if extra:
            self.inputs['unexpected'] = source
        self.destination = output
        self.requested = []

    def input(self, name):
        return self.inputs[name]

    def output(self, name):
        self.requested.append(name)
        assert name == 'final-rim.json'
        return self.destination


def terrain(body, path, *, owner='FarHills'):
    from terrain_product import Mesh, save
    from brinecove.region import OUTER_WORLD
    x0, y0, x1, y1 = OUTER_WORLD
    mesh = Mesh.from_polygons([(x0, y0, 1), (x1, y0, 2), (x1, y1, 3), (x0, y1, 4)],
                              [(0, 1, 2), (0, 2, 3)])
    save(path, mesh, owner=owner, stage='final', city=True)
    return path


def test_real_projection_and_serialization_match_original(body, tmp_path):
    source = terrain(body, tmp_path / 'far.npz')
    before = source.read_bytes()
    context = Context(source, tmp_path / 'final-rim.json')
    body.run(context)
    expected = body.rim_data.project(source)
    assert context.destination.read_text() == json.dumps(expected, sort_keys=True) + '\n'
    body.rim_data.read(json.loads(context.destination.read_bytes()))
    assert context.requested == ['final-rim.json']
    assert source.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['far.npz', 'final-rim.json']


@pytest.mark.parametrize('invalid', ['owner', 'missing', 'extra_slot'])
def test_invalid_content_never_requests_output(body, tmp_path, invalid):
    source = tmp_path / 'far.npz'
    if invalid != 'missing':
        terrain(body, source, owner='Other' if invalid == 'owner' else 'FarHills')
    context = Context(source, tmp_path / 'final-rim.json', extra=invalid == 'extra_slot')
    with pytest.raises((ValueError, FileNotFoundError)):
        body.run(context)
    assert not context.requested
    assert not context.destination.exists()


def test_declared_code_is_complete_without_fixed_source_hashes():
    from atelier.build_inputs import local_imports
    recipe = load('v2_rim_recipe', GAME / 'build_v2.py')
    script = REPO / recipe.RIM_SCRIPT
    actual = set(local_imports(script, (GAME / 'world', GAME / 'world/regions',
                                        REPO / 'platform/studio')))
    assert actual == {REPO / name for name in recipe.RIM_CODE}
    first, second = recipe.declaration(), recipe.declaration()
    assert first == second
    first['units'][0]['code'].clear()
    assert second['units'][0]['code']
    rim = next(unit for unit in second['units'] if unit['id'] == recipe.RIM_TARGET)
    assert rim['inputs'][0]['source'] == {'kind': 'file', 'path': recipe.RIM_INPUT}
    assert rim['outputs'][0]['files'] == [{'path': 'final-rim.json',
        'install_path': 'build/yorimichi/brinecove-data/final-rim.json'}]
    assert rim['params'] == {}
