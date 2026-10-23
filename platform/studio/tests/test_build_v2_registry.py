"""The v2 CI registry fails closed on missing or skipped evidence without native tools."""
import importlib.util
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


_path = Path(__file__).resolve().parents[3]/'platform/build-v2/tools/check_registry.py'
_spec = importlib.util.spec_from_file_location('build_v2_registry', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
check_registry = _module.check_registry
load_registry = _module.load_registry


SCENARIO = 'schema_version = 1\n[[scenarios]]\nid = "%s"\ntests = ["fixture/%s"]\n'


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


def write_fragments(tmp_path, files):
    directory = tmp_path/'registry'
    directory.mkdir()
    for name, text in files.items():
        (directory/name).write_text(text)
    return directory


def test_loader_merges_fragments_in_sorted_filename_order(tmp_path):
    directory = write_fragments(tmp_path, {
        'b2.toml': SCENARIO % ('b2.one', 'one'),
        'a3.toml': SCENARIO % ('a3.one', 'two')
        + '[[scenarios]]\nid = "a3.two"\ntests = ["fixture/three"]\nplatforms = ["linux"]\n'
        + '[[pending]]\nid = "t0.three"\ntask = "A3"\n',
    })
    assert load_registry(directory) == {
        'schema_version': 1,
        'scenarios': [
            {'id': 'a3.one', 'tests': ['fixture/two']},
            {'id': 'a3.two', 'tests': ['fixture/three'], 'platforms': ['linux']},
            {'id': 'b2.one', 'tests': ['fixture/one']},
        ],
        'pending': [{'id': 't0.three', 'task': 'A3'}],
    }


def test_loader_accepts_a_pending_only_fragment(tmp_path):
    directory = write_fragments(tmp_path, {
        'c5b.toml': 'schema_version = 1\n[[pending]]\nid = "t0.orphan-workers"\ntask = "C5"\n'})
    assert load_registry(directory)['pending'] == [{'id': 't0.orphan-workers', 'task': 'C5'}]


@pytest.mark.parametrize('name', ['notes.txt', 'A2.toml', '.hidden.toml', 'a2.TOML', 'a2.toml.bak'])
def test_loader_refuses_unexpected_entry_names(tmp_path, name):
    directory = write_fragments(tmp_path, {'base.toml': SCENARIO % ('base.one', 'one'),
                                           name: 'schema_version = 1\n'})
    with pytest.raises(ValueError, match='unexpected registry entry'):
        load_registry(directory)


def test_loader_refuses_a_nested_directory(tmp_path):
    directory = write_fragments(tmp_path, {'base.toml': SCENARIO % ('base.one', 'one')})
    (directory/'nested').mkdir()
    with pytest.raises(ValueError, match='unexpected registry entry'):
        load_registry(directory)


def test_loader_refuses_a_symbolic_link(tmp_path):
    directory = write_fragments(tmp_path, {'base.toml': SCENARIO % ('base.one', 'one')})
    outside = tmp_path/'outside.toml'
    outside.write_text(SCENARIO % ('outside.one', 'one'))
    os.symlink(outside, directory/'linked.toml')
    with pytest.raises(ValueError, match='unexpected registry entry'):
        load_registry(directory)


def test_loader_refuses_a_missing_or_empty_directory(tmp_path):
    with pytest.raises(ValueError, match='missing or not a directory'):
        load_registry(tmp_path/'absent')
    (tmp_path/'empty').mkdir()
    with pytest.raises(ValueError, match='no registry fragments'):
        load_registry(tmp_path/'empty')


@pytest.mark.parametrize(('text', 'message'), [
    ('schema_version = 2\n[[scenarios]]\nid = "x"\ntests = ["t"]\n', 'schema_version must be 1'),
    ('schema_version = true\n[[scenarios]]\nid = "x"\ntests = ["t"]\n', 'schema_version must be 1'),
    ('[[scenarios]]\nid = "x"\ntests = ["t"]\n', 'schema_version must be 1'),
    ('schema_version = 1\nextra = 1\n', 'unknown keys'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntexts = ["t"]\n', 'unknown keys'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = []\n', 'non-empty list of non-empty strings'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = "t"\n', 'non-empty list of non-empty strings'),
    ('schema_version = 1\n[[scenarios]]\nid = ""\ntests = ["t"]\n', 'non-empty string'),
    ('schema_version = 1\n[[scenarios]]\ntests = ["t"]\n', 'non-empty string'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\nplatforms = []\n', 'platforms'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\nplatforms = "darwin"\n', 'platforms'),
    ('schema_version = 1\n[[pending]]\nid = "x"\n', 'task'),
    ('schema_version = 1\n[[pending]]\nid = "x"\ntask = "A3"\nowner = "me"\n', 'unknown keys'),
    ('schema_version = 1\n', 'declares no rows'),
    ('schema_version = 1\nscenarios = 1\n', 'must be a list of tables'),
    ('schema_version = 1\nnot toml =\n', 'a3.toml'),
])
def test_loader_refuses_malformed_fragments(tmp_path, text, message):
    directory = write_fragments(tmp_path, {'a3.toml': text})
    with pytest.raises(ValueError, match=message):
        load_registry(directory)


def test_duplicate_ids_across_fragments_still_fail_in_the_checker(tmp_path):
    directory = write_fragments(tmp_path, {'a3.toml': SCENARIO % ('same', 'one'),
                                           'b2.toml': SCENARIO % ('same', 'one')})
    registry = load_registry(directory)
    assert [row['id'] for row in registry['scenarios']] == ['same', 'same']
    with pytest.raises(ValueError, match='duplicate or empty scenario id'):
        check_registry(registry, {})


def test_repository_fragments_load_with_the_single_registry_schema():
    directory = Path(__file__).resolve().parents[3]/'platform/build-v2/tests/registry'
    registry = load_registry(directory)
    assert registry['schema_version'] == 1
    assert registry['scenarios'] and all(row['tests'] for row in registry['scenarios'])


def test_cli_refuses_the_old_registry_file_flag(monkeypatch):
    monkeypatch.setattr('sys.argv', ['check_registry.py', '--registry', 'tests/registry.toml',
                                     '--listing', 'listing.json'])
    with pytest.raises(SystemExit):
        _module.main()
