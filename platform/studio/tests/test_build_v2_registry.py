"""The v2 CI registry fails closed on missing or skipped evidence without native tools."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


_path = Path(__file__).resolve().parents[3]/'platform/build-v2/tools/check_registry.py'
_spec = importlib.util.spec_from_file_location('build_v2_registry', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
check_registry = _module.check_registry


def evidence():
    registry = {'schema_version': 1, 'scenarios': [{'id': 'one', 'tests': ['fixture/test']}],
                'pending': [{'id': 'future', 'task': 'A8'}]}
    listing = {'test-count': 1, 'rust-suites': {'fixture': {'status': 'listed', 'testcases': {
        'test': {'ignored': False, 'filter-match': {'status': 'matches'}},
    }}}}
    junit = ET.fromstring('<testsuites time="0.1"><testsuite name="fixture">'
                          '<testcase classname="fixture" name="test" /></testsuite></testsuites>')
    return registry, listing, junit


def test_active_coverage_and_pending_are_reported_separately():
    registry, listing, junit = evidence()
    assert check_registry(registry, listing) == {'active_scenarios': 1, 'tests': 1, 'pending_scenarios': 1}
    assert check_registry(registry, listing, junit)['test_seconds'] == 0.1


@pytest.mark.parametrize('mutation', ['unmapped', 'missing', 'ignored', 'filtered', 'unlisted', 'duplicate-id', 'empty', 'count'])
def test_registry_refuses_incomplete_collection(mutation):
    registry, listing, _ = evidence()
    if mutation == 'unmapped':
        registry['scenarios'][0]['tests'] = ['fixture/other']
    elif mutation == 'missing':
        listing['rust-suites']['fixture']['testcases'] = {}
    elif mutation == 'ignored':
        listing['rust-suites']['fixture']['testcases']['test']['ignored'] = True
    elif mutation == 'filtered':
        listing['rust-suites']['fixture']['testcases']['test']['filter-match']['status'] = 'mismatch'
    elif mutation == 'unlisted':
        listing['rust-suites']['fixture']['status'] = 'skipped'
    elif mutation == 'duplicate-id':
        registry['pending'][0]['id'] = 'one'
    elif mutation == 'empty':
        registry['scenarios'][0]['tests'] = []
    else:
        listing['test-count'] = 2
    with pytest.raises(ValueError):
        check_registry(registry, listing)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'skipped', 'failure', 'error', 'slow', 'nan', 'negative'])
def test_registry_refuses_incomplete_or_slow_execution(mutation):
    registry, listing, junit = evidence()
    suite = junit.find('testsuite')
    if mutation == 'missing':
        suite.remove(suite.find('testcase'))
    elif mutation == 'duplicate':
        ET.SubElement(suite, 'testcase', classname='fixture', name='test')
    elif mutation in ('skipped', 'failure', 'error'):
        ET.SubElement(suite.find('testcase'), mutation)
    else:
        junit.set('time', {'slow': '10.01', 'nan': 'NaN', 'negative': '-1'}[mutation])
    with pytest.raises(ValueError):
        check_registry(registry, listing, junit)
