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
ROW_KEYS = {'scenarios': frozenset({'id', 'tests', 'platforms'}),
            'pending': frozenset({'id', 'task'})}


def load_registry(directory: Path) -> dict:
    """@cc [owner:fontanierh,label:correctness] build-v2-registry-fragments
    The registry loader MUST take one explicit directory and MUST reject a missing or empty one.
    Every directory entry MUST be a regular, non-symbolic, lowercase TOML file named
    [a-z0-9][a-z0-9._-]*.toml; any other entry MUST fail. Each fragment MUST declare
    schema_version = 1, use only the documented keys, give every row a non-empty id and the
    section's required values, and declare at least one row. Discovery MUST merge every fragment
    in sorted filename order without deduplication, filtering or coverage policy; duplicate ids,
    missing or unmapped scenarios, ignored and filtered tests, execution evidence and the
    ten-second budget remain the checker's.
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
                elif not isinstance(row.get('task'), str) or not row['task']:
                    raise ValueError(f'{where}.task: expected a non-empty string')
                merged[section].append(dict(row))
                rows += 1
        if not rows:
            raise ValueError(f'{path.name}: fragment declares no rows')
    return merged


def check_registry(registry: dict, listing: dict, junit: ET.Element | None = None) -> dict:
    """@cc [owner:fontanierh,label:correctness] active-scenario-evidence
    Active scenarios applicable to the recorded host platform MUST name collected, unignored
    and unfiltered tests. Every collected test MUST have an applicable active scenario. Execution
    evidence MUST include each applicable test exactly once with no failures, skips or errors,
    and finite nonnegative suite time at most ten seconds. Other-platform exclusions and pending
    scenarios MUST be reported separately and MUST NOT count as passed coverage.
    """
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
    supported = {'linux', 'darwin'}
    triple = listing['rust-build-meta']['platforms']['host']['platform']['triple']
    platform = 'darwin' if triple.endswith('-apple-darwin') else 'linux' if '-linux-' in triple else None
    if platform is None:
        raise ValueError(f'unsupported recorded host platform: {triple}')
    for row in active:
        platforms = row.get('platforms', sorted(supported))
        if not isinstance(platforms, list) or not platforms or any(item not in supported for item in platforms):
            raise ValueError(f'invalid scenario platform labels: {row["id"]}')
    selected = [row for row in active if platform in row.get('platforms', supported)]
    excluded = len(active) - len(selected)
    registered = {test for row in selected for test in row['tests']}
    collected = set()
    for binary, suite in listing['rust-suites'].items():
        if suite['status'] != 'listed':
            raise ValueError(f'unlisted suite: {binary}')
        for name, case in suite['testcases'].items():
            identity = f'{binary}/{name}'
            if case['ignored'] or case['filter-match']['status'] != 'matches':
                raise ValueError(f'ignored or filtered test: {identity}')
            collected.add(identity)
    if not collected or len(collected) != listing['test-count']:
        raise ValueError('incomplete collection')
    if registered != collected:
        raise ValueError(f'registry mismatch: missing tests={sorted(registered-collected)}, '
                         f'unmapped tests={sorted(collected-registered)}')
    summary = {'active_scenarios': len(selected), 'tests': len(collected), 'pending_scenarios': len(pending),
               'platform': platform, 'platform_excluded_scenarios': excluded}
    if junit is not None:
        executed = []
        for suite in junit.findall('testsuite'):
            for case in suite.findall('testcase'):
                identity = f"{case.attrib['classname']}/{case.attrib['name']}"
                if any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped', 'flakyFailure', 'flakyError')):
                    raise ValueError(f'unsuccessful test: {identity}')
                executed.append(identity)
        if len(executed) != len(set(executed)) or set(executed) != collected:
            raise ValueError('execution does not match collection exactly once')
        elapsed = float(junit.attrib['time'])
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed > 10:
            raise ValueError(f'T0 exceeded ten-second budget or invalid timing: {elapsed}')
        summary['test_seconds'] = elapsed
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--registry-dir', type=Path, required=True)
    parser.add_argument('--listing', type=Path, required=True)
    parser.add_argument('--junit', type=Path)
    args = parser.parse_args()
    registry = load_registry(args.registry_dir)
    listing = json.loads(args.listing.read_text())
    junit = ET.parse(args.junit).getroot() if args.junit else None
    print(json.dumps(check_registry(registry, listing, junit), sort_keys=True))


if __name__ == '__main__':
    main()
