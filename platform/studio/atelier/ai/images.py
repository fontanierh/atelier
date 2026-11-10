"""OpenAI image and GIF calls (gpt-image-2.6-sunburst) for the art tools: one client instead of a copy per script.

`sunburst` makes one request: /v1/images/edits when context images are given, /v1/images/generations otherwise.
Both endpoints support animated GIF output (`output_format='gif'`, `frame_count` 2..16 default 9,
`frame_duration_ms` >= 20 default 200) and `complexity` ('low', 'medium' or 'high') on GPT Image 2.6.
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

MODEL, QUALITY = 'gpt-image-2.6-sunburst', 'high'
API = 'https://api.openai.com/v1'
_RETIRED_MODELS = ('gpt-image-2.5-sunburst', 'gpt-image-2.5-sunburst-2026-09-08')
_FORMATS = ('png', 'jpeg', 'webp', 'gif', 'svg')
_COMPLEXITIES = ('low', 'medium', 'high')
_BACKGROUNDS = ('transparent', 'opaque', 'auto')


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _request_fields(prompt, size, *, quality=QUALITY, model=MODEL, output_format=None,
                    frame_count=None, frame_duration_ms=None, complexity=None, background=None):
    if model in _RETIRED_MODELS:
        raise ValueError(f'{model} is retired; use {MODEL}')
    if output_format is not None and output_format not in _FORMATS:
        raise ValueError(f'output_format must be one of {_FORMATS}')
    if (frame_count is not None or frame_duration_ms is not None) and output_format != 'gif':
        raise ValueError('frame_count and frame_duration_ms require output_format="gif"')
    if frame_count is not None and not (_is_int(frame_count) and 2 <= frame_count <= 16):
        raise ValueError('frame_count must be an integer from 2 to 16')
    if frame_duration_ms is not None and not (_is_int(frame_duration_ms) and 20 <= frame_duration_ms <= 655350):
        raise ValueError('frame_duration_ms must be an integer from 20 to 655350')
    if complexity is not None and complexity not in _COMPLEXITIES:
        raise ValueError(f'complexity must be one of {_COMPLEXITIES}')
    if background is not None and background not in _BACKGROUNDS:
        raise ValueError(f'background must be one of {_BACKGROUNDS}')
    fields = {'model': model, 'prompt': prompt, 'size': size, 'quality': quality}
    for name, value in (('output_format', output_format), ('frame_count', frame_count),
                        ('frame_duration_ms', frame_duration_ms), ('complexity', complexity),
                        ('background', background)):
        if value is not None:
            fields[name] = value
    return fields


def upload(path, maxw=1280):
    """An image as the API gets it: RGB JPEG at quality 92, at most maxw wide. Returns a multipart file tuple."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    if im.width > maxw:
        im = im.resize((maxw, round(im.height*maxw/im.width)))
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=92)
    return (Path(path).stem+'.jpg', buf.getvalue(), 'image/jpeg')


def compact(image, dest, width, quality, chroma='4:2:0'):
    """Write a compact JPEG copy of an image (bytes or path) at most `width` pixels wide (a smaller image is never
    enlarged), with `chroma` subsampling ('4:4:4', '4:2:2' or '4:2:0'). Returns its record."""
    from PIL import Image
    im = Image.open(io.BytesIO(image) if isinstance(image, bytes) else image).convert('RGB')
    if im.width > width: im = im.resize((width, round(im.height*width/im.width)), Image.LANCZOS)
    dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, 'JPEG', quality=quality, subsampling={'4:4:4': 0, '4:2:2': 1, '4:2:0': 2}[chroma])
    return dict(file=dest.name, size=f'{im.width}x{im.height}', jpeg_quality=quality, chroma=chroma)


def sunburst(prompt, size='auto', images=(), n=1, *, quality=QUALITY, model=MODEL, output_format=None,
             frame_count=None, frame_duration_ms=None, complexity=None, background=None, key=None, timeout=900):
    """n images or GIFs for prompt. Returns (list of decoded bytes, the response body without b64_json, seconds).

    key defaults to OPENAI_API_KEY from the environment or the ignored .env."""
    import httpx
    fields = _request_fields(prompt, size, quality=quality, model=model, output_format=output_format,
                             frame_count=frame_count, frame_duration_ms=frame_duration_ms,
                             complexity=complexity, background=background)
    if key is None:
        from atelier.env import require
        key = require('OPENAI_API_KEY')
    headers = {'Authorization': 'Bearer '+key}
    started = time.time()
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=30)) as client:
        if images:
            form = {**{k: str(v) for k, v in fields.items()}, 'n': str(n)}
            response = client.post(API+'/images/edits', headers=headers, data=form,
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


def paint(target, prompt, size='auto', images=(), *, record, metadata=(), **options):
    """One ledgered image or GIF at target (.png, .gif, ...); record is its provenance file, which must not exist yet.

    A `.gif` target defaults `output_format` to `'gif'`. Request options are validated before writing the ledger
    record, which holds metadata plus the request, then the output hash, usage and time once the call returns."""
    target = Path(target)
    call_options = dict(options)
    if target.suffix.lower() == '.gif' and call_options.get('output_format') is None:
        call_options['output_format'] = 'gif'
    allowed = {'quality', 'model', 'output_format', 'frame_count', 'frame_duration_ms',
               'complexity', 'background', 'key', 'timeout'}
    unknown = sorted(set(call_options) - allowed)
    if unknown:
        raise TypeError(f"Unexpected sunburst option(s): {', '.join(unknown)}")
    fields = _request_fields(prompt, size, **{k: v for k, v in call_options.items()
                                              if k not in ('key', 'timeout')})
    meta = {**dict(metadata), 'requested_model': fields['model'],
            'quality': fields['quality'], 'size': fields['size'],
            'endpoint': '/v1/images/edits' if images else '/v1/images/generations',
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
    for extra in ('output_format', 'frame_count', 'frame_duration_ms', 'complexity', 'background'):
        if extra in fields:
            meta[extra] = fields[extra]

    def call():
        blobs, body, seconds = sunburst(prompt, size, images, **call_options)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blobs[0])
        return dict(output=target.name, output_sha256=hashlib.sha256(blobs[0]).hexdigest(),
                    usage=body.get('usage'), elapsed_seconds=seconds)
    return ledger.run_once(record, meta, call)
