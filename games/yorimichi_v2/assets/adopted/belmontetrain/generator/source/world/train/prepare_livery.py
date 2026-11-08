"""Prepare the livery swatches generated in ChatGPT for the train build (plain Python with Pillow, run once by hand).

    python3 games/yorimichi/world/train/prepare_livery.py BLUE IVORY ROOF UNDERFRAME [BACKHEAD SMOKEBOX_DOOR]
    python3 games/yorimichi/world/train/prepare_livery.py wall WALL1 WALL2 WALL3
    python3 games/yorimichi/world/train/prepare_livery.py floors LINO TILES

Writes games/yorimichi/assets/vehicles/belmonte-train/textures/*.jpg, the committed sources build.py reads:
- livery-blue-panel.jpg: one lined lower-body panel (rivet strips, brass beading), 2048 x 1024, mapped once per
  panel between the doors, skirt to belt;
- livery-ivory.jpg: the upper-body enamel without the swatch's brass line (the shell models its own), cropped above
  that line and cross-faded top to bottom so it tiles both ways, 2048 x 1024 for 2.00 x 1.00 m;
- roof-canvas.jpg: the canvas roof cropped to a whole number of seam pitches (seven) so it tiles, turned a quarter so
  the seams run across the coach, 1024 x 1024;
- underframe.jpg: the riveted black steel of the bogies and underframe, 1024 x 1024;
- backhead.jpg and smokebox-door.jpg: the locomotive's firebox backhead (gauges, water glasses, valves and the
  fire-door arch painted on) and its round smokebox door, 1024 x 1024 each, mapped whole on their faces;
- wall-peel.jpg: the worn second class's matchboard walls, brown paint peeling onto an old green coat. Three square
  swatches drawn to join edge to edge (1|2|3|1) are laid side by side, 3072 x 1024 for 3.60 x 1.20 m, so a wall runs
  three different stretches before it repeats (textures.py resamples it to 2048 x 1024 for T_BT_PaintPeel: Unreal
  mips and streams only power-of-two textures);
- lino.jpg: the second-class saloon's worn green linoleum, a seamless swatch, 1024 x 1024 for 2.40 x 2.40 m;
- canteen-tiles.jpg: the canteen's greasy white tiles, cropped grout line to grout line (11 x 10 tiles of about
  10 cm) so the grid runs on across the seams, 1024 x 1024 for 1.10 x 1.00 m.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[2] / 'assets' / 'vehicles' / 'belmonte-train' / 'textures'
IVORY_CROP = 800              # rows above the swatch's brass line (rows 821-833 of 887)
FADE = 64
ROOF_CROP = (32, 1222)        # seven seam pitches of 170 px
TILE_CROP = (0, 0, 1253, 1172)  # the canteen tiles swatch, grout to grout: 11 tiles across, 10 down


def save(img, name, size):
    OUT.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').resize(size, Image.LANCZOS).save(OUT / name, quality=90, optimize=True)
    print(name, size)


def main(blue, ivory, roof, underframe, backhead=None, smokebox_door=None):
    save(Image.open(blue), 'livery-blue-panel.jpg', (2048, 1024))
    a = np.asarray(Image.open(ivory).convert('RGB'), float)[:IVORY_CROP]
    body = a[:-FADE].copy()
    t = np.linspace(0, 1, FADE)[:, None, None]
    body[:FADE] = a[-FADE:] * (1 - t) + a[:FADE] * t
    save(Image.fromarray(body.clip(0, 255).astype(np.uint8)), 'livery-ivory.jpg', (2048, 1024))
    r = Image.open(roof).convert('RGB')
    r = r.crop((0, ROOF_CROP[0], r.width, ROOF_CROP[1])).rotate(90, expand=True)
    save(r, 'roof-canvas.jpg', (1024, 1024))
    save(Image.open(underframe), 'underframe.jpg', (1024, 1024))
    if backhead:
        save(Image.open(backhead), 'backhead.jpg', (1024, 1024))
    if smokebox_door:
        save(Image.open(smokebox_door), 'smokebox-door.jpg', (1024, 1024))


def wall(*swatches):
    tiles = [Image.open(f).convert('RGB').resize((1024, 1024), Image.LANCZOS) for f in swatches]
    strip = Image.new('RGB', (1024 * len(tiles), 1024))
    for k, t in enumerate(tiles):
        strip.paste(t, (1024 * k, 0))
    save(strip, 'wall-peel.jpg', strip.size)


def floors(lino, tiles):
    save(Image.open(lino), 'lino.jpg', (1024, 1024))
    save(Image.open(tiles).convert('RGB').crop(TILE_CROP), 'canteen-tiles.jpg', (1024, 1024))


if __name__ == '__main__':
    if sys.argv[1:2] == ['wall']:
        wall(*sys.argv[2:5])
    elif sys.argv[1:2] == ['floors']:
        floors(*sys.argv[2:4])
    else:
        main(*sys.argv[1:7])
