"""Mix the sound of a filmed horse race (-racefilm) and encode the video.

    python games/yorimichi/tools/mix_race_film.py build/yorimichi/racefilm/<take> [--out name]

AHorseRace logs every sound it starts with the captured frame (audio.json), the camera for every frame (camera.csv),
and the song's start, its jumps back into the loop and its fade at the finish (film.json "music"). The song stays
stereo and is laid down exactly as the game played it; the crowd loop runs under the race from the moment it
started; every other cue is placed at its frame, attenuated by its distance from the camera and panned by its bearing
(the 2D cues are centred). Then the frames and the mix become an H.264/AAC MP4 (1080p60 and a 720p copy).

The machine is shared with guarded game runs, so ffmpeg runs at nice 10 with two decoder, filter and encoder threads,
and reports its progress (or its lack) every ten seconds; a stalled or overlong encode, or one past 4 GiB, is ended.
Encode only when no graded game is loading or running.
"""
import argparse, csv, json, math, queue, signal, subprocess, sys, threading, time, wave
from pathlib import Path
import numpy as np
from atelier.safety.guard import attach as attach_memory_guard

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
SOURCE = yori.OUT / 'audio/hippodrome'
RATE = 48000
FPS = 60
THREADS = ['-threads', '2']
FILTER_THREADS = ['-filter_threads', '2']
ENCODER_LIMIT_GIB = 4.   # the small render slot's ceiling; the encoder is expected to stay well under 3 GiB


def encode(label, inputs, outputs, frames, report):
    """One ffmpeg run, niced and thread-capped. A film encodes at a few frames a second, so it gets a second a frame
    plus ten minutes in all, and five minutes without a new frame counts as stalled."""
    cmd = ['nice', '-n', '10', 'ffmpeg', '-y', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1', *FILTER_THREADS,
           *inputs, *THREADS, *outputs]
    watch(cmd, label, frames, report, deadline=600 + frames, stall=300)


def watch(cmd, label, frames, report, deadline, stall):
    """Run cmd, which writes ffmpeg -progress lines, under its own memory guard (atelier.safety, pinned to the encoder's
    pid and start, at ENCODER_LIMIT_GIB): a guard around this script would not see the encoder's memory. Say every ten
    seconds how far it has got, or that it has not moved. Past the deadline or the stall limit, if the guard stops, or
    if it fails, its own child is ended and the error raised."""
    lines = queue.Queue()
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as p:
        reader = threading.Thread(target=lambda: [lines.put(l) for l in p.stdout], daemon=True); reader.start()
        t0 = last_note = moved = time.monotonic(); done = 0
        try:
            with attach_memory_guard(p.pid, report / 'memory-health.json', duration=deadline + 60,
                                     limit_gib=ENCODER_LIMIT_GIB) as monitor:
                while p.poll() is None or reader.is_alive() or not lines.empty():
                    try:
                        line = lines.get(timeout=1)
                        if line.startswith('frame='):
                            n = int(line[6:] or 0)
                            if n > done: done, moved = n, time.monotonic()
                    except queue.Empty:
                        pass
                    now = time.monotonic()
                    if now - last_note >= 10:
                        last_note = now
                        quiet = '' if now - moved < 10 else f', no frame progress for {now - moved:.0f} s'
                        print(f'{label}: frame {done}/{frames} ({100 * done / max(frames, 1):.0f}%), {now - t0:.0f} s, '
                              f'{footprint(report)}{quiet}', flush=True)
                    if p.poll() is None and monitor is not None and monitor.poll() is not None:
                        raise RuntimeError(f'{label}: the memory guard exited before ffmpeg')
                    if now - t0 > deadline or now - moved > stall:
                        raise TimeoutError(f'{label}: {"no frame progress for %.0f s" % (now - moved) if now - moved > stall else "past its %.0f s deadline" % deadline}')
        except BaseException:
            if p.poll() is None:
                p.terminate()
                try: p.wait(10)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
            raise
    print(f'{label}: frame {done}/{frames}, {time.monotonic() - t0:.0f} s, {footprint(report)}, exit {p.returncode}',
          flush=True)
    if p.returncode: raise subprocess.CalledProcessError(p.returncode, cmd)


def footprint(report):
    """The encoder's footprint and peak from its guard's report."""
    try: h = json.loads((report / 'memory-health.json').read_text())
    except (OSError, ValueError): return 'footprint not sampled yet'
    return f'{h.get("footprint_bytes", 0) / 2**30:.2f} GiB footprint, peak {h.get("peak_bytes", 0) / 2**30:.2f} GiB'


def read_wav(path):
    with wave.open(str(path)) as w:
        n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    assert sw == 2, (path, 'expects 16-bit PCM')
    a = np.frombuffer(raw, dtype='<i2').astype(np.float32).reshape(-1, ch) / 32768.
    if rate != RATE:
        t = np.arange(0, len(a), rate / RATE)
        a = np.stack([np.interp(t, np.arange(len(a)), a[:, c]) for c in range(ch)], 1)
    return a if ch == 2 else np.repeat(a, 2, 1)


def source_file(sound):
    """/Game/Audio/Hippodrome/HR_Hoof_03.HR_Hoof_03 -> audio/hippodrome/HR_Hoof/HR_Hoof_03.wav; Music_race_cup -> music/race_cup.wav."""
    name = sound.split('.')[-1]
    if name.startswith('Music_'): return SOURCE / 'music' / f'{name[6:]}.wav'
    return SOURCE / name.rsplit('_', 1)[0] / f'{name}.wav'


def gain_at(distance):
    if distance <= 450.: return 1.
    u = min(1., (distance - 450.) / 5000.)
    return 10 ** (-48. * math.sqrt(u) / 20.)


def music_track(events, frames, length):
    """The song as the game played it: from 'start', jumping at each 'seek', ducking at the 'fade'."""
    out = np.zeros((length, 2), np.float32)
    start = next((e for e in events if e['event'] == 'start'), None)
    if not start: return out
    song = read_wav(source_file(start['sound']))
    cuts = [(int(start['frame'] / FPS * RATE), float(start['at']))]
    cuts += [(int(e['frame'] / FPS * RATE), float(e['at'])) for e in events if e['event'] == 'seek']
    cuts.append((length, None))
    for (at, pos), (until, _) in zip(cuts, cuts[1:]):
        src = int(pos * RATE); n = min(until - at, len(song) - src)
        if n > 0: out[at:at + n] = song[src:src + n]
    gain = np.ones(length, np.float32)
    for e in events:
        if e['event'] != 'fade': continue
        a = int(e['frame'] / FPS * RATE); b = min(length, a + int(float(e['seconds']) * RATE))
        gain[a:b] = np.linspace(1., float(e['level']), b - a); gain[b:] = float(e['level'])
    return out * gain[:, None]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('take'); ap.add_argument('--out', default='race')
    a = ap.parse_args()
    take = Path(a.take)
    events = json.loads((take / 'audio.json').read_text())
    film = json.loads((take / 'film.json').read_text())
    cams = list(csv.DictReader(open(take / 'camera.csv')))
    frames = len(cams)
    length = int(frames / FPS * RATE)
    mix = music_track(film.get('music', []), frames, length) * .9
    cache, used = {}, {}
    for e in events:
        path = source_file(e['sound'])
        if not path.exists() and Path(e.get('source', '')).is_file(): path = Path(e['source'])   # a cue from outside the race (a footstep)
        if path not in cache: cache[path] = read_wav(path)
        s = cache[path]
        pitch = float(e.get('pitch', 1.))
        if abs(pitch - 1.) > 1e-3:
            t = np.arange(0, len(s) - 1, pitch)
            s = np.stack([np.interp(t, np.arange(len(s)), s[:, c]) for c in range(2)], 1)
        start = int(e['frame'] / FPS * RATE)
        if start >= length: continue
        if e.get('loop'):
            s = np.tile(s, (int(math.ceil((length - start) / len(s))), 1))
        if e.get('2d'):
            l = r = 1.
        else:
            cam = cams[min(max(e['frame'], 0), frames - 1)]
            eye = np.array([float(cam['x']), float(cam['y']), float(cam['z'])]); yaw = math.radians(float(cam['yaw']))
            d = np.array([e['x'], e['y'], e['z']]) - eye; dist = float(np.linalg.norm(d))
            g = gain_at(dist)
            right = np.array([-math.sin(yaw), math.cos(yaw), 0.])      # Unreal: +Y is right of +X
            pan = float(np.clip(np.dot(d / max(dist, 1.), right) * .7, -1, 1))
            mono = s.mean(1, keepdims=True); s = np.repeat(mono, 2, 1)
            l, r = g * math.cos((pan + 1) * math.pi / 4) * math.sqrt(2), g * math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
        vol = float(e.get('volume', 1.))
        end = min(length, start + len(s))
        mix[start:end, 0] += s[:end - start, 0] * vol * l
        mix[start:end, 1] += s[:end - start, 1] * vol * r
        used[path.name] = used.get(path.name, 0) + 1
    # Soft limiter, then peak at -1 dBFS.
    mix = np.tanh(mix * 1.1) / math.tanh(1.1)
    mix *= 10 ** (-1 / 20) / max(1e-6, float(np.abs(mix).max()))
    fade_in, fade_out = int(.5 * RATE), int(1.5 * RATE)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]; mix[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    out_wav = take / f'{a.out}.wav'
    with wave.open(str(out_wav), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype('<i2').tobytes())
    seconds = frames / FPS
    vf = f'fade=t=in:st=0:d=0.5,fade=t=out:st={seconds - 1.5:.3f}:d=1.5'
    mp4 = take / f'{a.out}.mp4'
    encode('1080p', [*THREADS, '-framerate', str(FPS), '-i', str(take / 'frame_%05d.jpg'), '-i', str(out_wav)],
           ['-vf', vf, '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
            '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', str(mp4)], frames, take / f'{a.out}.encode-1080p')
    small = take / f'{a.out}-720p.mp4'
    encode('720p', [*THREADS, '-i', str(mp4)], ['-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'slow', '-crf', '22',
                                               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(small)], frames,
           take / f'{a.out}.encode-720p')
    report = {'frames': frames, 'seconds': seconds, 'events': len(events), 'music': film.get('music', []), 'sounds_used': used,
              'video': str(mp4), 'video_720p': str(small), 'bytes': mp4.stat().st_size}
    (take / f'{a.out}-mix.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('sounds_used', 'music')}), len(used), 'distinct sounds')


if __name__ == '__main__':
    # A guard stops this script with SIGTERM. Unwind as an exception, so watch() ends its ffmpeg instead of orphaning it.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main()
