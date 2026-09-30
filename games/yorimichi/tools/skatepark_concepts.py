"""Generate pier design references with Sunburst, once per recorded prompt.

uv run python games/yorimichi/tools/skatepark_concepts.py
Full PNGs remain in build; compact references and provenance are kept with the park assets.
"""
import hashlib
import json
from pathlib import Path

from atelier.ai.ledger import run_once
from atelier.env import require
from atelier.paths import build_dir
from treehouse_art import sunburst, compact, MODEL, QUALITY

GAME = Path(__file__).resolve().parents[1]
REFERENCES = GAME / 'assets/skatepark/concepts'
OUTPUT = build_dir('yorimichi') / 'skatepark/concepts'


def main():
    require('OPENAI_API_KEY')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for item in json.loads((REFERENCES / 'prompts.json').read_text()):
        name, prompt = item['id'], item['prompt']
        provenance = REFERENCES / f'{name}.json'
        if provenance.exists():
            print(name, 'already recorded; not resubmitting', flush=True)
            continue
        def generate():
            png, usage = sunburst(prompt, '1536x1024', images=[build_dir('yorimichi') / path for path in item.get('references', [])])
            (OUTPUT / f'{name}.png').write_bytes(png)
            output = compact(png, REFERENCES / f'{name}.jpg', 'concepts')
            return {'usage': usage, 'png_sha256': hashlib.sha256(png).hexdigest(), 'output': output}
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': '1536x1024',
                             'prompt': prompt, 'references': {path: hashlib.sha256((build_dir('yorimichi') / path).read_bytes()).hexdigest() for path in item.get('references', [])}, 'purpose': 'skate pier design reference'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    main()
