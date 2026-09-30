"""Paint the Mega Park restyle references with Sunburst, once per recorded prompt.

uv run python games/yorimichi/tools/megapark_concepts.py
The references are in-game captures under build/yorimichi (tools/review_megapark.py --island, cropped to 3:2).
Full PNGs remain in build; compact copies and provenance are kept in assets/megapark/concepts.
"""
import hashlib
import json
from pathlib import Path

from atelier.ai.ledger import run_once
from atelier.env import require
from atelier.paths import build_dir
from treehouse_art import sunburst, compact, MODEL, QUALITY

GAME = Path(__file__).resolve().parents[1]
REFERENCES = GAME / 'assets/megapark/concepts'
OUTPUT = build_dir('yorimichi') / 'megapark/concepts'


def main():
    require('OPENAI_API_KEY')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for item in json.loads((REFERENCES / 'prompts.json').read_text()):
        name, prompt, references = item['id'], item['prompt'], item.get('references', [])
        provenance = REFERENCES / f'{name}.json'
        if provenance.exists():
            print(name, 'already recorded; not resubmitting', flush=True)
            continue
        def generate():
            png, usage = sunburst(prompt, '1536x1024', images=[build_dir('yorimichi') / path for path in references])
            (OUTPUT / f'{name}.png').write_bytes(png)
            output = compact(png, REFERENCES / f'{name}.jpg', 'concepts')
            return {'usage': usage, 'png_sha256': hashlib.sha256(png).hexdigest(), 'output': output}
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': '1536x1024', 'prompt': prompt,
                              'references': {path: hashlib.sha256((build_dir('yorimichi') / path).read_bytes()).hexdigest()
                                             for path in references},
                              'purpose': 'Mega Park restyle reference'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    main()
