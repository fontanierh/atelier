"""Mix and encode a take of the Mega Park access film (megapark_access_film.py).

    python games/yorimichi/scenarios/megapark_access_film_mix.py build/yorimichi/megapark/access-film/<take> [--out NAME]

The game's one-shots and the board's loops are mixed as in the skate showreel mixer (distance gain and pan from the
camera, loops through a phase accumulator), footsteps from the source the audio log recorded. The airship makes no
sound of its own, so a propeller drone (low harmonics with a blade-pass throb) and wind are synthesized under the
flight shots, louder when the camera rides close to the ship. The countryside ambience sits under everything. Writes
NAME.wav, NAME.mp4 (1080p H.264/AAC) and NAME-720p.mp4 in the take folder.
"""
import argparse, csv, json, math, subprocess, sys, wave
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
ROOT = yori.OUT
RATE, SIM, FILM = 48000, 60, 30
LOOPS = ['roll', 'grind', 'slide', 'skid', 'scrape']
AMBIENCE = ROOT / 'audio/combat/ambience_countryside/ambience_countryside_01.wav'
FLIGHT = ('takeoff', 'cruise_front', 'cruise_side', 'approach_park', 'landing')


def read(path):
    with wave.open(str(path)) as w:
        n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
        a = np.frombuffer(w.readframes(n), '<i2').astype(np.float32) / 32768.
    a = a.reshape(-1, ch).mean(1)
    if rate != RATE: a = np.interp(np.arange(0, len(a), rate / RATE), np.arange(len(a)), a)
    return a


def source(event):
    if event.get('source') and Path(event['source']).exists(): return Path(event['source'])
    name = event['sound'].split('.')[-1]
    if '/Audio/Skate/' in event['sound']: return ROOT / 'audio/skate' / name.rsplit('_', 1)[0] / f'{name}.wav'
    if '/Audio/Combat/' in event['sound']: return ROOT / 'audio/combat' / name.rsplit('_', 1)[0] / f'{name}.wav'
    hits = list((ROOT / 'audio').rglob(name + '.wav'))
    if hits: return hits[0]
    raise FileNotFoundError(event['sound'])


def gain(distance):
    if distance <= 500.: return 1.
    return 10 ** (-48. * math.sqrt(min(1., (distance - 500.) / 4500.)) / 20.)


def shaped_noise(n, rng, lo, hi, tilt):
    """White noise through a band (lo..hi Hz, soft edges) with a 1/f^tilt slope, done in one FFT."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1. / RATE); f[0] = 1.
    shape = f ** -tilt / (1 + (lo / f) ** 4) / (1 + (f / hi) ** 4)
    s = np.fft.irfft(spec * shape, n)
    return (s / (np.abs(s).max() + 1e-9)).astype(np.float32)


def slow_curve(n, rng, seconds, lo, hi):
    """A smooth random curve between lo and hi, with a new value every `seconds`."""
    k = int(n / RATE / seconds) + 3
    pts = rng.uniform(lo, hi, k)
    x = np.arange(n) / RATE / seconds
    i = x.astype(int); fr = x - i; fr = fr * fr * (3 - 2 * fr)
    return (pts[i] * (1 - fr) + pts[i + 1] * fr).astype(np.float32)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('take'); ap.add_argument('--out', default='megapark-access-film')
    a = ap.parse_args(); take = Path(a.take); out = a.out
    done = json.loads((take / 'done.json').read_text())
    frames = done['film_frames']; seconds = frames / FILM; length = int(seconds * RATE)
    shots = sorted(done['shots'], key=lambda s: s['film_frame'])
    mix = np.zeros((length, 2), np.float32)
    cams = list(csv.DictReader(open(take / 'camera.csv')))
    cache = {}
    for e in json.loads((take / 'audio.json').read_text()):
        if e['frame'] < 0: continue
        path = source(e)
        s = cache.setdefault(path, read(path))
        p = float(e.get('pitch', 1.))
        if abs(p - 1.) > 1e-3: s = np.interp(np.arange(0, len(s) - 1, p), np.arange(len(s)), s)
        cam = cams[min(max(e['frame'] // 2, 0), len(cams) - 1)]
        eye = np.array([float(cam['x']), float(cam['y']), float(cam['z'])]); yaw = math.radians(float(cam['yaw']))
        d = np.array([e['x'], e['y'], e['z']]) - eye; dist = float(np.linalg.norm(d))
        pan = float(np.clip(np.dot(d / max(dist, 1.), [-math.sin(yaw), math.cos(yaw), 0.]) * .6, -1, 1))
        v = float(e.get('volume', 1.)) * gain(dist)
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        start = int(e['frame'] / SIM * RATE); end = min(length, start + len(s))
        if end <= start: continue
        mix[start:end, 0] += s[:end - start] * v * l * math.sqrt(2); mix[start:end, 1] += s[:end - start] * v * r * math.sqrt(2)
    rows = [list(map(float, line.split())) for line in (take / 'loops.csv').read_text().split('\n') if line.strip()]
    sim_t = np.arange(len(rows)) / SIM
    t = np.arange(length) / RATE
    for k, cue in enumerate(LOOPS):
        wav = read(ROOT / f'audio/skate/{cue}/{cue}_01.wav')
        vol = np.interp(t, sim_t, [r[2 * k] if len(r) > 2 * k else 0. for r in rows])
        pitch = np.interp(t, sim_t, [r[2 * k + 1] if len(r) > 2 * k + 1 else 1. for r in rows])
        if vol.max() < 1e-3: continue
        phase = np.cumsum(pitch) % len(wav)
        i0 = phase.astype(int); frac = phase - i0
        s = wav[i0] * (1 - frac) + wav[(i0 + 1) % len(wav)] * frac
        mix[:, 0] += s * vol * .9; mix[:, 1] += s * vol * .9
    # The airship, from the takeoff to the first shot after the flight.
    fl = [s['film_frame'] for s in shots if s['shot'] in FLIGHT]
    after = [s['film_frame'] for s in shots if s['shot'] not in FLIGHT and fl and s['film_frame'] > fl[0]]
    if fl:
        a0, a1 = int(fl[0] / FILM * RATE), int((after[0] if after else frames) / FILM * RATE)
        n = a1 - a0; rng = np.random.default_rng(7); tt = np.arange(n) / RATE
        f0 = 41. * (1 + .01 * slow_curve(n, rng, 4., -1., 1.))
        ph = 2 * math.pi * np.cumsum(f0) / RATE
        drone = sum(a * np.sin(h * ph + h) for h, a in ((1, 1.), (2, .55), (3, .35), (4, .2), (6, .1)))
        drone *= .7 + .3 * np.sin(2 * math.pi * 10.3 * tt) ** 2
        drone = drone / np.abs(drone).max() * .5 + shaped_noise(n, rng, 30., 220., .5) * .25
        wind = shaped_noise(n, rng, 120., 1800., 1.) * slow_curve(n, rng, 2.5, .35, 1.)
        dist = np.array([float(c['dist']) for c in cams])
        near = np.interp(np.arange(n) / RATE * FILM + fl[0], np.arange(len(dist)), np.clip(1.6 - dist / 2500., .35, 1.))
        env = np.ones(n, np.float32); ramp = int(1.5 * RATE)
        env[:ramp] = np.linspace(0, 1, ramp); env[-int(.25 * RATE):] = np.linspace(1, 0, int(.25 * RATE))
        mix[a0:a1, 0] += (drone * .32 + wind * .22) * near * env
        mix[a0:a1, 1] += (drone * .32 + np.roll(wind, 2400) * .22) * near * env
    amb = read(AMBIENCE)
    mix += (np.tile(amb, int(math.ceil(length / len(amb))))[:length] * .45)[:, None]
    mix = np.tanh(mix * 1.1) / math.tanh(1.1)
    mix *= 10 ** (-1 / 20) / max(1e-6, float(np.abs(mix).max()))
    fi, fo = int(.8 * RATE), int(1.5 * RATE)
    mix[:fi] *= np.linspace(0, 1, fi)[:, None]; mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
    out_wav = take / f'{out}.wav'
    with wave.open(str(out_wav), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes((np.clip(mix, -1, 1) * 32767).astype('<i2').tobytes())
    mp4 = take / f'{out}.mp4'
    vf = f'fade=t=in:st=0:d=0.8,fade=t=out:st={seconds - 1.5:.3f}:d=1.5'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FILM), '-i', str(take / 'frame_%05d.jpg'), '-i', str(out_wav), '-vf', vf,
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest',
                    '-movflags', '+faststart', str(mp4)], check=True)
    small = take / f'{out}-720p.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'slow', '-crf', '22',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(small)], check=True)
    print(json.dumps({'frames': frames, 'seconds': round(seconds, 2), 'shots': shots, 'video': str(mp4), 'mb': round(mp4.stat().st_size / 1e6, 1),
                      'video_720p': str(small), 'mb_720p': round(small.stat().st_size / 1e6, 1)}))


if __name__ == '__main__':
    main()
