"""Run one CI group after normal pytest collection; plain pytest still runs everything."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

GROUPS = ('board', 'studio', 'games')


def group_for(nodeid):
    """@cc [owner:fontanierh,label:correctness] complete-ci-partition
    Every collected node MUST belong to exactly one CI group. Tests outside the two explicit
    groups MUST stay in the studio group, so new test locations cannot silently lose coverage.
    """
    path = PurePosixPath(nodeid.split('::', 1)[0])
    if path.parts[0] == 'games':
        return 'games'
    if path.parent in {PurePosixPath('platform/studio/tests'), PurePosixPath('platform/harness/tests')} and path.name.startswith('test_board'):
        return 'board'
    return 'studio'


class CollectionGroup:
    def __init__(self, group, report, worker_index=0, worker_count=1):
        self.group, self.report = group, report
        self.worker_index, self.worker_count = worker_index, worker_count
        self.empty_shard = False

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        selected, deselected = [], []
        for item in items:
            (selected if group_for(item.nodeid) == self.group else deselected).append(item)
        if self.report:
            self.report.parent.mkdir(parents=True, exist_ok=True)
            self.report.write_text(json.dumps({
                'group': self.group,
                'collected': [item.nodeid for item in items],
                'selected': [item.nodeid for item in selected],
            }, indent=2) + '\n')
        if self.worker_count > 1 and selected:
            by_file = {}
            for item in selected:
                by_file.setdefault(item.nodeid.split('::', 1)[0], []).append(item)
            loads = [0] * self.worker_count
            assigned_files = set()
            for file_key, file_items in sorted(by_file.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                target = min(range(self.worker_count), key=loads.__getitem__)
                loads[target] += max(len(file_items), 1)
                if target == self.worker_index:
                    assigned_files.add(file_key)
            shard_selected = []
            for item in selected:
                (shard_selected if item.nodeid.split('::', 1)[0] in assigned_files else deselected).append(item)
            self.empty_shard = not shard_selected
            selected = shard_selected
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def _extract_junitxml(pytest_args):
    remaining = []
    junit_path = None
    i = 0
    while i < len(pytest_args):
        arg = pytest_args[i]
        if arg.startswith('--junitxml='):
            junit_path = Path(arg.split('=', 1)[1])
        elif arg == '--junitxml' and i + 1 < len(pytest_args):
            junit_path = Path(pytest_args[i + 1])
            i += 1
        else:
            remaining.append(arg)
        i += 1
    return junit_path, remaining


def _merge_junitxml(junit_path, worker_paths):
    existing = [p for p in worker_paths if p.exists()]
    if not existing:
        return
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element('testsuite', {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '0', 'time': '0.0'})
    totals = {'errors': 0, 'failures': 0, 'skipped': 0, 'tests': 0}
    max_time = 0.0
    for path in existing:
        tree = ET.parse(path)
        root = tree.getroot()
        suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
        for s in suites:
            for key in totals:
                totals[key] += int(s.attrib.get(key, '0'))
            max_time = max(max_time, float(s.attrib.get('time', '0') or 0.0))
            for tc in s.findall('testcase'):
                suite.append(tc)
        path.unlink(missing_ok=True)
    for key, val in totals.items():
        suite.set(key, str(val))
    suite.set('time', f'{max_time:.3f}')
    root = ET.Element('testsuites')
    root.append(suite)
    ET.ElementTree(root).write(junit_path, encoding='utf-8', xml_declaration=True)


def _resolve_workers(spec):
    if spec == 'auto':
        return max(1, min(os.cpu_count() or 1, 4))
    return max(1, int(spec))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=GROUPS)
    parser.add_argument('--collection-report', type=Path)
    parser.add_argument('--workers', default='1')
    parser.add_argument('--worker-index', type=int, default=0)
    parser.add_argument('--worker-count', type=int, default=1)
    args, pytest_args = parser.parse_known_args()
    workers = _resolve_workers(args.workers)
    if workers > 1 and args.worker_count == 1:
        junit_path, base_pytest_args = _extract_junitxml(pytest_args)
        procs = []
        worker_xmls = []
        for idx in range(workers):
            cmd = [sys.executable, str(Path(__file__).resolve()), args.group,
                   '--worker-index', str(idx), '--worker-count', str(workers)]
            if idx == 0 and args.collection_report:
                cmd.extend(['--collection-report', str(args.collection_report)])
            worker_args = list(base_pytest_args)
            if junit_path is not None:
                w_xml = junit_path.with_name(f'{junit_path.stem}.worker-{idx}{junit_path.suffix}')
                worker_xmls.append(w_xml)
                worker_args.append(f'--junitxml={w_xml}')
            procs.append(subprocess.Popen(cmd + worker_args))
        codes = [p.wait() for p in procs]
        if junit_path is not None:
            _merge_junitxml(junit_path, worker_xmls)
        for code in codes:
            if code != 0:
                return code
        return 0
    # Preserve pytest's failure, collection-error and no-tests exit codes.
    plugin = CollectionGroup(args.group, args.collection_report, args.worker_index, args.worker_count)
    code = int(pytest.main(pytest_args, plugins=[plugin]))
    if code == 5 and plugin.empty_shard:
        return 0
    return code


if __name__ == '__main__':
    raise SystemExit(main())
