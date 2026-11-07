"""Run the one-time static-world migration for some regions into a V2 World Partition map (plan §6, P3 step 1).

    uv run python games/yorimichi_v2/tools/migrate/run.py region/w01-start region/w04-pier-approach \
        --environment region/w00-island --services SkyDome Sea --only-migrated --runtime-service SkatePark \
        [--claim TASK]

It writes the editor plan (each region's record bounds, its map), runs the guarded editor step `migrate.map`
(unreal/Scripts/migrate_map.py: the island pieces, the environment, and AJapanWorld::Load's scenery through
UV2Migration), then records every touched region's actor packages with save validation. Rerunning on unchanged
data creates nothing. All regions must share one map.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools/content'))
import authority  # noqa: E402
import records  # noqa: E402
import save_validate  # noqa: E402

LOG = REPO / 'build/yorimichi_v2/logs/migrate.map.guard/stdout.log'   # the guarded editor's output
PATCH = re.compile(r'V2 PATCH (\S+) (\S+)')
DONE = re.compile(r'V2 MIGRATE DONE created=(\d+) kept=(\d+) patches=(\d+)')


class MigrationError(RuntimeError):
    pass


def make_plan(game: Path, ids: list[str], environment: str, services, only_migrated, runtime_services, patch_m):
    _, regions = records.discover(game)
    by_id = {r.id: r for r in regions}
    missing = [i for i in ids + [environment] if i not in by_id]
    if missing:
        raise MigrationError(f'no region record for {missing}')
    maps = {m for i in ids + [environment] for m in by_id[i].maps}
    if len(maps) != 1:
        raise MigrationError(f'the regions must share exactly one map, not {sorted(maps)}')
    return {'map': maps.pop(), 'environment': environment, 'services': list(services), 'patch_m': patch_m,
            'only_migrated': only_migrated, 'runtime_services': list(runtime_services),
            'regions': [{'id': i, 'bounds_cm': list(by_id[i].bounds_cm)} for i in ids]}


def native_migrate(plan_file: Path):
    env = {**os.environ, 'V2_MIGRATE_PLAN': str(plan_file)}
    LOG.unlink(missing_ok=True)   # the rosters are read from this run's output only
    command = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', 'migrate.map']
    result = subprocess.run(command, cwd=REPO, env=env)
    if result.returncode:
        raise MigrationError(f'the editor migration failed (exit {result.returncode}); see {LOG}')


def patches_made(text: str) -> list[tuple[str, str]]:
    """Every scene patch the migrated map holds, from the editor's output; incomplete capture is a failure."""
    done = DONE.findall(text)
    if not done:
        raise MigrationError(f'the editor migration did not report completion in {LOG}')
    found = PATCH.findall(text)
    if len(found) != int(done[-1][2]):
        raise MigrationError(f'roster capture is incomplete: {len(found)} of {done[-1][2]} scene patch(es) in {LOG}')
    return found


def record_rosters(game: Path, made: list[tuple[str, str]]) -> None:
    """Add each patch to its region's committed roster (world/regions/<name>/patches.json): the scene
    patches the region must keep, so one deleted outright fails the content check instead of passing readiness."""
    rosters = {}
    for package, label in made:
        parts = label.split(':')
        if len(parts) < 4 or not parts[0].startswith('region/'):
            continue
        region, patch_id, key = parts[0], parts[-1], ':'.join(parts[1:-2])
        rel = 'unreal/Content/' + package[len('/Game/'):] + '.uasset'
        rosters.setdefault(region, {})[patch_id] = {'key': key, 'package': rel}
    for region, patches in rosters.items():
        path = game / 'world' / 'regions' / region.split('/', 1)[1] / 'patches.json'
        roster = json.loads(path.read_text())['patches'] if path.is_file() else {}
        roster.update(patches)
        records.write_json(path, {'schema': records.SCHEMA, 'region': region,
                                  'patches': dict(sorted(roster.items()))})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('regions', nargs='+', help='region IDs whose scenery and island pieces to migrate')
    parser.add_argument('--environment', required=True, help='the region owning map-wide actors and services')
    parser.add_argument('--services', nargs='*', default=[], choices=['SkyDome', 'Sea', 'SkatePark.Scenery'])
    parser.add_argument('--only-migrated', action='store_true', help='slice map: no runtime instance scenery')
    parser.add_argument('--runtime-service', nargs='*', default=[], help='with --only-migrated: services that run')
    parser.add_argument('--patch-m', type=float, default=32.0)
    parser.add_argument('--claim', help='refused: the one-time migration is a D04 bootstrap write')
    args = parser.parse_args(argv)
    try:
        plan = make_plan(GAME, args.regions, args.environment, args.services, args.only_migrated,
                         args.runtime_service, args.patch_m)
        # The one-time migration is a D04 bootstrap write: World Partition names its actor packages only when it
        # saves them, so no claim can list them in advance. Save validation then records exactly what it wrote.
        if args.claim:
            raise MigrationError('the one-time migration runs only as the D04 bootstrap writer, without a claim')
        authority.authorize([], None, 'map migration')
        out = REPO / 'build/yorimichi_v2/migrate'
        out.mkdir(parents=True, exist_ok=True)
        plan_file = out / 'plan.json'
        plan_file.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
        native_migrate(plan_file)
        made = patches_made(LOG.read_text(errors='replace') if LOG.is_file() else '')
        print(f'{len(made)} scene patch(es) on the map')
        record_rosters(GAME, made)
        for region in args.regions + [args.environment]:
            save_validate.validate(GAME, region, claim=args.claim)
    except (MigrationError, authority.Unauthorized, save_validate.ValidationError, records.RecordError) as error:
        print(f'migration failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
