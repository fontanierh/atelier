"""Explicit offline ingestion of publisher-signed portable source products.

Signatures authenticate publisher assertions; they do not independently prove a
clean/pushed/guarded build, redistribution rights, or the absence of secrets.
There is no publisher, network lookup, archive extraction, or checkout hydration.
"""
import base64
import binascii
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from types import SimpleNamespace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import build_cache, build_products


class BundleError(ValueError):
    """A fixed, safe diagnostic for untrusted bundle rejection."""


DOMAIN = b'atelier-artifact-bundle-v1\0'
NAMESPACE = 'atelier.portable-source.v1'
MAX_MANIFEST = 2 * 1024 * 1024
MAX_TRUST = 64 * 1024
MAX_RECORDS = 4096
MAX_PRODUCTS = 256
MAX_ROOTS = 32
MAX_BYTES = 256 * 1024 * 1024
IDENTIFIER = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
FORBIDDEN = {'auth', 'authentication', 'credential', 'credentials', 'secret', 'secrets',
             'token', 'tokens', 'billing', 'ledger', 'password', 'passwords', 'authorization'}
RESERVED = {'content', 'binaries', 'intermediate', 'saved', 'logs', 'stamps', '.state',
            '.git', '.ssh', '.aws', '.azure', '.kube', '.netrc', '.npmrc', '.pypirc',
            'id_rsa', 'id_ed25519', 'api-key.json', 'api_key.json', 'apikey.json'}
NATIVE = build_cache.NATIVE_SUFFIXES | {'.exe', '.app', '.dmg', '.o', '.obj', '.a', '.lib', '.pdb',
                                      '.pak', '.ucas', '.utoc', '.metallib', '.spv'}


def _fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise BundleError('Invalid bundle fields')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BundleError('Duplicate JSON key')
            result[key] = value
        return result

    def forbidden(_):
        raise BundleError('Non-integer JSON number')

    value = json.loads(data, object_pairs_hook=pairs, parse_float=forbidden, parse_constant=forbidden)
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 32 or count > 50000:
            raise BundleError('JSON structure exceeds limit')
        if type(item) is dict:
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            pending.extend((v, depth + 1) for v in item)
        elif type(item) not in (str, int, bool, type(None)):
            raise BundleError('Invalid JSON value')
    return value


def _decode(value, size):
    if type(value) is not str:
        raise BundleError('Invalid signature or key encoding')
    raw = base64.b64decode(value, validate=True)
    if len(raw) != size or base64.b64encode(raw).decode('ascii') != value:
        raise BundleError('Invalid signature or key length')
    return raw


def _open_file(stack, name, *, parent=None):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise BundleError('Bundle inputs must be regular files')
    return fd, info


def _signature(info):
    return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_json(stack, name, limit, *, parent=None):
    fd, before = _open_file(stack, name, parent=parent)
    if before.st_size > limit:
        raise BundleError('JSON byte limit exceeded')
    data = bytearray()
    while len(data) <= limit:
        chunk = os.read(fd, min(65536, limit + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > limit or len(data) != before.st_size or _signature(os.fstat(fd)) != _signature(before):
        raise BundleError('JSON input changed or exceeded limit')
    return _json(data)


def _names(fd, limit):
    names = set()
    with os.scandir(fd) as entries:
        for entry in entries:
            if len(names) >= limit:
                raise BundleError('Bundle directory entry limit exceeded')
            names.add(entry.name)
    return names


def _safe_member(relative):
    if len(str(relative)) > 1024 or len(relative.parts) > 32:
        raise BundleError('Product path limit exceeded')
    for part in relative.parts:
        lower = part.casefold()
        if (lower in RESERVED or lower.startswith('.env') or
                FORBIDDEN.intersection(re.split(r'[^a-z0-9]+', lower)) or
                Path(lower).suffix in NATIVE or ':' in part):
            raise BundleError('Sensitive or native product path refused')


def _records(entry):
    _fields(entry, ('schema', 'key', 'products'))
    if type(entry['schema']) is not int or entry['schema'] != 1 or not build_cache.DIGEST.fullmatch(entry['key']):
        raise BundleError('Invalid portable action identity')
    products = entry['products']
    if type(products) is not dict or not 1 <= len(products) <= MAX_PRODUCTS:
        raise BundleError('Product count exceeds limit')
    decoded, blobs, logical, count = {}, {}, 0, 0
    for name, record in products.items():
        if not IDENTIFIER.fullmatch(name):
            raise BundleError('Invalid product name')
        _fields(record, ('digest', 'inventory'))
        inventory = record['inventory']
        _fields(inventory, ('schema', 'files'))
        if type(inventory['schema']) is not int or inventory['schema'] != 1 or type(inventory['files']) is not dict:
            raise BundleError('Invalid product inventory')
        count += len(inventory['files'])
        if count > MAX_RECORDS:
            raise BundleError('Inventory record limit exceeded')
        if build_products.identity(inventory) != record['digest']:
            raise BundleError('Product inventory digest differs')
        roots = sum(name.endswith('/.') for name in inventory['files'])
        if not 1 <= roots <= MAX_ROOTS:
            raise BundleError('Product root count exceeds limit')
        members = list(build_cache.members(inventory, roots))
        seen = set()
        for index, relative, item in members:
            _safe_member(relative)
            # Refuse missing parents before touching staging. Otherwise a sparse, invalid
            # inventory could create many implicit directories before the final byte check.
            parent = relative
            while parent != PurePosixPath('.'):
                parent = parent.parent
                declaration = inventory['files'].get(f'{index}/{parent.as_posix()}')
                if not isinstance(declaration, dict) or declaration.get('kind') != 'directory':
                    raise BundleError('Incomplete product directory inventory')
            alias = index, str(relative).casefold()
            if alias in seen:
                raise BundleError('Aliased product paths')
            seen.add(alias)
            if item['kind'] == 'file':
                _fields(item, ('kind', 'size', 'sha256'))
                logical += item['size']
                if logical > MAX_BYTES:
                    raise BundleError('Logical product bytes exceed limit')
                digest = item['sha256']
                if digest in blobs and blobs[digest] != item['size']:
                    raise BundleError('Contradictory blob sizes')
                blobs[digest] = item['size']
            else:
                _fields(item, ('kind',))
        decoded[name] = roots, members
    return decoded, blobs, logical, count


def _verify(stack, directory, trust_file):
    # System aliases such as /tmp are fine; bundle/trust roots themselves are not links.
    directory = Path(directory)
    root = os.open(directory.parent.resolve() / directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stack.callback(os.close, root)
    if _names(root, 3) != {'manifest.json', 'blobs'}:
        raise BundleError('Unexpected bundle contents')
    payload_file = _read_json(stack, 'manifest.json', MAX_MANIFEST, parent=root)
    _fields(payload_file, ('payload', 'signature'))
    payload = payload_file['payload']
    _fields(payload, ('schema', 'namespace', 'publisher', 'entry', 'producer', 'redistribution', 'root_names'))
    if type(payload['schema']) is not int or payload['schema'] != 1 or payload['namespace'] != NAMESPACE:
        raise BundleError('Unsupported bundle namespace')
    trust_file = Path(trust_file)
    trust = _read_json(stack, trust_file.parent.resolve() / trust_file.name, MAX_TRUST)
    _fields(trust, ('schema', 'publishers'))
    if type(trust['schema']) is not int or trust['schema'] != 1 or type(trust['publishers']) is not dict:
        raise BundleError('Invalid publisher trust configuration')
    publishers = {}
    for key_id, encoded in trust['publishers'].items():
        public = _decode(encoded, 32)
        if hashlib.sha256(public).hexdigest() != key_id:
            raise BundleError('Publisher key identity differs')
        publishers[key_id] = public
    publisher = payload['publisher']
    if type(publisher) is not str or publisher not in publishers:
        raise BundleError('Publisher is not pinned')
    Ed25519PublicKey.from_public_bytes(publishers[publisher]).verify(
        _decode(payload_file['signature'], 64), DOMAIN + _canonical(payload))
    producer = payload['producer']
    _fields(producer, ('source_commit', 'clean', 'pushed', 'guarded', 'tool_context'))
    if (not COMMIT.fullmatch(producer['source_commit']) or
            not build_cache.DIGEST.fullmatch(producer['tool_context']) or
            any(producer[name] is not True for name in ('clean', 'pushed', 'guarded'))):
        raise BundleError('Required publisher attestations missing')
    decoded, blobs, logical, count = _records(payload['entry'])
    labels = payload['root_names']
    if type(labels) is not dict or set(labels) != set(decoded):
        raise BundleError('Signed root names required for every product')
    for name, (root_count, _) in decoded.items():
        if type(labels[name]) is not list or len(labels[name]) != root_count:
            raise BundleError('Signed root names differ from inventory')
        for label in labels[name]:
            if (type(label) is not str or not label or len(label) > 255 or '\\' in label or
                    '\0' in label or len(PurePosixPath(label).parts) != 1 or label in ('.', '..') or
                    label != PurePosixPath(label).as_posix()):
                raise BundleError('Invalid root basename')
            _safe_member(PurePosixPath(label))
    grants = payload['redistribution']
    if type(grants) is not dict or set(grants) != set(decoded):
        raise BundleError('Explicit redistribution grants required for every product')
    for grant in grants.values():
        _fields(grant, ('permission', 'grant'))
        if grant['permission'] not in ('private', 'public') or not IDENTIFIER.fullmatch(grant['grant']):
            raise BundleError('Invalid redistribution grant')
    blob_dir = os.open('blobs', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    stack.callback(os.close, blob_dir)
    if _names(blob_dir, MAX_RECORDS + 1) != set(blobs):
        raise BundleError('Bundle blob set differs from inventories')
    return payload, decoded, blobs, logical, count, blob_dir


def import_bundle(directory: Path, trust_file: Path, *, store=None, dry_run=False):
    """@cc [owner:fontanierh,label:security] authenticated-offline-artifact-ingestion
    Only pinned publisher signatures with explicit grants MAY admit portable source products.
    Every blob and complete staged inventory MUST be verified before Store.publish; its unchanged
    action-index-last protocol MUST be the only store writer. Dry runs MUST NOT touch the store,
    checkout outputs, or stamps. Provenance/grants are signer assertions, not independent proof.
    """
    try:
        if type(dry_run) is not bool:
            raise BundleError('Dry run must be a boolean')
        with ExitStack() as inputs, tempfile.TemporaryDirectory(prefix='atelier-bundle-') as folder:
            payload, decoded, blobs, logical, count, blob_dir = _verify(inputs, directory, trust_file)
            staging = Path(folder)
            copies = staging / 'blobs'
            copies.mkdir()
            for digest, size in blobs.items():
                with ExitStack() as blob_input:
                    fd, before = _open_file(blob_input, digest, parent=blob_dir)
                    if before.st_size != size:
                        raise BundleError('Blob size differs')
                    checksum = hashlib.sha256()
                    copied = 0
                    with (copies / digest).open('wb') as output:
                        while True:
                            chunk = os.read(fd, min(1024 * 1024, size + 1 - copied))
                            if not chunk:
                                break
                            copied += len(chunk)
                            if copied > size:
                                raise BundleError('Blob grew during verification')
                            checksum.update(chunk)
                            output.write(chunk)
                    if copied != size or checksum.hexdigest() != digest or _signature(os.fstat(fd)) != _signature(before):
                        raise BundleError('Blob digest differs or input changed')
            products = []
            for number, (name, (root_count, members)) in enumerate(decoded.items()):
                roots = tuple(staging / 'products' / str(number) / str(i) for i in range(root_count))
                for index, relative, record in members:
                    target = roots[index] / relative
                    if record['kind'] == 'directory':
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        # Parent declarations have already been validated against the inventory.
                        target.parent.mkdir(parents=True, exist_ok=True)
                        build_cache.copy_file(copies / record['sha256'], target)
                products.append(build_products.Product(name, roots))
            from .build import Python, Step
            step = Step('bundle-import', [Python(staging / 'unused.py')], products=products)
            records = payload['entry']['products']
            if build_products.records(step) != records:
                raise BundleError('Staged inventory differs')
            if not dry_run:
                destination = build_cache.Store() if store is None else store
                conflict = destination.action(payload['entry']['key']).with_suffix('.conflict.json')
                if conflict.exists():
                    raise BundleError('Action key conflict; inspect atelier cache status')
                try:
                    destination.publish(SimpleNamespace(out=staging), step, payload['entry']['key'], records)
                except ValueError as error:
                    if str(error) == 'Same action key produced different bytes; reuse disabled for this key':
                        raise BundleError('Action key conflict; inspect atelier cache status') from None
                    raise
                if conflict.exists():
                    raise BundleError('Action key conflict; inspect atelier cache status')
            return {'schema': 1, 'namespace': NAMESPACE, 'key': payload['entry']['key'],
                    'publisher': payload['publisher'], 'manifest_sha256': hashlib.sha256(_canonical(payload)).hexdigest(),
                    'products': sorted(decoded), 'blobs': len(blobs), 'logical_bytes': logical,
                    'inventory_records': count, 'dry_run': bool(dry_run), 'imported': not dry_run,
                    'producer_attestation': payload['producer'], 'redistribution': payload['redistribution'],
                    'public_redistribution_asserted': all(
                        grant['permission'] == 'public' for grant in payload['redistribution'].values()),
                    'provenance_verification': 'pinned publisher assertion only'}
    except BundleError:
        raise
    except InvalidSignature:
        raise BundleError('Invalid publisher signature') from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,
            binascii.Error):
        # Untrusted values and host paths must not escape through parser/filesystem exceptions.
        raise BundleError('Bundle verification or import failed') from None
