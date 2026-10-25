"""Original transport validation failures prevent a reusable native readiness result."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('transport_preflight_test', ROOT / 'games/yorimichi/world/transport_preflight_v2.py')
body = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(body)


def validator(monkeypatch, name, function):
    parts = name.split('.')
    parent = None
    for index, part in enumerate(parts):
        fullname = '.'.join(parts[:index + 1])
        module = ModuleType(fullname)
        if index < len(parts) - 1:
            module.__path__ = []
        monkeypatch.setitem(sys.modules, fullname, module)
        if parent is not None:
            setattr(parent, part, module)
        parent = module
    parent.validate_service = function


def test_ferry_source_and_harbor_cut_both_pass_before_readiness_is_written(tmp_path, monkeypatch):
    service, cut, report = [tmp_path / name for name in ('service.json', 'cut.json', 'result/proof.json')]
    service.write_text('{"source":"current"}')
    calls = []
    validator(monkeypatch, 'regions.ferry.service', lambda data, root: calls.append((data, root)))
    cut.write_text('{"failures":["blocked opening"]}')
    with pytest.raises(ValueError, match='Harbor cut failed'):
        body.ferry(service, cut, tmp_path, report)
    assert not report.exists()
    assert calls == [({'source': 'current'}, tmp_path / 'ferry')]
    cut.write_text('{"failures":[]}')
    body.ferry(service, cut, tmp_path, report)
    assert json.loads(report.read_text()) == {'passed': True}


@pytest.mark.parametrize('kind', ['ferry', 'gondola'])
def test_original_service_refusal_never_publishes_readiness(tmp_path, monkeypatch, kind):
    source, report = tmp_path / 'service.json', tmp_path / 'proof.json'
    source.write_text('{}')
    def refuse(*args):
        raise ValueError('original source audit failed')
    validator(monkeypatch, 'regions.ferry.service' if kind == 'ferry' else 'gondola.service', refuse)
    with pytest.raises(ValueError, match='original source audit failed'):
        if kind == 'ferry':
            body.ferry(source, tmp_path / 'not-read-cut.json', tmp_path, report)
        else:
            body.gondola(source, tmp_path, report)
    assert not report.exists()


def test_native_gate_binds_the_actual_final_cut_product_and_orders_every_native_owner():
    spec = importlib.util.spec_from_file_location('transport_provider_test', ROOT / 'games/yorimichi/v2_native_units.py')
    provider = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provider)
    cut = 'build/yorimichi/hidamari/final-source-data/harbor-cut.json'
    rows = [{'id': 'unreal.ferry', 'inputs': [], 'code': [], 'needs': ['world.ferry_service'],
             'products': [], 'outputs': [], 'commands': [], 'verify': None},
            {'id': 'world.hidamari.geometry.HD_Harbor', 'products': [
                {'id': 'hidamari.harbor_cut', 'paths': [cut], 'optional_paths': []}]}]
    family = {'units': [{'id': 'raw', 'inputs': []}, {'id': 'finish', 'inputs': []}],
              'staged_inputs': {'raw': {}, 'finish': {}}}
    native = {}
    gate = provider._transport_preflight(native, family, rows, 'ferry', checkout=ROOT)
    authored, = native['rows']
    declared = {entry['path'] for entry in authored['inputs']}
    assert cut in declared
    assert 'build/yorimichi/hidamari/ferry/cut.json' not in declared
    for unit in family['units']:
        assert unit['inputs'][0]['source'] == {'kind': 'item', 'unit': gate, 'item': 'output0'}
    defaults = authored['commands'][0]['fn']['defaults']
    assert {'path': cut} in defaults
