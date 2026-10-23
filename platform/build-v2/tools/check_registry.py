"""Check active build-v2 scenario coverage against nextest collection and execution."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import tomllib
import xml.etree.ElementTree as ET


FRAGMENT_NAME = re.compile(r'[a-z0-9][a-z0-9._-]*\.toml')
FRAGMENT_KEYS = frozenset({'schema_version', 'scenarios', 'pending'})
# Host tiers run as separate steps of the same CI job. Native tiers are explicit exclusions:
# they never run in either step and never count as coverage.
TIER_BUDGETS = {'t0': 10.0, 't1a': 30.0}
NATIVE_TIERS = frozenset({'t1b', 't2'})
TIERS = frozenset({*TIER_BUDGETS, *NATIVE_TIERS})
SUPPORTED_PLATFORMS = frozenset({'linux', 'darwin'})
FILTER_SKIP_MESSAGE = 'Skipped: test does not match the provided expression filters'
ROW_KEYS = {'scenarios': frozenset({'id', 'tests', 'platforms', 'tier'}),
            'pending': frozenset({'id', 'task'})}


def load_registry(directory: Path) -> dict:
    """@cc [owner:fontanierh,label:correctness] build-v2-registry-fragments
    The registry loader MUST take one explicit directory and MUST reject a missing or empty one.
    Every directory entry MUST be a regular, non-symbolic, lowercase TOML file named
    [a-z0-9][a-z0-9._-]*.toml; any other entry MUST fail. Each fragment MUST declare
    schema_version = 1, use only the documented keys, give every row a non-empty id and the
    section's required values, and declare at least one row. Every active row MUST declare a tier
    of t0, t1a, t1b or t2. Discovery MUST merge every fragment in sorted filename order without
    deduplication, filtering or coverage policy; duplicate ids, missing or unmapped scenarios,
    ignored and filtered tests, execution evidence, tier assignment and each tier's time budget
    remain the checker's.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f'registry directory is missing or not a directory: {directory}')
    fragments = []
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        if entry.is_symlink() or not entry.is_file() or not FRAGMENT_NAME.fullmatch(entry.name):
            raise ValueError(f'unexpected registry entry: {entry.name}')
        fragments.append(entry)
    if not fragments:
        raise ValueError(f'no registry fragments in {directory}')

    merged = {'schema_version': 1, 'scenarios': [], 'pending': []}
    for path in fragments:
        try:
            fragment = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f'{path.name}: {error}') from error
        unknown = sorted(set(fragment) - FRAGMENT_KEYS)
        if unknown:
            raise ValueError(f'{path.name}: unknown keys {unknown}')
        if type(fragment.get('schema_version')) is not int or fragment['schema_version'] != 1:
            raise ValueError(f'{path.name}: schema_version must be 1')
        rows = 0
        for section in ('scenarios', 'pending'):
            table = fragment.get(section, [])
            if not isinstance(table, list):
                raise ValueError(f'{path.name}: {section} must be a list of tables')
            for index, row in enumerate(table):
                where = f'{path.name}: {section}[{index}]'
                if not isinstance(row, dict):
                    raise ValueError(f'{where}: expected a table')
                unknown = sorted(set(row) - ROW_KEYS[section])
                if unknown:
                    raise ValueError(f'{where}: unknown keys {unknown}')
                if not isinstance(row.get('id'), str) or not row['id']:
                    raise ValueError(f'{where}.id: expected a non-empty string')
                if section == 'scenarios':
                    tests = row.get('tests')
                    if (not isinstance(tests, list) or not tests
                            or any(not isinstance(test, str) or not test for test in tests)):
                        raise ValueError(f'{where}.tests: expected a non-empty list of non-empty strings')
                    platforms = row.get('platforms')
                    if platforms is not None and (not isinstance(platforms, list) or not platforms
                                                  or any(not isinstance(item, str) or not item
                                                         for item in platforms)):
                        raise ValueError(
                            f'{where}.platforms: expected a non-empty list of non-empty strings')
                    if not isinstance(row.get('tier'), str) or row['tier'] not in TIERS:
                        raise ValueError(f'{where}.tier: expected one of t0, t1a, t1b, t2')
                elif not isinstance(row.get('task'), str) or not row['task']:
                    raise ValueError(f'{where}.task: expected a non-empty string')
                merged[section].append(dict(row))
                rows += 1
        if not rows:
            raise ValueError(f'{path.name}: fragment declares no rows')
    return merged


def _host_platform(listing: dict) -> str:
    triple = listing['rust-build-meta']['platforms']['host']['platform']['triple']
    if triple.endswith('-apple-darwin'):
        return 'darwin'
    if '-linux-' in triple:
        return 'linux'
    raise ValueError(f'unsupported recorded host platform: {triple}')


def _iter_cases(listing: dict, filtered: bool = False):
    """Yield (identity, binary-id, name, case).

    A full collection must list every suite. A filtered listing reports a suite with no
    matching tests as skipped with no testcases; that is expected, and any other skipped shape
    still fails.
    """
    for binary, suite in listing['rust-suites'].items():
        status = suite['status']
        if filtered and status == 'skipped':
            if suite['testcases']:
                raise ValueError(f'skipped suite carries tests: {binary}')
            continue
        if status != 'listed':
            raise ValueError(f'unlisted suite: {binary}')
        binary_id = suite.get('binary-id', binary)
        for name, case in suite['testcases'].items():
            yield f'{binary}/{name}', binary_id, name, case


def _plan(registry: dict, listing: dict) -> dict:
    """Validate the registry against one full collection and assign host tests to tiers."""
    if registry.get('schema_version') != 1:
        raise ValueError('unsupported registry version')
    active = registry['scenarios']
    pending = registry.get('pending', [])
    ids = [row['id'] for row in [*active, *pending]]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError('duplicate or empty scenario id')
    if any(not row.get('task') for row in pending):
        raise ValueError('pending scenario must name its implementation task')
    if not active or any(not row.get('tests') for row in active):
        raise ValueError('active scenario must name tests')
    platform = _host_platform(listing)
    for row in active:
        if row.get('tier') not in TIERS:
            raise ValueError(f'scenario {row["id"]} must declare a tier of t0, t1a, t1b or t2')
        platforms = row.get('platforms', sorted(SUPPORTED_PLATFORMS))
        if (not isinstance(platforms, list) or not platforms
                or any(item not in SUPPORTED_PLATFORMS for item in platforms)):
            raise ValueError(f'invalid scenario platform labels: {row["id"]}')
    owners: dict[str, list[str]] = {}
    for row in active:
        for test in row['tests']:
            owners.setdefault(test, []).append(row['id'])
    overlap = {test: rows for test, rows in owners.items() if len(rows) > 1}
    if overlap:
        raise ValueError(f'overlapping scenario mappings: {overlap}')
    selected = [row for row in active
                if platform in row.get('platforms', sorted(SUPPORTED_PLATFORMS))]
    expected = {tier: set() for tier in TIER_BUDGETS}
    ci_owner: dict[str, str] = {}
    for row in selected:
        if row['tier'] in TIER_BUDGETS:
            for test in row['tests']:
                expected[row['tier']].add(test)
                ci_owner[test] = row['tier']
    native = {test: row['id'] for row in selected if row['tier'] in NATIVE_TIERS
              for test in row['tests']}
    collected = set()
    native_collected = set()
    coordinates = {}
    listed = 0
    for identity, binary_id, name, case in _iter_cases(listing):
        listed += 1
        matched = case['filter-match']['status'] == 'matches'
        if identity in native:
            if matched and not case['ignored']:
                native_collected.add(identity)
                coordinates[identity] = (binary_id, name)
            continue
        if case['ignored']:
            raise ValueError(f'ignored test: {identity}')
        if not matched:
            raise ValueError(f'filtered test: {identity}')
        if identity not in ci_owner:
            raise ValueError(f'unmapped test: {identity}')
        collected.add(identity)
        coordinates[identity] = (binary_id, name)
    if listing['test-count'] != listed:
        raise ValueError('incomplete collection')
    missing = set(ci_owner) - collected
    if missing:
        raise ValueError(f'registry mismatch: missing tests={sorted(missing)}')
    return {'platform': platform, 'expected': expected, 'native': native,
            'native_collected': native_collected, 'collected': collected,
            'coordinates': coordinates,
            'selected': selected, 'excluded': len(active) - len(selected),
            'native_rows': [row for row in selected if row['tier'] in NATIVE_TIERS]}


def _executed(junit: ET.Element, other_tier, native) -> tuple[list[str], list[str], list[str]]:
    """Split one tier's JUnit into passes and documented other-tier and native filter skips."""
    executed = []
    excluded_other = []
    excluded_native = []
    for suite in junit.findall('testsuite'):
        for case in suite.findall('testcase'):
            identity = f"{case.attrib['classname']}/{case.attrib['name']}"
            if any(case.find(tag) is not None
                   for tag in ('failure', 'error', 'flakyFailure', 'flakyError')):
                raise ValueError(f'unsuccessful test: {identity}')
            skip = case.find('skipped')
            if skip is None:
                executed.append(identity)
                continue
            if skip.attrib.get('message') != FILTER_SKIP_MESSAGE:
                raise ValueError(f'skipped test without the filter message: {identity}')
            if identity in other_tier:
                excluded_other.append(identity)
            elif identity in native:
                excluded_native.append(identity)
            else:
                raise ValueError(
                    f'skipped test is neither another host tier nor a declared native tier: {identity}')
    if len(excluded_other) != len(set(excluded_other)):
        raise ValueError('an excluded test was reported more than once')
    if len(excluded_native) != len(set(excluded_native)):
        raise ValueError('an excluded native test was reported more than once')
    return executed, excluded_other, excluded_native


def check_registry(registry: dict, listing: dict, *,
                   results: dict[str, ET.Element] | None = None,
                   tier_listings: dict[str, dict] | None = None) -> dict:
    """@cc [owner:fontanierh,label:correctness] active-scenario-evidence
    Active scenarios MUST name collected, unignored tests, and every collected test MUST map to
    exactly one host-applicable active scenario. Each scenario's tier MUST select exactly one host
    CI step (t0 or t1a); native tiers (t1b, t2) and other-platform scenarios MUST be reported as
    explicit exclusions that never count as passed coverage. A tier's own listing MUST match that
    tier's tests exactly. Execution evidence MUST include every host CI test exactly once, with no
    failures, errors, duplicate runs or skips other than nextest's documented filter exclusion of
    tests mapped to another host tier or declared native (t1b, t2), and finite nonnegative suite
    time within each tier's budget: ten seconds for t0 and thirty for t1a. An excluded test MUST
    NOT count as a pass.
    """
    plan = _plan(registry, listing)
    expected = plan['expected']
    pending = registry.get('pending', [])
    tier_listings = tier_listings or {}
    results = results or {}
    for tier in (*tier_listings, *results):
        if tier not in TIER_BUDGETS:
            raise ValueError(f'{tier} is not a host CI tier')
    selected = plan['selected']
    summary = {
        'active_scenarios': len(selected),
        'tests': len(plan['collected']),
        'pending_scenarios': len(pending),
        'platform': plan['platform'],
        'platform_excluded_scenarios': plan['excluded'],
        'native_excluded_scenarios': len(plan['native_rows']),
        'native_excluded_tests': len(plan['native_collected']),
        'tiers': {tier: {'scenarios': sum(1 for row in selected if row['tier'] == tier),
                         'tests': len(tests)}
                  for tier, tests in expected.items()},
    }
    for tier, filtered in tier_listings.items():
        filtered_platform = _host_platform(filtered)
        if filtered_platform != plan['platform']:
            raise ValueError(f'{tier} listing host {filtered_platform} does not match the '
                             f'collection host {plan["platform"]}')
        matched = set()
        for identity, _binary_id, _name, case in _iter_cases(filtered, filtered=True):
            if case['filter-match']['status'] != 'matches':
                continue
            if case['ignored']:
                raise ValueError(f'ignored test in {tier} listing: {identity}')
            matched.add(identity)
        if matched != expected[tier]:
            raise ValueError(f'{tier} listing mismatch: '
                             f'missing tests={sorted(expected[tier] - matched)}, '
                             f'extra tests={sorted(matched - expected[tier])}')
        summary['tiers'][tier]['listed'] = len(matched)
    executed_all: list[str] = []
    all_ci = set().union(*expected.values())
    for tier, junit in results.items():
        executed, excluded_other, excluded_native = _executed(
            junit, all_ci - expected[tier], set(plan['native']))
        if len(executed) != len(set(executed)):
            raise ValueError(f'{tier} executed a test more than once')
        if set(executed) != expected[tier]:
            raise ValueError(f'{tier} execution mismatch: '
                             f'missing tests={sorted(expected[tier] - set(executed))}, '
                             f'extra tests={sorted(set(executed) - expected[tier])}')
        elapsed = float(junit.attrib['time'])
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed > TIER_BUDGETS[tier]:
            raise ValueError(f'{tier} exceeded its time budget or has invalid timing: {elapsed}')
        summary['tiers'][tier]['test_seconds'] = elapsed
        summary['tiers'][tier]['excluded_other_tier'] = len(excluded_other)
        summary['tiers'][tier]['excluded_native'] = len(excluded_native)
        executed_all.extend(executed)
    if results:
        if set(results) != set(TIER_BUDGETS):
            raise ValueError('execution evidence must cover every host CI tier: '
                             f'{sorted(results)}')
        if len(executed_all) != len(set(executed_all)):
            raise ValueError('a test was executed in more than one tier')
    return summary


def _token(text: str) -> str:
    """Escape one unquoted nextest filter token; the DSL has no quoted strings."""
    if any(character in text for character in '( \t\n\r"\''):
        raise ValueError(f'test identity cannot be expressed as a nextest token: {text!r}')
    return (text.replace('\\', '\\\\').replace('/', '\\/')
            .replace(')', '\\)').replace(',', '\\,'))


def nextest_filter(tests, coordinates=None) -> str:
    """Return a pinned nextest filter expression selecting exactly these test identities."""
    by_binary: dict[str, list[str]] = {}
    for identity in sorted(tests):
        if coordinates and identity in coordinates:
            binary, name = coordinates[identity]
        else:
            binary, name = identity.split('/', 1)
        by_binary.setdefault(binary, []).append(name)
    if not by_binary:
        return 'none()'
    groups = []
    for binary in sorted(by_binary):
        names = ' | '.join(f'test(={_token(name)})' for name in by_binary[binary])
        groups.append(f'binary_id(={_token(binary)}) & ({names})')
    return ' | '.join(f'({group})' for group in groups)


def _tier_path(text: str) -> tuple[str, Path]:
    tier, separator, path = text.partition('=')
    if not separator or tier not in TIER_BUDGETS or not path:
        raise argparse.ArgumentTypeError(f'expected TIER=PATH for t0 or t1a, got {text!r}')
    return tier, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--registry-dir', type=Path, required=True)
    parser.add_argument('--listing', type=Path, required=True)
    parser.add_argument('--plan-dir', type=Path,
                        help='write one <tier>.filter nextest expression derived from the registry')
    parser.add_argument('--tier-listing', action='append', default=[], type=_tier_path,
                        metavar='TIER=PATH')
    parser.add_argument('--result', action='append', default=[], type=_tier_path, metavar='TIER=PATH')
    args = parser.parse_args()
    registry = load_registry(args.registry_dir)
    listing = json.loads(args.listing.read_text())
    tier_listings = dict(args.tier_listing)
    results = dict(args.result)
    if len(tier_listings) != len(args.tier_listing) or len(results) != len(args.result):
        parser.error('each tier may appear only once in --tier-listing and --result')
    summary = check_registry(
        registry, listing,
        tier_listings={tier: json.loads(path.read_text()) for tier, path in tier_listings.items()},
        results={tier: ET.parse(path).getroot() for tier, path in results.items()})
    if args.plan_dir:
        plan = _plan(registry, listing)
        args.plan_dir.mkdir(parents=True, exist_ok=True)
        for tier, tests in plan['expected'].items():
            (args.plan_dir/f'{tier}.filter').write_text(
                nextest_filter(tests, plan['coordinates']) + '\n')
        (args.plan_dir/'plan.json').write_text(json.dumps(
            {'platform': plan['platform'],
             'tiers': {tier: sorted(tests) for tier, tests in plan['expected'].items()},
             'native_excluded': sorted(plan['native'])}, indent=2) + '\n')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()

