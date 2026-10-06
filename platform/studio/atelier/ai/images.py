"""OpenAI image calls (gpt-image-2.5-sunburst) for the art tools: one client instead of a copy per script.

`sunburst` makes one request: /v1/images/edits when context images are given, /v1/images/generations otherwise.
The key goes in an in-process header, never on a command line, and is never printed. `paint` wraps one request in
`atelier.ai.ledger.run_once`, so the provenance record exists before the paid call and a failure stays on record as
uncertain instead of being retried.
"""
import base64
import hashlib
import io
import time
from pathlib import Path

from atelier.ai import ledger

MODEL, QUALITY = 'gpt-image-2.5-sunburst', 'high'
API = 'https://api.openai.com/v1'


def upload(path, maxw=1280):
    """An image as the API gets it: RGB JPEG at quality 92, at most maxw wide. Returns a multipart file tuple."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    if im.width > maxw:
        im = im.resize((maxw, round(im.height*maxw/im.width)))
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=92)
    return (Path(path).stem+'.jpg', buf.getvalue(), 'image/jpeg')


def sunburst(prompt, size, images=(), n=1, *, quality=QUALITY, model=MODEL, key=None, timeout=900):
    """n images for prompt. Returns (list of PNG bytes, the response body without the image data, seconds).

    key defaults to OPENAI_API_KEY from the environment or the ignored .env."""
    import httpx
    if key is None:
        from atelier.env import require
        key = require('OPENAI_API_KEY')
    headers = {'Authorization': 'Bearer '+key}
    fields = {'model': model, 'prompt': prompt, 'size': size, 'quality': quality}
    started = time.time()
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=30)) as client:
        if images:
            response = client.post(API+'/images/edits', headers=headers, data={**fields, 'n': str(n)},
                                   files=[('image[]', upload(p)) for p in images])
        else:
            response = client.post(API+'/images/generations', headers=headers, json={**fields, 'n': n})
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(f'Sunburst HTTP {response.status_code} without JSON') from None
    if response.status_code >= 400 or not body.get('data'):
        raise RuntimeError(f'Sunburst HTTP {response.status_code}: {(body.get("error") or {}).get("message", "no image")}')
    blobs = [base64.b64decode(d.pop('b64_json')) for d in body['data']]
    return blobs, body, round(time.time()-started, 1)


def paint(target, prompt, size, images=(), *, record, metadata=(), **options):
    """One ledgered image at target (a .png path); record is its provenance file, which must not exist yet.

    The record holds metadata plus the request, then the output hash, usage and time once the call returns."""
    target = Path(target)
    meta = {**dict(metadata), 'requested_model': options.get('model', MODEL),
            'quality': options.get('quality', QUALITY), 'size': size,
            'endpoint': '/v1/images/edits' if images else '/v1/images/generations',
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}

    def call():
        blobs, body, seconds = sunburst(prompt, size, images, **options)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blobs[0])
        return dict(output=target.name, output_sha256=hashlib.sha256(blobs[0]).hexdigest(),
                    usage=body.get('usage'), elapsed_seconds=seconds)
    return ledger.run_once(record, meta, call)
