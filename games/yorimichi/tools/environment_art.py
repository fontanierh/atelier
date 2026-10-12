"""Sunburst concepts and textures for the refined island and Tuscan north.

Each paid image has an immutable ledger record before submission. Full PNGs
and native reference captures stay under build; selected compact source art
and public provenance live in the game's environment library.
"""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time

from atelier.ai import images

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]
WORK = ROOT / 'build/yorimichi/environment-art'
LIBRARY = GAME / 'assets/environment'
STYLE = '''Production concept for Yorimichi, a beautiful stylized exploration game.
Use rich painterly materials, organic modeled forms, convincing soft afternoon
lighting and full detailed foliage. This is an achievable polished real-time 3D
scene. Preserve the geography and architecture in the layout references, while
replacing coarse terrain and crude trees. No faceted toy mountain, polygon cone
trees, balloon crowns, bare saplings, confetti canopy or flat forest photograph.
Trees have trunks and branches, overlapping textured leaf masses, depth and
natural varied silhouettes. No HUD, text, labels, border or watermark.'''
CONCEPTS = {
    'transition': '''The first image is the rejected in-game crossing, viewed from
above the north side of the volcano toward Belmonte. Keep this camera, the
mountain position, the valley footprint and the distant Tuscan buildings/courses.
Replace the visible three straight bands with one continuous, naturally shaped
landscape. Detailed weathered volcanic rock and snow remnants lead into wooded
foothills with full interlocking Japanese autumn canopies. Those woods gradually
become green Mediterranean oak and olive groves, cypress avenues, meadow, shrubs
and cultivated Tuscan fields. Use organic clusters, glades, contour-following
paths and rock outcrops. The ground material, relief and planting blend together;
no rectangular edge, blank strip, abrupt species wall or repeated flat texture.
Show both existing Yorimichi and Tuscan Belmonte as geographic context.''',
    'volcano-far': '''Use the first image as the exact existing Hidamari-to-volcano
layout: retain the harbour, streets, buildings and mountain location/scale.
Upgrade the distant volcanic mountain into a memorable organically modeled
snow-capped summit with eroded radial ridges, gullies, cliffs, rock strata and
large readable snow channels. It must read beautifully at one kilometre and
remain plausible up close. Preserve broad landmark silhouette but remove visible
grid triangles and the smooth toy-cone look. Rich dark rock, weathered grey scree,
off-white snow and mossy lower shelves. The forest climbs naturally in mixed full
canopies toward the treeline. No uniform speckle carpet or artificial straight
forest boundary. Keep Japanese autumn colour near Hidamari; the far northern
valley belongs to Tuscan Belmonte, with evergreen olive/oak/cypress character.''',
    'volcano-near': '''A close ground-level reference on the same snow-capped
volcanic mountain. Human-scale rock detail: layered fractured basalt, rounded
weathering, scree, cracks, moss in sheltered seams, small alpine plants and
patches of dirty compacted snow. The summit's eroded ridges are visible behind
the foreground surface. Show a coherent natural transition from solid cliff
faces to gravel and vegetation, with readable macro and micro texture. Refined
painterly realism appropriate to Yorimichi; organically smooth terrain geometry,
not a photoreal photograph and not visible triangulated planes. No architecture,
characters or new landmarks.''',
    'tuscan-foliage': '''A production reference sheet of four beautiful Tuscan
tree forms for adapting Yorimichi's detailed leaf-card trees: Italian cypress,
gnarled olive, Mediterranean holm oak and umbrella stone pine. Show each whole
tree and one close crown/leaf detail, naturally arranged on a pale neutral
ground. Cypress has narrow dark green irregular columnar foliage; olive has a
twisted branching trunk and airy but full silver-green small-leaf clusters;
holm oak has broad dense evergreen crowns; pine has an organic umbrella canopy.
Ground companions are rosemary, lavender, low meadow grasses and small shrubs.
The leaf structures must be modeled and textured with real depth and overlapping
foliage, with beautiful visible branch structure. No orange Japanese autumn
palette in these Tuscan variants, no crude conical or blob geometry, no text.''',
}
TEXTURES = {
    'leaf-olive': '''Game foliage atlas, exactly four distinct olive twig clusters in
four equal square cells (2 by 2). Each cluster has many small narrow silver-green
olive leaves, irregular overlapping leaves and visible fine branching. Isolated
on pure black, black gaps between leaves, generous black cell-edge margins.
Flat orthographic, neutral diffuse colour, no shadow, no text, no trunk or ground.''',
    'leaf-cypress': '''Game foliage atlas, four distinct Italian cypress foliage
sprays in four equal square cells (2 by 2). Dense dark evergreen fine scale-like
sprays with irregular feathery edges and believable branching. Isolated on pure
black with black gaps and generous cell margins. Flat orthographic, neutral
diffuse colour, no shadow, text, trunk or ground.''',
    'leaf-oak': '''Game foliage atlas, four distinct Mediterranean holm oak leafy
twigs in four equal square cells (2 by 2). Dense overlapping small leathery
oval leaves in deep muted green with lighter undersides, irregular cluster
edges and fine branching. Isolated on pure black with black gaps and generous
cell margins. Flat neutral diffuse colour, no shadow, text, trunk or ground.''',
    'leaf-pine': '''Game foliage atlas, four distinct stone pine needle sprays
in four equal square cells (2 by 2). Full feathery muted green needle bundles,
fine branching, natural irregular edges and depth within each spray. Isolated
on pure black with black gaps and generous cell margins. Flat orthographic,
neutral diffuse colour, no shadow, text, trunk or ground.''',
    'volcanic-rock': '''Seamless tileable volcanic rock base-colour texture for a
stylized painterly 3D mountain. Weathered charcoal and warm grey basalt, broken
layering, fissures, subtle mineral variation and fine stone grain. Orthographic
flat material scan, neutral diffuse lighting, no cast shadows or perspective,
no snow, no large objects, no text. Detail at several scales; edge-to-edge tile.''',
    'scree-moss': '''Seamless tileable painterly mountain-ground base-colour
texture: grey volcanic scree and gravel, muted brown soil, sparse olive moss and
small irregular mineral chips. Natural material variation, not noisy confetti.
Orthographic flat scan, neutral diffuse lighting, no baked highlights, no cast
shadows, no perspective, no large objects or text. Seamless on every edge.''',
    'tuscan-ground': '''Seamless tileable refined painterly Tuscan meadow/soil
base-colour texture. Warm earth under muted olive-green meadow grass, small dry
straw strands, occasional pale stones, subtle natural patches. Keep restrained
Mediterranean colours and fine ground detail, not an orange autumn forest.
Orthographic flat scan in neutral diffuse light; no perspective, cast shadows,
large recognizable objects or text. Seamless on all edges.''',
}


def generate(kind, name, revision, refs):
    prompt = (STYLE + '\n\n' + CONCEPTS[name]) if kind == 'concepts' else TEXTURES[name]
    folder = WORK / revision / kind
    target = folder / (name + '.png')
    record = folder / (name + '.ledger.json')
    metadata = {'revision': revision, 'use': kind, 'name': name,
                'inputs': [{'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in refs]}
    stop = threading.Event()
    started = time.monotonic()
    def progress():
        while not stop.wait(25):
            print(f'SUNBURST waiting: {name}, {time.monotonic()-started:.0f}s since single submission', flush=True)
    threading.Thread(target=progress, daemon=True).start()
    try:
        result = images.paint(target, prompt, '1536x1024' if kind == 'concepts' else '1024x1024',
                              refs, record=record, metadata=metadata, model=images.MODEL, quality='high')
    finally:
        stop.set()
    source = LIBRARY / kind / (name + '.jpg')
    compact = images.compact(target, source, 1600 if kind == 'concepts' else 1024, 94, '4:4:4')
    public = {**result, 'prompt': prompt, 'source': compact,
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    source.with_suffix('.provenance.json').write_text(json.dumps(public, indent=2) + '\n')
    print('SUNBURST COMPLETE', name, source.relative_to(ROOT), result['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('concepts', 'textures'))
    parser.add_argument('name')
    parser.add_argument('--revision', default='r01')
    parser.add_argument('--reference', action='append', type=Path, default=[])
    args = parser.parse_args()
    choices = CONCEPTS if args.kind == 'concepts' else TEXTURES
    if args.name not in choices:
        parser.error('unknown art recipe')
    generate(args.kind, args.name, args.revision, args.reference)
