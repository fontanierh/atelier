#!/usr/bin/env python3
"""Paint the Brinecove redesign references for the 2026-10-19 playtest notes with gpt-image-2.5-sunburst.

    uv run python games/yorimichi/world/regions/brinecove/references/redesign.py --notes DIR [--only a,b]
    uv run python games/yorimichi/world/regions/brinecove/references/redesign.py --finish

DIR holds the playtest notes' screenshots (note-001.png ... note-012.png). Concepts are edits grounded in the note
screenshot that shows the defect; textures are plain tileable generations. Every paid call is recorded by
atelier.ai.ledger before submission. The raw PNGs stay in build/yorimichi/brinecove-review/redesign; compact JPEG
copies, the prompts, provenance and the context frames the edits saw are committed in references/redesign.
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REFERENCES, REVIEW, TEXTURES  # noqa: E402

RAW = REVIEW / 'redesign'
OUT = REFERENCES / 'redesign'
MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'

WORLD = (
    'Brinecove is a warm hand-painted pirate port in a stylised low-poly adventure game: ochre, rust, cream, sage, '
    'weathered teal and dark timber, golden afternoon light, chunky readable shapes, clean painterly surfaces with '
    'real form shading. Keep the camera, horizon and surroundings of the attached game screenshot, and repaint only '
    'the subject as a finished game-art concept of what it should become, buildable from simple low-poly meshes '
    'with tileable textures. No text, no labels, no border, no UI. '
)
TILE = (
    'A seamless tileable material texture for the same stylised hand-painted pirate-port game, seen perfectly flat '
    'and straight-on filling the whole square edge to edge, matte, even diffuse light with no directional shadow, '
    'no vignette, no perspective, no border, no text. Soft painterly strokes, medium detail that still reads at '
    'distance, gentle value range so it never looks like a photograph. The surface: '
)

# slug: (note screenshot the edit is grounded in, or None for a tileable texture; size; prompt)
JOBS = {
    'fort': ('note-012.png', '1536x1024', (
        'The subject is the stone fort on the knoll. Redesign it as a convincing Mediterranean coastal fortress: a '
        'tall tapered keep with corbelled machicolations, arrow slits, a shallow slate-blue pyramid roof and a red '
        'banner; two round corner towers with conical terracotta roofs; a battered curtain wall with merlons and '
        'cannon embrasures that follows the slope of the knoll in steps; an arched gatehouse reached by a stone '
        'ramp; buttresses, string courses, worn honey limestone with darker coursing, ivy and small trees at its '
        'foot. Same footprint and hill position as the screenshot.')),
    'shipyard': ('note-010.png', '1536x1024', (
        'The subject is the confusing wooden pole structure on the harbour plaza. Redesign it as a clearly readable '
        'pirate shipyard slipway: a half-built ship hull on a timber cradle sloping toward the water, exposed curved '
        'ribs over a long keel, planking covering the lower third, scaffold decks with handrails and ladders along '
        'both sides, a tall timber shear-leg crane with rope and a hanging beam, stacked planks, barrels and a '
        'workbench. It must read instantly as a ship being built.')),
    'stairs': ('note-011.png', '1536x1024', (
        'The subject is the floating set of stair slabs on the wooded hillside. Redesign it as a believable '
        'switchback stone stairway climbing the slope from the lower terrace to the hamlet above: each flight sits '
        'on the ground with solid stone stringers and retaining walls, flat landings at every turn, low parapets '
        'with caps, lanterns on posts, and a clear arrival at a small stone plaza with an arch at the top. '
        'Nothing floats.')),
    'cannon': ('note-008.png', '1536x1024', (
        'The subject is the cannon on the quay. Redesign it as a handsome eighteenth-century naval cannon: a smooth '
        'dark bronze-iron barrel with reinforcing rings, a flared muzzle, trunnions and a cascabel knob; a sturdy '
        'oak sea carriage with stepped cheeks, iron straps, eye bolts with rope breeching, and four small solid '
        'wooden trucks with iron tyres. Clean continuous surfaces and subtle metal highlights, no noise.')),
    'rocks': ('note-006.png', '1536x1024', (
        'The subject is the blocky cube rocks on the grassy headland. Redesign them as convincing natural rocks: '
        'weathered limestone boulders and low outcrops with rounded eroded shoulders, fractured faces and bedding '
        'lines, half buried in the ground with soil and grass tufts around their bases, moss on the tops, varied '
        'sizes from knee-high stones to large outcrops, grouped naturally. Nothing floats or interpenetrates.')),
    'cliffs': ('note-007.png', '1536x1024', (
        'The subject is the long pale cliff band behind the town, which currently looks like one flat repeated '
        'texture. Redesign it with real depth and silhouette: projecting buttresses and recessed gullies, layered '
        'horizontal strata ledges catching the light, scree fans at the foot, varied height along its length, '
        'shrubs and trees in the ledges and dark shadowed clefts, so it reads as sculpted rock from far away.')),
    'shore': ('note-005.png', '1536x1024', (
        'The subject is the beach and the green slope above it. Replace the hard square-edged sand patches and the '
        'flat repeating green carpet with a natural shore transition: wet darker sand at the waterline, dry rippled '
        'sand with scattered pebbles and driftwood, a soft irregular edge where dune grass and sea thrift take over, '
        'then a meadow of short grass with clover, ferns and small shrubs on the slope, varied in tone, with '
        'boulders bedded into the ground.')),
    'groundcover': ('note-001.png', '1536x1024', (
        'The subject is the forest floor around the character, which is currently a flat printed picture of leaves. '
        'Redesign it as real three-dimensional undergrowth: clumps of ferns, broad-leaf ground plants and grass tufts '
        'standing up from a soil and leaf-litter ground, with gaps of bare earth, roots and small stones between '
        'them, density varying naturally, all in the game\'s chunky low-poly painted leaf style.')),
    'water': ('note-009.png', '1536x1024', (
        'The subject is the waterfall and its pool. Redesign the water as a lively stylised cascade: a translucent '
        'teal-white curtain with clear vertical streaks and darker gaps, breaking over two rock steps, a churning '
        'white plunge zone with spray and mist, and soft concentric foam rings and ripples spreading and fading '
        'across the pool, thin foam lines hugging the rocks at the shore. No hard white stripes floating on '
        'open water.')),
    # The r10 playtest notes (2026-10-19 23:26); their context frames carry an r10- prefix beside the earlier set.
    'market-stall': ('r10:note-009.png', '1536x1024', (
        'The subject is the striped market stalls on the harbour square. Redesign each stall as a detailed working '
        'pirate-port market stall: a sturdy four-post timber frame with corner braces and a ridge beam, a thick '
        'two-layer striped canvas canopy with a scalloped valance and visible timber battens underneath, a solid '
        'planked counter with front boards and a lower shelf, and tiered wares resting firmly on it: crates of '
        'oranges and limes, baskets of fish on ice, clay amphorae and jars, rolled bolts of cloth, coils of rope; '
        'dried fish, lanterns and garlic hanging from the beam on short cords; sacks and barrels on the ground. '
        'Every object sits on a surface or hangs from the frame; nothing floats.')),
    'market-stall-under': ('r10:note-010.png', '1536x1024', (
        'The subject is the market stall canopy seen from below. Redesign it as a solid striped canvas canopy whose '
        'underside is clearly visible: canvas stretched over timber rafters and a ridge beam on four braced posts, '
        'the stripes showing through in a slightly darker shade, a scalloped valance all round, lanterns and goods '
        'hanging from the rafters, the counter and wares beneath. Nothing is see-through or missing.')),
    'anchor': ('r10:note-013.png', '1536x1024', (
        'The subject is the anchor monument on the quay. Redesign it as a handsome old admiralty anchor set upright '
        'on a low dressed-stone plinth: a long dark wrought-iron shank, an oak stock bound with iron bands across '
        'the top, a heavy iron ring wrapped in thick hemp rope, two curved arms ending in broad spade flukes, a '
        'length of chain draped over the plinth, clean continuous surfaces with subtle rust and painted highlights.')),
    'waterfall': ('r10:note-005.png', '1536x1024', (
        'The subject is the waterfall falling off the sea cliff. Redesign it as a natural cascade: three to five '
        'separate tongues of white water pouring over an uneven rocky lip at different heights, split by dark wet '
        'rock ribs, each tongue narrowing and breaking into ragged streaks as it falls, a few small ledges where the '
        'water bounces, mist and foam at the bottom. No rectangular sheet, no flat top edge.')),
    'arcade': ('r10:note-011.png', '1536x1024', (
        'The subject is the long dark plank on round pillars at the edge of the market square. Redesign it as a '
        'short covered stone colonnade along the square: separate bays of sturdy stone columns with capitals '
        'carrying arched or lintelled openings, a timber pergola roof with rafters and a striped canvas shade over '
        'each bay, a clear end at each side before the terrace wall. No long floating beam.')),
    'tex_forest_floor': (None, '1024x1024', (
        'forest floor of dark loamy soil with scattered fallen leaves in ochre, rust and olive, small twigs, tiny '
        'pebbles and patches of low moss; no large leaves, no plants standing up')),
    'tex_meadow': (None, '1024x1024', (
        'short meadow grass seen from above with fine clover and tiny wildflower specks, soft sage and olive greens '
        'with warm sunlit tips and a few bare soil flecks, fine even scale, no large leaves')),
    'tex_rock': (None, '1024x1024', (
        'weathered honey-coloured limestone rock surface with fractures, shallow bedding lines, pitting and small '
        'lichen spots, pale warm cream and ochre with grey-blue shadowed cracks')),
    # The first rock tile came out as coursed masonry: boulders and cliffs read as painted walls in game.
    'tex_rock_natural': (None, '1024x1024', (
        'natural weathered coastal limestone cliff rock seen straight on: irregular fractured planes, deep dark '
        'crevices and chipped edges, no masonry, no bricks, no regular courses or rectangular blocks; warm ochre and '
        'cream lit planes with cool grey weathering, dark water streaks, small moss and lichen patches, strong value '
        'contrast between lit faces and shadowed cracks')),
    'tex_waterfall': (None, '1024x1024', (
        'falling water streaks for a waterfall: many long vertical white and pale teal streaks of varied width on a '
        'deep teal background, broken into separate ribbons with darker gaps between them, tileable top to bottom '
        'and left to right')),
    'tex_foam': (None, '1024x1024', (
        'sea foam lace on dark teal water seen from above: delicate white foam filaments, bubbles and rings forming '
        'an irregular net with plenty of open dark water between them, no solid white areas')),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paint_one(slug, notes):
    from atelier.ai import images, ledger
    context, size, subject = JOBS[slug]
    prompt = (WORLD + subject) if context else (TILE + subject + '.')
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    target = RAW / f'{slug}.png'
    record = OUT / f'{slug}.provenance.json'
    (OUT / f'{slug}.prompt.txt').write_text(prompt + '\n')
    shown = []
    if context:
        tag, _, context = context.rpartition(':')
        source = notes / context
        frame = OUT / 'context' / ((tag + '-' if tag else '') + Path(context).stem + '.jpg')
        images.compact(source, frame, 1280, 85)
        shown = [frame]
    if record.exists():
        data = json.loads(record.read_text())
        if data.get('status') == 'done' and target.exists():
            return slug, target, None
        return slug, None, 'already recorded; set the record aside to pay again'

    def call():
        blobs, body, seconds = images.sunburst(prompt, size, shown, 1, model=MODEL, quality=QUALITY)
        target.write_bytes(blobs[0])
        images.compact(blobs[0], OUT / f'{slug}.jpg', 1280 if context else 1024, 88)
        return dict(elapsed_seconds=seconds, output=target.name, output_sha256=sha(target), usage=body.get('usage'))

    prov, error = ledger.try_once(record, dict(
        stage='brinecove-redesign', slug=slug, requested_model=MODEL, quality=QUALITY, size=size,
        endpoint='/v1/images/edits' if shown else '/v1/images/generations',
        execution='games/yorimichi/world/regions/brinecove/references/redesign.py',
        context=[dict(file=f'context/{p.name}', sha256=sha(p)) for p in shown],
        prompt_file=f'{slug}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()), call)
    return slug, target if prov else None, error


def height_maps(albedo, strength):
    """Normal map (RGB, tangent space, +z out) and cavity (A) from a painted albedo's luminance, both tileable.

    The paintings carry their own soft shading, so the cavity stays shallow: the material uses it as ambient
    occlusion only, never on the base colour, and the light is not darkened twice."""
    import numpy as np
    lum = albedo[..., :3] @ np.array([.2126, .7152, .0722])

    def blur(a, sigma):
        k = np.exp(-0.5 * (np.arange(-3 * sigma, 3 * sigma + 1) / sigma) ** 2)
        k /= k.sum()
        for axis in (0, 1):
            a = sum(w * np.roll(a, int(o), axis) for o, w in zip(np.arange(-3 * sigma, 3 * sigma + 1), k))
        return a
    h = blur(lum, 1.5)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.stack([-dx, dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    cavity = np.clip(1.0 - np.maximum(blur(h, 6) - h, 0) * 3.0, 0.62, 1.0)
    return np.concatenate([n * 0.5 + 0.5, cavity[..., None]], -1)


def keyed(image, floor, ceil):
    """Colour and alpha for a lace or streak painted on dark teal: whiteness over the background becomes alpha,
    feathered between floor and ceil, so the background is fully transparent and only the strands stay."""
    import numpy as np
    rgb = image[..., :3]
    background = np.median(rgb.reshape(-1, 3), 0)
    white = np.clip((rgb.mean(-1) - background.mean()) / max(1e-3, 1.0 - background.mean()), 0, 1)
    t = np.clip((white - floor) / (ceil - floor), 0, 1)
    alpha = t * t * (3 - 2 * t)
    colour = np.clip(rgb + (1 - rgb) * 0.35 * alpha[..., None], 0, 1)
    return np.concatenate([colour, alpha[..., None]], -1)


# Committed material inputs: (source slug or existing texture, output stem, size, normal strength or key range).
FINISH = [('tex_meadow', 'terrain_meadow', 1024, 3.0), ('tex_forest_floor', 'terrain_forest', 1024, 4.0),
          ('tex_rock_natural', 'terrain_rock', 1024, 6.0), ('sand', 'terrain_sand', 1024, 2.5),
          ('tex_foam', 'foam_lace', 512, (0.28, 0.62)), ('tex_waterfall', 'waterfall_streaks', 512, (0.30, 0.70))]


# The old beach tile's dark pebble pits repeat densely across the beach and read as perforations (front-man review
# of the 2026-10-19 capture): lift dark spots most of the way to the local mean, keeping the ripples.
SOFTEN = {'terrain_sand': 0.85}


def soften_pits(a, amount, radius=32):
    import numpy as np
    from PIL import Image, ImageFilter
    blur = np.asarray(Image.fromarray((a * 255 + .5).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius)))
    blur = blur.astype(np.float32) / 255.0
    dark = np.clip(blur.mean(-1) - a.mean(-1), 0, None)[..., None]
    return np.clip(a + (blur - a) * np.clip(dark * 12.0, 0, 1) * amount, 0, 1)


def finish():
    import numpy as np
    from PIL import Image
    from textures import seamless
    records = {}
    for slug, stem, size, option in FINISH:
        source = RAW / f'{slug}.png' if slug.startswith('tex_') else TEXTURES / f'{slug}.jpg'
        image = Image.open(source).convert('RGB').resize((size, size), Image.LANCZOS)
        a = seamless(np.asarray(image).astype(np.float32) / 255.0)
        if stem in SOFTEN:
            a = soften_pits(a, SOFTEN[stem])
        if isinstance(option, tuple):
            out = keyed(a, *option)
            Image.fromarray((out * 255 + .5).astype(np.uint8), 'RGBA').save(TEXTURES / f'{stem}.png')
            records[stem] = dict(source=source.name, size=size, alpha_key=list(option))
            continue
        Image.fromarray((a * 255 + .5).astype(np.uint8)).save(TEXTURES / f'{stem}.jpg', quality=90)
        n = height_maps(a, option)
        # Relief reads at half the colour's resolution; the full size only doubled the committed bytes.
        Image.fromarray((n * 255 + .5).astype(np.uint8), 'RGBA').resize((size // 2, size // 2), Image.LANCZOS).save(
            TEXTURES / f'{stem}_n.png')
        records[stem] = dict(source=source.name, size=size, normal_strength=option)
    (OUT / 'finish.json').write_text(json.dumps(records, indent=1) + '\n')
    print(f'finished {len(records)} material inputs into {TEXTURES.name}/')


def main():
    if '--finish' in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        return finish()
    ap = argparse.ArgumentParser()
    ap.add_argument('--notes', type=Path, required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    slugs = [s for s in args.only.split(',') if s] or list(JOBS)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for slug, path, error in pool.map(lambda s: paint_one(s, args.notes), slugs):
            print(f'{slug}: {path or "not painted"}' + (f' ({error})' if error else ''), flush=True)


if __name__ == '__main__':
    main()
