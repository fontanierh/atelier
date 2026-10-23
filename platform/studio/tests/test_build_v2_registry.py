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
    listing = {'rust-build-meta': {'platforms': {'host': {'platform': {'triple': 'x86_64-unknown-linux-gnu'}}}}, 'test-count': 1, 'rust-suites': {'fixture': {'status': 'listed', 'testcases': {
        'test': {'ignored': False, 'filter-match': {'status': 'matches'}},
    }}}}
    junit = ET.fromstring('<testsuites time="0.1"><testsuite name="fixture">'
                          '<testcase classname="fixture" name="test" /></testsuite></testsuites>')
    return registry, listing, junit


def test_active_coverage_and_pending_are_reported_separately():
    registry, listing, junit = evidence()
    assert check_registry(registry, listing) == {'active_scenarios': 1, 'tests': 1, 'pending_scenarios': 1,
                                                'platform': 'linux', 'platform_excluded_scenarios': 0}
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


def test_platform_exclusions_are_explicit_and_not_passed_coverage():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'mac-only', 'tests': ['fixture/apfs'], 'platforms': ['darwin']})
    summary = check_registry(registry, listing)
    assert summary['active_scenarios'] == 1
    assert summary['platform_excluded_scenarios'] == 1
    listing['rust-build-meta']['platforms']['host']['platform']['triple'] = 'aarch64-apple-darwin'
    with pytest.raises(ValueError, match='registry mismatch'):
        check_registry(registry, listing)
    listing['rust-suites']['fixture']['testcases']['apfs'] = {'ignored': False, 'filter-match': {'status': 'matches'}}
    listing['test-count'] = 2
    assert check_registry(registry, listing)['active_scenarios'] == 2


@pytest.mark.parametrize('platforms', [[], ['windows'], 'darwin'])
def test_invalid_platform_labels_fail_instead_of_silently_excluding(platforms):
    registry, listing, _ = evidence()
    registry['scenarios'][0]['platforms'] = platforms
    with pytest.raises(ValueError, match='platform labels'):
        check_registry(registry, listing)


def test_unknown_recorded_host_fails():
    registry, listing, _ = evidence()
    listing['rust-build-meta']['platforms']['host']['platform']['triple'] = 'x86_64-pc-windows-msvc'
    with pytest.raises(ValueError, match='unsupported recorded host'):
        check_registry(registry, listing)
