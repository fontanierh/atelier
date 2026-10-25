"""Ordinary build selection invokes the real v2 engine without an older scheduler."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from atelier import build, paths
from atelier.build_v2 import controller_entry as entry
from atelier.build_v2.controller_recipe import ControllerTarget, ControllerSelection


def marker(name='data.rim'):
    return ControllerTarget(name, 'fixture', {
        'schema_version': 2, 'cache_version': 'v2-1', 'units': [{
            'id': name, 'op': {'kind': 'py_data', 'version': '1'},
            'script': 'ops/body.py', 'code': ['ops/body.py'], 'inputs': [],
            'outputs': [{'id': 'data', 'logical_path': '/Game/Data/'+name+'.json', 'class': 'JsonData',
                'destination': 'checkout', 'files': [{'path': name+'.json', 'install_path': 'Game/'+name+'.json'}]}],
        }]}, {name: {}}, {}, ('Game',))


def observed():
    return {'state': 'observed', 'cancelled': False, 'report': {'observation': {
        'summary': {'units': []}, 'cancellation_requested': False,
        'final_requirements_satisfied': True, 'source_finalization': 'complete', 'root_finalization': 'complete'}}}


def test_normal_build_never_discovers_or_invokes_old_scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    targets = {name: marker(name) for name in ('data.rim', 'data.course')}
    from copy import deepcopy
    conflicting = deepcopy(targets['data.rim'].declaration['units'][0])
    conflicting['params'] = {'unrequested_conflict': True}
    targets['data.course'].declaration['units'].append(conflicting)
    monkeypatch.setattr(entry, 'discover', lambda game, **kwargs: targets)
    def forbidden(*args, **kwargs): raise AssertionError('invoked old recipe/runtime')
    monkeypatch.setattr(build, 'Context', forbidden)
    monkeypatch.setattr(build, 'load_recipe', forbidden)
    monkeypatch.setattr(build, '_prepared_build', forbidden)
    calls = []
    def invoke(selection, **kwargs): calls.append(selection.request(tmp_path)); return observed()
    monkeypatch.setattr(entry, '_invoke_marker', invoke)
    assert build.build('fixture', ['data.rim'], echo=lambda _: None) == 0
    assert len(calls) == 1 and calls[0]['targets'] == ['data.rim']
    assert {u['id'] for u in calls[0]['declaration']['units']} == {'data.rim'}
    assert not (tmp_path / 'build').exists()


def test_multiple_explicit_targets_share_one_existing_controller_request(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    targets = {name: marker(name) for name in ('data.rim', 'data.course')}
    monkeypatch.setattr(entry, 'discover', lambda game, **kwargs: targets)
    selection = entry.exact_selection('fixture', ['data.course', 'data.rim'])
    request = selection.request(tmp_path)
    assert request['targets'] == ['data.course', 'data.rim']
    assert set(request['staged_inputs']) == set(targets)
    assert request['declaration']['schema_version'] == 2


def test_default_full_selector_cannot_succeed_as_partial_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(entry, 'discover', lambda game, **kwargs: {'data.rim': marker()})
    monkeypatch.setattr(entry, '_invoke_marker', lambda *a, **k: pytest.fail('dispatched missing full target'))
    with pytest.raises(ValueError, match='unreal.package'):
        build.build('fixture')
    assert not (tmp_path / 'build').exists()


def test_full_selector_routes_exact_declared_v2_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    owned = marker('unreal.package')
    monkeypatch.setattr(entry, 'discover', lambda game, **kwargs: {owned.unit: owned})
    assert entry.exact_selection('fixture', ()).request(tmp_path)['targets'] == ['unreal.package']


@pytest.mark.parametrize('kind', ['unit', 'header', 'project', 'staging', 'contract'])
def test_conflicting_declaration_data_refuses(tmp_path, kind):
    first = marker(); second = deepcopy(first)
    if kind == 'unit': second.declaration['units'][0]['script'] = 'ops/foreign.py'
    elif kind == 'header': second.declaration['cache_version'] = 'other'
    elif kind == 'project': second = replace(second, project='other')
    elif kind == 'staging': second.staged_inputs[first.unit] = {'other': 'input'}
    else:
        first.content_slots['source'] = False; second.content_slots['source'] = True
    with pytest.raises(ValueError, match='conflict'):
        ControllerSelection((first, second), (first.unit,)).request(tmp_path)


def test_duplicate_selector_refuses(tmp_path):
    with pytest.raises(ValueError, match='unique'):
        ControllerSelection((marker(),), ('data.rim', 'data.rim')).request(tmp_path)


def test_readonly_plan_does_not_bootstrap_engine_or_claim_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(entry, 'discover', lambda game, **kwargs: {'data.rim': marker()})
    monkeypatch.setattr(entry, 'execute', lambda *a, **k: pytest.fail('plan executed'))
    lines = []
    assert build.build('fixture', ['data.rim'], dry=True, echo=lines.append) == 0
    assert 'unknown' in lines[0] and not (tmp_path / 'build').exists()


def test_unimplemented_option_refuses_instead_of_old_fallback(monkeypatch):
    monkeypatch.setattr(build, '_prepared_build', lambda *a, **k: pytest.fail('fallback'))
    with pytest.raises(ValueError, match='no v2 implementation'):
        build.build('fixture', ['data.rim'], touch=True)


@pytest.mark.parametrize('state', ['incomplete', 'cancelled'])
def test_incomplete_or_cancelled_controller_never_reports_success(tmp_path, monkeypatch, state):
    result = observed()
    if state == 'incomplete': result['report']['observation']['final_requirements_satisfied'] = False
    else: result['cancelled'] = True
    monkeypatch.setattr(entry, '_invoke_marker', lambda *a, **k: result)
    assert entry.execute(marker(), echo=lambda _: None) == (130 if state == 'cancelled' else 1)
