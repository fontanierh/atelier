"""Export one selected encoded mesh packet to its GLB and public receipt inside a v2 job.

The body is the original encoded export (`atelier.encoded_glb.export`): unchanged encoded
bytes, its exclusive membership checks and `export_manifest.publish_receipt` validation. No
subprocess, project scheduling, build cache or directory scan beyond the declared member.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'platform/studio'))
from atelier import encoded_glb  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import validate  # noqa: E402


def _member(value):
    if (type(value) is not str or not value or PurePosixPath(value).name != value or '\\' in value
            or value in ('.', '..') or not value.endswith('.mesh') or value == '.mesh'):
        raise ValueError('Expected one canonical .mesh member name')
    return value


def run(context):
    """@cc [owner:fontanierh,label:correctness] v2-encoded-export-piece
    The job MUST consume exactly its declared payload slot: a group-member directory holding
    exactly the named .mesh packet, nothing else and no links. It MUST emit exactly
    <asset>.glb and export.json through the original encoded export and receipt validation,
    with the decoded role equal to the declared payload_role. It MUST NOT re-encode bytes.
    The only receipt change is metadata.payload_sha256, the SHA-256 of the selected packet,
    written canonically after the original export and validation, then validated again.
    """
    params = context.params
    if (params.get('payload_encoding') != 'encoded_glb' or params.get('payload_role') not in ('render', 'collision')
            or set(context.inputs) != {'payload'}):
        raise ValueError('Only one selected encoded_glb render/collision payload is supported')
    member = _member(params.get('payload_member'))
    root = context.input('payload')
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected the selected member directory')
    if sorted(path.name for path in root.iterdir()) != [member]:
        raise ValueError('Selected payload directory contains unowned members')
    payload = root / member
    if payload.is_symlink() or not payload.is_file() or payload.stat().st_nlink != 1:
        raise ValueError('Missing, linked or shared selected payload')
    if payload.stat().st_size > encoded_glb.MAX_BYTES:
        raise ValueError('Selected payload exceeds its bounded envelope')
    original = payload.read_bytes()
    key = member[:-len('.mesh')]
    identity, _ = encoded_glb.decode(original, key=key)
    if identity['role'] != params['payload_role']:
        raise ValueError('Selected payload role differs from its declared role')
    primary = identity['asset'] + '.glb'
    if set(context.outputs) != {primary, 'export.json'}:
        raise ValueError('Declared outputs differ from the selected piece GLB and receipt')
    destination = context.output(primary).parent
    receipt = encoded_glb.export(payload, destination)
    if receipt['asset'] != identity['asset'] or receipt['primary'] != primary:
        raise ValueError('Encoded export receipt differs from the selected payload')
    if payload.read_bytes() != original:
        raise ValueError('Selected payload changed during the export')
    value = json.loads(context.output('export.json').read_text())
    if 'payload_sha256' in value['metadata']:
        raise ValueError('Original receipt already names a payload digest')
    value['metadata']['payload_sha256'] = hashlib.sha256(original).hexdigest()
    atomic_json(context.output('export.json'), value)
    final = validate(destination, key=identity['asset'])
    if final['metadata'].get('payload_sha256') != value['metadata']['payload_sha256']:
        raise ValueError('Canonical receipt lost its payload digest')
