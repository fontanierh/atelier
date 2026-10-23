"""The v2 CI tier registry fails closed on missing, misclassified or skipped evidence."""
import importlib.util
import json
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
nextest_filter = _module.nextest_filter


SCENARIO = ('schema_version = 1\n[[scenarios]]\nid = "%s"\ntests = ["fixture/%s"]\n'
            'tier = "t0"\n')
LINUX = 'x86_64-unknown-linux-gnu'
DARWIN = 'aarch64-apple-darwin'


def listing_of(*tests, triple=LINUX, ignored=()):
    suites = {}
    for identity in tests:
        binary, name = identity.split('/', 1)
        suite = suites.setdefault(binary, {'status': 'listed', 'testcases': {}})
        suite['testcases'][name] = {'ignored': identity in ignored,
                                    'filter-match': {'status': 'matches'}}
    return {'rust-build-meta': {'platforms': {'host': {'platform': {'triple': triple}}}},
            'test-count': len(tests), 'rust-suites': suites}


def junit_of(*identities, seconds=0.1):
    root = ET.Element('testsuites', time=str(seconds))
    suites = {}
    for identity in identities:
        binary, name = identity.split('/', 1)
        suites.setdefault(binary, []).append(name)
    for binary, names in suites.items():
        suite = ET.SubElement(root, 'testsuite', name=binary)
        for name in names:
            ET.SubElement(suite, 'testcase', classname=binary, name=name)
    return root


def suite_of(junit, binary):
    for suite in junit.findall('testsuite'):
        if suite.attrib['name'] == binary:
            return suite
    raise AssertionError(f'no suite {binary}')


def case_of(junit, identity):
    binary, name = identity.split('/', 1)
    for case in suite_of(junit, binary).findall('testcase'):
        if case.attrib['name'] == name:
            return case
    raise AssertionError(f'no case {identity}')


def evidence():
    registry = {'schema_version': 1,
                'scenarios': [{'id': 'one', 'tests': ['fixture/test'], 'tier': 't0'}],
                'pending': [{'id': 'future', 'task': 'A8'}]}
    return registry, listing_of('fixture/test'), junit_of('fixture/test')


def test_active_coverage_and_pending_are_reported_separately():
    registry, listing, junit = evidence()
    assert check_registry(registry, listing) == {
        'active_scenarios': 1, 'tests': 1, 'pending_scenarios': 1, 'platform': 'linux',
        'platform_excluded_scenarios': 0, 'native_excluded_scenarios': 0,
        'native_excluded_tests': 0,
        'tiers': {'t0': {'scenarios': 1, 'tests': 1}, 't1a': {'scenarios': 0, 'tests': 0}}}
    summary = check_registry(registry, listing, results={
        't0': junit, 't1a': ET.fromstring('<testsuites time="0.0" />')})
    assert summary['tiers']['t0']['test_seconds'] == 0.1
    assert summary['tiers']['t1a']['test_seconds'] == 0.0


@pytest.mark.parametrize('mutation', ['unmapped', 'missing', 'ignored', 'filtered', 'unlisted',
                                      'duplicate-id', 'empty', 'count', 'no-tier'])
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
    elif mutation == 'no-tier':
        del registry['scenarios'][0]['tier']
    else:
        listing['test-count'] = 2
    with pytest.raises(ValueError):
        check_registry(registry, listing)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'skipped', 'failure', 'error',
                                      'slow', 'nan', 'negative'])
def test_registry_refuses_incomplete_or_slow_execution(mutation):
    registry, listing, junit = evidence()
    if mutation == 'missing':
        suite_of(junit, 'fixture').remove(case_of(junit, 'fixture/test'))
    elif mutation == 'duplicate':
        ET.SubElement(suite_of(junit, 'fixture'), 'testcase', classname='fixture', name='test')
    elif mutation in ('skipped', 'failure', 'error'):
        ET.SubElement(case_of(junit, 'fixture/test'), mutation)
    else:
        junit.set('time', {'slow': '10.01', 'nan': 'NaN', 'negative': '-1'}[mutation])
    with pytest.raises(ValueError):
        check_registry(registry, listing, results={
            't0': junit, 't1a': ET.fromstring('<testsuites time="0.0" />')})


def test_each_tier_has_its_own_budget():
    registry, listing, _ = evidence()
    with pytest.raises(ValueError, match='t1a exceeded its time budget'):
        check_registry(registry, listing, results={
            't0': junit_of('fixture/test', seconds=0.1),
            't1a': ET.fromstring('<testsuites time="30.01" />')})


def two_tier_evidence():
    registry = {'schema_version': 1, 'pending': [], 'scenarios': [
        {'id': 'one', 'tests': ['fixture/test'], 'tier': 't0'},
        {'id': 'two', 'tests': ['fixture/python'], 'tier': 't1a'}]}
    return registry, listing_of('fixture/test', 'fixture/python')


def skipped_case(junit, suite_name, name, message=None):
    case = ET.SubElement(suite_of(junit, suite_name), 'testcase', classname=suite_name, name=name)
    ET.SubElement(case, 'skipped',
                  message=_module.FILTER_SKIP_MESSAGE if message is None else message)


def test_another_tiers_filter_exclusion_is_accepted_but_never_a_pass():
    registry, listing = two_tier_evidence()
    t0 = junit_of('fixture/test')
    skipped_case(t0, 'fixture', 'python')
    summary = check_registry(registry, listing, results={
        't0': t0, 't1a': junit_of('fixture/python')})
    assert summary['tiers']['t0'] == {'scenarios': 1, 'tests': 1, 'test_seconds': 0.1,
                                      'excluded_other_tier': 1, 'excluded_native': 0}


@pytest.mark.parametrize(('name', 'message', 'error'), [
    ('python', 'Skipped: something else', 'without the filter message'),
    ('ghost', None, 'neither another host tier'),
    ('test', None, 'neither another host tier'),
])
def test_a_skip_that_is_not_another_tiers_filter_exclusion_fails(name, message, error):
    registry, listing = two_tier_evidence()
    t0 = junit_of('fixture/test')
    skipped_case(t0, 'fixture', name, message)
    with pytest.raises(ValueError, match=error):
        check_registry(registry, listing, results={
            't0': t0, 't1a': junit_of('fixture/python')})


def test_a_declared_native_test_may_be_filter_excluded_and_is_never_a_pass():
    registry, listing = two_tier_evidence()
    registry['scenarios'].append({'id': 'native', 'tests': ['fixture/blender'], 'tier': 't1b'})
    listing['rust-suites']['fixture']['testcases']['blender'] = {
        'ignored': False, 'filter-match': {'status': 'matches'}}
    listing['test-count'] = 3
    t0 = junit_of('fixture/test')
    skipped_case(t0, 'fixture', 'blender')
    t1a = junit_of('fixture/python')
    skipped_case(t1a, 'fixture', 'blender')
    skipped_case(t1a, 'fixture', 'test')
    summary = check_registry(registry, listing, results={'t0': t0, 't1a': t1a})
    assert summary['tiers']['t0'] == {'scenarios': 1, 'tests': 1, 'test_seconds': 0.1,
                                      'excluded_other_tier': 0, 'excluded_native': 1}
    assert summary['tiers']['t1a']['excluded_native'] == 1
    assert summary['tiers']['t1a']['excluded_other_tier'] == 1
    assert summary['native_excluded_tests'] == 1


def test_a_native_test_that_passes_in_a_host_tier_is_a_mismatch():
    registry, listing = two_tier_evidence()
    registry['scenarios'].append({'id': 'native', 'tests': ['fixture/blender'], 'tier': 't2'})
    listing['rust-suites']['fixture']['testcases']['blender'] = {
        'ignored': False, 'filter-match': {'status': 'matches'}}
    listing['test-count'] = 3
    with pytest.raises(ValueError, match='t0 execution mismatch'):
        check_registry(registry, listing, results={
            't0': junit_of('fixture/test', 'fixture/blender'),
            't1a': junit_of('fixture/python')})


def test_execution_evidence_must_cover_every_host_tier():
    registry, listing, junit = evidence()
    with pytest.raises(ValueError, match='every host CI tier'):
        check_registry(registry, listing, results={'t0': junit})


def test_platform_exclusions_are_explicit_and_not_passed_coverage():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'mac-only', 'tests': ['fixture/apfs'],
                                  'platforms': ['darwin'], 'tier': 't0'})
    summary = check_registry(registry, listing)
    assert summary['active_scenarios'] == 1
    assert summary['platform_excluded_scenarios'] == 1
    listing['rust-build-meta']['platforms']['host']['platform']['triple'] = DARWIN
    with pytest.raises(ValueError, match='registry mismatch'):
        check_registry(registry, listing)
    listing['rust-suites']['fixture']['testcases']['apfs'] = {
        'ignored': False, 'filter-match': {'status': 'matches'}}
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


def test_mixed_tiers_inside_one_binary_are_split_per_test():
    t0_test = 'atelier-build-v2/python_backend::tests::starts_in_process'
    t1a_test = 'atelier-build-v2/python_backend::tests::runs_a_sandboxed_job'
    registry = {'schema_version': 1, 'pending': [], 'scenarios': [
        {'id': 't0.in-process', 'tests': [t0_test], 'tier': 't0'},
        {'id': 't1a.sandboxed', 'tests': [t1a_test], 'tier': 't1a'}]}
    listing = listing_of(t0_test, t1a_test)
    assert check_registry(registry, listing)['tiers'] == {
        't0': {'scenarios': 1, 'tests': 1}, 't1a': {'scenarios': 1, 'tests': 1}}
    summary = check_registry(registry, listing, results={
        't0': junit_of(t0_test), 't1a': junit_of(t1a_test)})
    assert summary['tiers']['t1a']['tests'] == 1
    assert nextest_filter({t1a_test}) == (
        '(binary_id(=atelier-build-v2) & '
        '(test(=python_backend::tests::runs_a_sandboxed_job)))')
    with pytest.raises(ValueError, match='t0 listing mismatch'):
        check_registry(registry, listing, tier_listings={'t0': listing_of(t0_test, t1a_test)})
    with pytest.raises(ValueError, match='t0 execution mismatch'):
        check_registry(registry, listing, results={
            't0': junit_of(t0_test, t1a_test), 't1a': junit_of(t1a_test)})
    with pytest.raises(ValueError, match='t1a execution mismatch'):
        check_registry(registry, listing, results={
            't0': junit_of(t0_test), 't1a': junit_of(t0_test)})


def test_an_omitted_tier_listing_test_fails():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'two', 'tests': ['fixture/second'], 'tier': 't0'})
    listing = listing_of('fixture/test', 'fixture/second')
    with pytest.raises(ValueError, match='t0 listing mismatch'):
        check_registry(registry, listing, tier_listings={'t0': listing_of('fixture/test')})


def test_a_tier_listing_from_another_host_is_refused():
    registry, listing, _ = evidence()
    with pytest.raises(ValueError, match='listing host darwin does not match the collection host linux'):
        check_registry(registry, listing, tier_listings={'t0': listing_of('fixture/test', triple=DARWIN)})


def test_a_filtered_listing_may_report_only_empty_skipped_suites():
    registry, listing, _ = evidence()
    filtered = listing_of('fixture/test')
    filtered['rust-suites']['unmatched'] = {'status': 'skipped', 'testcases': {}}
    summary = check_registry(registry, listing, tier_listings={'t0': filtered})
    assert summary['tiers']['t0']['listed'] == 1


def test_a_filtered_listing_refuses_skipped_tests_and_unknown_statuses():
    registry, listing, _ = evidence()
    filtered = listing_of('fixture/test')
    filtered['rust-suites']['unmatched'] = {'status': 'skipped', 'testcases': {
        'stale': {'ignored': False, 'filter-match': {'status': 'mismatch'}}}}
    with pytest.raises(ValueError, match='skipped suite carries tests'):
        check_registry(registry, listing, tier_listings={'t0': filtered})
    filtered['rust-suites']['unmatched'] = {'status': 'failed', 'testcases': {}}
    with pytest.raises(ValueError, match='unlisted suite'):
        check_registry(registry, listing, tier_listings={'t0': filtered})


def test_overlapping_tier_assignment_is_refused():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'two', 'tests': ['fixture/test'], 'tier': 't1a'})
    with pytest.raises(ValueError, match='overlapping scenario mappings'):
        check_registry(registry, listing)


def test_native_tiers_are_explicit_exclusions_never_coverage():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'native.blender', 'tests': ['fixture/blender'],
                                  'tier': 't1b'})
    listing['rust-suites']['fixture']['testcases']['blender'] = {
        'ignored': True, 'filter-match': {'status': 'matches'}}
    listing['test-count'] = 2
    summary = check_registry(registry, listing)
    assert summary['native_excluded_scenarios'] == 1
    assert summary['native_excluded_tests'] == 0
    assert summary['tiers']['t0'] == {'scenarios': 1, 'tests': 1}
    with pytest.raises(ValueError, match='not a host CI tier'):
        check_registry(registry, listing, results={'t1b': ET.fromstring('<testsuites time="0" />')})


def test_a_native_test_is_never_required_in_a_host_tier_run():
    registry, listing, _ = evidence()
    registry['scenarios'].append({'id': 'native.unreal', 'tests': ['fixture/unreal'],
                                  'tier': 't2'})
    assert check_registry(registry, listing)['native_excluded_scenarios'] == 1
    with pytest.raises(ValueError, match='t1a listing mismatch'):
        check_registry(registry, listing, tier_listings={'t1a': listing_of('fixture/unreal')})


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
        + 'tier = "t1a"\n'
        + '[[pending]]\nid = "t0.three"\ntask = "A3"\n',
    })
    assert load_registry(directory) == {
        'schema_version': 1,
        'scenarios': [
            {'id': 'a3.one', 'tests': ['fixture/two'], 'tier': 't0'},
            {'id': 'a3.two', 'tests': ['fixture/three'], 'platforms': ['linux'], 'tier': 't1a'},
            {'id': 'b2.one', 'tests': ['fixture/one'], 'tier': 't0'},
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
    ('schema_version = 2\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\n',
     'schema_version must be 1'),
    ('schema_version = true\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\n',
     'schema_version must be 1'),
    ('[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\n', 'schema_version must be 1'),
    ('schema_version = 1\nextra = 1\n', 'unknown keys'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntexts = ["t"]\n', 'unknown keys'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\nkind = "unit"\n',
     'unknown keys'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = []\ntier = "t0"\n',
     'non-empty list of non-empty strings'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = "t"\ntier = "t0"\n',
     'non-empty list of non-empty strings'),
    ('schema_version = 1\n[[scenarios]]\nid = ""\ntests = ["t"]\ntier = "t0"\n',
     'non-empty string'),
    ('schema_version = 1\n[[scenarios]]\ntests = ["t"]\ntier = "t0"\n', 'non-empty string'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\nplatforms = []\n',
     'platforms'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "t0"\nplatforms = "darwin"\n',
     'platforms'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\n', 'tier'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = "fast"\n', 'tier'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = 1\n', 'tier'),
    ('schema_version = 1\n[[scenarios]]\nid = "x"\ntests = ["t"]\ntier = ""\n', 'tier'),
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


def test_repository_fragments_load_with_the_tiered_schema():
    directory = Path(__file__).resolve().parents[3]/'platform/build-v2/tests/registry'
    registry = load_registry(directory)
    assert registry['schema_version'] == 1
    assert registry['scenarios'] and all(row['tests'] for row in registry['scenarios'])
    assert all(row['tier'] in {'t0', 't1a', 't1b', 't2'} for row in registry['scenarios'])
    # One pinned sentinel: the real Python op rows must stay T1a, so a mass re-tiering is caught.
    py_data = [row for row in registry['scenarios'] if row['id'].startswith('d1.py_data.')]
    assert len(py_data) == 8 and all(row['tier'] == 't1a' for row in py_data)
    # The tier the checker collects is the tier the fragments declare on this host.
    applicable = [row for row in registry['scenarios']
                  if 'linux' in row.get('platforms', ['linux', 'darwin'])]
    listing = listing_of(*(test for row in applicable for test in row['tests']), triple=LINUX)
    plan = _module._plan(registry, listing)
    declared = {}
    for row in applicable:
        declared.setdefault(row['tier'], set()).update(row['tests'])
    assert plan['expected']['t0'] == declared.get('t0', set())
    assert plan['expected']['t1a'] == declared.get('t1a', set())
    assert set(plan['native']) == declared.get('t1b', set()) | declared.get('t2', set())


def test_cli_writes_one_filter_per_tier_from_the_registry(tmp_path, monkeypatch, capsys):
    directory = write_fragments(tmp_path, {'tiers.toml': SCENARIO % ('one', 'test')
                                           + '[[scenarios]]\nid = "two"\ntests = ["fixture/python"]\n'
                                           + 'tier = "t1a"\n'})
    listing_path = tmp_path/'listing.json'
    listing_path.write_text(json.dumps(listing_of('fixture/test', 'fixture/python')))
    plan = tmp_path/'plan'
    monkeypatch.setattr('sys.argv', ['check_registry.py', '--registry-dir', str(directory),
                                     '--listing', str(listing_path), '--plan-dir', str(plan)])
    _module.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary['tests'] == 2
    assert (plan/'t0.filter').read_text() == '(binary_id(=fixture) & (test(=test)))\n'
    assert (plan/'t1a.filter').read_text() == '(binary_id(=fixture) & (test(=python)))\n'
    assert json.loads((plan/'plan.json').read_text())['tiers']['t1a'] == ['fixture/python']


def test_the_filter_uses_the_binary_id_recorded_in_the_listing():
    identity = 'atelier-build-v2/checkout_locks::tests::lock'
    listing = listing_of(identity)
    listing['rust-suites']['atelier-build-v2']['binary-id'] = 'atelier-build-v2::lib'
    registry, _, _ = evidence()
    registry['scenarios'][0]['tests'] = [identity]
    assert check_registry(registry, listing)['tests'] == 1
    plan = _module._plan(registry, listing)
    assert plan['coordinates'][identity] == ('atelier-build-v2::lib', 'checkout_locks::tests::lock')
    assert nextest_filter({identity}, plan['coordinates']) == (
        '(binary_id(=atelier-build-v2::lib) & (test(=checkout_locks::tests::lock)))')


def test_filter_tokens_escape_the_documented_dsl_characters():
    backslash = chr(92)
    assert nextest_filter({'fixture/plain/name'}) == (
        '(binary_id(=fixture) & (test(=plain' + backslash + '/name)))')
    assert nextest_filter({'fixture/a,b)c'}) == (
        '(binary_id(=fixture) & (test(=a' + backslash + ',b' + backslash + ')c)))')
    with pytest.raises(ValueError, match='cannot be expressed'):
        nextest_filter({'fixture/has space'})


def test_cli_refuses_the_old_registry_file_flag(monkeypatch):
    monkeypatch.setattr('sys.argv', ['check_registry.py', '--registry', 'tests/registry.toml',
                                     '--listing', 'listing.json'])
    with pytest.raises(SystemExit):
        _module.main()

