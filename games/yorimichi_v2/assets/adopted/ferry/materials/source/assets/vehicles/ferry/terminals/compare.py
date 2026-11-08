"""Put the terminal review renders beside the v2 concepts (concept left, render right).

uv run python games/yorimichi/assets/vehicles/ferry/terminals/compare.py [CONCEPT_DIR]
Reads build/yorimichi/ferry/terminals/review/*.png and writes compare_*.png beside them.
"""
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from compare import flatten, pair  # noqa: E402

REVIEW = HERE.parents[5] / 'build' / 'yorimichi' / 'ferry' / 'terminals' / 'review'
CONCEPTS = {'hidamari': 'hidamari_port_terminal_v2.jpg', 'brinecove': 'brinecove_ferry_terminal_v2.jpg'}


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / '.cache/atelier/handoff/jim5/transport-concepts'
    for town, concept in CONCEPTS.items():
        art = Image.open(root / concept).convert('RGB')
        for shot in sorted(REVIEW.glob(f'{town}_*.png')):
            pair(art, flatten(shot), f'concept v2 ({town})', f'Blender kit: {shot.stem}').save(REVIEW / f'compare_{shot.stem}.png')
    print('wrote', *sorted(p.name for p in REVIEW.glob('compare_*.png')))


if __name__ == '__main__':
    main()
