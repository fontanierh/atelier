"""Explicit controller ownership cannot silently become a v1 empty-command success."""
from copy import deepcopy
from pathlib import Path

import pytest

from atelier import build
from atelier.build_v2.controller_recipe import ControllerTarget, validate_markers


def marker():
    return ControllerTarget(
        unit='data.copy', project='fixture', allowed_install_roots=('Game',),
        content_slots={'source': True}, staged_inputs={'data.copy': {'source': 'inputs/source.json'}},
        declaration={'schema_version': 2, 'cache_version': 'v2-1', 'units': [{
            'id': 'data.copy', 'op': {'kind': 'py_data', 'version': '1'},
            'script': 'ops/copy.py', 'code': ['ops/copy.py'],
            'inputs': [{'role': 'content', 'name': 'source', 'source': {'kind': 'file', 'path': 'source.json'}}],
            'outputs': [{'id': 'copy', 'logical_path': '/Game/Data/copy.json', 'class': 'JsonData',
                         'destination': 'checkout', 'files': [{'path': 'copy.json', 'install_path': 'Game/copy.json'}]}],
        }]})


def test_controller_marker_serializes_complete_control_data_without_python_keys(tmp_path):
    value = marker()
    step = build.Step(value.unit, [], outputs=list(value.outputs(tmp_path)), controller=value)
    validate_markers([step], tmp_path)
    request = value.request(tmp_path)
    assert request['targets'] == ['data.copy']
    assert request['checkout'] == str(tmp_path)
    assert set(request) == {'version', 'checkout', 'project', 'allowed_install_roots', 'declaration',
                            'targets', 'data_contract', 'staged_inputs'}
    request['declaration']['units'].clear()
    assert value.request(tmp_path)['declaration']['units']
    with pytest.raises(ValueError, match='v1 fingerprint'):
        build.fingerprint_state(step, {})
    # Empty commands on an ordinary v1 aggregate are not inferred to be controller-owned.
    ordinary = build.Step('ordinary.aggregate', [])
    assert ordinary.controller is None
    assert build.fingerprint_state(ordinary, {})[0]


@pytest.mark.parametrize('field,value', [
    ('commands', [build.Call('wrong', lambda ctx, log: None)]), ('inputs', [Path('hidden.json')]),
    ('needs', ['legacy.producer']), ('cache', True), ('toolchain', True), ('heavy', True),
    ('checkpoint_outputs', (Path('Game/elsewhere'),)), ('cutoff', True),
])
def test_controller_marker_refuses_v1_execution_and_certificate_fields(tmp_path, field, value):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    setattr(step, field, value)
    with pytest.raises(ValueError, match='v1 execution'):
        validate_markers([step], tmp_path)


@pytest.mark.parametrize('path', ['Game/copy.json', 'Game', 'game/COPY.JSON'])
def test_global_controller_overlap_refuses_even_for_unselected_legacy_owner(tmp_path, path):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    unrelated = build.Step('unselected.legacy', [], outputs=[tmp_path / path])
    with pytest.raises(ValueError, match='ownership overlaps'):
        validate_markers([step, unrelated], tmp_path)


def test_controller_marker_requires_complete_exact_output_contract(tmp_path):
    owned = marker()
    with pytest.raises(ValueError, match='complete declaration'):
        validate_markers([build.Step(owned.unit, [], outputs=[], controller=owned)], tmp_path)
    changed = deepcopy(owned)
    changed.declaration['units'][0]['outputs'][0]['destination'] = 'store'
    with pytest.raises(ValueError, match='checkout JsonData'):
        changed.outputs(tmp_path)
