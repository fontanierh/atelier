"""Paint the bike concepts with Sunburst, once per recorded prompt.

uv run python games/yorimichi/tools/bike_concepts.py [--only ID,ID]
References live under build/yorimichi/bike/concepts: a game-review capture of Cairo, the community park restyle
concept as the shared art direction, and Blender stills of Cairo (`cairo_*.png`). The capture shows recovered park
surfaces, so the paintings, their full PNGs and provenance stay in the ignored build folder; only the prompts are
tracked.
"""
import argparse
import json
from pathlib import Path

from atelier.ai.ledger import run_once
from atelier.env import require
from atelier.paths import build_dir
from treehouse_art import sunburst, sha, MODEL, QUALITY

GAME = Path(__file__).resolve().parents[1]
PROMPTS = GAME / 'assets/vehicles/bike/concepts/prompts.json'
OUT = build_dir('yorimichi') / 'bike' / 'concepts'
CONCEPTS = OUT / 'sunburst'


def references():
    """Crop the riding capture to 3:2 and copy the art-direction concept beside it."""
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    capture, style = OUT / 'game-cairo.png', OUT / 'style-communitypark.png'
    if not capture.exists():
        im = Image.open(build_dir('yorimichi') / 'communitypark/game-review/ride_deck.png').convert('RGB')
        width = min(im.width, round(im.height*1.5)); height = round(width/1.5); left = (im.width-width)//2; top = (im.height-height)//2
        im.crop((left, top, left+width, top+height)).save(capture)
    if not style.exists():
        Image.open(build_dir('yorimichi') / 'communitypark/concepts/sunburst/surfaces.png').convert('RGB').save(style)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--only', default='')
    only = set(filter(None, parser.parse_args().only.split(',')))
    require('OPENAI_API_KEY')
    references(); CONCEPTS.mkdir(parents=True, exist_ok=True)
    for item in json.loads(PROMPTS.read_text()):
        name, prompt, refs, size = item['id'], item['prompt'], item.get('references', []), item.get('size', '1536x1024')
        if only and name not in only: continue
        provenance = CONCEPTS / f'{name}.json'
        if provenance.exists():
            print(name, 'already recorded; not resubmitting', flush=True)
            continue
        paths = [build_dir('yorimichi') / ref for ref in refs]
        def generate():
            png, usage = sunburst(prompt, size, images=paths)
            (CONCEPTS / f'{name}.png').write_bytes(png)
            return {'usage': usage, 'png_sha256': sha(png), 'output': {'file': f'{name}.png'}}
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': size, 'prompt': prompt,
                              'references': {ref: sha(path.read_bytes()) for ref, path in zip(refs, paths)},
                              'purpose': 'Bike concept'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    main()
