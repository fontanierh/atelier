"""Mix and encode a filmed skate showreel (skate_showreel.py).

    python games/yorimichi/scenarios/skate_mix_showreel.py build/yorimichi/skatefilm/<take> [--out showreel]

One-shots come from audio.json (sim frames at 60 fps), attenuated by distance to the camera (the game's sphere: full
inside 5 m, -48 dB at 50 m) and panned by bearing; the board's five loops follow loops.csv (volume and pitch every sim
frame, played through a phase accumulator so pitch glides are smooth); the countryside ambience sits under everything.
The 30 fps viewport frames and the mix become H.264/AAC MP4s (1080p and 720p).
"""
import argparse, csv, json, math, subprocess, sys, wave
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
ROOT = yori.OUT
RATE, SIM, FILM = 48000, 60, 30
LOOPS = ['roll', 'grind', 'slide', 'skid', 'scrape']
AMBIENCE = ROOT / 'audio/combat/ambience_countryside/ambience_countryside_01.wav'


def read(path):
    with wave.open(str(path)) as w:
        n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
        a = np.frombuffer(w.readframes(n), '<i2').astype(np.float32) / 32768.
    a = a.reshape(-1, ch).mean(1)
    if rate != RATE: a = np.interp(np.arange(0, len(a), rate / RATE), np.arange(len(a)), a)
    return a


def source(event):
    name = event['sound'].split('.')[-1]
    if '/Audio/Skate/' in event['sound']: return ROOT / 'audio/skate' / name.rsplit('_', 1)[0] / f'{name}.wav'
    if '/Audio/Combat/' in event['sound']: return ROOT / 'audio/combat' / name.rsplit('_', 1)[0] / f'{name}.wav'
    if '/Audio/Footsteps/' in event['sound']: return ROOT / 'audio/footsteps' / event['sound'].split('/')[-2] / f'{name}.wav'
    raise FileNotFoundError(event['sound'])


def gain(distance):
    if distance <= 500.: return 1.
    return 10 ** (-48. * math.sqrt(min(1., (distance - 500.) / 4500.)) / 20.)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('take'); ap.add_argument('--out', default='showreel'); ap.add_argument('--music', type=Path, help='Original or licensed soundtrack WAV')
    ap.add_argument('--title', help='Opening title over the first five seconds'); a = ap.parse_args()
    take = Path(a.take)
    done = json.loads((take / 'done.json').read_text())
    frames = done['film_frames']; seconds = frames / FILM
    length = int(seconds * RATE)
    mix = np.zeros((length, 2), np.float32)
    cams = list(csv.DictReader(open(take / 'camera.csv')))
    cache = {}
    for e in json.loads((take / 'audio.json').read_text()):
        if e['frame'] < 0: continue                          # played before the film started
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
    # Loops: per-sim-frame volume and pitch, interpolated per sample; the phase runs on through a shot.
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
    amb = read(AMBIENCE)
    mix += (np.tile(amb, int(math.ceil(length / len(amb))))[:length] * .45)[:, None]
    if a.music:
        music = read(a.music)
        mix += (np.tile(music, int(math.ceil(length / len(music))))[:length] * .30)[:, None]
    mix = np.tanh(mix * 1.1) / math.tanh(1.1)
    mix *= 10 ** (-1 / 20) / max(1e-6, float(np.abs(mix).max()))
    fi, fo = int(.4 * RATE), int(1. * RATE)
    mix[:fi] *= np.linspace(0, 1, fi)[:, None]; mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
    out_wav = take / f'{a.out}.wav'
    with wave.open(str(out_wav), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes((np.clip(mix, -1, 1) * 32767).astype('<i2').tobytes())
    mp4 = take / f'{a.out}.mp4'
    # Desktop capture follows the monitor aspect; fixed cameras letterbox to 16:9.
    # Centre-crop that frame before scaling so the skater keeps correct proportions.
    vf = "crop='min(iw,ih*16/9)':'min(ih,iw*9/16)',scale=1920:1080"
    if a.title:
        title = take / f'{a.out}-title.txt'
        title.write_text(a.title, encoding='utf-8')
        filename = str(title.resolve()).replace('\\', '\\\\').replace(':', '\\:').replace("'", "'\\''")
        vf += f",drawtext=textfile='{filename}':font='Arial\\:style=Bold':fontsize=72:fontcolor=white:x=96:y=96:shadowcolor=black@0.35:shadowx=2:shadowy=2:enable='between(t,0.6,5)':alpha='if(lt(t,1.2),(t-0.6)/0.6,if(gt(t,4.4),(5-t)/0.6,1))'"
    vf += f",fade=t=in:st=0:d=0.4,fade=t=out:st={seconds - 1.:.3f}:d=1"
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FILM), '-i', str(take / ('frame_%05d.' + done.get('frame_extension', 'jpg'))), '-i', str(out_wav), '-vf', vf,
                    '-c:v', 'libx264', '-threads', '4', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(mp4)], check=True)
    small = take / f'{a.out}-720p.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=1280:720', '-c:v', 'libx264', '-threads', '4', '-preset', 'slow', '-crf', '22',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(small)], check=True)
    print(json.dumps({'frames': frames, 'seconds': round(seconds, 2), 'video': str(mp4), 'video_720p': str(small), 'mb': round(small.stat().st_size / 1e6, 1)}))


if __name__ == '__main__':
    main()
