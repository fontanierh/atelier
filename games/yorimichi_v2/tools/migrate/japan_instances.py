"""@cc [owner:fontanierh,label:correctness] yorimichi-v2-single-writer
The 41 Japan material instances held by the seven adopted records adopted/japan/materials/{bark, buildings, foliage,
ground, rock-concrete, sky-wind, water}, planned as material-instance records (one per adopted record) from what the
donor scripts write (small_instances.expected_japan), each agreeing with the committed editor read
(docs/inventory/small-families-reads/instances/japan.json), base-property overrides included.

    uv run python games/yorimichi_v2/tools/migrate/japan_instances.py              # plan: agreement and the records
    uv run python games/yorimichi_v2/tools/migrate/japan_instances.py --paths      # claim paths (lock or path), scopes
    uv run python games/yorimichi_v2/tools/migrate/japan_instances.py --claim TASK # the one journaled write

The write is small_families.claim_ops over these records only: the new records, each adopted record that gives up every
package deleted with its verified.json, the folder's units.json without the moved packages, and every record that
references a moved adopted record rewritten to name the new one. A held instance stays in its adopted record. Nothing is
imported here; tools/import/run.py imports the records under the claim.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import small_families as sf  # noqa: E402
import small_instances as si  # noqa: E402

FAMILY = 'japan'


def plan(game: Path = sf.GAME) -> list:
    """The material-instance records for the agreeing Japan instances (the donor is not read: its values are tabled)."""
    return sf.instance_records(game, None, {}, families=(FAMILY,))


def held() -> dict:
    return {p: v['held'] for p, v in si.agreement(FAMILY, None).items() if not v['agree']}


def ops(game: Path = sf.GAME) -> dict:
    return sf.claim_ops(game, None, plan(game))


def print_paths(game: Path) -> None:
    result = ops(game)
    paths = sorted(set(result['writes']) | set(result['deletes']))
    full = [f'{sf.GAME_REL}/{rel}' for rel in paths]
    locks = sf.locked_paths(full)
    for rel in full:
        print(('lock ' if rel in locks else 'path ') + rel)
    print('scopes: ' + ' '.join(sf.claim_scopes(game, result)))


def materialize(game: Path, claim: str, *, echo=print) -> None:
    sf.apply.Journal(game).recover(claim)
    recs = plan(game)
    result = sf.claim_ops(game, None, recs)
    scopes = sf.claim_scopes(game, result)
    paths = sorted(set(result['writes']) | set(result['deletes']))
    try:
        sf.authority.authorize([f'{sf.GAME_REL}/{rel}' for rel in paths], claim,
                               'Yorimichi V2 Japan material instances', scopes=scopes)
    except sf.authority.Unauthorized as error:
        raise sf.PlanError(str(error)) from None
    sf.apply.execute(game, result, scopes=scopes)
    echo(f'materialize: {len(recs)} record(s), {sum(len(r.outputs) for r in recs)} instance(s); '
         f'{len(paths)} path(s) under {claim}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', type=Path, default=sf.GAME)
    parser.add_argument('--paths', action='store_true', help='print the claim paths (lock or path), then the scopes')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write')
    args = parser.parse_args(argv)
    try:
        if args.claim:
            materialize(args.game, args.claim)
        elif args.paths:
            print_paths(args.game)
        else:
            for rec in plan(args.game):
                print(f'{rec.id}: {len(rec.outputs)} instance(s) from {rec.adopted}; inputs {", ".join(rec.inputs)}')
            for package, reasons in sorted(held().items()):
                print(f'held {package}: {"; ".join(reasons)}')
        return 0
    except (sf.FamilyError, sf.records.RecordError, sf.apply.SplitError) as error:
        print(f'japan_instances: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
