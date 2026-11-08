"""Shared pieces of the tree house art tools (treehouse_concepts, treehouse_refs, treehouse_textures and
treehouse_props): where the files live, the Sunburst call and the compact JPEG copies (atelier.ai.images), the
ledger's set_aside and redact, contact sheets (atelier.review.contact_sheet) and the compact GLB (atelier.gltf).

In git, under games/yorimichi/assets/treehouse/: a compact copy of every chosen painting and model, with its prompt and
provenance. Not in git, under build/yorimichi/treehouse/: the full-size PNGs the API returned (originals/), the Tripo
work folders with the raw downloads and the private API responses (tripo/), and the game stills the paintings are
steered with (scout/, captures/, and the plan views in build/yorimichi/review/treehouse/plan/), which the game and
the world scripts can make again.

Only the standard library and Atelier modules built on it are imported at load time, so treehouse_props.py can be
imported from Blender's Python.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from atelier.ai import images as client
from atelier.ai.ledger import redact, set_aside  # noqa: F401 - the art tools import them from here
from atelier.gltf import compact_glb, glb_pack, glb_parts  # noqa: F401
from atelier.review import contact_sheet

ART = yori.ASSETS / 'treehouse'
CONCEPTS, REFS, TEXTURES, PROPS = ART / 'concepts', ART / 'refs', ART / 'textures', ART / 'props'
WORK = yori.OUT / 'treehouse'
ORIGINALS = WORK / 'originals'                     # full-size PNGs as the API returned them
TRIPO = WORK / 'tripo'                             # Tripo work folders: job, raw downloads, api-private
SCOUT = WORK / 'scout'                             # game stills: player/, r01/, r02/
PLAN = yori.REVIEW / 'treehouse' / 'plan'          # plan-map.png, plan-section.png (world/regions/treehouse/plan_views.py)
CAPTURES = WORK / 'captures' / 'blockout-r01'      # the in-game blockout still of each view
SHEETS = yori.REVIEW / 'treehouse'                 # contact sheets for checking, never needed by the game
MODEL, QUALITY = 'gpt-image-2.5-sunburst', 'high'
# the committed copies: (largest width in pixels, JPEG quality, chroma subsampling); smaller images are never
# enlarged. Textures keep full colour resolution (4:4:4): finish divides a surface by its mean, which magnifies errors.
COMPACT = {'concepts': (1600, 88, '4:2:0'), 'refs': (1600, 88, '4:2:0'), 'textures': (1024, 92, '4:4:4'),
           'props': (1024, 90, '4:2:0')}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    """A path as provenance records it: relative to the repository, or build/yorimichi/... for build files (the
    file name alone for anything else, so no home-directory path is ever recorded)."""
    path = Path(path).resolve()
    for root, prefix in ((yori.REPO.resolve(), ''), (yori.OUT.resolve(), 'build/yorimichi/')):
        if path.is_relative_to(root):
            return prefix + path.relative_to(root).as_posix()
    return path.name


def sunburst(prompt, size, images=()):
    """One image from gpt-image-2.5-sunburst at quality high: /v1/images/edits with the context images, or
    /v1/images/generations without. Returns (PNG bytes, usage). The key comes from OPENAI_API_KEY (or the ignored
    .env) and is never printed."""
    blobs, body, _ = client.sunburst(prompt, size, images, model=MODEL, quality=QUALITY)
    return blobs[0], body.get('usage')


def compact(image, dest, kind):
    """Write the committed JPEG copy of an image (bytes or path) for `kind` (a COMPACT key); returns its record."""
    return client.compact(image, dest, *COMPACT[kind])


def keep(png, kind, name, dest):
    """Keep a painting: the full-size PNG under originals/<kind>/<name>.png, the compact JPEG at dest. Returns the
    PNG's hash and the compact record."""
    original = ORIGINALS/kind/f'{name}.png'; original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(png)
    return sha(png), compact(png, dest, kind)


def sheet(items, dest, w, h, cols):
    """A contact sheet of (image path, caption) pairs."""
    dest = contact_sheet.sheet(items, dest, w, h, cols)
    if dest: print('sheet', rel(dest))
    return dest
