"""Watch the horse racing in the running slice game through its live bridge and check it (F15).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen -racingsave=SAVE   # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/racing.py --session ID --out OUT
    uv run python games/yorimichi_v2/tools/test/racing.py --session ID2 --out OUT2 --resume OUT/report.json   # after a restart

The check skips the racing clock ahead (racing.Next), and the game saves its racing day as it always does, so give
the session a scratch -racingsave= file rather than the checkout's Saved/racing/world.json.

With a screenshot and a state line at each step:
  1. today's venue: travel there, skip to just before the next start (racing.Next) and watch from beside the track;
     the runners line up, run (each one's distance never falls back, every runner placed on the course) and finish,
     and that race becomes the last result with its top places
  2. the next race, watched on the four Belmonte TVs in turn: each screen's watch point has it nearest and live,
     capturing frames
  3. the next day's first race, at the other venue: it starts and its runners move
  4. --resume: in a fresh session after a restart, the saved racing day carries on from the earlier report's (the
     same day or later, with a last result)
OUT/racing.jsonl holds the steps; OUT/report.json the session, the checkout's revision, the races watched and the
day and last result to resume from. Exit 0 only when every step holds. It saves nothing itself; the game saves its
racing day (to the -racingsave= file).
"""
import argparse
import json
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

TVS = ('osteria_front', 'osteria_back', 'salon_paris', 'salon_bar')


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


def state():
    return json.loads(value('unreal.RacingLive.racing_state()'))


def tv():
    return json.loads(value('unreal.RacingLive.racing_tv_state()'))


class Review:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.lines, self.step = [], 0

    def log(self, what, shot=None, extra=None):
        s = state()
        race = s['race']
        line = {'what': what, 'wall': round(time.time(), 1), 'day': s['day'], 'race': race['key'], 'venue': race['venue'],
                't': race['t'], 'run': race['run'], 'shown': s['shown'], 'last': s['last'], **(extra or {})}
        if shot:
            self.step += 1
            path = self.out / f'{self.step:02d}-{shot}.png'
            if path.exists():
                path.unlink()
            py(f'unreal.LiveLibrary.screenshot({str(path)!r})')
            for _ in range(80):
                if path.exists() and path.stat().st_size:
                    break
                time.sleep(.1)
            line['shot'] = path.name
        self.lines.append(line)
        print('RACING', what, '| day', s['day'], race['venue'], race['key'], f't {race["t"]:.0f}', 'shown', s['shown'], flush=True)
        (self.out / 'racing.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def wait(self, read, test, timeout, every=.5):
        end = time.time() + timeout
        while time.time() < end:
            s = read()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(read())[:1500])


def watch_point(along, outwards):
    # The yaw is an out parameter: Python returns it after the point.
    out = value(f'(lambda r: f"{{r[0].x}} {{r[0].y}} {{r[0].z}} {{r[1]}}")(unreal.RacingLive.racing_view_point({along}, {outwards}))')
    x, y, z, yaw = map(float, out.split())
    assert (x, y, z) != (0, 0, 0), 'no race to watch'
    assert value(f'unreal.YorimichiLive.travel(unreal.Vector({x}, {y}, {z}), {yaw})') == 'True', 'travel beside the track refused'


def next_race(r, lead):
    assert value(f'unreal.RacingLive.racing_next({lead})') == 'True', 'racing.Next refused'
    return r.wait(state, lambda s: s['race']['key'] and -lead - 5 < s['race']['t'] < 0, 20)


def watch(r, args):
    # The next start can be tomorrow's, at the other venue: jump first, then travel to wherever it runs.
    s = next_race(r, args.lead)
    key, venue = s['race']['key'], s['race']['venue']
    assert value(f'unreal.RacingLive.racing_go({venue.lower()!r})') == 'True', f'travel to {venue} refused'
    time.sleep(args.settle)
    watch_point(args.along, args.outwards)
    time.sleep(5)
    r.log(f'1 {venue}: {s["race"]["name"]} lining up', 'lineup', {'runners': len(s['race']['runners'])})
    s = r.wait(state, lambda s: s['race']['key'] == key and s['race']['t'] > 1, args.lead + 30)
    r.log('1 running', 'start')
    worst = {'backwards': 0, 'unplaced': 0, 'samples': 0}
    before = None
    end = time.time() + args.race_timeout
    while time.time() < end:
        s = state()
        if s['race']['key'] != key or s['last']['race'] == key:
            break
        runners = s['race']['runners']
        worst['samples'] += 1
        worst['unplaced'] += sum(not x['placed'] for x in runners)
        if before:
            worst['backwards'] += sum(x['distance'] < b['distance'] - .5 for x, b in zip(runners, before))
        before = runners
        if worst['samples'] == 20:
            r.log('1 mid-race', 'mid')
        time.sleep(1)
    s = r.wait(state, lambda s: s['last']['race'] == key and s['last']['top'], 60)
    r.log('1 finished', 'finish', {'worst': worst, 'top': s['last']['top']})
    assert len(before or []) >= 2, f'{key} had {len(before or [])} runners'
    assert worst['backwards'] == 0, f'runners went backwards: {worst}'
    assert worst['unplaced'] == 0, f'runners off the course: {worst}'
    return {'race': key, 'venue': venue, 'runners': len(before), 'top': s['last']['top'], **worst}


def tvs(r, args):
    s = next_race(r, args.lead)
    key = s['race']['key']
    r.wait(state, lambda s: s['race']['t'] > 1, args.lead + 30)
    seen = {}
    for spot in TVS:
        assert value(f'unreal.RacingLive.racing_tv_go({spot!r})') == 'True', f'racing.Tv {spot} refused'
        time.sleep(args.tv_settle)
        before = tv()['captures']
        time.sleep(3)
        t = tv()
        seen[spot] = {'nearest': t['nearest'], 'live': t['live'], 'captures': t['captures'] - before, 'shot': t['shot']}
        r.log(f'2 TV {spot}', f'tv-{spot}', {'tv': seen[spot]})
    assert state()['race']['key'] == key, 'the race ended before every TV was seen; raise --lead or lower --tv-settle'
    bad = {k: v for k, v in seen.items() if v['nearest'] != k or not v['live'] or v['captures'] <= 0}
    assert not bad, f'TVs not showing the race: {bad}'
    return {'race': key, 'screens': seen}


def other_venue(r, args, first):
    day = state()['day']
    for _ in range(16):
        # Each start has to pass before racing.Next finds the one after it.
        s = next_race(r, 2)
        if s['day'] != day:
            break
        r.wait(state, lambda s: s['race']['t'] > 1, 30)
    assert s['day'] != day, f'still day {day} after 16 races'
    venue = s['race']['venue']
    assert value(f'unreal.RacingLive.racing_go({venue.lower()!r})') == 'True', f'travel to {venue} refused'
    time.sleep(args.settle)
    s = r.wait(state, lambda s: s['race']['t'] > 10, 60)
    first_runners = [x['distance'] for x in s['race']['runners']]
    time.sleep(5)
    s = state()
    moved = sum(x['distance'] > d for x, d in zip(s['race']['runners'], first_runners))
    r.log(f'3 day {s["day"]} at {venue}', 'other-venue', {'moved': moved})
    assert venue != first, f'day {s["day"]} raced at {venue} again'
    assert moved == len(first_runners) > 0, f'{moved} of {len(first_runners)} runners moved'
    return {'day': s['day'], 'venue': venue, 'race': s['race']['key'], 'moved': moved}


def resume(r, previous):
    s = state()
    r.log('4 after the restart', 'resumed')
    assert s['courses'], 'courses not loaded'
    assert s['day'] >= previous['day'], f'racing day went back from {previous["day"]} to {s["day"]}'
    assert s['last']['race'], 'no last result after the restart'
    return {'day': s['day'], 'from_day': previous['day'], 'last': s['last']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'racing')
    parser.add_argument('--resume', type=Path, help='report.json of an earlier session: only check the saved day carried on')
    parser.add_argument('--lead', type=float, default=60.0, help='seconds before a start that racing.Next leaves (covers travel)')
    parser.add_argument('--along', type=float, default=60.0, help='metres along the course to watch from')
    parser.add_argument('--outwards', type=float, default=14.0, help='metres outwards from the course centre to watch from')
    parser.add_argument('--settle', type=float, default=15.0, help='seconds for a venue to load after travel')
    parser.add_argument('--tv-settle', type=float, default=6.0, help='seconds at each TV before reading it')
    parser.add_argument('--race-timeout', type=float, default=400.0, help='seconds from the start to the result')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the racing to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    r = Review(args.out)
    report = {'session': args.session, 'revision': source, 'passed': False}
    try:
        s = r.wait(state, lambda s: s.get('courses'), 60)
        report['save'] = s['save']
        if args.resume:
            report['resumed'] = resume(r, json.loads(args.resume.read_text()))
        else:
            report['watched'] = watch(r, args)
            report['tvs'] = tvs(r, args)
            report['other_venue'] = other_venue(r, args, report['watched']['venue'])
            s = state()
            report.update(day=s['day'], last=s['last'])
        report['passed'] = True
    except (AssertionError, TimeoutError) as error:
        report['failure'] = str(error)[:2000]
        print('RACING FAILED', error, file=sys.stderr)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('RACING', 'PASSED' if report['passed'] else 'FAILED', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
