"""Repaint the enlarged volcano and its caldera on the painted world map, from the exact game terrain.

    python games/yorimichi/world/map/repaint_volcano.py prepare
    python games/yorimichi/world/map/repaint_volcano.py paint
    python games/yorimichi/world/map/repaint_volcano.py register

The volcano grew and moved (docs/VOLCANO.md), and Belmonte moved 600 m north with its map knots, so Belmonte keeps its
painted pixels. Only the volcano, its former summit and the strip up to Belmonte's join are repainted: the edit mask
covers them and leaves the Mega Park, the city, the coast and Belmonte. One Sunburst high call is recorded by
atelier.ai.ledger before and after submission; an existing ledger prevents a second call. Pixels outside the
feathered mask equal the parent. Work and evidence stay in build/yorimichi/map/volcano_repaint/.
"""
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402
_sys.path.insert(0, str(yori.REGIONS)); _sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, hashlib, json, shutil, sys, time
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageFilter

from map_projection import BOUNDS, X_KNOTS, Y_KNOTS, project, unproject

SHEET = yori.MAP / 'painted' / 'world_map.png'
PROVENANCE = yori.MAP / 'painted' / 'world_map_provenance.json'
REGISTRATION = yori.MAP / 'painted' / 'world_map_registration.json'
LEDGER = yori.MAP / 'painted' / 'volcano_repaint.provenance.json'
WORK = yori.OUT / 'map' / 'volcano_repaint'
OW, OH = 1536, 1024                  # the painting call (3:2)
TOP = 180                            # sheet row where the 3:2 crop starts: Belmonte's river stays in view
FORMER = (550., 1930., 800.)         # the former summit's painted snow, to clear (x, y, radius)
KEEP = (-150., 1300., 520.)          # the Mega Park and its canyon keep their painting (x, y, radius)
FEATHER = 14                         # sheet pixels


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def to_world(px, py):
    """Sheet pixels (one per projected unit, row zero at BOUNDS[3]) to world metres."""
    return unproject(BOUNDS[0] + np.asarray(px, float), X_KNOTS), unproject(BOUNDS[3] - np.asarray(py, float), Y_KNOTS)


def crop_box(sheet):
    w = sheet.width; h = round(w / 1.5)
    return [0, TOP, w, TOP + h]


def edit_mask(size):
    """Where the sheet changes: the new cone, the former summit's snow and the strip up to Belmonte's join."""
    from hidamari import mountains as M
    w, h = size
    px, py = np.meshgrid(np.arange(w) + .5, np.arange(h) + .5)
    x, y = to_world(px, py)
    _, _, r, _ = M.polar(x, y)
    area = (r < M.BASE_RADIUS - 80) | (np.hypot(x - FORMER[0], y - FORMER[1]) < FORMER[2])
    area |= M.contains(x, y) & (y > M.BOUNDS[3] - 650)
    area &= np.hypot(x - KEEP[0], y - KEEP[1]) > KEEP[2]
    area &= y > 760                                          # the city's northern edge keeps its painting
    im = Image.fromarray(area.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(FEATHER))
    return im


def plan(sheet, mask):
    """The parent sheet with the masked area drawn from the game's terrain: forest, rock, snow and relief shading."""
    from hidamari import layout as H, mountains as M
    gx, gy, gz = M.surface_grid(H.north_base_height)
    snow = M.snow(gx, gy, H.north_base_height); col = M.colours(gx, gy, gz)
    dy, dx = np.gradient(gz, M.STEP, M.STEP)
    n = np.stack([-dx, -dy, np.ones_like(gz)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = np.array([-.5, .55, .67]); shade = np.clip(n @ (light / np.linalg.norm(light)), 0, 1)
    w, h = sheet.size
    px, py = np.meshgrid(np.arange(w) + .5, np.arange(h) + .5)
    x, y = to_world(px, py)
    fx = np.clip((x - M.BOUNDS[0]) / M.STEP, 0, gz.shape[1] - 1.001); fy = np.clip((y - M.BOUNDS[1]) / M.STEP, 0, gz.shape[0] - 1.001)
    i, j = fx.astype(int), fy.astype(int)
    c = col[j, i]; s = snow[j, i][..., None]; l = shade[j, i][..., None]
    # Map colours: the painting's autumn woodland where the ground is forest green, grey rock where it is exposed,
    # white snow; light from the north-west.
    # Trees stand to the same tree line as the game plants them (hidamari/layout.py), over rock-coloured ground too.
    z = gz[j, i]; _, _, r, angle = M.polar(x, y)
    ceiling = M.lifted(330) + M.noise(x, y, 140, 77) * 60 * M.LIFT
    woodland = (M.smooth((ceiling - z) / (100 * M.LIFT)) * (r > M.rim_radius(angle)) * (snow[j, i] < .3))[..., None]
    woodland = np.maximum(woodland, np.clip((c[..., 1:2] / np.maximum(c[..., 0:1], 1e-4) - 1.1) / .5, 0, 1))
    hue = M.noise(x, y, 60., 7)[..., None]
    wood = np.where(hue > .25, np.array([214, 120, 44]), np.where(hue > -.3, np.array([200, 160, 62]), np.array([70, 96, 52])))
    ground = (wood * woodland + np.array([132, 126, 118]) * (1 - woodland)) * (.55 + .7 * l)
    drawn = ground * (1 - s) + np.array([236, 240, 246]) * (.7 + .35 * l) * s
    a = np.asarray(mask, float)[..., None] / 255
    out = np.asarray(sheet, float) * (1 - a) + drawn * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def prepare(args):
    WORK.mkdir(parents=True, exist_ok=True)
    if (WORK / 'parent.png').exists() and not args.force:
        sys.exit('prepare: parent.png is already there (the sheet before the edit); --force to take the committed one again')
    shutil.copyfile(SHEET, WORK / 'parent.png'); shutil.copyfile(PROVENANCE, WORK / 'parent_provenance.json')
    parent = Image.open(WORK / 'parent.png').convert('RGB')
    mask = edit_mask(parent.size); mask.save(WORK / 'mask.png')
    box = crop_box(parent)
    plan(parent, mask).save(WORK / 'plan.png')
    parent.crop(box).resize((OW, OH), Image.LANCZOS).save(WORK / 'current-crop.png')
    Image.open(WORK / 'plan.png').crop(box).resize((OW, OH), Image.LANCZOS).save(WORK / 'layout-crop.png')
    info = dict(crop_box=box, parent_file_sha256=sha((WORK / 'parent.png').read_bytes()))
    json.dump(info, open(WORK / 'prepare.json', 'w'), indent=2)
    print('prepare:', json.dumps(info))


PROMPT = (
    'Use case: precise-object-edit. This is a local correction to Yorimichi\'s hand-painted watercolour world map. '
    'Image1 is the edit target: the existing map, with the town and racecourse of Belmonte and its river at the top, '
    'the autumn foothills in the middle and the grid city by the sea below. Image2 is the same frame and scale with '
    'the middle band redrawn as an exact plan from the game: the volcano is now far larger and stands farther '
    'north-east. Repaint only that band, following Image2 for every position, outline and size. '
    'Paint one huge volcano whose summit is a wide caldera: a broad, nearly circular crater with a flat floor dusted '
    'with patchy snow, ringed by steep grey rock walls and a broken crest with three small spires. Long white snow '
    'gullies radiate down its flanks from the crest; between them grey volcanic rock gives way lower down to the '
    'same autumn forest (orange, gold and dark green) as the rest of the map. The map is seen from high above and '
    'its north is compressed, so the volcano reads as a wide, low bird\'s-eye shape, exactly as wide and as tall as in '
    'Image2. Remove the old small snow-capped volcano west of it: that ground is now a forested, rocky shoulder of the '
    'big volcano. Keep Image1\'s framing, watercolour style, colours and paper texture. Keep Belmonte, its river, '
    'racecourse and town, the city grid, the coast, the sea, the lake and the canyon park in the western foothills '
    'exactly as they are. Top-down map view, same scale, no text, pins, labels, frame or legend. No second volcano.'
)


def paint(args):
    sys.path.insert(0, str(yori.GAME / 'tools'))
    from treehouse_art import MODEL, QUALITY, rel, sunburst
    from atelier.ai.ledger import run_once
    inputs = [WORK / 'current-crop.png', WORK / 'layout-crop.png']
    missing = [rel(p) for p in inputs if not p.exists()]
    if missing: sys.exit(f'paint: missing {missing}; run prepare first')
    if args.dry_run:
        print(PROMPT); return
    if LEDGER.exists():
        sys.exit(f'paint: {rel(LEDGER)} exists (status {json.load(open(LEDGER)).get("status")}): the call is never sent twice')
    from atelier.env import require
    require('OPENAI_API_KEY')                       # loads the ignored .env; never prints the value
    record = dict(stage='world-map-volcano-repaint', requested_model=MODEL, quality=QUALITY,
                  size=f'{OW}x{OH}', endpoint='/v1/images/edits', execution='games/yorimichi/world/map/repaint_volcano.py',
                  prompt=PROMPT, prompt_sha256=sha(PROMPT.encode()),
                  reference_files={rel(p): sha(p.read_bytes()) for p in inputs},
                  crop_box=json.load(open(WORK / 'prepare.json'))['crop_box'], started_at=now())
    def operation():
        t = time.time()
        png, usage = sunburst(PROMPT, f'{OW}x{OH}', inputs)
        (WORK / 'generated.png').write_bytes(png)
        return dict(usage=usage, output={rel(WORK / 'generated.png'): sha(png)}, elapsed_seconds=round(time.time() - t, 1),
                    hashes='Input file hashes; output is the returned PNG. The registered crop is the committed sheet.')
    try: result = run_once(LEDGER, record, operation)
    except Exception as error:
        sys.exit(f'paint: submission uncertain ({type(error).__name__}); inspect the ledger, do not resubmit')
    print('paint:', result['status'], f'({result["elapsed_seconds"]} s)')


def register(args):
    """Lay the painting on its crop of the parent inside the feathered mask, then commit the sheet and its knots."""
    sys.path.insert(0, str(yori.GAME / 'tools'))
    from treehouse_art import rel
    parent = Image.open(WORK / 'parent.png').convert('RGB'); box = json.load(open(WORK / 'prepare.json'))['crop_box']
    gen = Image.open(WORK / 'generated.png').convert('RGB').resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    painted = parent.copy(); painted.paste(gen, box[:2])
    a = np.asarray(Image.open(WORK / 'mask.png'), float)[..., None] / 255
    sheet = np.asarray(parent, float) * (1 - a) + np.asarray(painted, float) * a
    sheet = Image.fromarray(np.clip(np.rint(sheet), 0, 255).astype(np.uint8))
    outside = np.asarray(Image.open(WORK / 'mask.png')) == 0
    assert np.array_equal(np.asarray(sheet)[outside], np.asarray(parent)[outside]), 'pixels outside the mask changed'
    sheet.save(WORK / 'world_map_candidate.png')
    check = sheet.copy(); check.paste(Image.new('RGB', sheet.size, (255, 40, 40)), (0, 0),
                                      Image.open(WORK / 'mask.png').point(lambda v: 60 if 8 < v < 248 else 0))
    check.convert('RGB').save(WORK / 'registration-check.jpg', quality=88)
    if args.dry_run:
        print('register: candidate and check written; nothing committed'); return
    sheet.save(SHEET, optimize=True)
    json.dump({'bounds': BOUNDS, 'projection_x': [[float(a), float(b)] for a, b in X_KNOTS],
               'projection_y': [[float(a), float(b)] for a, b in Y_KNOTS]}, open(REGISTRATION, 'w'), indent=2)
    ledger = json.load(open(LEDGER))
    prov = dict(model='mixed; the volcano band by gpt-image-2.5-sunburst', quality='high',
                parent=json.load(open(WORK / 'parent_provenance.json')),
                edit=dict(stage=ledger['stage'], model=ledger['requested_model'], quality=ledger['quality'], size=ledger['size'],
                          prompt=ledger['prompt'], crop_box=box, mask='build/yorimichi/map/volcano_repaint/mask.png',
                          ledger=rel(LEDGER), generated_sha256=next(iter(ledger['output'].values()))),
                sheet_sha256=sha(SHEET.read_bytes()), registered_at=now())
    json.dump(prov, open(PROVENANCE, 'w'), indent=2)
    print('register: committed', rel(SHEET), sheet.size)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('stage', choices=['prepare', 'paint', 'register'])
    ap.add_argument('--force', action='store_true'); ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    dict(prepare=prepare, paint=paint, register=register)[args.stage](args)


if __name__ == '__main__':
    main()
