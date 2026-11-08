#!/usr/bin/env python3
"""Paint the Brinecove reference set with gpt-image-2.5-sunburst, quality high.

Every call is recorded before submission by atelier.ai.ledger. The existing Yorimichi world-map painting is the
style reference: warm watercolour palette, low-poly-readable masses, no outlines and no photoreal texture.

    uv run python games/yorimichi/world/regions/brinecove/references/generate.py [--only slug,slug] [--n 1]
"""
import argparse
import hashlib
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REPO, REVIEW  # noqa: E402

from atelier.ai import images, ledger  # noqa: E402

MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'
SIZE = '1536x1024'
OUT = REVIEW / 'references'
STYLE_REF = REPO / 'games/yorimichi/world/map/painted/world_map.png'

STYLE = (
    "The attached painting is the world map of our game Yorimichi. Match its painting language: a warm, hand-painted "
    "storybook palette of ochre, rust, cream, sage, pine green and blue-green sea; broad readable masses; soft "
    "watercolour edges; simple faceted forms that could be built from low-poly primitives; no outlines; no photoreal "
    "texture; no text or labels. The subject is Brinecove, a neutral pirate port on the same island: weathered but "
    "prosperous, lived in, never grim. Everything must share the same geography and architecture across the set. "
)

GEO = (
    "GEOGRAPHY: a deep horseshoe cove opening south. A long stone quay runs across the north shore with three dark "
    "timber piers reaching into turquoise water. Behind the quay is a cobbled market square, then a street of tall "
    "cream, ochre and faded-coral taverns with timber galleries, shutters, canvas awnings and terracotta or oxidized "
    "teal roofs. Narrow stairs climb to a second terrace of houses. A square stone watchtower with a cannon platform "
    "stands on the crest above the roofs. The west arm of the cove is a windy headland with a banded lighthouse; the "
    "east arm is a wet jungle cliff with a tall waterfall and a rope bridge. Two three-masted pirate galleons are "
    "moored at the central pier, a half-built hull sits on the east slipway, and a wreck lies on the western rocks. "
    "A weathered stone statue of a pirate queen on a rock islet marks the harbor mouth. Dense jungle palms and "
    "broadleaf trees crown the cliffs. Late afternoon, high warm sun, pale blue sky, soft haze on the far headlands. "
)

CONCEPTS = {
    '01-aerial-hero': (
        "Wide aerial three-quarter view from the south-east, 250 m above the water, looking into the cove. The whole "
        "town, all three piers, both headlands, the watchtower and the waterfall are visible at once. This is the "
        "defining layout image. Emphasise the horseshoe bay, the layered roofscape, the two galleons and the contrast "
        "between the busy quay and the wild headlands."
    ),
    '02-harbor-approach': (
        "Eye-level view from a small boat just inside the harbor mouth, looking north at the quay. The pirate-queen "
        "statue is a strong silhouette on the left, the central pier and the masts of two galleons fill the middle, "
        "the watchtower rises above the roofs, and the waterfall and shipyard close the right side. Strong horizontal "
        "quay wall, layered balconies and awnings behind it."
    ),
    '03-market-square': (
        "Street-level view in the cobbled market square. Canvas stalls with fish, fruit, rope and pottery; a raised "
        "auction block; a tall signal mast with banners and rigging; taverns leaning in on three sides. In the "
        "background the grand stair climbs between retaining walls to the upper terrace and the watchtower. Bustling "
        "but readable, strong colour accents, warm shade."
    ),
    '04-upper-terrace': (
        "View from the upper terrace looking down over the roofs to the bay. Narrow lane, potted palms, laundry "
        "lines, a stone cistern, houses stepping down the slope, the grand stair cutting a diagonal, the three piers "
        "and galleons below. The watchtower is just behind the viewer, casting a long shadow into the frame."
    ),
    '05-lighthouse-headland': (
        "View along the western headland toward the banded lighthouse and keeper's cottage, with the town across "
        "the water behind. Wind-bent grass, dark rock shelves, a ruined signal wall, seabirds, the wreck on the rocks "
        "below. The lighthouse is white with two broad rust-red bands and a dark lantern room."
    ),
    '06-shipyard': (
        "View of the east shore shipyard: a half-built galleon hull on a timber slipway, stacked planks, a wooden "
        "crane, rope coils, shipwrights' sheds, and the waterfall dropping into a rock pool behind. The east pier and "
        "a small sloop are in the foreground, town roofs beyond."
    ),
    '07-waterfall-bridge': (
        "View up the east ravine: a tall waterfall dropping over dark wet rock into a turquoise pool, a rope bridge "
        "crossing the ravine between two jungle ledges, ferns and palms, a small cliffside shrine with lanterns. The "
        "harbor and shipyard are glimpsed below through the foliage."
    ),
    '08-night-harbor': (
        "The same harbor at blue hour. Lantern strings along the quay and between the taverns, warm windows, "
        "lanterns on the piers and ships, the lighthouse beam sweeping the water, a faint glow behind the waterfall, "
        "deep teal water with warm reflections. The statue and watchtower remain legible as dark silhouettes."
    ),
    '09-rum-row': (
        "Close street-level view of Rum Row, the waterfront tavern street. Three-storey timber-framed buildings with "
        "galleries, hanging signs, barrels, crates, a fishmonger's table, an awning, a steep outside stair and a "
        "narrow gap framing the masts and water beyond. Rich material variety in cream plaster, dark timber, faded "
        "coral and teal paint."
    ),
    '10-cliff-shacks': (
        "A cluster of precarious cliffside shacks on the west slope, built on stilts and stone ledges, connected by "
        "ladders, planks and a rope bridge. Laundry, potted plants, a tiny terrace, a lantern, and a steep drop to "
        "the water. The main town and pier are visible across the cove."
    ),
    '11-building-kit': (
        "A clean architectural concept sheet on a warm cream background: eight modular pirate-port building pieces "
        "in three-quarter view, arranged in two rows. Long warehouse, three-storey tavern with gallery, narrow "
        "gabled townhouse, corner shop with awning, stone watchtower, lighthouse, timber crane and market stall. "
        "Same construction language, readable silhouettes, no labels or dimensions."
    ),
    '12-prop-kit': (
        "A clean prop concept sheet on a warm cream background: barrels, rope coils, crates, anchors, cannon, "
        "lanterns, buoys, fish baskets, a hanging tavern sign, a capstan, palm pots and a ship's wheel. Arranged in "
        "a loose grid, three-quarter views, consistent scale and palette, no labels."
    ),
    '13-map': (
        "A painted top-down map of the whole Brinecove basin on parchment, in the same watercolour style as the "
        "attached Yorimichi map. Show the horseshoe bay, three piers, market square, lower town, upper terrace, "
        "grand stair, watchtower, lighthouse headland, waterfall, shipyard, wreck and jungle slopes. No labels, no "
        "compass rose, no border text; keep the geography clear and readable."
    ),
}


def key():
    from atelier.env import load
    load()
    import os
    value = os.environ.get('OPENAI_API_KEY')
    if not value:
        raise SystemExit('OPENAI_API_KEY is not set')
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paint_one(slug, n):
    prompt = STYLE + GEO + 'VIEW: ' + CONCEPTS[slug]
    target = OUT / f'{slug}.png'
    record = OUT / f'{slug}.provenance.json'
    prompt_file = OUT / f'{slug}.prompt.txt'
    prompt_file.write_text(prompt + '\n')
    if record.exists():
        data = json.loads(record.read_text())
        if data.get('status') == 'done' and target.exists():
            return slug, str(target), None
        return slug, None, 'already recorded; set the record aside to pay again'

    def call():
        blobs, body, seconds = images.sunburst(prompt, SIZE, [STYLE_REF], n, model=MODEL,
                                               quality=QUALITY, key=key())
        paths = []
        for i, blob in enumerate(blobs):
            path = target if n == 1 else OUT / f'{slug}-{i + 1}.png'
            path.write_bytes(blob)
            paths.append(path)
        return dict(elapsed_seconds=seconds, outputs={p.name: sha(p) for p in paths}, usage=body.get('usage'))

    prov, error = ledger.try_once(record, dict(
        stage='brinecove-concept', concept=slug, requested_model=MODEL, quality=QUALITY, size=SIZE, n=n,
        endpoint='/v1/images/edits', execution='games/yorimichi/world/regions/brinecove/references/generate.py',
        prompt_file=prompt_file.name, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        reference_files={str(STYLE_REF.relative_to(REPO)): sha(STYLE_REF)}), call)
    return slug, str(target) if prov else None, error


def contact_sheet():
    from PIL import Image, ImageDraw
    files = sorted(OUT.glob('*.png'))
    if not files:
        return
    cols, thumb_w = 3, 640
    thumbs = []
    for path in files:
        im = Image.open(path).convert('RGB')
        im = im.resize((thumb_w, round(im.height * thumb_w / im.width)), Image.LANCZOS)
        thumbs.append((path, im))
    pad = 16
    rows = math.ceil(len(thumbs) / cols)
    cell_h = max(im.height for _, im in thumbs) + 42
    canvas = Image.new('RGB', (cols * thumb_w + (cols + 1) * pad, rows * cell_h + (rows + 1) * pad), (235, 227, 208))
    draw = ImageDraw.Draw(canvas)
    for i, (path, im) in enumerate(thumbs):
        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * cell_h
        canvas.paste(im, (x, y + 26))
        draw.text((x, y + 4), path.stem, fill=(63, 49, 40))
    canvas.save(OUT / 'contact-sheet.jpg', quality=90)
    (OUT / 'contact-sheet.json').write_text(json.dumps([p.name for p, _ in thumbs], indent=2) + '\n')
    print('contact sheet:', OUT / 'contact-sheet.jpg')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--jobs', type=int, default=3)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    key()
    slugs = [s for s in args.only.split(',') if s] or list(CONCEPTS)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for slug, path, error in pool.map(lambda s: paint_one(s, args.n), slugs):
            print(f'{slug}: {path or "not painted"}{(" (" + error + ")") if error else ""}', flush=True)
    contact_sheet()


if __name__ == '__main__':
    main()
