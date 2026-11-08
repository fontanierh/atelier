"""Where Brinecove's sources and generated files live."""
from pathlib import Path

from atelier.paths import build_root

REGION = Path(__file__).resolve().parent
GAME = REGION.parents[2]
REPO = GAME.parents[1]
ASSETS = GAME / 'assets' / 'brinecove'
MODELS = ASSETS / 'models'
TEXTURES = ASSETS / 'textures'
REFERENCES = ASSETS / 'references'
BUILD = build_root() / 'yorimichi' / 'brinecove'
REVIEW = build_root() / 'yorimichi' / 'brinecove-review'  # Eevee review renders, the three.js viewer and source-model jobs; never read by the game
