"""Caption and encode the volumetric fog film (fog_film.py) into an MP4, and pair its stills fog on | fog off.

    python games/yorimichi/scenarios/fog_film_cut.py build/yorimichi/fog_film/fog.mp4 fog1 [--stills] [--skip TEXT]

Every frame carries its shot's caption and whether the "Volumetric fog" setting was on. The frames are 30 fps and
real time; the MP4 is H.264 (CRF 20). --stills also writes <take>/compare/<view>.jpg: the view with the fog on (left)
and off (right), each labelled with its GPU frame time. --skip TEXT leaves out every shot whose caption contains TEXT.
"""
import json, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from atelier.engine import unreal_root

ROOT = Path(__file__).resolve().parents[3]
FILMS = ROOT / 'build/yorimichi/fog_film'
FONTS = unreal_root()/'Engine/Content/Slate/Fonts'


def font(size, bold=True):
    name = FONTS / ('Roboto-Bold.ttf' if bold else 'Roboto-Regular.ttf')
    return ImageFont.truetype(str(name), size) if name.exists() else ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', size)


def caption(img, lines, corner='bl'):
    d = ImageDraw.Draw(img, 'RGBA')
    s = img.height / 720.
    big, small = font(round(26 * s)), font(round(20 * s), False)
    pad = round(18 * s)
    y = img.height - pad - round(64 * s) if corner == 'bl' else pad
    for text, f in zip(lines, (big, small)):
        if not text:
            continue
        w = d.textlength(text, font=f)
        d.rounded_rectangle((pad - 8 * s, y - 4 * s, pad + w + 8 * s, y + f.size + 8 * s), 6 * s, fill=(0, 0, 0, 120))
        d.text((pad, y), text, font=f, fill=(255, 255, 255, 255))
        y += f.size + round(14 * s)


def frame(job):
    src, dst, text, on = job
    img = Image.open(src).convert('RGB')
    caption(img, [text, 'Volumetric fog: on' if on else 'Volumetric fog: off'])
    img.save(dst, quality=95)


def film(out, take, skip=()):
    folder = FILMS / take
    frames = [f for f in json.load(open(folder / 'frames.json'))['frames'] if not any(t in f[1] for t in skip)]
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(folder / ('frame_%05d.jpg' % i), Path(tmp) / ('f_%05d.jpg' % n), text, on) for n, (i, text, on) in enumerate(frames)]
        with ProcessPoolExecutor(4) as pool:
            list(pool.map(frame, jobs, chunksize=16))
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', str(Path(tmp) / 'f_%05d.jpg'),
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                        str(out)], check=True)
    print(out, len(frames), 'frames')


def stills(take):
    folder = FILMS / take
    gpu = json.load(open(folder / 'frames.json')).get('gpu', {})
    (folder / 'compare').mkdir(exist_ok=True)
    for on in sorted(folder.glob('*_on.png')):
        view = on.name[:-len('_on.png')]
        off = folder / f'{view}_off.png'
        if not off.exists():
            continue
        a, b = Image.open(on).convert('RGB'), Image.open(off).convert('RGB')
        sheet = Image.new('RGB', (a.width + b.width + 8, a.height), (20, 20, 20))
        ms = gpu.get(view, {})
        for img, x, side in ((a, 0, 'on'), (b, a.width + 8, 'off')):
            t = ms.get(side)
            caption(img, [f'{view.replace("_", " ")}: fog {side}', f'GPU {t:.1f} ms' if t else ''], 'tl')
            sheet.paste(img, (x, 0))
        sheet.save(folder / 'compare' / f'{view}.jpg', quality=92)
        print(folder / 'compare' / f'{view}.jpg')


if __name__ == '__main__':
    argv, skip = sys.argv[1:], []
    while '--skip' in argv:
        i = argv.index('--skip'); skip.append(argv[i + 1]); del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    if '--stills' in sys.argv:
        stills(args[1])
    if (FILMS / args[1] / 'frames.json').exists() and json.load(open(FILMS / args[1] / 'frames.json'))['frames']:
        film(Path(args[0]), args[1], skip)
