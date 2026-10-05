"""Caption and encode the move set review films (botw_moves_film.py) into one MP4.

    python games/yorimichi/scenarios/botw_moves_film_cut.py [--audio] build/yorimichi/botw/moves_film/review.mp4 link1 \
        cairo1:-Shield cairo2:Shield

A take may name the sections to keep (take:A,B) or to leave out (take:-A,B); --skip TEXT leaves out every shot whose
caption contains TEXT. Each character's sections play in the
film's order whichever take they come from, characters in the order they first appear; each character opens with a
title card. Every frame carries
the character and section, the shot's caption, the move set's action and mode, and its stamina wheels and health bar,
all read from the take's frames.json. The frames are 30 fps and real time; the MP4 is H.264. Silent, or with --audio
the game's own sounds from each take's audio.json (whooshes, clangs, footsteps, at the frame each started on) over the
countryside ambience, as AAC.
"""
import json, os, subprocess, sys, tempfile, wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
FILMS = ROOT / 'build/yorimichi/botw/moves_film'
FONTS = Path('/Users/Shared/Epic Games/UE_5.8/Engine/Content/Slate/Fonts')
CARD = 75                                    # title card frames (2.5 s)
ORDER = ['On foot', 'Sprint', 'Double jump', 'Equipment', 'Lock-on and dodges', 'Sword', 'Fight', 'Knocked down', 'Sword guard', 'Shield',
         'Getting hit', 'Paraglider', 'Paraglider grip', 'Swimming', 'Climbing']
AUDIO = ROOT / 'build/yorimichi/audio'
RATE = 48000


def font(size, bold=True):
    for name in ('Roboto-Bold.ttf' if bold else 'Roboto-Regular.ttf', 'Roboto-Bold.ttf'):
        if (FONTS / name).exists():
            return ImageFont.truetype(str(FONTS / name), size)
    return ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', size)


def title(who):
    return who


def shadowed(d, xy, text, f, fill=(255, 255, 255, 255)):
    d.text((xy[0] + 2, xy[1] + 2), text, font=f, fill=(0, 0, 0, 170))
    d.text(xy, text, font=f, fill=fill)


def wheels(d, x, y, stamina, rings, exhausted):
    """BOTW's stamina wheels: one ring per unit, filled clockwise from the top; red while exhausted."""
    r = 18
    for i in range(int(rings)):
        cx = x + i * (2 * r + 10)
        box = (cx - r, y - r, cx + r, y + r)
        d.ellipse(box, outline=(0, 0, 0, 110), width=8)
        part = max(0., min(1., stamina - i))
        if part > 0:
            colour = (235, 80, 60, 255) if exhausted else (140, 230, 110, 255)
            d.arc(box, -90, -90 + 360 * part, fill=colour, width=8)


def card(size, who):
    img = Image.new('RGB', size, (14, 18, 24))
    d = ImageDraw.Draw(img)
    big, small = font(64), font(28, False)
    w = d.textlength(title(who), font=big)
    d.text(((size[0] - w) / 2, size[1] / 2 - 70), title(who), font=big, fill=(255, 255, 255))
    for i, line in enumerate(("The merged move set: Link's moves and Cairo's double jump, filmed in real time",
                              'Captions: the move, then the move set\'s own action and mode; top right, stamina and health')):
        w = d.textlength(line, font=small)
        d.text(((size[0] - w) / 2, size[1] / 2 + 20 + i * 40), line, font=small, fill=(190, 200, 210))
    return img


def caption(job):
    src, dst, row, who, rings = job
    img = Image.open(src).convert('RGBA')
    W, H = img.size
    over = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    _, section, label, action, mode, stamina, exhausted, health, armed = row
    # Top left: who, and the section.
    shadowed(d, (28, 22), title(who).upper(), font(22))
    shadowed(d, (28, 52), section, font(30))
    # Top right: stamina wheels and the health bar.
    wheels(d, W - 40 - (int(rings) - 1) * 46, 46, stamina, rings, exhausted)
    bar = (W - 228, 82, W - 28, 96)
    d.rectangle(bar, fill=(0, 0, 0, 120))
    d.rectangle((bar[0], bar[1], bar[0] + (bar[2] - bar[0]) * max(0., min(1., health / 100.)), bar[3]), fill=(235, 95, 85, 230))
    shadowed(d, (bar[0], bar[3] + 6), f'health {health:.0f}', font(18, False), (235, 235, 235, 255))
    # The lower third: the shot's caption, and the move set's own state under it.
    f = font(34)
    w = d.textlength(label, font=f)
    d.rectangle((0, H - 132, max(w + 76, 420), H - 38), fill=(0, 0, 0, 120))
    shadowed(d, (36, H - 122), label, f)
    shadowed(d, (36, H - 74), f'action {action}  ·  mode {mode}' + ('  ·  sword drawn' if armed else ''),
             font(22, False), (200, 230, 255, 255))
    Image.alpha_composite(img, over).convert('RGB').save(dst, quality=92)
    return dst


def read(path):
    """A 16- or 24-bit PCM WAV as mono floats at RATE."""
    with wave.open(str(path)) as w:
        n, ch, rate, width = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
    if width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        a = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) << 8 >> 8).astype(np.float32) / 8388608.
    else:
        a = np.frombuffer(raw, '<i2').astype(np.float32) / 32768.
    a = a.reshape(-1, ch).mean(1)
    if rate != RATE:
        a = np.interp(np.arange(0, len(a), rate / RATE), np.arange(len(a)), a)
    return a


def sound(event, cache):
    """An audio log event's wave: its recorded source file, else the cue's file in the build's audio folder."""
    name = event['sound'].split('.')[-1]
    if name not in cache:
        path = Path(event['source']) if event.get('source') and Path(event['source']).exists() else None
        if path is None:
            hits = list(AUDIO.rglob(name + '.wav'))
            path = hits[0] if hits else None
        cache[name] = read(path) if path else None
    return cache[name]


def mix(placed, frames, path):
    """placed: (output frame, event) for every sound; writes a 16-bit stereo WAV of them over the ambience."""
    out = np.zeros(int(frames / 30. * RATE) + RATE, np.float32)
    cache, missing = {}, set()
    for frame, e in placed:
        a = sound(e, cache)
        if a is None:
            missing.add(e['sound']); continue
        pitch = float(e.get('pitch', 1.) or 1.)
        if abs(pitch - 1.) > 1e-3:
            a = np.interp(np.arange(0, len(a), pitch), np.arange(len(a)), a)
        gain = float(e.get('volume', 1.))
        start = int(frame / 30. * RATE)
        end = min(len(out), start + len(a))
        out[start:end] += a[:end - start] * gain * .8
    ambience = AUDIO / 'combat/ambience_countryside/ambience_countryside_01.wav'
    if ambience.exists():
        bed = read(ambience)
        out += np.resize(bed, len(out)) * .18
    peak = np.abs(out).max()
    if peak > .98:
        out *= .98 / peak
    out = out[:int(frames / 30. * RATE)]
    pcm = (np.repeat(out[:, None], 2, 1) * 32767.).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    if missing:
        print('no wave for', sorted(missing)[:8])
    return len(placed) - len(missing)


def main():
    args = sys.argv[1:]
    audio = '--audio' in args
    # --skip TEXT (repeatable) leaves out every shot whose caption contains TEXT (a retake elsewhere, or a bad shot).
    skips = [args[i + 1] for i, a in enumerate(args) if a == '--skip']
    args = [a for i, a in enumerate(args) if a not in ('--audio', '--skip') and (i == 0 or args[i - 1] != '--skip')]
    out, takes = Path(args[0]), args[1:]
    if not takes:
        raise SystemExit(__doc__)
    # Every kept section of every take, as (who, section, folder, rows, rings).
    parts = []
    for arg in takes:
        take, _, spec = arg.partition(':')
        folder = Path(take) if os.path.isdir(take) else FILMS / take
        data = json.load(open(folder / 'frames.json'))
        drop = spec.startswith('-')
        named = [x for x in spec.lstrip('-').split(',') if x]
        unknown = [x for x in named if x not in ORDER]
        if unknown:
            raise SystemExit(f'{take}: no section {unknown}; sections are {ORDER}')
        rows = [r for r in data['frames'] if (folder / ('frame_%05d.jpg' % r[0])).exists() and not any(t in r[2] for t in skips)]
        for section in dict.fromkeys(r[1] for r in rows):
            if named and (section in named) == drop:
                continue
            parts.append((data['who'], section, folder, [r for r in rows if r[1] == section], data['rings']))
            print(folder.name, data['who'], section, len(parts[-1][3]), 'frames')
    people = list(dict.fromkeys(p[0] for p in parts))
    parts.sort(key=lambda p: (people.index(p[0]), ORDER.index(p[1]) if p[1] in ORDER else len(ORDER)))
    work = Path(tempfile.mkdtemp(prefix='cut_', dir=out.parent))
    n, jobs, who = 0, [], None
    placed, positions = [], {}   # each kept take frame's output frame, per folder
    for person, section, folder, rows, rings in parts:
        if person != who:
            size = Image.open(folder / ('frame_%05d.jpg' % rows[0][0])).size
            who, title_card = person, card(size, person)
            for _ in range(CARD):
                title_card.save(work / ('frame_%05d.jpg' % n), quality=92); n += 1
        for r in rows:
            positions.setdefault(folder, {})[r[0]] = n
            jobs.append((folder / ('frame_%05d.jpg' % r[0]), work / ('frame_%05d.jpg' % n), r, person, rings)); n += 1
    with ProcessPoolExecutor() as pool:
        for i, _ in enumerate(pool.map(caption, jobs, chunksize=32)):
            if i % 1000 == 0:
                print('captioned', i, '/', len(jobs), flush=True)
    sound_in = []
    if audio:
        for folder, where in positions.items():
            log = folder / 'audio.json'
            if not log.exists():
                print(folder.name, 'has no audio.json'); continue
            for e in json.loads(log.read_text()):
                if e.get('frame', -1) in where:
                    placed.append((where[e['frame']], e))
        track = work / 'audio.wav'
        print('sounds mixed:', mix(placed, n, track))
        sound_in = ['-i', str(track), '-c:a', 'aac', '-b:a', '192k', '-shortest']
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', str(work / 'frame_%05d.jpg'), *sound_in[:2],
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '23', '-pix_fmt', 'yuv420p', *sound_in[2:], '-movflags', '+faststart',
                    str(out)], check=True)
    for f in work.iterdir():
        f.unlink()
    work.rmdir()
    print(out, f'{n} frames, {n / 30.:.0f} s, {out.stat().st_size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
