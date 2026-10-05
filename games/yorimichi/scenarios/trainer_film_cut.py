"""Caption and encode the sword trainer film (trainer_film.py) into an MP4.

    python games/yorimichi/scenarios/trainer_film_cut.py build/yorimichi/trainer_film/kaede.mp4 kaede1 [--skip TEXT]

Every frame carries its shot's caption and a line of Kaede's state (her level, what her brain is doing, both healths).
The frames are 30 fps and real time; the MP4 is H.264 (CRF 20). --skip TEXT leaves out every shot whose caption
contains TEXT. menu.png (her menu) is kept beside the film as it is.
"""
import json, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fog_film_cut import caption   # noqa: E402  (the same caption boxes)

ROOT = Path(__file__).resolve().parents[3]
FILMS = ROOT / 'build/yorimichi/trainer_film'


def state_line(k):
    if not k or k.get('bout') in (None, 'home', 'talking'):
        return ''
    hp = lambda v: '-' if v is None else f'{v:.0f}'
    return f"Kaede · {k.get('level')} · {k.get('intent')}   her health {hp(k.get('health'))}   yours {hp(k.get('player_health'))}"


def frame(job):
    src, dst, text, k = job
    img = Image.open(src).convert('RGB')
    caption(img, [text, state_line(k)])
    img.save(dst, quality=95)


def film(out, take, skip=()):
    folder = FILMS / take
    frames = [f for f in json.load(open(folder / 'frames.json'))['frames'] if not any(t in f[1] for t in skip)]
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(folder / ('frame_%05d.jpg' % i), Path(tmp) / ('f_%05d.jpg' % n), text, k) for n, (i, text, k) in enumerate(frames)]
        with ProcessPoolExecutor(4) as pool:
            list(pool.map(frame, jobs, chunksize=16))
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', str(Path(tmp) / 'f_%05d.jpg'),
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                        str(out)], check=True)
    print(out, len(frames), 'frames')


if __name__ == '__main__':
    argv, skip = sys.argv[1:], []
    while '--skip' in argv:
        i = argv.index('--skip'); skip.append(argv[i + 1]); del argv[i:i + 2]
    film(Path(argv[0]), argv[1], skip)
