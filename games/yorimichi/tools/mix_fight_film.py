"""Mix the sound of a filmed fight (-fightfilm) and encode the video.

    python games/yorimichi/tools/mix_fight_film.py build/yorimichi/fightfilm/<take> [--out name]

The game logs every sound it starts (AJapanCombatFX and the footsteps) with the captured frame, its position,
volume and pitch (audio.json), and the camera for every frame (camera.csv). This rebuilds the soundtrack offline,
frame-accurately: each source WAV is pitched, attenuated by its distance from the camera (the in-game sphere
falloff: full inside 4.5 m, -48 dB at 50 m) and panned by its bearing in the camera frame; the countryside
ambience loops under everything, as it does in the game. Then the frames and the mix become an H.264/AAC MP4
(1080p60 and a 720p copy) with a short fade in and out.
"""
import argparse, csv, json, math, subprocess, sys, wave
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
ROOT = yori.OUT
RATE = 48000
FPS = 60
AMBIENCE = ROOT / 'audio/combat/ambience_countryside/ambience_countryside_01.wav'


def read_wav(path):
    with wave.open(str(path)) as w:
        n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    assert sw == 2, (path, 'expects 16-bit PCM')
    a = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.
    a = a.reshape(-1, ch)
    if rate != RATE:
        t = np.arange(0, len(a), rate / RATE)
        a = np.stack([np.interp(t, np.arange(len(a)), a[:, c]) for c in range(ch)], 1)
    return a


def source_file(event):
    src = event.get('source') or ''
    if src and Path(src).exists(): return Path(src)
    name = event['sound'].split('.')[-1]
    if '/Audio/Combat/' in event['sound']:
        return ROOT / 'audio/combat' / name.rsplit('_', 1)[0] / f'{name}.wav'
    if '/Footsteps/' in event['sound']:
        surface = event['sound'].split('/Footsteps/')[1].split('/')[0]
        return ROOT / 'audio/footsteps' / surface / f'{name}.wav'
    raise FileNotFoundError(event['sound'])


def gain_at(distance, footstep):
    inner = 350. if footstep else 450.
    if distance <= inner: return 1.
    u = min(1., (distance - inner) / 5000.)
    return 10 ** (-48. * math.sqrt(u) / 20.)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('take'); ap.add_argument('--out', default='fight')
    a = ap.parse_args()
    take = Path(a.take)
    events = json.loads((take / 'audio.json').read_text())
    cams = list(csv.DictReader(open(take / 'camera.csv')))
    frames = len(cams)
    length = int(frames / FPS * RATE) + RATE
    mix = np.zeros((length, 2), np.float32)
    cache = {}
    used = {}
    for e in events:
        path = source_file(e)
        if path not in cache: cache[path] = read_wav(path)
        s = cache[path]
        if s.shape[1] == 2: s = s.mean(1, keepdims=True)
        pitch = float(e.get('pitch', 1.))
        if abs(pitch - 1.) > 1e-3:
            t = np.arange(0, len(s) - 1, pitch)
            s = np.interp(t, np.arange(len(s)), s[:, 0])[:, None]
        cam = cams[min(max(e['frame'], 0), frames - 1)]
        eye = np.array([float(cam['x']), float(cam['y']), float(cam['z'])])
        yaw = math.radians(float(cam['yaw']))
        at = np.array([e['x'], e['y'], e['z']])
        footstep = '/Footsteps/' in e['sound']
        if e.get('2d'):
            g, pan = 1., 0.
        else:
            d = at - eye; dist = float(np.linalg.norm(d))
            g = gain_at(dist, footstep)
            right = np.array([-math.sin(yaw), math.cos(yaw), 0.])      # Unreal: +Y is right of +X
            pan = float(np.clip(np.dot(d / max(dist, 1.), right) * .7, -1, 1))
        vol = float(e.get('volume', 1.)) * g
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        start = int(e['frame'] / FPS * RATE)
        end = min(length, start + len(s))
        if end <= start: continue
        mix[start:end, 0] += s[:end - start, 0] * vol * l * math.sqrt(2)
        mix[start:end, 1] += s[:end - start, 0] * vol * r * math.sqrt(2)
        used[path.name] = used.get(path.name, 0) + 1
    amb = read_wav(AMBIENCE)
    if amb.shape[1] == 1: amb = np.repeat(amb, 2, 1)
    reps = int(math.ceil(length / len(amb)))
    mix += np.tile(amb, (reps, 1))[:length] * .7
    mix = mix[:int(frames / FPS * RATE)]
    # Soft limiter, then peak at -1 dBFS.
    mix = np.tanh(mix * 1.1) / math.tanh(1.1)
    mix *= 10 ** (-1 / 20) / max(1e-6, float(np.abs(mix).max()))
    fade_in, fade_out = int(.5 * RATE), int(1.2 * RATE)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]; mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    out_wav = take / f'{a.out}.wav'
    with wave.open(str(out_wav), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype('<i2').tobytes())
    seconds = frames / FPS
    vf = f'fade=t=in:st=0:d=0.5,fade=t=out:st={seconds - 1.2:.3f}:d=1.2'
    mp4 = take / f'{a.out}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', str(take / 'frame_%05d.jpg'), '-i', str(out_wav),
                    '-vf', vf, '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
                    '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', str(mp4)], check=True)
    small = take / f'{a.out}-720p.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(small)], check=True)
    report = {'frames': frames, 'seconds': seconds, 'events': len(events), 'sounds_used': used, 'video': str(mp4), 'video_720p': str(small),
              'bytes': mp4.stat().st_size}
    (take / f'{a.out}-mix.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sounds_used'}), len(used), 'distinct sounds')


if __name__ == '__main__':
    main()
