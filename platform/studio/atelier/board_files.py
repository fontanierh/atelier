"""Board attachments: files saved on this machine and named in a message by a plain trailer of absolute paths.

The web UI uploads into the same folder the CLI copies into, and both write the same trailer, so an agent reading
the board with `atelier board read` can open every attachment directly.
"""
import json
import re
import secrets
import shutil
from pathlib import Path
from urllib.parse import quote, unquote

from . import board


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


ATTACHMENT_LIMIT = 512 * 1024 * 1024
ATTACHMENT_ID = re.compile(r'[0-9a-f]{24}')
TRAILER = 'Attachments (files on this machine):'
TRAILER_PATTERN = re.compile(r'(?:\A|\n\n)' + re.escape(TRAILER) + r'\n((?:- [^\n]*(?:\n|\Z))+)\Z')
# Only these types display inline; everything else downloads, so an uploaded page or SVG can never run here.
INLINE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/heic', 'image/heif', 'image/avif',
                'video/mp4', 'video/quicktime', 'video/webm', 'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/x-m4a',
                'audio/wav', 'application/pdf'}


def attachments_dir():
    return board.root() / 'board-attachments'


def file_name(name):
    name = unquote(name or '').replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^\w.\- ()]+', '_', name).strip(' .')[:120]
    return name or 'file'


def size_text(size):
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'bytes' else f'{size:.1f} {unit}'
        size /= 1024


def store_upload(stream, length, name, mime):
    """Stream one upload to disk; nothing is posted until a message refers to it."""
    if not 0 < length <= ATTACHMENT_LIMIT:
        raise ValueError(f'Files can be up to {ATTACHMENT_LIMIT // 1024 // 1024} MB.')
    mime = mime if re.fullmatch(r'[\w.+-]+/[\w.+-]+', mime or '') else 'application/octet-stream'
    ident, name = secrets.token_hex(12), file_name(name)
    folder = attachments_dir() / ident
    folder.mkdir(parents=True)
    try:
        remaining, partial = length, folder / '.partial'
        with partial.open('wb') as out:
            while remaining:
                chunk = stream.read(min(1 << 20, remaining))
                if not chunk:
                    raise ValueError('The upload was interrupted. Try again.')
                out.write(chunk)
                remaining -= len(chunk)
        partial.replace(folder / name)
        (folder / '.meta.json').write_text(json.dumps({'name': name, 'mime': mime, 'size': length}))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {'id': ident, 'name': name, 'mime': mime, 'size': length}


def attachment(ident):
    if not isinstance(ident, str) or not ATTACHMENT_ID.fullmatch(ident):
        return None
    meta = read_json(attachments_dir() / ident / '.meta.json')
    if not meta:
        return None
    path = attachments_dir() / ident / meta['name']
    if not path.is_file():
        return None
    return {'id': ident, 'name': meta['name'], 'mime': meta['mime'], 'size': meta['size'], 'path': path,
            'url': f'/api/attachment/{ident}/{quote(meta["name"])}'}


def with_attachments(body, ids):
    if not ids:
        return body
    if not isinstance(ids, list) or len(ids) > 10 or len(set(map(str, ids))) != len(ids):
        raise ValueError('Attach at most 10 different files to one message.')
    lines = []
    for ident in ids:
        item = attachment(ident)
        if not item:
            raise ValueError('An attachment is no longer available. Remove it and add it again.')
        lines.append(f"- {item['name']} ({item['mime']}, {size_text(item['size'])}): {item['path']}")
    if not isinstance(body, str):
        raise ValueError('A message must be text.')
    return (body.rstrip() + '\n\n' if body.strip() else '') + TRAILER + '\n' + '\n'.join(lines)


def split_attachments(body):
    """The message text and the attachments its trailer names. Unknown or removed files are listed as missing."""
    match = TRAILER_PATTERN.search(body)
    if not match:
        return body, []
    files = []
    for line in match[1].splitlines():
        found = re.search(r'/board-attachments/([0-9a-f]{24})/[^/]+$', line)
        item = attachment(found[1]) if found else None
        if item:
            files.append({key: item[key] for key in ('id', 'name', 'mime', 'size', 'url')})
        else:
            files.append({'missing': True, 'name': line[2:].split(' (')[0]})
    return body[:match.start()], files


def store_file(path):
    """Copy a local file into the attachment folder, as an upload would."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ValueError(f'{path} is not a file')
    import mimetypes
    with path.open('rb') as source:
        return store_upload(source, path.stat().st_size, path.name, mimetypes.guess_type(path.name)[0])
