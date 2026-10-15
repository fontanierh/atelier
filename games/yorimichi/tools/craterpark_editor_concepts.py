"""Paint the editor Crater Park's art-direction concepts with Sunburst, once per recorded prompt.

uv run python games/yorimichi/tools/craterpark_editor_concepts.py [NAME ...]
The references are packaged-game stills under build/yorimichi/craterpark/shots/<shot>/view.png (benchmark custom
cameras) and the park's restyle paintover in assets/craterpark/concepts. Full PNGs stay in build; compact copies and
provenance are kept in assets/craterpark/concepts/editor.
"""
import hashlib
import json
import sys
from pathlib import Path

from atelier.ai.ledger import run_once
from atelier.env import require
from atelier.paths import build_dir
from treehouse_art import sunburst, compact, MODEL, QUALITY

GAME = Path(__file__).resolve().parents[1]
CONCEPTS = GAME / 'assets/craterpark/concepts/editor'
OUTPUT = build_dir('yorimichi') / 'craterpark/concepts/editor'


def reference(path):
    """A reference image: build/yorimichi/... for captures, or a path inside the game folder."""
    return build_dir('yorimichi') / path[len('build/yorimichi/'):] if path.startswith('build/yorimichi/') else GAME / path


def main(names):
    require('OPENAI_API_KEY')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for item in json.loads((CONCEPTS / 'prompts.json').read_text()):
        name, prompt, references = item['id'], item['prompt'], item.get('references', [])
        if names and name not in names:
            continue
        provenance = CONCEPTS / f'{name}.json'
        if provenance.exists():
            print(name, 'already recorded; not resubmitting', flush=True)
            continue
        def generate():
            png, usage = sunburst(prompt, '1536x1024', images=[reference(path) for path in references])
            (OUTPUT / f'{name}.png').write_bytes(png)
            output = compact(png, CONCEPTS / f'{name}.jpg', 'concepts')
            return {'usage': usage, 'png_sha256': hashlib.sha256(png).hexdigest(), 'output': output}
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': '1536x1024', 'prompt': prompt,
                              'references': {path: hashlib.sha256(reference(path).read_bytes()).hexdigest()
                                             for path in references},
                              'purpose': 'Crater Park editor park art direction'}, generate)
        print(name, 'saved', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
