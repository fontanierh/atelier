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


@pytest.mark.parametrize('kind', ['output', 'checkpoint', 'pool', 'required_product', 'optional_product'])
def test_controller_and_default_graph_refuse_existing_parent_alias_with_absent_leaf(tmp_path, kind):
    from atelier.build_products import Graph, Product
    (tmp_path / 'Game').mkdir()
    alias = tmp_path / 'Alias'
    alias.symlink_to(tmp_path / 'Game', target_is_directory=True)
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    other = build.Step('unselected.legacy', [])
    if kind == 'output':
        other.outputs = [alias / 'copy.json']
    elif kind == 'checkpoint':
        other.checkpoint_outputs = (alias,)  # An ancestor claims the future owned file too.
    elif kind == 'pool':
        other.pool_roots = (alias,)
    elif kind == 'required_product':
        other.products = (Product('legacy.mesh', (alias / 'copy.json',)),)
    else:
        other.products = (Product('legacy.mesh', (tmp_path / 'Elsewhere/main.bin',),
                                  optional_paths=(alias / 'copy.json',)),)
    assert not step.outputs[0].exists()
    for validate in (lambda: validate_markers([step, other], tmp_path), lambda: Graph([step, other])):
        with pytest.raises(ValueError, match='controller output ownership overlaps'):
            validate()
    assert not step.outputs[0].exists()


def test_controller_alias_witness_is_fresh_and_never_rewrites_disjoint_system_anchor_paths(tmp_path):
    from atelier.build_products import Graph
    (tmp_path / 'Game').mkdir()
    (tmp_path / 'Elsewhere').mkdir()
    anchor = tmp_path / 'SystemAlias'
    anchor.symlink_to(tmp_path, target_is_directory=True)
    alias = tmp_path / 'Alias'
    alias.symlink_to(tmp_path / 'Elsewhere', target_is_directory=True)
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    other = build.Step('legacy.package', [], outputs=[alias / 'copy.json', anchor / 'Packages/game.pak'])
    original = list(other.outputs)
    validate_markers([step, other], tmp_path)
    Graph([step, other])
    assert other.outputs == original  # Comparison never substitutes a canonical execution path.
    assert not (tmp_path / 'Packages').exists()
    alias.unlink()
    alias.symlink_to(tmp_path / 'Game', target_is_directory=True)
    for validate in (lambda: validate_markers([step, other], tmp_path), lambda: Graph([step, other])):
        with pytest.raises(ValueError, match='ownership overlaps'):
            validate()
    assert other.outputs == original


@pytest.mark.parametrize('target', ['missing', 'loop'])
def test_controller_ownership_refuses_uncertain_existing_ancestor_resolution(tmp_path, target):
    from atelier.build_products import Graph
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    alias = tmp_path / 'Alias'
    alias.symlink_to(alias if target == 'loop' else tmp_path / 'Missing', target_is_directory=True)
    other = build.Step('legacy.output', [], outputs=[alias / 'out.json'])
    for validate in (lambda: validate_markers([step, other], tmp_path), lambda: Graph([step, other])):
        with pytest.raises(ValueError, match='cannot establish controller output ownership alias'):
            validate()
    assert not (tmp_path / 'Game').exists()
