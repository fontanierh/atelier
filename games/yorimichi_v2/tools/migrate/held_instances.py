"""@cc [owner:fontanierh,label:correctness] yorimichi-v2-single-writer
The material instances an adopted record still holds, planned family by family as material-instance records (one per
adopted record) from what the donor scripts write (small_instances.EXPECTED), each agreeing with the committed editor
read (docs/inventory/small-families-reads/instances/<family>.json), base-property overrides included:
- japan: the 41 instances of adopted/japan/materials/{bark, buildings, foliage, ground, rock-concrete, sky-wind, water};
- hidamari: MI_HD_flat (adopted/japan/hidamari/surface-flat);
- megapark: the two natural seam instances left in adopted/megapark/seam (the others moved under SMALLFAM);
- treehouse: MI_TH_pane (adopted/japan/treehouse/surface-pane).

    uv run python games/yorimichi_v2/tools/migrate/held_instances.py --family F [--donor PATH]              # plan
    uv run python games/yorimichi_v2/tools/migrate/held_instances.py --family F [--donor PATH] --paths      # claim paths
    uv run python games/yorimichi_v2/tools/migrate/held_instances.py --family F [--donor PATH] --claim TASK # the write

The write is small_families.claim_ops over these records only: the new records, each adopted record that gives up every
package deleted with its verified.json (one that keeps some loses only the moved outputs), the folder's units.json
without the moved packages, and every record that references a fully moved adopted record rewritten to name the new one.
A held instance stays in its adopted record. Nothing is imported here; tools/import/run.py imports the records under the
claim. Mega Park needs the donor (its rows come from the donor build report); Japan and Hidamari do not.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import small_families as sf  # noqa: E402
import small_instances as si  # noqa: E402

FAMILIES = ('japan', 'hidamari', 'megapark', 'treehouse')
# The new record of an adopted record whose default id (material/<adopted>-instances) an earlier claim took.
IDS = {'adopted/megapark/seam': 'material/megapark/seam-two-sided-instances'}


def plan(family: str, donor: Path | None, game: Path = sf.GAME) -> list:
    """The material-instance records for the agreeing instances an adopted record still holds."""
    return sf.instance_records(game, donor, {}, families=(family,), ids=IDS)


def held(family: str, donor: Path | None) -> dict:
    return {p: v['held'] for p, v in si.agreement(family, donor).items() if not v['agree']}


def print_paths(family: str, donor: Path | None, game: Path) -> None:
    result = sf.claim_ops(game, donor, plan(family, donor, game))
    paths = sorted(set(result['writes']) | set(result['deletes']))
    full = [f'{sf.GAME_REL}/{rel}' for rel in paths]
    locks = sf.locked_paths(full)
    for rel in full:
        print(('lock ' if rel in locks else 'path ') + rel)
    print('scopes: ' + ' '.join(sf.claim_scopes(game, result)))


def materialize(family: str, donor: Path | None, game: Path, claim: str, *, echo=print) -> None:
    sf.apply.Journal(game).recover(claim)
    recs = plan(family, donor, game)
    result = sf.claim_ops(game, donor, recs)
    scopes = sf.claim_scopes(game, result)
    paths = sorted(set(result['writes']) | set(result['deletes']))
    try:
        sf.authority.authorize([f'{sf.GAME_REL}/{rel}' for rel in paths], claim,
                               f'Yorimichi V2 {family} material instances', scopes=scopes)
    except sf.authority.Unauthorized as error:
        raise sf.PlanError(str(error)) from None
    sf.apply.execute(game, result, scopes=scopes)
    echo(f'materialize: {len(recs)} record(s), {sum(len(r.outputs) for r in recs)} instance(s); '
         f'{len(paths)} path(s) under {claim}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--family', choices=FAMILIES, required=True)
    parser.add_argument('--donor', type=Path, default=None, help='a donor checkout (read-only); Mega Park needs it')
    parser.add_argument('--game', type=Path, default=sf.GAME)
    parser.add_argument('--paths', action='store_true', help='print the claim paths (lock or path), then the scopes')
    parser.add_argument('--claim', metavar='TASK', help='the one journaled write')
    args = parser.parse_args(argv)
    try:
        if args.claim:
            materialize(args.family, args.donor, args.game, args.claim)
        elif args.paths:
            print_paths(args.family, args.donor, args.game)
        else:
            for rec in plan(args.family, args.donor, args.game):
                print(f'{rec.id}: {len(rec.outputs)} instance(s) from {rec.adopted}; inputs {", ".join(rec.inputs)}')
            for package, reasons in sorted(held(args.family, args.donor).items()):
                print(f'held {package}: {"; ".join(reasons)}')
        return 0
    except (sf.FamilyError, sf.records.RecordError, sf.apply.SplitError) as error:
        print(f'held_instances: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
