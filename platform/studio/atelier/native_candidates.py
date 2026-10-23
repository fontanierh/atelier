"""Read-only candidate admission inside native imports; no controller or guard dependencies."""
import re
import stat
from .build_hashes import digest_file, signature
from .native_protocol import (CheckpointError, HEX, ReadStore as Store, context, identity, read_json,
                              relative, safe_destination, validate)

def task_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value) or '..' in value:
        raise CheckpointError('Invalid candidate task name')
    return value


def root(ctx):
    return safe_destination(ctx.out, '.state/import-candidates')


def original(store, key):
    if not HEX.fullmatch(key):
        raise CheckpointError('Invalid candidate checkpoint key')
    try:
        return store.load(key)
    except FileNotFoundError:
        value = read_json(store.directory / 'candidate-sources' / (key + '.json'))
        validate(value, store.game)
        if identity(value) != key:
            raise CheckpointError('Candidate source manifest identity differs')
        return value


def inventory(ctx, key, task):
    """Original immutable member inventory and historical compatibility evidence, without copies."""
    task_name(task)
    saved = original(Store(ctx.game), key)
    stamp = {**saved['stamps'], **saved.get('incremental_stamps', {}), **saved.get('historical_stamps', {})}.get(task)
    # Revision is provenance only: geometry is proved by the receiver's import validation, so
    # dirty or unrevisioned producers donate on input identity alone.
    revision = saved.get('source_revision', '')
    if (saved['context'] != context(ctx) or not stamp or stamp.get('touched')
            or not isinstance(revision, str) or revision and not re.fullmatch(r'[0-9a-f]{40}', revision)):
        raise CheckpointError('Candidate needs compatible engine/platform and historical task proof')
    return dict(schema=1, checkpoint=key, donor_task=task, donor_fingerprint=stamp['fingerprint'],
                source_revision=revision, donor_stamp=stamp, context=saved['context'], provenance='compatibility-only', files=saved['files'])


def object_path(entry):
    return 'objects/' + entry['sha256'] + '-' + format(entry['mode'], '03o')


def checked_file(directory, member, entry, *, shared=False, verified=None):
    relative(member)
    if not isinstance(entry, dict) or not HEX.fullmatch(entry.get('sha256', '')):
        raise CheckpointError('Invalid staged candidate member')
    expected_path = object_path(entry) if shared else 'files/' + member
    if entry.get('path') != expected_path:
        raise CheckpointError('Invalid staged candidate member')
    path = safe_destination(directory, entry['path'])
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_size != entry['size']
            or stat.S_IMODE(before.st_mode) != entry['mode']):
        raise CheckpointError('Staged candidate bytes changed')
    # One fresh verification pass hashes each shared object once. This cache is never persisted
    # or carried into a later member access; a changed stat identity forces another hash.
    key = (str(path), signature(before), entry['sha256'])
    if ((verified is None or key not in verified) and digest_file(path) != entry['sha256']
            or signature(path.lstat()) != signature(before)):
        raise CheckpointError('Staged candidate bytes changed')
    if verified is not None:
        verified.add(key)
    return path


class Bundle(dict):
    """Loaded once per importer; each member access verifies only that member's actual bytes."""
    def __init__(self, value, directory, receiver):
        super().__init__(value)
        self.directory = directory
        self.receiver = receiver

    def member_path(self, member):
        entry = self['files'].get(member)
        return checked_file(self.directory, member, entry, shared=self['schema'] == 2) if entry is not None else None


def completion(ctx, value, directory, *, verify_files=True, verified=None):
    if (not isinstance(value, dict) or value.get('schema') not in (1, 2) or value.get('provenance') != 'compatibility-only'
            or value.get('context') != context(ctx) or not HEX.fullmatch(value.get('checkpoint', ''))
            or not HEX.fullmatch(value.get('donor_fingerprint', ''))
            or not re.fullmatch(r'([0-9a-f]{40})?', value.get('source_revision', ''))
            or not isinstance(value.get('files'), dict) or not value['files']):
        raise CheckpointError('Invalid or incompatible candidate completion')
    task_name(value['donor_task'])
    proof = inventory(ctx, value['checkpoint'], value['donor_task'])
    if any(value.get(k) != proof[k] for k in ('source_revision', 'context', 'donor_fingerprint', 'donor_stamp')):
        raise CheckpointError('Candidate completion differs from immutable donor evidence')
    for member, entry in value['files'].items():
        original_entry = proof['files'].get(member)
        if not isinstance(entry, dict) or original_entry is None or original_entry['kind'] != 'file' or any(
                entry.get(k) != original_entry[k] for k in ('sha256', 'size', 'mode')):
            raise CheckpointError('Candidate completion contains unproved donor members')
    bundle = Bundle(value, directory, (ctx.game, root(ctx)))
    if verify_files:
        for member in value['files']:
            checked_file(directory, member, value['files'][member], shared=value['schema'] == 2, verified=verified)
    return bundle


def load_all(ctx, task):
    """@cc [owner:fontanierh,label:correctness] compatibility-candidates-are-not-success
    A candidate pointer MUST stay within ignored receiving staging. Load MUST verify engine/
    platform context and staged file integrity. It MUST NOT publish a receiving stamp or claim
    current importer compatibility. A failed check MUST yield a normal cache miss. Reuse of
    native assets requires the native owner's current source/policy/material/collision proof.
    """
    try:
        pointer = read_json(root(ctx) / (task_name(task) + '.json'))
        if not isinstance(pointer, dict):
            return []
        manifests = ([pointer['manifest']] if pointer.get('schema') == 1 else
                     pointer['manifests'] if pointer.get('schema') == 2 else [])
        if (not isinstance(manifests, list) or not manifests
                or any(not isinstance(p, str) for p in manifests) or len(set(manifests)) != len(manifests)):
            return []
        bundles, verified = [], set()
        for member in manifests:
            try:
                manifest = safe_destination(root(ctx), member)
                bundle = completion(ctx, read_json(manifest), manifest.parent, verified=verified)
                if bundle.get('receiver_task') == task:
                    bundles.append(bundle)
            except (OSError, ValueError, KeyError, TypeError, CheckpointError):
                continue  # Each donor remains independently proved; one cannot hide the rest.
        return bundles
    except (OSError, ValueError, KeyError, TypeError, CheckpointError):
        return []


def load(ctx, task):
    """Legacy primary-donor accessor; composition-aware consumers use load_all()."""
    bundles = load_all(ctx, task)
    return bundles[0] if bundles else None


def member_path(ctx, task, member, *, bundle=None):
    """Pass the Bundle from load() to avoid rehashing the bundle on each member access."""
    try:
        bundle = bundle if bundle is not None else load(ctx, task)
        if bundle is not None and (bundle.get('receiver_task') != task or bundle.receiver != (ctx.game, root(ctx))):
            return None
        return bundle.member_path(member) if bundle is not None else None
    except (OSError, ValueError, KeyError, TypeError, CheckpointError):
        return None
