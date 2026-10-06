#!/usr/bin/env python3
"""Hidamari hippodrome structures: a Sunburst concept of each object alone, painted from its drawing on the approved
kit sheet (assets/hippodrome/concepts/kit.jpg), then a Tripo image-to-model. The same stages as
tools/hidamari_props.py, so the concepts are checked before any credits are spent.

    uv run python games/yorimichi/tools/hippodrome_props.py concept [--only grandstand,stable] [--dry-run]
    uv run python games/yorimichi/tools/hippodrome_props.py model [--only ...] [--dry-run] [--approval "..."]
    uv run python games/yorimichi/tools/hippodrome_props.py sheet

Each structure lives in games/yorimichi/assets/hippodrome/props/<slug>/: concept.jpg with concept.json (the ledger
record of the paid call, atelier.ai.ledger.run_once: a slug with a record is never painted again; rename the record to
concept.rejected-N.json and the picture likewise to repaint), then job.json (the Tripo settings, task id and credits)
and <slug>.glb, the model with its texture made a 1024 JPEG (tools/treehouse_props.py's model stage: Tripo P2
image-to-model, a task submitted once and resumed by id, an uncertain POST never repeated).

concept: gpt-image-2.5-sunburst, quality high, through /v1/images/edits with three context images: the object's own
drawing cut from the kit sheet (CROP, a fixed pixel box, so the cut is reproducible from the committed sheet), the
whole kit sheet and the aerial concept. Build files go to build/yorimichi/hippodrome/props/: refs/ (the cuts),
concepts/<slug>/concept.png (the full-size paintings) and tripo/<slug>/ (the Tripo work folders).
sheet: the concepts side by side, and four flat-shaded orthographic views of each GLB (drawn here in Python, no
Blender) with its triangle count, bounds and texture size, in build/yorimichi/review/hippodrome/.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, glb_parts, rel, sha, sheet as contact_sheet, sunburst

OUT = yori.ASSETS / 'hippodrome' / 'props'
WORK = yori.OUT / 'hippodrome' / 'props'
ORIGINALS, TRIPO, CUTS = WORK / 'concepts', WORK / 'tripo', WORK / 'refs'
CONCEPTS = yori.ASSETS / 'hippodrome' / 'concepts'
KIT, AERIAL = CONCEPTS / 'kit.jpg', CONCEPTS / 'aerial.jpg'
SHEETS = yori.REVIEW / 'hippodrome'

STYLE = ('Paint ONE object alone for 3D reconstruction: shown whole, in a three-quarter front view from slightly above, '
         'centred with a clear margin all round, on a plain flat light-grey background, soft even light, no cast '
         'shadow, no floor or ground, no text, letters or logos anywhere{allowed}, nothing else in the picture. '
         'Image 1 is the approved design of this object, cut from Image 2, the modelling reference sheet of the '
         'Hidamari hippodrome, a small countryside racecourse in Yorimichi, a stylised Japanese autumn game; Image 3 '
         'shows the racecourse from the air. Keep the design of the object in Image 1: the same shapes, colours, '
         'materials, proportions and hand-made character, in the same warm hand-painted style, chunky readable shapes, '
         'gently rounded edges, matte colours with soft variation and light weathering, believable real-world '
         'proportions, no photographic noise, no glossy highlights. Paint only this one object, none of the other '
         'things on the sheet. Every part must be solid and connected; nothing floating. The object: ')

# slug: (the object, the text allowed on it, its size in metres for the game (longest side, or height for upright
# things), the canvas, the Tripo face limit)
PROPS = {
    'grandstand': ('the long wooden grandstand of the racecourse, a single long building: a dark grey Japanese tiled '
                   'hip roof with gently upturned eaves on exposed timber posts and beams, rows of stepped wooden bench '
                   'seating rising toward the back, a central raised judges\' balcony with a timber railing and a small '
                   'roofed cupola on the ridge, a timber railing along the front, stairs at both ends, square stone '
                   'footings under every post; the front facing the viewer is open to the track and the back is a '
                   'closed timber plank wall', '', 60.0, '1536x1024', 30000),
    'starting_gate': ('an eight-stall horse racing starting gate in dark green painted steel: a row of eight narrow '
                      'stalls side by side under an open lattice frame top, each stall with a pair of front doors, a '
                      'number plate above each stall, the whole gate standing on four big black rubber wheels',
                      ', except the stall numbers 1 to 8 on the plates above the stalls, as in Image 1', 12.0,
                      '1536x1024', 20000),
    'judges_tower': ('a small square timber judges\' tower on four braced timber legs with cross bracing, square stone '
                     'footings, an external wooden stair with a railing climbing to a glazed lookout box with windows '
                     'on every side, under a dark grey tiled pyramid roof', '', 8.0, '1024x1536', 15000),
    'finish_post': ('a slim white painted round finish post of a racecourse on a small square stone base, topped by '
                    'a flat round red disc with a white rim facing the viewer', '', 5.5, '1024x1536', 6000),
    'tote_board': ('a racecourse results board: a wide painted timber frame on two thick posts with stone footings, a '
                   'small dark grey tiled roof on top, a round white clock face with black hands at the top centre, '
                   'two columns of dark number panels with a small white plate of a digit beside each row, low stone '
                   'planters of red, orange and yellow autumn flowers at its feet',
                   ', except the plain digits beside the panels and the clock numerals, as in Image 1', 10.0,
                   '1024x1024', 15000),
    'stable': ('a long low timber stable block with a dark grey Japanese tiled gable roof, white plastered gable ends '
               'with dark timber framing, six horse stall doors in a row along the long side, each a wooden lower half '
               'door with iron bars across its open upper half, lamps under the eaves, a few hay bales stacked by the '
               'doors and a small wheelbarrow, on a stone plinth', '', 28.0, '1536x1024', 20000),
}
# where each object is drawn on the kit sheet (left, top, right, bottom, in its 1536 x 1024 pixels)
CROP = {'grandstand': (0, 25, 1072, 345), 'starting_gate': (1064, 100, 1536, 340),
        'judges_tower': (112, 350, 420, 665), 'finish_post': (25, 350, 125, 665),
        'tote_board': (1118, 340, 1520, 655), 'stable': (5, 660, 845, 965)}


def prompt_for(slug):
    what, allowed = PROPS[slug][:2]
    return STYLE.format(allowed=allowed) + what + '.'


def cut(slug):
    """The object's drawing cut from the kit sheet, written to build/; returns its path."""
    from PIL import Image
    dest = CUTS / f'{slug}.jpg'; dest.parent.mkdir(parents=True, exist_ok=True)
    Image.open(KIT).convert('RGB').crop(CROP[slug]).save(dest, 'JPEG', quality=95)
    return dest


def concept(slug, dry):
    from atelier.ai.ledger import run_once
    folder = OUT / slug; record = folder / 'concept.json'; prompt = prompt_for(slug); size = PROPS[slug][3]
    refs = [cut(slug), KIT, AERIAL]
    if dry:
        print(f'--- {slug} {size}{" (recorded)" if record.exists() else ""}\n{prompt}\n'); return slug, None
    if record.exists(): return slug, None
    folder.mkdir(parents=True, exist_ok=True); t = time.time()

    def generate():
        png, usage = sunburst(prompt, size, images=refs)
        (ORIGINALS / slug).mkdir(parents=True, exist_ok=True); (ORIGINALS / slug / 'concept.png').write_bytes(png)
        return {'usage': usage, 'concept_sha256': sha(png), 'seconds': round(time.time() - t, 1),
                'compact_copy': compact(png, folder / 'concept.jpg', 'props')}
    try:
        run_once(record, {'model': MODEL, 'quality': QUALITY, 'size': size, 'endpoint': '/v1/images/edits',
                          'prompt': prompt, 'references': {rel(p): sha(p.read_bytes()) for p in refs},
                          'reference_cut': {'from': rel(KIT), 'box': list(CROP[slug])},
                          'execution': 'games/yorimichi/tools/hippodrome_props.py',
                          'purpose': 'Hidamari hippodrome structure concept for Tripo'}, generate)
    except Exception as e:  # noqa: BLE001 - kept by the ledger as submission_uncertain; never retried here
        print(slug, 'FAILED', type(e).__name__, flush=True); return slug, type(e).__name__
    print(slug, f'ok {time.time() - t:.0f}s', flush=True)
    return slug, None


def model(slug, faces, approval, dry):
    import treehouse_props
    return treehouse_props.model(slug, faces or PROPS[slug][4], approval, dry, out=OUT, tripo=TRIPO,
                                 originals=ORIGINALS, stage='hippodrome_prop', record='concept.json')


# ------------------------------------------------------------------ GLB check views (no Blender)
def _accessor(doc, binary, index):
    import numpy as np
    acc = doc['accessors'][index]; view = doc['bufferViews'][acc['bufferView']]
    dtype = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}[acc['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']]
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0); item = np.dtype(dtype).itemsize * width
    stride = view.get('byteStride', item)
    raw = np.frombuffer(binary, np.uint8, count=stride * (acc['count'] - 1) + item, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, (acc['count'], item), (stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(acc['count'], width)


def _matrix(node):
    import numpy as np
    if 'matrix' in node: return np.array(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', (0, 0, 0, 1))
    r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    m = np.eye(4); m[:3, :3] = r * np.array(node.get('scale', (1, 1, 1))); m[:3, 3] = node.get('translation', (0, 0, 0))
    return m


def glb_mesh(path):
    """(world positions (n, 3), triangles (m, 3), per-triangle colour (m, 3), stats) of a GLB, in glTF axes (+y up)."""
    import io, numpy as np
    from PIL import Image
    doc, binary = glb_parts(Path(path).read_bytes())
    textures = {}
    for i, image in enumerate(doc.get('images', [])):
        v = doc['bufferViews'][image['bufferView']]; s = v.get('byteOffset', 0)
        textures[i] = np.asarray(Image.open(io.BytesIO(binary[s:s + v['byteLength']])).convert('RGB'))
    verts, tris, cols = [], [], []; base = 0

    def walk(n, parent):
        nonlocal base
        node = doc['nodes'][n]; m = parent @ _matrix(node)
        for prim in doc['meshes'][node['mesh']]['primitives'] if 'mesh' in node else []:
            pos = _accessor(doc, binary, prim['attributes']['POSITION']).astype(float)
            idx = (_accessor(doc, binary, prim['indices']).reshape(-1, 3) if 'indices' in prim
                   else np.arange(len(pos)).reshape(-1, 3))
            world = pos @ m[:3, :3].T + m[:3, 3]
            colour = np.full((len(idx), 3), 200.0)
            mat = doc.get('materials', [{}])[prim['material']] if 'material' in prim else {}
            tex = (mat.get('pbrMetallicRoughness') or {}).get('baseColorTexture')
            if tex and 'TEXCOORD_0' in prim['attributes']:
                image = textures[doc['textures'][tex['index']]['source']]
                uv = _accessor(doc, binary, prim['attributes']['TEXCOORD_0'])[idx].mean(1) % 1.0
                h, w = image.shape[:2]
                colour = image[(uv[:, 1] * (h - 1)).astype(int), (uv[:, 0] * (w - 1)).astype(int)].astype(float)
            verts.append(world); tris.append(idx + base); cols.append(colour); base += len(pos)
        for c in node.get('children', []): walk(c, m)
    scene = doc['scenes'][doc.get('scene', 0)]
    for n in scene['nodes']: walk(n, np.eye(4))
    v, t, c = np.concatenate(verts), np.concatenate(tris), np.concatenate(cols)
    lo, hi = v.min(0), v.max(0)
    stats = {'triangles': int(len(t)), 'vertices': int(len(v)), 'bounds_min': [round(float(x), 4) for x in lo],
             'bounds_max': [round(float(x), 4) for x in hi], 'extent_xyz': [round(float(x), 4) for x in hi - lo],
             'textures': [f'{im.shape[1]}x{im.shape[0]}' for im in textures.values()],
             'bytes': Path(path).stat().st_size}
    return v, t, c, stats


# view name: (screen-right axis, screen-up axis, toward-the-viewer axis), in glTF axes
VIEWS = {'+z': ((1, 0, 0), (0, 1, 0), (0, 0, 1)), '+x': ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
         '-z': ((-1, 0, 0), (0, 1, 0), (0, 0, -1)), '-x': ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
         'top (+y)': ((1, 0, 0), (0, 0, -1), (0, 1, 0))}


def views(path, dest, cell=360):
    """Flat-shaded orthographic views of a GLB, painter's order, one texture sample per triangle."""
    import numpy as np
    from PIL import Image, ImageDraw
    v, t, c, stats = glb_mesh(path)
    centre = (v.min(0) + v.max(0)) / 2; scale = (cell - 24) / max(v.max(0) - v.min(0))
    tri = v[t]; normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-12
    canvas = Image.new('RGB', (cell * len(VIEWS), cell + 28), (236, 234, 228)); d = ImageDraw.Draw(canvas)
    for k, (name, (right, up, toward)) in enumerate(VIEWS.items()):
        right, up, toward = map(np.array, (right, up, toward))
        light = np.abs(normal @ (toward * .8 + up * .5 + right * .3) / np.linalg.norm(toward * .8 + up * .5 + right * .3))
        shade = np.clip(c * (.45 + .55 * light)[:, None], 0, 255).astype(int)
        p = tri - centre
        sx = cell * k + cell / 2 + (p @ right) * scale; sy = cell / 2 - (p @ up) * scale
        for i in np.argsort((p @ toward).mean(1)):
            d.polygon([(sx[i, j], sy[i, j]) for j in range(3)], fill=tuple(shade[i]))
        d.text((cell * k + 8, cell + 6), name, fill=(30, 30, 30))
    Path(dest).parent.mkdir(parents=True, exist_ok=True); canvas.save(dest, quality=88)
    return dest, stats


def sheet(slugs=None):
    slugs = slugs or list(PROPS)
    contact_sheet([(OUT / s / 'concept.jpg', s) for s in slugs], SHEETS / 'props-concepts.jpg', 512, 384, 3)
    report = {}
    for s in slugs:
        glb = OUT / s / f'{s}.glb'
        if not glb.exists(): continue
        _, stats = views(glb, SHEETS / 'props' / f'{s}-views.jpg')
        e = stats['extent_xyz']; stats['proportions_xyz'] = [round(x / max(e), 3) for x in e]
        stats['game_size_m'] = PROPS[s][2]
        job = OUT / s / 'job.json'
        if job.exists(): stats['credits_consumed'] = json.loads(job.read_text()).get('credits_consumed')
        report[s] = stats; print(s, json.dumps(stats), flush=True)
    if report:
        contact_sheet([(SHEETS / 'props' / f'{s}-views.jpg', s) for s in report], SHEETS / 'props-models.jpg',
                      1800, 360, 1)
        (SHEETS / 'props-models.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'model', 'sheet'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--faces', type=int, default=0, help='Tripo face limit (default: each structure\'s own)')
    ap.add_argument('--concurrency', type=int, default=4, help='Tripo refuses (HTTP 429) beyond about five running tasks')
    ap.add_argument('--approval', default='pending', help='who approved spending the credits, kept in job.json')
    a = ap.parse_args()
    slugs = [s for s in PROPS if not a.only or s in a.only.split(',')]
    if a.stage == 'sheet': return sheet(slugs)
    if a.stage == 'concept' and not a.dry_run:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; never prints the value
    job = (lambda s: concept(s, a.dry_run)) if a.stage == 'concept' else (lambda s: model(s, a.faces, a.approval, a.dry_run))
    with ThreadPoolExecutor(1 if a.dry_run else a.concurrency) as ex:
        results = list(ex.map(job, slugs))
    bad = [(s, e) for s, e in results if e]
    for s, e in bad: print('FAILED', s, e)
    if a.stage == 'concept' and not a.dry_run: sheet(slugs)
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
