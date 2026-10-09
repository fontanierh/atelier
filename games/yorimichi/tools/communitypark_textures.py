"""Community park restyle textures: warm painterly concrete, honey ramp boards, indigo coping and painted panels.

    uv run python games/yorimichi/tools/communitypark_textures.py paint [--only smooth_concrete,waves] [--dry-run]
    uv run python games/yorimichi/tools/communitypark_textures.py finish

paint: gpt-image-2.5-sunburst, quality high, once per recorded prompt (atelier.ai.ledger). Every painting is made from
text alone, in the art direction of the community park concepts (tools/communitypark_concepts.py). The compact
copy and provenance go to assets/communitypark/restyle/<slug>.jpg|json; the full PNG stays in build/yorimichi/communitypark/restyle.

finish: offline. Writes build/yorimichi/communitypark/restyle/<material>.png for each source material and
textures.json ({material: {png, sha256}}), which world/regions/communitypark/build.py uses in place of the library
maps. Surfaces are made seamless and brought to a palette colour; concrete gets its 2 m expansion joints on the tile
edge (UV1 repeats every 2 m). The wave and maple panels are made seamless; all three paint the wall murals
(world/regions/communitypark/murals.py).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from megapark_textures import load, seamless, to_mean  # noqa: E402
import yori  # noqa: E402
from treehouse_art import sha  # noqa: E402

GAME = Path(__file__).resolve().parents[1]
PAINTED = GAME / 'assets' / 'communitypark' / 'restyle'
WORK = yori.OUT / 'communitypark' / 'restyle'

SURFACE = ('A seamless tileable texture for a skate park in a stylised game set on a Japanese island in autumn: soft '
           'painterly shapes and flat matte colour, hand-painted like the background art of a Japanese animated film, '
           'soft strokes that still read as the real material, medium detail that holds up when repeated. Seen '
           'perfectly flat and straight-on, filling the square edge to edge: no perspective, no object outline, no '
           'border, no joints or lines along the edges, no shadows or lighting gradient, even brightness everywhere, '
           'no text. The surface: ')
PANEL = ('A flat, straight-on mural for the outside wall of a concrete skate park in a stylised game set on a Japanese '
         'island in autumn, painted with a roller and stencils on concrete and a little faded and scuffed by '
         'skateboards: bold flat shapes, a limited palette of faded indigo, vermilion, mustard yellow and warm cream, '
         'soft painterly edges, faint concrete texture showing through the paint. Filling the whole frame edge to '
         'edge, with no frame, no perspective, no shadows, no people, no lettering or text of any kind. The mural: ')

# slug: (source material it replaces, description, palette mean sRGB). In the island's light an albedo change shows at
# only ~0.58 of its size on screen, over a bright cool haze (game captures before and after a retone), so these are
# fitted to put the lit concrete near the concepts' warm beige rather than chosen to look right flat.
SURFACES = {
    'smooth_concrete': ('smooth-concrete', 'smooth hand-trowelled skate park concrete in warm light grey, faint '
                        'overlapping arcs of trowel marks, gentle soft mottling of slightly warmer and cooler greys, a '
                        'few tiny pores and very light wheel scuffs, clean and bright', (186, 152, 103)),
    'poured_concrete': ('poured-concrete', 'broom-finished poured concrete in mid warm grey, fine parallel brush '
                        'texture, small specks of exposed aggregate, faint darker weathering patches', (150, 121, 78)),
    'skatelite': ('skatelite', 'a smooth composite skate ramp board in warm honey brown, faint fibrous grain running '
                  'one way, soft darker wheel scuffs and small worn spots, matte', (164, 112, 62)),
    'steel': ('steel', 'painted steel pipe coping seen flat: faded deep indigo enamel paint, worn and chipped in small '
              'spots and streaks where skateboard trucks grind, showing bright bare silver steel beneath', (40, 54, 112)),
    'granite': ('granite', 'a polished granite skate ledge stone, warm grey with small speckles of charcoal, cream '
                'and rust, a few faint veins', (140, 112, 80)),
}
PANELS = {
    'waves': ('1536x1024', 'deep faded indigo ground covered edge to edge with large white overlapping seigaiha '
              'wave arcs in neat rows'),
    'sunburst': ('1536x1024', 'a vermilion ground with a large stylised rising sun in warm cream at the lower left, '
                 'its broad rays sweeping across the whole wall, a thin indigo band along the bottom'),
    'maples': ('1536x1024', 'a mustard yellow ground with large simple stencilled maple leaves in vermilion and '
               'warm cream scattered across it, a few small indigo leaves between them'),
}

REPEATING = ('waves', 'maples')   # tiled across walls; the sunburst is one composition


def job(slug):
    if slug in SURFACES: return SURFACE+SURFACES[slug][1]+'.', '1024x1024'
    size, text = PANELS[slug]; return PANEL+text+'.', size


def paint(only, dry):
    from atelier.ai.ledger import run_once
    from atelier.env import require
    from treehouse_art import MODEL, QUALITY, compact, sunburst
    if not dry: require('OPENAI_API_KEY')
    for slug in [s for s in list(SURFACES)+list(PANELS) if not only or s in only]:
        prompt, size = job(slug)
        provenance = PAINTED / f'{slug}.json'
        if dry:
            print(f'--- {slug} {size}{" (recorded)" if provenance.exists() else ""}\n{prompt}\n'); continue
        if provenance.exists():
            print(slug, 'already recorded; not resubmitting', flush=True); continue

        def generate(prompt=prompt, size=size, slug=slug):
            png, usage = sunburst(prompt, size)
            WORK.mkdir(parents=True, exist_ok=True); (WORK / f'{slug}.png').write_bytes(png)
            return {'usage': usage, 'png_sha256': sha(png), 'output': compact(png, PAINTED / f'{slug}.jpg', 'textures')}
        PAINTED.mkdir(parents=True, exist_ok=True)
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': size, 'prompt': prompt, 'references': {},
                              'purpose': 'Community park restyle texture'}, generate)
        print(slug, 'saved', flush=True)


def joints(a, width=3, depth=.72):
    """Darken the tile border: a 2 m grid of saw-cut joints once UV1 repeats the tile."""
    import numpy as np
    h, w = a.shape[:2]; k = np.ones((h, w))
    for i in range(width):
        f = depth+(1-depth)*i/width
        k[i, :] = k[-1-i, :] = np.minimum(k[i, :], f); k[:, i] = k[:, -1-i] = np.minimum(k[:, i], f)
    return a*k[..., None]


def finish():
    import numpy as np
    from PIL import Image
    WORK.mkdir(parents=True, exist_ok=True); record = {}
    for slug, (material, unused, mean) in SURFACES.items():
        a = load(PAINTED / f'{slug}.jpg', (1024, 1024))[..., :3]
        a = np.clip(to_mean(seamless(a), mean), 0, 1)
        if 'concrete' in slug: a = joints(a)
        path = WORK / f'{material}.png'; Image.fromarray((a*255+.5).astype(np.uint8)).save(path)
        record[material] = {'png': path.name, 'sha256': sha(path.read_bytes()), 'painting': f'{slug}.jpg'}
    for slug in PANELS:
        a = load(PAINTED / f'{slug}.jpg')[..., :3]
        if slug in REPEATING: a = np.clip(seamless(a, band=.12), 0, 1)
        path = WORK / f'panel-{slug}.png'; Image.fromarray((a*255+.5).astype(np.uint8)).save(path)
        record[f'panel-{slug}'] = {'png': path.name, 'sha256': sha(path.read_bytes()), 'painting': f'{slug}.jpg'}
    (WORK / 'textures.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=('paint', 'finish'))
    parser.add_argument('--only', default=''); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.step == 'paint': paint(set(filter(None, args.only.split(','))), args.dry_run)
    else: finish()


if __name__ == '__main__':
    main()
