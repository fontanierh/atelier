"""Paint community park improvement concepts with Sunburst, once per recorded prompt.

uv run python games/yorimichi/tools/communitypark_concepts.py [--only ID,ID]
References are game-review captures cropped to 3:2 under build/yorimichi/communitypark/concepts, plus the Mega Park
restyle concept as the shared art direction. The full paintings and provenance stay in the ignored build folder;
only the prompts are tracked.
"""
import argparse
import json
from pathlib import Path

from atelier.ai.ledger import run_once
from atelier.env import require
from atelier.paths import build_dir
from treehouse_art import sunburst, sha, MODEL, QUALITY

GAME = Path(__file__).resolve().parents[1]
PROMPTS = GAME / 'assets/communitypark/concepts/prompts.json'
OUT = build_dir('yorimichi') / 'communitypark'
CONCEPTS = OUT / 'concepts/sunburst'


def references():
    """Crop the review captures to 3:2 and copy the art-direction reference beside them."""
    from PIL import Image
    folder = OUT / 'concepts'; folder.mkdir(parents=True, exist_ok=True)
    for name in ('entrance', 'bowls', 'overview'):
        target = folder / f'before-{name}.png'
        if target.exists(): continue
        im = Image.open(OUT / 'game-review' / f'{name}.png').convert('RGB')
        width = min(im.width, round(im.height*1.5)); height = round(width/1.5); left = (im.width-width)//2; top = (im.height-height)//2
        im.crop((left, top, left+width, top+height)).save(target)
    style = folder / 'style-megapark.png'
    if not style.exists():
        Image.open(GAME / 'assets/megapark/concepts/restyle-inside.jpg').convert('RGB').save(style)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--only', default='')
    only = set(filter(None, parser.parse_args().only.split(',')))
    require('OPENAI_API_KEY')
    references(); CONCEPTS.mkdir(parents=True, exist_ok=True)
    for item in json.loads(PROMPTS.read_text()):
        name, prompt, refs = item['id'], item['prompt'], item.get('references', [])
        if only and name not in only: continue
        provenance = CONCEPTS / f'{name}.json'
        if provenance.exists():
            print(name, 'already recorded; not resubmitting', flush=True)
            continue
        paths = [build_dir('yorimichi') / ref for ref in refs]
        def generate():
            png, usage = sunburst(prompt, '1536x1024', images=paths)
            (CONCEPTS / f'{name}.png').write_bytes(png)
            return {'usage': usage, 'png_sha256': sha(png), 'output': {'file': f'{name}.png'}}
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': '1536x1024', 'prompt': prompt,
                              'references': {ref: sha(path.read_bytes()) for ref, path in zip(refs, paths)},
                              'purpose': 'Community park improvement concept'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    main()
