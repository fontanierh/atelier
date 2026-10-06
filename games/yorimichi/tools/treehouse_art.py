"""Shared pieces of the tree house art tools (treehouse_concepts, treehouse_refs, treehouse_textures and
treehouse_props): where the files live, the Sunburst call (atelier.ai.images), the compact JPEG copies and the compact GLB.

In git, under games/yorimichi/assets/treehouse/: a compact copy of every chosen painting and model, with its prompt and
provenance. Not in git, under build/yorimichi/treehouse/: the full-size PNGs the API returned (originals/), the Tripo
work folders with the raw downloads and the private API responses (tripo/), and the game stills the paintings are
steered with (scout/, captures/, and the plan views in build/yorimichi/review/treehouse/plan/), which the game and
the world scripts can make again.

Only the standard library is imported at load time, so treehouse_props.py can be imported from Blender's Python.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import hashlib, io, json, re, struct
from datetime import datetime, timezone
from pathlib import Path

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
    from atelier.ai import images as client
    blobs, body, _ = client.sunburst(prompt, size, images, model=MODEL, quality=QUALITY)
    return blobs[0], body.get('usage')


def compact(image, dest, kind):
    """Write the committed JPEG copy of an image (bytes or path) for `kind` (a COMPACT key); returns its record."""
    from PIL import Image
    width, quality, chroma = COMPACT[kind]
    im = Image.open(io.BytesIO(image) if isinstance(image, bytes) else image).convert('RGB')
    if im.width > width: im = im.resize((width, round(im.height*width/im.width)), Image.LANCZOS)
    dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, 'JPEG', quality=quality, subsampling={'4:4:4': 0, '4:2:2': 1, '4:2:0': 2}[chroma])
    return dict(file=dest.name, size=f'{im.width}x{im.height}', jpeg_quality=quality, chroma=chroma)


def keep(png, kind, name, dest):
    """Keep a painting: the full-size PNG under originals/<kind>/<name>.png, the compact JPEG at dest. Returns the
    PNG's hash and the compact record."""
    original = ORIGINALS/kind/f'{name}.png'; original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(png)
    return sha(png), compact(png, dest, kind)


def set_aside(path):
    """Rename path to <stem>.rejected-N<suffix> (ignored by git) and return the new path."""
    path = Path(path); n = 1
    while path.with_name(f'{path.stem}.rejected-{n}{path.suffix}').exists(): n += 1
    return path.rename(path.with_name(f'{path.stem}.rejected-{n}{path.suffix}'))


def redact(text):
    """An error message safe to print and record: signed download URLs removed."""
    return re.sub(r'https://\S+', '<URL omitted>', str(text))


def sheet(items, dest, w, h, cols):
    """A contact sheet of (image path, caption) pairs."""
    from PIL import Image, ImageDraw, ImageFont
    items = [(p, c) for p, c in items if Path(p).exists()]
    if not items: return None
    cap = 40 if w > 400 else 30
    canvas = Image.new('RGB', (cols*w, -(-len(items)//cols)*(h+cap)), (244, 241, 234)); d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 22 if w > 400 else 18)
    except OSError:
        font = ImageFont.load_default()
    for i, (path, caption) in enumerate(items):
        x, y = (i % cols)*w, (i//cols)*(h+cap)
        canvas.paste(Image.open(path).convert('RGB').resize((w, h)), (x, y))
        d.text((x+10, y+h+6), caption, font=font, fill=(30, 30, 30))
    Path(dest).parent.mkdir(parents=True, exist_ok=True); canvas.save(dest, quality=86)
    print('sheet', rel(dest))
    return dest


# ------------------------------------------------------------------ compact GLB
def glb_parts(data):
    """(JSON document, BIN chunk) of a binary glTF."""
    magic, version, length = struct.unpack('<4sII', data[:12])
    if magic != b'glTF' or version != 2 or length != len(data): raise ValueError('not a glTF 2 binary')
    size, kind = struct.unpack('<I4s', data[12:20])
    if kind != b'JSON': raise ValueError('first chunk is not JSON')
    doc = json.loads(data[20:20+size])
    at = 20+size; binary = b''
    if at < len(data):
        size, kind = struct.unpack('<I4s', data[at:at+8])
        if kind != b'BIN\0': raise ValueError('second chunk is not BIN')
        binary = data[at+8:at+8+size]
    return doc, binary


def glb_pack(doc, binary):
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' '*(-len(text) % 4); binary += b'\0'*(-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28+len(text)+len(binary)) + struct.pack('<I4s', len(text), b'JSON') + text
            + struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def compact_glb(data, size=1024, quality=90):
    """The same GLB with every embedded image re-encoded as a JPEG at most `size` pixels on a side. Geometry and
    every other buffer view keep their exact bytes; the views are laid out again, 4-byte aligned, in their order."""
    from PIL import Image
    doc, binary = glb_parts(data)
    views = doc['bufferViews']
    if len(doc.get('buffers', [])) != 1 or 'uri' in doc['buffers'][0] or any(v.get('buffer', 0) for v in views):
        raise ValueError('expected one embedded buffer')
    new = {}
    for image in doc.get('images', []):
        if 'bufferView' not in image: continue
        v = views[image['bufferView']]; start = v.get('byteOffset', 0)
        im = Image.open(io.BytesIO(binary[start:start+v['byteLength']])).convert('RGB')
        scale = size/max(im.size)
        if scale < 1: im = im.resize((round(im.width*scale), round(im.height*scale)), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=quality)
        new[image['bufferView']] = buf.getvalue(); image['mimeType'] = 'image/jpeg'
    order = sorted(range(len(views)), key=lambda i: views[i].get('byteOffset', 0))
    for a, b in zip(order, order[1:]):
        if views[a].get('byteOffset', 0)+views[a]['byteLength'] > views[b].get('byteOffset', 0):
            raise ValueError('overlapping buffer views')
    out = bytearray()
    for i in order:
        v = views[i]; start = v.get('byteOffset', 0)
        chunk = new.get(i, binary[start:start+v['byteLength']])
        out += b'\0'*(-len(out) % 4)
        v['byteOffset'] = len(out); v['byteLength'] = len(chunk); out += chunk
    doc['buffers'][0]['byteLength'] = len(out)
    return glb_pack(doc, bytes(out))
