"""Check active build-v2 scenario coverage against nextest collection and execution."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import tomllib
import xml.etree.ElementTree as ET


def check_registry(registry: dict, listing: dict, junit: ET.Element | None = None) -> dict:
    """@cc [owner:fontanierh,label:correctness] active-scenario-evidence
    Active scenarios MUST name collected, unignored and unfiltered tests. Every collected test
    MUST have an active scenario. Execution evidence MUST include each test exactly once with
    no failures, skips or errors, and finite nonnegative suite time at most ten seconds.
    Pending scenarios MUST remain explicitly pending and MUST NOT count as passed coverage.
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--listing', type=Path, required=True)
    parser.add_argument('--junit', type=Path)
    args = parser.parse_args()
    registry = tomllib.loads(args.registry.read_text())
    listing = json.loads(args.listing.read_text())
    junit = ET.parse(args.junit).getroot() if args.junit else None
    print(json.dumps(check_registry(registry, listing, junit), sort_keys=True))


if __name__ == '__main__':
    main()
