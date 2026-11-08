"""Travel to every world-map zone in the running slice game through its live bridge and check each arrival (F18).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/map_travel.py --session ID --out OUT [--zones KEY ...]

Each zone of map.json goes through the map's own travel (UJapanMap::TeleportToZone, as clicking its pin does: the
Crater Park tower and the train stations keep their own routes). After --settle seconds the player must stand on
walkable ground, within --near metres of the zone's point, and stay put for two seconds; a screenshot of each
arrival goes to OUT. An unknown zone must be refused and leave the player where they are. OUT/travel.jsonl holds
each arrival; OUT/report.json the session, the checkout's revision and the zones that failed. Exit 0 only when every
zone arrives and the refusal holds. It saves nothing.
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'platform' / 'studio'))
from launch import launch_revision, revision  # noqa: E402
from atelier import live  # noqa: E402
from atelier.live_sessions import Unreachable  # noqa: E402

MAP = GAME / 'unreal' / 'Content' / 'Data' / 'map' / 'map.json'

HELPERS = r'''
import json, unreal
def map_travel(key):
    m = [m for m in unreal.ObjectIterator(unreal.JapanMap) if not m.get_path_name().startswith('/Script/')][0]
    return m.teleport_to_zone(key)
def map_player():
    p = unreal.GameplayStatics.get_player_pawn(unreal.LiveLibrary.game_world(), 0)
    m = p.get_component_by_class(unreal.CharacterMovementComponent)
    l = p.get_actor_location()
    return json.dumps({'at': [l.x, l.y, l.z], 'ground': m.is_moving_on_ground(), 'mode': int(m.movement_mode.value)})
'''


def py(code):
    # A busy game can miss the session check, which runs before anything is sent: only that is retried.
    for attempt in range(8):
        try:
            out = live.request('/python', code)
            break
        except Unreachable:
            if attempt == 7:
                raise
            time.sleep(3)
    if not out.get('ok'):
        raise RuntimeError(out.get('result') or out)
    return out.get('output', '').strip()


def value(expression):
    return py(f'print({expression})')


def player():
    return json.loads(value('map_player()'))


def shot(path):
    if path.exists():
        path.unlink()
    py(f'unreal.LiveLibrary.screenshot({str(path)!r})')
    for _ in range(80):
        if path.exists() and path.stat().st_size:
            return path.name
        time.sleep(.1)
    return None


def visit(zone, args, index):
    accepted = value(f'map_travel({zone["key"]!r})') == 'True'
    time.sleep(args.settle)
    first = player()
    time.sleep(2)
    last = player()
    # The zone's point in Unreal cm (AJapanWorld::ToUE: metres, y flipped).
    point = [zone['x'] * 100, -zone['y'] * 100, zone['z'] * 100]
    row = {'key': zone['key'], 'name': zone['name'], 'accepted': accepted, 'at': last['at'], 'ground': last['ground'],
           'from_point_m': round(math.dist(point[:2], last['at'][:2]) / 100, 1),
           'moved_cm': round(math.dist(first['at'], last['at']), 1), 'shot': shot(args.out / f'{index:02d}-{zone["key"]}.png')}
    row['problems'] = [p for p, bad in (('refused', not accepted), ('not on the ground', not last['ground'] or not first['ground']),
                                         (f'{row["from_point_m"]} m from its point', row['from_point_m'] > args.near),
                                         (f'moved {row["moved_cm"]} cm standing', row['moved_cm'] > 15)) if bad]
    print('MAP', zone['key'], 'OK' if not row['problems'] else '; '.join(row['problems']), flush=True)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'map-travel')
    parser.add_argument('--zones', nargs='+', help='zone keys to visit (default: every map.json zone, in its order)')
    parser.add_argument('--settle', type=float, default=12.0, help='seconds for a zone to load after travel')
    parser.add_argument('--near', type=float, default=20.0, help='metres the arrival may be from the zone point')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the travel to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    args.out.mkdir(parents=True, exist_ok=True)
    py(HELPERS)
    zones = json.loads(MAP.read_text())['zones']
    if args.zones:
        unknown = set(args.zones) - {z['key'] for z in zones}
        if unknown:
            parser.error(f'unknown zones: {sorted(unknown)}')
        zones = [z for z in zones if z['key'] in args.zones]
    rows = []
    for index, zone in enumerate(zones, 1):
        rows.append(visit(zone, args, index))
        (args.out / 'travel.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    before = player()['at']
    refused = value("map_travel('no_such_zone')") == 'False'
    time.sleep(2)
    stayed = math.dist(before, player()['at']) < 15
    failed = {r['key']: r['problems'] for r in rows if r['problems']}
    report = {'session': args.session, 'revision': source, 'zones': len(rows), 'failed': failed,
              'unknown_refused': refused and stayed, 'passed': not failed and refused and stayed}
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('MAP TRAVEL', 'PASSED' if report['passed'] else 'FAILED', f'{len(rows) - len(failed)}/{len(rows)} zones', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
