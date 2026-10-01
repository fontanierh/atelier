"""Paths for Yorimichi's world scripts. Import it before anything else.

It puts the Atelier studio package, the regions folder and this folder on sys.path, so `import village.layout` and
`from atelier import paths` work from plain Python and from Blender (which does not add a script's folder to the
path). Everything a build generates goes to OUT (build/yorimichi, or $ATELIER_BUILD_ROOT/yorimichi); the prototype
wrote the same files to japan/out.

Some scripts share a region's name (scenarios/zeppelin.py, scenarios/treehouse.py, scenarios/skatepark.py), and a
script's own folder is on the path. So every region is a regular package (it has an __init__.py: a regular module
anywhere on the path beats a namespace package), and these folders go to the front of the path even when they are
already on it, so the region is found before a script of the same name.
"""
import sys
from pathlib import Path

WORLD = Path(__file__).resolve().parent
REGIONS = WORLD / 'regions'
GAME = WORLD.parent
REPO = GAME.parents[1]
for _path in (REPO / 'platform' / 'studio', REGIONS, WORLD):
    while str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

from atelier.paths import build_dir  # noqa: E402

OUT = build_dir('yorimichi')
TEXTURES = OUT / 'textures'        # gen_textures.py
REVIEW = OUT / 'review'            # check renders, never needed by the game
ASSETS = GAME / 'assets'
MAP = WORLD / 'map'
