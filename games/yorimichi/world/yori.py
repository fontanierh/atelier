"""Paths for Yorimichi's world scripts. Import it before anything else.

It puts the Atelier studio package, the regions folder and this folder on sys.path, so `import village.layout` and
`from atelier import paths` work from plain Python and from Blender (which does not add a script's folder to the
path). Everything a build generates goes to OUT (build/yorimichi, or $ATELIER_BUILD_ROOT/yorimichi); the prototype
wrote the same files to japan/out.
"""
import sys
from pathlib import Path

WORLD = Path(__file__).resolve().parent
REGIONS = WORLD / 'regions'
GAME = WORLD.parent
REPO = GAME.parents[1]
for _path in (REPO / 'platform' / 'studio', REGIONS, WORLD):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atelier.paths import build_dir  # noqa: E402

OUT = build_dir('yorimichi')
TEXTURES = OUT / 'textures'        # gen_textures.py
REVIEW = OUT / 'review'            # check renders, never needed by the game
ASSETS = GAME / 'assets'
MAP = WORLD / 'map'
