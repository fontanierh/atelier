"""Retain invocation-validated native candidates during ordinary builds, without workspace capture."""
import copy
from pathlib import Path
import re
import stat
import subprocess
import time

from . import build_products, paths
from .atomic_files import atomic_json
from .native_protocol import CheckpointError, context, identity, safe_destination, validate


def _revision():
    argv = ['git', '--no-optional-locks', '-C', str(paths.REPO)]
    head = subprocess.check_output([*argv, 'rev-parse', 'HEAD'], timeout=10, text=True).strip()
    dirty = subprocess.check_output([*argv, 'status', '--porcelain=v1', '-z', '--untracked-files=all'], timeout=15)
    return head if not dirty and re.fullmatch('[0-9a-f]{40}', head) else None


def _roots(ctx):
    return {'generated': ctx.out, 'content': ctx.uproject.parent / 'Content'}


def _destination(ctx, member):
    label, slash, tail = member.partition('/')
    if not slash or label not in _roots(ctx):
        raise CheckpointError('Unsupported native candidate member')
    return safe_destination(_roots(ctx)[label], tail)


def _label(ctx, path):
    path = Path(path)
    for label, root in _roots(ctx).items():
        if path.is_relative_to(root):
            member = label + '/' + path.relative_to(root).as_posix()
            if _destination(ctx, member) == path:
                return member
    raise CheckpointError('Native candidate source has a noncanonical path')


def _file(ctx, path, expected=None):
    member = _label(ctx, path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise CheckpointError('Native candidate members must be regular files')
    digest = build_products.file_digest(path)
    if expected is not None and (expected.get('sha256') != digest or expected.get('size') != info.st_size):
        raise CheckpointError('Final native package changed after successful receipt publication')
    return member, dict(kind='file', sha256=digest, size=info.st_size,
                        mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns)


def publish(ctx, step, stamp, *, fresh, echo=print):
    """@cc [owner:fontanierh,label:correctness] automatic-native-candidate-retention
    Ordinary success MAY retain only this invocation's finalized native mesh package groups
    plus its declared candidate metadata files. It MUST preserve the original task input
    evidence, recheck source/context/package bytes and publish independent immutable copies.
    It MUST NOT scan broad Content roots, invent action success, or replace live receiving
    assets. A later failed task MUST NOT remove earlier retained candidates. Consumers MUST
    still perform ordinary source/policy/current-native admission; a catalogue is not a hit.
    """
    observations = ctx.__dict__.get('native_candidate_observations', {}).pop(step.name, [])
    scope = getattr(step, 'candidate_scope', None)
    if not observations or scope is None:
        return None
    try:
        from .checkpoint_candidates import CandidateScope
        from .checkpoint_store import Store
        from .mesh_reuse import resolve_source, package_inventory
        if not isinstance(scope, CandidateScope) or scope.donor_task not in (None, step.name):
            raise CheckpointError('Unsupported native candidate producer scope')
        if stamp.get('touched') or not isinstance(stamp.get('input_state'), dict):
            raise CheckpointError('Native candidate requires original completed task inputs')
        revision = _revision()
        if revision is None:
            raise CheckpointError('Native candidate source revision is not clean')
        fingerprint = stamp['fingerprint']
        current = context(ctx)
        if any(current != packet.get('context') for packet in observations) or fresh() != fingerprint:
            raise CheckpointError('Native candidate inputs/context changed before retention')
        required = dict(_file(ctx, Path(path)) for path in scope.files)
        prefixes = [_label(ctx, Path(path)).rstrip('/') + '/' for path in scope.directories]
        files, groups, proofs = dict(required), [], []
        for packet in observations:
            for name, record in packet['records'].items():
                entry = packet['entries'][name]
                try:
                    for source in entry['sources']:
                        if build_products.file_digest(resolve_source(ctx, source['member'])) != source['sha256']:
                            raise CheckpointError('Native candidate source changed after admission')
                    if package_inventory(ctx.uproject.parent / 'Content', entry['packages']) != record['packages']:
                        raise CheckpointError('Native candidate package membership changed')
                    members = dict(_file(ctx, _destination(ctx, member), expected)
                                   for member, expected in record['packages'].items())
                except (OSError, ValueError, RuntimeError):
                    continue  # A later command may legitimately replace an earlier package group.
                if not all(member in required or any(member.startswith(prefix) for prefix in prefixes)
                           for member in members):
                    continue  # Collision/LOD groups are indivisible, even across scope boundaries.
                files.update(members)
                groups.append(set(members))
                proofs.append((entry, record))
        if not groups:
            return None
        retained = {name: files[name] for name in sorted(files)}
        value = dict(schema=1, game=ctx.game, checkout=identity(str(paths.REPO)), context=current,
                     source_revision=revision, files=retained, stamps={}, actions={},
                     historical_stamps={step.name: copy.deepcopy(stamp)})
        validate(value, ctx.game)
        store = Store(ctx.game)
        with store.locked():
            spoken = time.monotonic()
            for count, (member, entry) in enumerate(retained.items(), 1):
                store.put(_destination(ctx, member), entry['sha256'])
                if time.monotonic() - spoken >= 25:
                    echo(step.name + ': retaining native candidates ' + str(count) + '/' + str(len(retained)) + ' files')
                    spoken = time.monotonic()
            if (_revision() != revision or context(ctx) != current or fresh() != fingerprint
                    or any(_file(ctx, _destination(ctx, member), entry)[1] != entry for member, entry in retained.items())
                    or any(package_inventory(ctx.uproject.parent / 'Content', item['packages']) != record['packages']
                           for item, record in proofs)
                    or any(build_products.file_digest(resolve_source(ctx, source['member'])) != source['sha256']
                           for item, _ in proofs for source in item['sources'])):
                raise CheckpointError('Native producer changed during candidate retention')
            key = identity(value)
            target = store.directory/'candidate-sources'/(key+'.json')
            if target.is_symlink():
                raise CheckpointError('Linked native candidate catalogue')
            atomic_json(target, value)
        echo(step.name+': automatically retained '+str(len(groups))+' validated native candidate groups')
        return key
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        echo(step.name+': native candidate retention skipped ('+str(error)+')')
        return None
