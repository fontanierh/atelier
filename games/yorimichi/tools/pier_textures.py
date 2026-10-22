"""Author Sunset Pier's Sunburst surfaces, then finish repeatable game texture maps.

    uv run python games/yorimichi/tools/pier_textures.py paint
    uv run python games/yorimichi/tools/pier_textures.py finish

Paid images are recorded by atelier.ai.ledger and never resubmitted. Chosen compact
sources and provenance live in assets/skatepark/textures; full PNGs and finished
albedo, roughness and normal maps live in build/yorimichi/skatepark/textures.
"""
import argparse
import hashlib
import json
from pathlib import Path

from pier_texture_finish import SURFACES, finish

from treehouse_art import MODEL, QUALITY, compact, sunburst
from atelier.ai.ledger import run_once
from atelier.paths import build_dir

GAME = Path(__file__).resolve().parents[1]
ART = GAME / 'assets/skatepark/textures'
OUT = build_dir('yorimichi') / 'skatepark/textures'
PROMPTS = {'concrete': 'warm pale grey skate plaza concrete, finely burnished with tiny exposed aggregate, '
             'subtle trowel arcs and understated scuffs from skateboard wheels, excellent nuanced '
             'material detail without large cracks or dirt blotches',
 'ceramic': 'small glazed Japanese ceramic mosaic tiles in muted sea-glass sage and pale jade, '
            'regular square grid with narrow cream grout, each tile subtly varied and hand glazed, '
            'restrained crazing and gentle salt weathering, no broken tiles',
 'steel': 'polished stainless steel worn by skateboard trucks, fine lengthwise brushing and '
          'scratches, very subtle warm patina at the edges, clean silver steel without rust holes',
 'wood': 'beautiful weathered Japanese cedar timber, long straight grain, fine pores and small '
         'knots, warm honey brown with softly bleached salt-air fibres, grain runs vertically'}
BASE = ('A production-quality seamless tileable game material albedo texture, completely flat orthographic '
        'view of the surface, edge to edge with identical scale everywhere. Painterly realism for a beautiful '
        'stylised Japanese coastal adventure game: tactile, finely observed materials with soft hand-painted '
        'microdetail. Uniform diffuse lighting, no cast shadows, no specular highlights, no perspective, no '
        'objects, no text, no border. Seamless in both directions. The surface is ')
MURAL = ('Paint a spectacular panoramic skateboard plaza mural: a curling Japanese indigo ocean wave with '
         'a vermilion koi jumping through it, a golden setting sun and windblown maple leaves. Original '
         'woodblock-inspired contemporary skate art, powerful sweeping composition, bone cream, indigo, '
         'vermilion and ochre, intricate ink strokes and subtly distressed silkscreen texture. Flat artwork '
         'edge to edge, no frame, no perspective, no lighting, no lettering, no logos. This will be printed '
         'on the wall behind a street skating line in a warm Japanese seaside game.')


def paint():
    ART.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    for name in (*SURFACES, 'mural'):
        ledger = ART / f'{name}.json'
        if ledger.exists():
            print(name, 'record exists; not resubmitting', flush=True); continue
        prompt = MURAL if name == 'mural' else BASE + PROMPTS[name]
        size = '1536x1024' if name == 'mural' else '1024x1024'
        def generate():
            png, usage = sunburst(prompt, size)
            (OUT / f'{name}-original.png').write_bytes(png)
            record = compact(png, ART / f'{name}.jpg', 'textures' if name != 'mural' else 'concepts')
            return {'usage': usage, 'png_sha256': hashlib.sha256(png).hexdigest(), 'output': record}
        run_once(ledger, {'model': MODEL, 'quality': QUALITY, 'size': size, 'prompt': prompt,
                         'purpose': 'Sunset Pier material' if name != 'mural' else 'Sunset Pier wave wall'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=('paint', 'finish'))
    args = parser.parse_args(); paint() if args.mode == 'paint' else finish()
