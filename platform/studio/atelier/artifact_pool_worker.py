"""Private file worker; its parent owns normal guarded admission and final certification."""
import argparse


def main():
    from .artifact_pool_transfer import execute
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['publish', 'restore', 'abandon'])
    parser.add_argument('game');parser.add_argument('step')
    parser.add_argument('--invocation', required=True)
    parser.add_argument('--expected-key', required=True)
    parser.add_argument('--expected-journal', required=True)
    args = parser.parse_args()
    return execute(args.action, args.game, args.step, invocation=args.invocation,
                   expected_key=args.expected_key, expected_journal=args.expected_journal)


if __name__ == '__main__':
    raise SystemExit(main())
