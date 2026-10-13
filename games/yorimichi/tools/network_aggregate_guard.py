"""Compound QA guard with an explicitly authorized, bounded session ceiling.

Individual games retain their ordinary guards. The default aggregate is 10 GiB;
larger choices require operator authorization before launching that QA session.
"""
import argparse
from pathlib import Path

from atelier.safety.tree_guard import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--expected-start', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--limit-gib', type=int, choices=(10, 14, 16, 18), default=10)
    args = parser.parse_args()
    return run(args.pid, args.expected_start, args.report, args.duration, args.stop_file, args.limit_gib)


if __name__ == '__main__':
    raise SystemExit(main())
