"""Crater Park restyle textures: the park's realistic textures repainted in the island's style (docs/CRATERPARK.md,
"Restyle"), after the art-direction paintovers in assets/craterpark/concepts.

    uv run python games/yorimichi/tools/craterpark_textures.py paint [--only pool,bowl] [--redo] [--jobs 3] [--dry-run]
    python games/yorimichi/tools/craterpark_textures.py finish

paint: gpt-image-2.5-sunburst, quality high, one ledgered call per recorded prompt (atelier.ai.images.paint, which
records it with atelier.ai.ledger before submitting). A surface is an edit of the original texture (Image 1, stretched
to the request's frame so its layout maps one to one) in the style of a paintover crop (Image 2): 1024x1024 for a square
texture, 1536x1024 for a wide one, 1024x1536 for a tall one. A world texture, for a material whose meshes have no UVs,
is a new painting in the style of a crop. The compact copy and provenance go to assets/craterpark/restyle/<slug>.jpg|json
(and into assets/source-library.json); the full PNG stays in build/yorimichi/craterpark/restyle. A recorded slug is
never submitted again: --redo (with --only) moves a done record and its copy to build/.../restyle/rejected/ and pays
for a new one; a record whose call is uncertain is never retried.

finish: offline, any Python with NumPy and Pillow. Writes build/yorimichi/craterpark/textures/<slug>.png for every
original texture and <material>.png for the world textures, and textures.json:

    {"textures": {"textures/tex-0073.png": {"png", "sha256", "slug", "how"}},
     "world_aligned": {"material_024": {"png", "sha256", "slug", "metres", "how"}}}

A surface keeps the original's aspect at 1024 pixels on its long side; it is made to wrap on the axes the original wraps
on and brought to its palette colour (an albedo), its variation stretched (DETAIL); a REPAINTED surface is finished from
another surface's painting. A world texture is 1024x1024, wraps both ways and carries the material's colour
itself, so its material's Tint becomes white; `metres` is the suggested world size of one tile for a world-aligned
(triplanar) projection. The skating geometry and its UVs are never touched.
"""
import argparse
import hashlib
import json
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402

GAME = Path(__file__).resolve().parents[1]
SOURCE = GAME / 'assets' / 'craterpark'
PAINTED = SOURCE / 'restyle'
CONCEPTS = SOURCE / 'concepts'
MEGAPARK = GAME / 'assets' / 'megapark'
LIBRARY = GAME / 'assets' / 'source-library.json'
WORK = yori.OUT / 'craterpark' / 'restyle'
OUT = yori.OUT / 'craterpark' / 'textures'
# Style crops (file, box in its pixels): the tiled plaza with its pale concrete, terracotta and wooden ramps; the dark
# snake-run bowls with their pale walls and wooden deck tops; the Mega Park paintover's lavender-grey rock close up.
STYLES = {
    'plaza': (CONCEPTS / 'paintover-dropin.jpg', (0, 560, 1536, 1024)),
    'bowls': (CONCEPTS / 'paintover-bowls.jpg', (0, 420, 900, 1024)),
    'rock': (MEGAPARK / 'concepts' / 'improve-riding.jpg', (0, 330, 820, 1024)),
    # the editor park's approved concepts: a viaduct pier, and a ramp's boards
    'viaduct': (CONCEPTS / 'editor' / 'support-design-viaduct.jpg', (1080, 90, 1536, 700)),
    'ramps': (CONCEPTS / 'editor' / 'prado-graphics-layout.jpg', (1150, 690, 1536, 1024)),
    # the crater floor's dark cinder, stones, moss and grass tufts (concepts/editor/crater-floor-layout.jpg)
    'crater': (CONCEPTS / 'editor' / 'crater-floor-layout.jpg', (680, 400, 1360, 1000)),
    # the approved crater floor's ground: cool grey volcanic stone and darker gravel (concepts/editor/crater-floor.jpg)
    'crater_stone': (CONCEPTS / 'editor' / 'crater-floor.jpg', (640, 400, 1000, 620)),
}
SURFACE = ('Image 1 is a tileable texture from a skate park in a stylised game, stretched to fill this frame. Image 2 '
           'shows the art direction of the game: soft painterly shapes, flat matte colour, clean well-kept surfaces, pale '
           'warm concrete, dark grey bowl concrete, warm wooden ramps, terracotta tiles. Repaint Image 1 as a tileable '
           'texture in that style, keeping exactly the layout, scale, proportions and direction of its features (bands, '
           'edges, joints, tiles, boards, stones, cracks) so it fits the same 3D surfaces: every feature stays where it is '
           'and meets the frame edges where it did. Seen perfectly flat and straight-on, filling the frame edge to edge: '
           'no perspective, no object outline, no shadows or lighting gradient, even brightness everywhere, no text. '
           'Hand-painted like the background art of a Japanese animated film: soft broad strokes and gentle colour '
           'variation that still read as the real material, medium detail that holds up when repeated, no photographic '
           'grime, stains, dirt or noise. The surface: ')
WORLD = ('Image 1 shows the art direction of a stylised game: soft painterly shapes, flat matte colour. Paint a seamless '
         'tileable texture in that style, seen from directly above, perfectly flat and straight-on, filling the square '
         'edge to edge: no perspective, no horizon, no object outline, no shadows or lighting gradient, even brightness '
         'everywhere, no text, repeating seamlessly on all four sides. Hand-painted like the background art of a '
         'Japanese animated film, soft strokes, medium detail that holds up when repeated over a large area, no '
         'photographic grime or noise. The surface: ')

# The palette means are albedos, not the colours the paintovers show: the island's sun, blue sky fill and grade
# (setup_project.py: film toe .3, slope .7, cool shadow gain) show a sunlit flat surface at about albedo^0.5 per channel
# in linear terms, which halves value contrast and saturation. Each mean is the target colour (assets/craterpark/concepts,
# target-* and paintover-*) taken back through that response, measured on the review shots (docs/CRATERPARK.md, "Restyle").
PALE = (168, 164, 152)          # the targets' pale near-neutral concrete
WOOD = (170, 124, 84)
# slug: (original texture, style, the axes it wraps on, how it is made to wrap, description, palette mean sRGB or None)
# 'blend' wraps a stochastic surface with a half-tile offset copy; 'edges' keeps a laid-out one in place and only evens
# out the colour where its opposite edges meet.
SURFACES = {
    'concrete_deck': ('textures/tex-0073.png', 'plaza', 'xy', 'edges', 'smooth poured concrete deck in pale warm '
                      'cream-grey, its slightly darker margins kept, a few soft trowel sweeps and one or two fine hairline '
                      'cracks', PALE),
    'ledge': ('textures/tex-0051.png', 'plaza', 'x', 'edges', 'two long smooth cast-concrete ledge blocks in pale warm '
              'sandstone beige with a thin joint between them and softly rounded top and bottom edges', (172, 165, 150)),
    'flagstone': ('textures/tex-0004.png', 'rock', 'xy', 'edges', 'irregular flagstone paving of pale lavender-grey and '
                  'warm grey volcanic stones with a few ochre-tinted stones and pale cream mortar joints', (150, 144, 146)),
    'bowl': ('textures/tex-0024.png', 'bowls', 'xy', 'blend', 'smooth dark slate-grey skate-bowl concrete with a faint '
             'cool blue cast, soft broad trowel strokes and very subtle mottling', (48, 52, 60)),
    'stamped': ('textures/tex-0059.png', 'plaza', 'xy', 'edges', 'stamped concrete paving in pale warm sand beige with '
                'a soft network of shallow irregular flagstone-like grooves', (170, 160, 138)),
    'concrete_edge': ('textures/tex-0029.png', 'plaza', 'xy', 'edges', 'smooth pale warm grey poured concrete with the '
                      'slightly darker trowelled strips along its left and right edges, clean, no moss', PALE),
    # Rust-brown frames round the plaza (g_air); a saturated orange mean read as drawn lines.
    'tile_edge': ('textures/tex-0006.png', 'plaza', 'x', 'edges', 'glazed terracotta tiles in warm orange-brown with '
                  'thin cream grout lines and a rounded terracotta bullnose band, as in Image 1', (138, 92, 70)),
    # The plaza deck: warm tan, as the g_air target's timber-toned decks; pale beige washed out from above.
    'paving': ('textures/tex-0064.png', 'plaza', 'xy', 'edges', 'large irregular cut-stone paving slabs in pale warm '
               'grey and soft beige with narrow joints', (160, 128, 92)),
    'concrete': ('textures/tex-0043.png', 'plaza', 'xy', 'blend', 'smooth pale warm grey concrete with a very fine '
                 'soft speckle', (168, 164, 152)),
    'masonite': ('textures/tex-0060.png', 'bowls', 'xy', 'edges', 'a warm honey-brown masonite skate ramp surface, two '
                 'smooth panels with a joint between them, soft wood-fibre grain', WOOD),
    'herringbone': ('textures/tex-0030.png', 'plaza', 'xy', 'edges', 'herringbone terracotta brick paving in warm '
                    'orange-brown, crossed by bands of charcoal-grey bricks exactly as in Image 1, thin pale joints', None),
    'coping_frieze': ('textures/tex-0001.png', 'plaza', 'x', 'edges', 'a pale warm grey concrete coping band with a '
                      'rounded edge above a band of carved pale stone ornament, as in Image 1', None),
    'coping_tile': ('textures/tex-0058.png', 'bowls', 'x', 'edges', 'a pale warm grey concrete coping band with a '
                    'rounded edge above a row of dark slate-grey square tiles, as in Image 1', None),
    'aggregate': ('textures/tex-0074.png', 'plaza', 'x', 'edges', 'a narrow band of indigo-and-white painted ceramic '
                  'tiles along the top above warm ochre-brown exposed pebble aggregate concrete, as in Image 1', None),
    'ramp_boards': ('textures/tex-0032.png', 'bowls', 'xy', 'edges', 'warm honey-brown plywood skate ramp boards with '
                    'thin seams and smooth soft grain', WOOD),
    'retaining_wall': ('textures/tex-0031.png', 'rock', 'xy', 'edges', 'an irregular dry-stone retaining wall of '
                       'lavender-grey volcanic stones with small yellow-green moss in a few joints', (88, 84, 82)),
    'stair_brick': ('textures/tex-0036.png', 'plaza', 'xy', 'edges', 'rows of long glazed bricks for stair treads in '
                    'alternating bands of warm terracotta orange and dark umber brown, as in Image 1', None),
    'pool': ('textures/tex-0016.png', 'plaza', 'xy', 'blend', 'a smooth painted swimming-pool floor in clear bright '
             'sky blue with very soft lighter brush strokes', (82, 158, 212)),
    'planter': ('textures/tex-0067.png', 'plaza', 'xy', 'edges', 'a board-formed concrete planter wall in soft warm '
                'mid-grey with faint vertical form-board lines, clean, no writing', (146, 134, 114)),
    'turtle': ('textures/tex-0021.png', 'plaza', 'xy', 'edges', 'a Portuguese cobble mosaic of small square setts: a '
               'big cream sea-turtle figure on charcoal-grey setts exactly as in Image 1, with its dark border strip',
               None),
    'side_bank': ('textures/tex-0025.png', 'plaza', 'xy', 'edges', 'a pale warm grey concrete bank panel with a smooth '
                  'raised border frame around a finely textured inner field, and the thin dark tile strip down its left '
                  'side, as in Image 1', (166, 161, 150)),
}
# slug: (style, how it is made to wrap, description) of the world textures painted from nothing; the formwork grid is
# laid out, so it keeps its joints in place
WORLD_PAINTINGS = {
    'ground': ('rock', 'blend', 'the bare ground of a volcanic crater: lavender-grey volcanic gravel and scree with scattered '
               'small and medium grey rocks, a little fine dark ash soil, a few tufts of dry golden grass and small '
               'yellow-green moss patches; no snow, no leaves'),
    # the editor park's support towers (v2/editor_supports.py), after concepts/editor/supports-rock*.jpg
    'basalt': ('rock', 'blend', 'the side of a tall columnar basalt cliff: dark blue-grey volcanic basalt columns standing '
               'side by side in long vertical stripes with crisp narrow joints, faint horizontal cracks, soft lighter '
               'grey edges, a few small patches of yellow-green moss and pale lichen; no snow, no sky, no ground'),
    # the editor park's viaduct supports (v2/editor_supports.py), after concepts/editor/support-design-viaduct.jpg
    'masonry': ('viaduct', 'edges', 'the wall of a mountain viaduct as in Image 1: squarish warm charcoal-grey and '
                'grey-brown basalt blocks of slightly varied sizes in rough courses, soft rounded worn edges, thin joints '
                'only a little lighter than the stone so they stay subtle, gentle painterly variation from block to block, '
                'two or three tiny yellow-green moss tufts; not blue, no bright mortar grid, no snow'),
    'cast_concrete': ('bowls', 'edges', 'a large smooth cast-concrete wall in pale warm grey, faint rectangular formwork panel '
                      'joints in a regular grid of four equal panels, very subtle soft tonal variation, clean'),
    # the editor park's crater floor, for the volcano's ground inside the crater (not a park material: WORLD_ALIGNED)
    'crater_floor': ('crater_stone', 'blend', 'the bare ground of a volcanic crater floor, only its stone and gravel as in '
                     'Image 1: a light cool mid-grey volcanic stone surface, soft and slightly bluish grey, broken by large '
                     'irregular patches of darker charcoal-grey gravel and fine scree several times bigger than the small '
                     'stones, the patches rounded blobs of different sizes scattered evenly in every direction, never '
                     'diagonal bands, stripes, rows or streaks, seen from straight above; scattered small and medium angular grey stones with pale tops, broad gentle variation in tone '
                     'over the whole square; neutral and cool, no brown, no tan, no snow, no moss, no grass, no plants, '
                     'no boulders, no paths'),
}
# material: (painting, metres per tile, palette mean sRGB). The meshes have no UVs: the hillside and the foundations and
# bridges get world-aligned textures. 'megapark:rock' is the Mega Park's restyled rock, reused for the edge guard's
# steep walls.
WORLD_ALIGNED = {
    'material_023': ('cast_concrete', 4, (172, 166, 152)),      # foundations
    'material_024': ('ground', 8, (116, 112, 116)),             # the block's hillside (snow on top in the material)
    'material_025': ('cast_concrete', 4, (170, 165, 153)),      # access bridges
    'material_026': ('cast_concrete', 4, (148, 142, 132)),      # bridge supports
    'material_027': ('megapark:rock', 10, (150, 146, 152)),     # the edge guard (darker read as black shards in shade)
    'material_028': ('basalt', 6, (104, 106, 114)),             # editor-park basalt support towers
    'material_029': ('masonry', 5, (84, 80, 80)),              # editor-park viaducts and ramp sides: the concept's charcoal stone
    # not a park material: the volcano's ground inside the crater (hidamari/mountains.py), for M_NorthMountains
    'crater_floor': ('crater_floor', 16, (100, 98, 100)),       # the concept's warm dark grey gravel
}
# slug: (texture, style, how it is made to wrap, description, palette mean sRGB) of the UV-mapped textures painted from
# nothing: a material whose texture is `texture` gets the painting on its own UVs (the editor ramps' boards, laid along
# each piece: v2/editor_generate.piece_uv)
UV_PAINTINGS = {
    'ramp_planks': ('textures/ramp_planks.png', 'ramps', 'edges', 'the smooth wooden riding surface of a big skate ramp '
                    'exactly as in Image 1: soft warm honey and pale golden wood, six long boards stacked from top to bottom, '
                    'each running unbroken across the whole frame from left to right with no butt joints, the seams between '
                    'them only faint thin lines a little darker than the wood, gentle broad painterly variation in tone '
                    'from board to board, barely visible soft straight grain; calm and smooth, no knots, no nails, no '
                    'screws, no stripes of strong contrast', WOOD),
    # the ramps' outer sides: a fascia, not more riding boards
    'ramp_fascia': ('textures/ramp_fascia.png', 'ramps', 'edges', 'the smooth outer side panel (fascia) of a big wooden '
                    'skate ramp, as the ramp sides in Image 1: large smooth sheets of warm dark-stained plywood in a deep '
                    'chestnut brown, two tall panels side by side with one thin vertical joint, a narrow slightly darker '
                    'band along the top edge, soft broad painterly tonal variation, almost no grain; no boards, no planks, '
                    'no stripes, no nails', (112, 76, 52)),
    # the Prado bowl's rim: the concept's glazed terracotta brick coping
    'brick_coping': ('textures/brick_coping.png', 'bowls', 'edges', 'a band of glazed terracotta brick coping as on the '
                     'rim of the bowl in Image 1: one row of rounded bullnose terracotta bricks laid end to end from left '
                     'to right across the whole frame, each brick about one eighth of the frame wide, warm orange-red '
                     'glaze with soft highlights, thin pale cream grout lines between them; the brick row fills the frame '
                     'top to bottom', (176, 92, 62)),
}
# slug: (texture, plan, concept, size, description) of the decals painted onto one piece's own plan: the plan (a top-down
# render of the piece, v2/editor_generate.decal_frame) is Image 1 and the approved concept Image 2; the painting is laid
# over the piece from above (editor_generate.decal_uv), so it is never tiled
DECALS = {
    'prado': ('textures/prado.png', CONCEPTS / 'editor' / 'prado-plan.png', CONCEPTS / 'editor' / 'prado-graphics-layout.jpg',
              '1024x1536', 'Image 1 is the exact top-down plan of a concrete skate bowl called Prado, seen straight down: '
              'the flat floor is light, the curved transition walls darken toward the rim, the mid-grey ring round it is '
              'the flat deck, the thin dark line near the bottom is a spine, and everything black is outside the bowl. '
              'Image 2 is the approved design for its graphics. Paint the bowl\'s surface as a flat texture that fits '
              'Image 1 exactly, straight down, no perspective, no shadows, no lighting, keeping every edge exactly where it '
              'is: a smooth pale warm cream concrete floor; a big golden-yellow sun with soft rays on the floor in the '
              'upper wide part; sweeping deep blue and teal wave bands with a few orange accents following the walls all '
              'round; the word PRADO in big rounded navy-blue letters across the middle of the floor, reading left to '
              'right, upright with the top of the image at the top; a band of glazed terracotta tiles right along the '
              'rim where the walls meet the deck; the deck ring pale grey concrete; outside the bowl plain black. '
              'Hand-painted like the background art of a Japanese animated film, clean, soft, flat matte colour'),
}
# Surfaces finished from another surface's painting: slug: (painting, palette mean sRGB). The snake run's box tops carry
# the irregular-stone texture (material_003), but the paintovers make them wooden decks.
REPAINTED = {'flagstone': ('masonite', (160, 122, 86))}
# The paintings are smooth (about 5-10 grey levels of spread against 17-36 in the originals and the Mega Park's): their
# variation is stretched about the mean up to DETAIL of the mean luminance (at least DETAIL_MIN, at most DETAIL_GAIN times),
# so the concrete reads as a material under the island's flattening light (palette means above).
DETAIL = .14
DETAIL_MIN = 8.
DETAIL_GAIN = 2.5
# paintings that already carry the concepts' calm surface keep their own variation (at most this gain)
CALM = {'ramp_planks': 1., 'masonry': 1.2, 'ramp_fascia': 1., 'brick_coping': 1.2}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    """A path as provenance records it: repository-relative, or build/yorimichi/... (never a home-directory path)."""
    path = Path(path).resolve()
    for root, prefix in ((yori.REPO.resolve(), ''), (yori.OUT.resolve(), 'build/yorimichi/')):
        if path.is_relative_to(root):
            return prefix + path.relative_to(root).as_posix()
    return path.name


def size_for(w, h):
    return '1024x1024' if w == h else '1536x1024' if w > h else '1024x1536'


def style(key):
    """The crop a painting is styled on, written to build (its hash goes into each provenance)."""
    from PIL import Image
    path = WORK / f'style-{key}.png'
    if not path.exists():
        WORK.mkdir(parents=True, exist_ok=True)
        file, box = STYLES[key]
        Image.open(file).convert('RGB').crop(box).save(path)
    return path


def stretched(slug, texture, size):
    """The original texture resized to the request's frame, so the painting's layout maps one to one onto it."""
    from PIL import Image
    path = WORK / f'{slug}-source.png'
    w, h = map(int, size.split('x'))
    WORK.mkdir(parents=True, exist_ok=True)
    Image.open(SOURCE / texture).convert('RGB').resize((w, h), Image.LANCZOS).save(path)
    return path


def job(slug):
    """(prompt, size, reference images, metadata) of one painting."""
    if slug in SURFACES:
        texture, key, *_, text, _ = SURFACES[slug]
        from PIL import Image
        size = size_for(*Image.open(SOURCE / texture).size)
        refs = [stretched(slug, texture, size), style(key)]
        return SURFACE + text + '.', size, refs, {'original': {texture: sha((SOURCE / texture).read_bytes())}}
    if slug in DECALS:
        texture, plan, concept, size, text = DECALS[slug]
        return text + '.', size, [plan, concept], {'texture': texture}
    if slug in UV_PAINTINGS:
        texture, key, _, text, _ = UV_PAINTINGS[slug]
        return WORLD + text + '.', '1024x1024', [style(key)], {'texture': texture}
    key, _, text = WORLD_PAINTINGS[slug]
    return WORLD + text + '.', '1024x1024', [style(key)], {'materials': sorted(
        m for m, (s, *_) in WORLD_ALIGNED.items() if s == slug)}


def record_library():
    """Record every committed restyle and concept image in the asset library's manifest."""
    contract = json.loads(LIBRARY.read_text())
    files = {k: v for k, v in contract['files'].items()
             if not k.startswith(('craterpark/restyle/', 'craterpark/concepts/'))}
    for folder in (PAINTED, CONCEPTS):
        for path in sorted(folder.glob('*')):
            if path.suffix in {'.jpg', '.png'}:
                files[path.relative_to(LIBRARY.parent).as_posix()] = {'bytes': path.stat().st_size,
                                                                       'sha256': sha(path.read_bytes())}
    contract['files'] = dict(sorted(files.items()))
    LIBRARY.write_text(json.dumps(contract, indent=2) + '\n')


def set_aside(slug):
    """Move a done record and its copy out of the library, to build/.../restyle/rejected/, before paying again."""
    record = PAINTED / f'{slug}.json'
    if not record.exists():
        return
    status = json.loads(record.read_text()).get('status')
    if status != 'done':
        raise SystemExit(f'{slug}: its last call is {status}; reconcile it with the provider, never retry it blindly')
    dest = WORK / 'rejected'; dest.mkdir(parents=True, exist_ok=True)
    n = 1
    while (dest / f'{slug}.{n}.json').exists(): n += 1
    for path in (record, PAINTED / f'{slug}.jpg', WORK / f'{slug}.png'):
        if path.exists():
            shutil.move(path, dest / f'{slug}.{n}{path.suffix}')
    print(slug, f'set aside as rejected/{slug}.{n}', flush=True)


def paint_one(slug):
    from atelier.ai import images
    prompt, size, refs, extra = job(slug)
    record = PAINTED / f'{slug}.json'
    metadata = {'model': images.MODEL, 'prompt': prompt, 'references': {rel(p): sha(p.read_bytes()) for p in refs},
                **extra, 'purpose': 'Crater Park restyle texture'}
    stop = threading.Event(); started = time.monotonic()

    def heartbeat():
        while not stop.wait(25):
            print(f'{slug}: waiting on its single submission, {time.monotonic() - started:.0f}s', flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        result = images.paint(WORK / f'{slug}.png', prompt, size, refs, record=record, metadata=metadata,
                              model=images.MODEL, quality='high')
    finally:
        stop.set()
    result['compact'] = images.compact(WORK / f'{slug}.png', PAINTED / f'{slug}.jpg', 1024, 92, '4:4:4')
    record.write_text(json.dumps(result, indent=2) + '\n')
    print(slug, 'saved', result['elapsed_seconds'], 's', flush=True)
    return result['elapsed_seconds']


def paint(only, redo, jobs, dry):
    slugs = [s for s in list(SURFACES) + list(WORLD_PAINTINGS) + list(UV_PAINTINGS) + list(DECALS) if not only or s in only]
    if dry:
        for slug in slugs:
            prompt, size, refs, _ = job(slug)
            recorded = ' (recorded)' if (PAINTED / f'{slug}.json').exists() else ''
            print(f'--- {slug} {size} {[p.name for p in refs]}{recorded}\n{prompt}\n')
        return
    if redo:
        if not only:
            raise SystemExit('--redo needs --only')
        for slug in slugs: set_aside(slug)
    todo = []
    for slug in slugs:
        if (PAINTED / f'{slug}.json').exists():
            print(slug, 'already recorded; not resubmitting', flush=True)
        else:
            todo.append(slug)
    PAINTED.mkdir(parents=True, exist_ok=True)
    for key in STYLES: style(key)           # written once, before the calls run side by side
    print('PAINT', len(todo), 'calls:', ', '.join(todo), flush=True)
    failed = []

    def run(slug):
        try:
            return paint_one(slug)
        except Exception as error:  # noqa: BLE001 - the ledger has recorded it as uncertain; never retried
            from atelier.ai.ledger import redact
            failed.append(slug); print(slug, 'FAILED (recorded as uncertain):', redact(error)[:300], flush=True)
            return 0.
    with ThreadPoolExecutor(max(1, jobs)) as pool:
        seconds = sum(pool.map(run, todo))
    record_library()
    print('PAINT COMPLETE', len(todo) - len(failed), 'painted,', len(failed), 'failed', failed, f'{seconds:.0f}s total',
          flush=True)


# ---- finish -------------------------------------------------------------------------------------------------------

def lin(a):
    import numpy as np
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)


def srgb(a):
    import numpy as np
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def seamless(a, band=.22):
    """A half-tile offset copy blended in at the borders, where it wraps without a seam; deviations are rescaled so
    the blend keeps the texture's contrast (as tools/megapark_textures.py)."""
    import numpy as np
    h, w = a.shape[:2]
    r = np.roll(a, (h // 2, w // 2), (0, 1))
    y = np.minimum(np.arange(h) + .5, h - np.arange(h) - .5) / h; x = np.minimum(np.arange(w) + .5, w - np.arange(w) - .5) / w
    s = lambda t: np.clip(t / band, 0, 1) ** 2 * (3 - 2 * np.clip(t / band, 0, 1))
    k = np.minimum(s(y)[:, None], s(x)[None, :])[..., None]
    mean = a.reshape(-1, a.shape[2]).mean(0)
    return mean + ((a - mean) * k + (r - mean) * (1 - k)) / np.sqrt(k ** 2 + (1 - k) ** 2)


def match_edges(a, axis, band=.08):
    """Even out the colour where the two ends of `axis` meet when the texture wraps, leaving the layout in place: half
    the mismatch between the last and first few lines (smoothed along the edge) is spread over a band at each end, and
    the outermost lines are cross-faded across the seam."""
    import numpy as np
    b = np.moveaxis(a, axis, 0).copy()
    n, m = b.shape[:2]
    k = max(2, n // 128)
    d = b[-k:].mean(0) - b[:k].mean(0)                       # (m, channels)
    r = max(1, m // 48)
    pad = np.concatenate([d[-r:], d, d[:r]])                 # the edge itself wraps along the other axis
    c = np.cumsum(np.concatenate([np.zeros((1,) + d.shape[1:]), pad]), 0)
    d = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
    width = max(4, int(n * band)); t = (np.arange(width) + .5) / width
    fall = (1 - t * t * (3 - 2 * t))[:, None, None]
    b[:width] += d / 2 * fall; b[-width:] -= d / 2 * fall[::-1]
    f = max(2, n // 256)                                     # detail: cross-fade the last lines across the seam
    for i in range(f):
        w = .5 * (1 - (i + .5) / f)
        top, bottom = b[i].copy(), b[n - 1 - i].copy()
        b[i] = top * (1 - w) + bottom * w; b[n - 1 - i] = bottom * (1 - w) + top * w
    return np.moveaxis(b, 0, axis)


def tile(a, axes, how):
    """a (linear RGB) made to wrap on `axes` ('x', 'y' or 'xy')."""
    if how == 'blend' and axes == 'xy':
        return seamless(a)
    for axis in (1 if c == 'x' else 0 for c in axes):
        a = match_edges(a, axis)
    return a


def to_mean(rgb, target):
    """Per-channel linear gain so the mean colour is `target` (sRGB 0-255)."""
    import numpy as np
    a = lin(rgb); want = lin(np.asarray(target, float) / 255)
    return srgb(a * want / np.maximum(a.reshape(-1, 3).mean(0), 1e-4))


def detail(rgb, target, cap=DETAIL_GAIN):
    """rgb (sRGB 0-1) brought to the palette mean `target` with its variation stretched (DETAIL). Returns (rgb, gain)."""
    import numpy as np
    a = to_mean(rgb, target)
    luma = a @ np.array([.2126, .7152, .0722])
    want = max(DETAIL_MIN / 255, DETAIL * float(luma.mean()))
    gain = float(np.clip(want / max(float(luma.std()), 1e-4), 1., cap))
    mean = a.reshape(-1, 3).mean(0)
    return to_mean(np.clip(mean + (a - mean) * gain, 0, 1), target), gain


def load(path, size):
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert('RGB')
    if im.size != size: im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, float) / 255


def finish():
    import numpy as np
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'textures': {}, 'world_aligned': {}}

    def save(name, a):
        path = OUT / f'{name}.png'
        Image.fromarray((np.clip(a, 0, 1) * 255 + .5).astype(np.uint8), 'RGB').save(path)
        return {'png': path.name, 'sha256': sha(path.read_bytes())}

    for slug, (texture, _, axes, how, _, mean) in SURFACES.items():
        painting, mean = REPAINTED.get(slug, (slug, mean))
        src = PAINTED / f'{painting}.jpg'
        if not src.exists():
            print('not painted yet:', painting); continue
        if painting != slug:
            axes, how = SURFACES[painting][2:4]
        w, h = Image.open(SOURCE / texture).size
        s = 1024 / max(w, h)
        a = srgb(tile(lin(load(src, (round(w * s), round(h * s)))), axes, how))
        note = f'painted{"" if painting == slug else " " + painting}, wraps {axes} ({how})'
        if mean:
            a, gain = detail(a, mean)
            note += f', mean {list(mean)}, detail x{gain:.2f}'
        report['textures'][texture] = {**save(slug, a), 'slug': slug, 'how': note}
    for slug, (texture, _, _, size, _) in DECALS.items():
        src = PAINTED / f'{slug}.jpg'
        if not src.exists():
            print('not painted yet:', slug); continue
        a = load(src, tuple(map(int, size.split('x'))))
        report['textures'][texture] = {**save(slug, a), 'slug': slug, 'how': 'a decal on its piece, not tiled'}
    for slug, (texture, _, how, _, mean) in UV_PAINTINGS.items():
        src = PAINTED / f'{slug}.jpg'
        if not src.exists():
            print('not painted yet:', slug); continue
        a, gain = detail(srgb(tile(lin(load(src, (1024, 1024))), 'xy', how)), mean, CALM.get(slug, DETAIL_GAIN))
        report['textures'][texture] = {**save(slug, a), 'slug': slug,
                                       'how': f'painted, wraps xy ({how}), mean {list(mean)}, detail x{gain:.2f}'}
    for material, (slug, metres, mean) in WORLD_ALIGNED.items():
        src = (MEGAPARK / 'restyle' / f'{slug.split(":")[1]}.jpg') if slug.startswith('megapark:') else PAINTED / f'{slug}.jpg'
        if not src.exists():
            print('not painted yet:', slug, 'for', material); continue
        how = WORLD_PAINTINGS[slug][1] if slug in WORLD_PAINTINGS else 'blend'
        a, gain = detail(srgb(tile(lin(load(src, (1024, 1024))), 'xy', how)), mean, CALM.get(slug, DETAIL_GAIN))
        report['world_aligned'][material] = {**save(material, a), 'slug': slug, 'metres': metres,
                                             'how': f'world-aligned {rel(src)}, wraps xy ({how}), mean {list(mean)}, '
                                                    f'detail x{gain:.2f}; Tint white'}
    (OUT / 'textures.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    print('CRATERPARK TEXTURES', len(report['textures']), 'restyled,', len(report['world_aligned']), 'world-aligned',
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('paint', 'finish'))
    parser.add_argument('--only', default='')
    parser.add_argument('--redo', action='store_true', help='set aside the done records of --only and paint them again')
    parser.add_argument('--jobs', type=int, default=1, help='calls in flight at once')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    only = {s for s in args.only.split(',') if s}
    unknown = only - set(SURFACES) - set(WORLD_PAINTINGS) - set(UV_PAINTINGS) - set(DECALS)
    if unknown:
        parser.error(f'unknown slugs {sorted(unknown)}')
    if args.command == 'paint':
        paint(only, args.redo, args.jobs, args.dry_run)
    else:
        finish()


if __name__ == '__main__':
    main()
