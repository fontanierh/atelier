"""Cut and mix a Mega Park Ride film take (megapark_ride_film.py).

    python games/yorimichi/scenarios/megapark_ride_film_mix.py build/yorimichi/megapark/ride-film/<take> \\
        [--out ride-film] [--audio DIR] [--only shot,shot] [--trim shot:first-last ...]

The kept shots' parts follow each other in the order they were filmed; after the slow-motion shot, its biggest air
plays again at a third of the speed (each 90 Hz frame of the window becomes a 30 fps frame). Sounds stamped with a
shot's own clock move onto the film's 60 Hz clock (the replay repeats its window's sounds three times slower and a
little quieter), and the loops and camera rows follow; skate_mix_showreel.mix then mixes and encodes. The cut's frames
are links in <take>/cut/, and cut.json lists where each shot starts in the film. --trim leaves a shot's frames out
(first-last, or first- for the rest of the shot), with their sounds, where a camera lost the rider.
"""
import argparse, json, os, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skate_mix_showreel as reel  # noqa: E402

NEUTRAL_LOOPS = '0 1 0 1 0 1 0 1 0 1'
REPLAY_VOLUME = .8


def cut(shots, events, base, trims=None):
    """Join the kept shots' parts. shots: each part's shot.json in filming order; events: audio.json; base: the audio
    stamp of a shot k's first frame is base * (k + 1); trims: {shot name: [(first, last or None), ...]} source frames
    left out. Returns (frames, cams, loops, events, marks): frame files relative to the take, camera rows per film
    frame, a loop row per 60 Hz frame, the sounds on the film's 60 Hz clock and where each shot (and replay) starts."""
    frames, cams, loops, out, marks = [], [], [], [], []
    for s in shots:
        n = s.get('frames', 0)
        if not s.get('keep', True) or n == 0: continue
        gone = (trims or {}).get(s['name'], [])
        kept = [i for i in range(n) if not any(a <= i and (b is None or i <= b) for a, b in gone)]
        pos = {i: j for j, i in enumerate(kept)}
        lo = base * (s['k'] + 1)
        f0 = len(frames); v0 = 2 * f0
        marks.append({'shot': s['name'], 'film_frame': f0, 'seconds': round(len(pos) / 30., 2)})
        frames += [f"parts/{s['dir']}/f{i:05d}.jpg" for i in pos]
        cams += [[f0 + pos[int(r[0])]] + list(r[1:]) for r in s['cams'] if int(r[0]) in pos]
        rows = list(s['loops'][:2 * n])
        rows += [rows[-1] if rows else NEUTRAL_LOOPS] * (2 * n - len(rows))
        loops += [rows[2 * i + h] for i in pos for h in (0, 1)]
        for e in events:
            v = e['frame'] - lo; i = int(v // 2)
            if 0 <= v < 2 * n and i in pos: out.append(dict(e, frame=v0 + 2 * pos[i] + v - 2 * i))
        rp = s.get('replay')
        win = [b for b in s.get('slowbuf', []) if rp and rp['from_t'] <= b[0] <= rp['to_t'] and b[2]]
        if not win: continue
        f0 = len(frames); v0 = 2 * f0; stretch = rp.get('stretch', 3)
        a, b = win[0][1], win[-1][1] + 2. / stretch
        marks.append({'shot': s['name'] + ' (replay)', 'film_frame': f0, 'seconds': round(len(win) / 30., 2)})
        frames += [f"parts/{s['dir']}/{w[2]}" for w in win]
        cams += [[f0 + i] + list(w[3]) for i, w in enumerate(win)]
        for w in win: loops += [w[4], w[4]]
        out += [dict(e, frame=v0 + int(round((e['frame'] - lo - a) * stretch)), volume=e.get('volume', 1.) * REPLAY_VOLUME)
                for e in events if a - .5 <= e['frame'] - lo < b - .5]
    return frames, cams, loops, out, marks


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('take'); ap.add_argument('--out', default='ride-film')
    ap.add_argument('--audio', help="the audio folder of another build (default: this checkout's build/yorimichi/audio)")
    ap.add_argument('--only', default='', help='comma-separated shot names to cut (a rough cut of a rehearsal)')
    ap.add_argument('--trim', action='append', default=[], help='shot:first-last (or shot:first-) frames to leave out')
    a = ap.parse_args()
    take = Path(a.take)
    done = json.loads((take / 'done.json').read_text())
    if done.get('rehearse'): sys.exit('a rehearsal take has no frames')
    only = [o for o in a.only.split(',') if o]
    shots = [json.loads((take / 'parts' / s['dir'] / 'shot.json').read_text()) for s in done['shots'] if s.get('dir')]
    shots = [s for s in shots if not only or s['name'] in only]
    events = json.loads((take / 'audio.json').read_text())
    trims = {}
    for t in a.trim:
        name, _, rng = t.partition(':'); first, _, last = rng.partition('-')
        trims.setdefault(name, []).append((int(first), int(last) if last else None))
    frames, cams, loops, events, marks = cut(shots, events, done['audio_base'], trims)
    missing = [f for f in frames if not (take / f).exists()]
    if missing: sys.exit(f'{len(missing)} frames missing, first {missing[0]}')
    links = take / 'cut'
    shutil.rmtree(links, ignore_errors=True); links.mkdir()
    for i, f in enumerate(frames):
        os.symlink(os.path.join('..', f), links / f'frame_{i:05d}.jpg')
    (take / 'cut.json').write_text(json.dumps({'frames': len(frames), 'shots': marks, 'trims': a.trim}, indent=1))
    print(json.dumps(reel.mix(take, links / 'frame_%05d.jpg', len(frames), cams, loops, events, a.out, a.audio)))


if __name__ == '__main__':
    main()
