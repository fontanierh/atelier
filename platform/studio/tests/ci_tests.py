"""Run one CI group after normal pytest collection; plain pytest still runs everything."""
import argparse
import json
from pathlib import Path, PurePosixPath

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
    if path.parent == PurePosixPath('platform/studio/tests') and path.name.startswith('test_board'):
        return 'board'
    return 'studio'


class CollectionGroup:
    def __init__(self, group, report):
        self.group, self.report = group, report

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
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=GROUPS)
    parser.add_argument('--collection-report', type=Path)
    args, pytest_args = parser.parse_known_args()
    # Preserve pytest's failure, collection-error and no-tests exit codes.
    return pytest.main(pytest_args, plugins=[CollectionGroup(args.group, args.collection_report)])


if __name__ == '__main__':
    raise SystemExit(main())
