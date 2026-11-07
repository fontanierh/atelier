"""Run the one-time static-world migration for some regions into a V2 World Partition map (plan §6, P3 step 1).

    uv run python games/yorimichi_v2/tools/migrate/run.py region/w01-start region/w04-pier-approach \
        --environment region/w00-island --services SkyDome Sea --only-migrated --runtime-service SkatePark \
        [--claim TASK]

It writes the editor plan (each region's record bounds, its map), runs the guarded editor step `migrate.map`
(unreal/Scripts/migrate_map.py: the island pieces, the environment, and AJapanWorld::Load's scenery through
UV2Migration), then records every touched region's actor packages with save validation. Rerunning on unchanged
data creates nothing. All regions must share one map.

It writes as the D04 bootstrap writer while D04 is open, or with `--claim TASK`: an active claim holding every
touched region's scope. World Partition names actor packages only when it saves them, so a claimed run may create
new files in those regions' actor folders; the build step refuses any other write and binds the created files to
the claim with their LFS locks (authority.bind_created), and every one must end up in a touched region's record.
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


def overlap(a, b) -> bool:
    """Two half-open [min x, min y, max x, max y) boxes share area."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def make_plan(game: Path, ids: list[str], environment: str, services, only_migrated, runtime_services, patch_m):
    _, regions = records.discover(game)
    by_id = {r.id: r for r in regions}
    missing = [i for i in ids + [environment] if i not in by_id]
    if missing:
        raise MigrationError(f'no region record for {missing}')
    maps = {m for i in ids + [environment] for m in by_id[i].maps}
    if len(maps) != 1:
        raise MigrationError(f'the regions must share exactly one map, not {sorted(maps)}')
    # An instance is copied into every region whose box holds it: two migrated regions of one map never overlap.
    # The environment owns what no region holds, so its box (the whole map) is the one exception.
    mapped = sorted((r for r in regions if maps <= set(r.maps) and r.id != environment), key=lambda r: r.id)
    for index, a in enumerate(mapped):
        for b in mapped[index + 1:]:
            if overlap(a.bounds_cm, b.bounds_cm) and (a.id in ids or b.id in ids):
                raise MigrationError(f'{a.id} and {b.id} overlap on {next(iter(maps))}: their scenery would be copied twice')
    return {'map': maps.pop(), 'environment': environment, 'services': list(services), 'patch_m': patch_m,
            'only_migrated': only_migrated, 'runtime_services': list(runtime_services),
            'regions': [{'id': i, 'bounds_cm': list(by_id[i].bounds_cm)} for i in ids]}


def native_migrate(plan_file: Path) -> str:
    """The guarded editor step; returns its output, from which the rosters are read."""
    env = {**os.environ, 'V2_MIGRATE_PLAN': str(plan_file)}
    LOG.unlink(missing_ok=True)   # the rosters are read from this run's output only
    command = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi_v2', 'migrate.map']
    result = subprocess.run(command, cwd=REPO, env=env)
    if result.returncode:
        raise MigrationError(f'the editor migration failed (exit {result.returncode}); see {LOG}')
    return LOG.read_text(errors='replace') if LOG.is_file() else ''


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


def migrate(game: Path, plan: dict, claim: str | None = None, *, editor=native_migrate,
            out: Path = REPO / 'build/yorimichi_v2/migrate', echo=print) -> list[str]:
    """Authorize, run the editor step, record rosters and regions; returns the game-relative files it created.
    The build step re-checks the plan itself; this checks first so a refused run never starts the editor."""
    regions = [r['id'] for r in plan['regions']] + [plan['environment']]
    if claim:
        authority.creation_claim(claim, regions, 'map migration')
    else:
        authority.authorize([], None, 'map migration')
    out.mkdir(parents=True, exist_ok=True)
    plan_file = out / 'plan.json'
    plan_file.write_text(json.dumps({**plan, 'claim': claim}, indent=2, sort_keys=True) + '\n')
    before = authority.content_snapshot(game)
    made = patches_made(editor(plan_file))
    created = sorted(set(authority.content_snapshot(game)) - set(before))
    echo(f'{len(made)} scene patch(es) on the map, {len(created)} file(s) created')
    record_rosters(game, made)
    for region in regions:
        save_validate.validate(game, region, claim=claim, echo=echo)
    if claim:   # bound to the claim by the build step; each must now have its one owning region record
        by_id = {r.id: r for r in records.discover(game)[1]}
        recorded = {rel for r in regions if by_id[r].actors.is_file()
                    for rel in records.load_verified(by_id[r].actors)['files']}
        unowned = [rel for rel in created if rel not in recorded]
        if unowned:
            raise MigrationError(f'{len(unowned)} created file(s) no touched region records, e.g. {unowned[0]}: label '
                                 'them with their region or place them inside its bounds, or delete them')
    return created


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('regions', nargs='+', help='region IDs whose scenery and island pieces to migrate')
    parser.add_argument('--environment', required=True, help='the region owning map-wide actors and services')
    parser.add_argument('--services', nargs='+', action='extend', default=[], choices=['SkyDome', 'Sea', 'SkatePark.Scenery'])
    parser.add_argument('--only-migrated', action='store_true', help='slice map: no runtime instance scenery')
    parser.add_argument('--runtime-service', nargs='+', action='extend', default=[],
                        help='with --only-migrated: services that run (repeatable; every name is kept)')
    parser.add_argument('--patch-m', type=float, default=32.0)
    parser.add_argument('--claim', help='claims task holding every touched region (else the D04 bootstrap writer)')
    args = parser.parse_args(argv)
    try:
        plan = make_plan(GAME, args.regions, args.environment, args.services, args.only_migrated,
                         args.runtime_service, args.patch_m)
        migrate(GAME, plan, args.claim)
    except (MigrationError, authority.Unauthorized, save_validate.ValidationError, records.RecordError) as error:
        print(f'migration failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
