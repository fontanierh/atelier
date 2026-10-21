"""Inspect and prune the portable product store. Live checkouts never depend on cached files."""
import json
from collections import Counter
import math
from pathlib import Path
import shutil
import sys
import time

from .build_cache import DIGEST, Store, atomic_json, members
from .build_products import identity


def snapshot(store):
    """Read-only accounting of unique content bytes, not APFS physical space or reclaimable space."""
    blobs, actions, invalid = {}, [], []
    for path in sorted(store.path('blobs').glob('*/*')):
        digest = path.parent.name + path.name
        if DIGEST.fullmatch(digest) and path.is_file() and not path.is_symlink():
            blobs[digest] = store.blob(digest).stat().st_size
    for path in sorted(store.path('actions').glob('*.json')):
        if not DIGEST.fullmatch(path.stem):
            continue
        try:
            value = json.loads(path.read_text())
            if path.is_symlink() or value['schema'] != 1 or value['key'] != path.stem:
                raise ValueError('Invalid action')
            used = set()
            for product in value['products'].values():
                inventory = product['inventory']
                if identity(inventory) != product['digest']:
                    raise ValueError('Invalid inventory')
                count = sum(p.endswith('/.') for p in inventory['files'])
                for _, _, item in members(inventory, count):
                    if item['kind'] == 'file':
                        used.add(item['sha256'])
            actions.append({'key': path.stem, 'used': path.stat().st_mtime, 'blobs': sorted(used),
                            'pinned': path.with_suffix('.pin').exists()})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            invalid.append(path.stem)
    conflicts = sorted(p.name.removesuffix('.conflict.json') for p in (store.root / 'actions').glob('*.conflict.json')
                       if DIGEST.fullmatch(p.name.removesuffix('.conflict.json')))
    from .artifact_snapshot import retention
    retained = retention(store)
    for action in actions:
        action['snapshot_retained'] = action['key'] in retained['snapshot_actions']
    return {'unique_bytes': sum(blobs.values()), 'blobs': blobs, 'actions': actions,
            'invalid_actions': invalid, 'conflicts': conflicts, **retained}


def prune(store, *, max_bytes, max_age_days, dry=False, now=None):
    """Drop old/unpinned LRU actions, then unreferenced blobs, under the exclusive store lock."""
    if max_bytes < 0 or not math.isfinite(max_age_days) or max_age_days < 0:
        raise ValueError('Cache limits must be nonnegative')
    now = time.time() if now is None else now
    if not store.root.exists():
        return {'removed_actions': [], 'removed_bytes': 0, 'remaining_bytes': 0, 'dry_run': dry}
    with store.lock(exclusive=True):
        state = snapshot(store)
        if state['invalid_actions']:
            raise ValueError('Invalid action manifests; inspect and forget them before pruning: '
                             + ', '.join(state['invalid_actions']))
        if state['invalid_snapshots']:
            raise ValueError('Invalid snapshots or retained members; unpin/repair/remove explicitly before pruning: '
                             + ', '.join(state['invalid_snapshots']))
        keep = {item['key']: item for item in state['actions']}
        candidates = sorted((a for a in keep.values() if not a['pinned'] and not a['snapshot_retained']),
                            key=lambda a: (a['used'], a['key']))
        for item in candidates:
            if item['used'] < now - max_age_days * 86400:
                keep.pop(item['key'])
        references = Counter(b for item in keep.values() for b in item['blobs'])
        retained_bytes = sum(state['blobs'].get(b, 0) for b in references)
        for item in candidates:
            if retained_bytes <= max_bytes:
                break
            if keep.pop(item['key'], None) is None:
                continue
            for blob in item['blobs']:
                references[blob] -= 1
                if not references[blob]:
                    retained_bytes -= state['blobs'].get(blob, 0)
                    del references[blob]
        removed = sorted(a['key'] for a in state['actions'] if a['key'] not in keep)
        garbage = state['blobs'].keys() - references.keys()
        freed = sum(state['blobs'][b] for b in garbage)
        if not dry:
            for key in removed:
                store.action(key).unlink(missing_ok=True)
            for digest in garbage:
                store.blob(digest).unlink(missing_ok=True)
            # No transfer can own temporary files while the exclusive lock is held.
            for folder in store.path('blobs').glob('*/.blob-*'):
                if folder.is_dir() and not folder.is_symlink():
                    shutil.rmtree(folder)
            for path in store.path('actions').glob('.write-*'):
                path.unlink()
        return {'removed_actions': removed, 'removed_bytes': freed, 'remaining_bytes': state['unique_bytes'] - freed,
                'dry_run': dry}


def pin(store, key, enabled):
    with store.lock(exclusive=True):
        action = store.action(key)
        marker = action.with_suffix('.pin')
        if not enabled:
            marker.unlink(missing_ok=True)
        elif not action.is_file() or action.with_suffix('.conflict.json').exists():
            raise ValueError('Only an existing, non-conflicting action may be pinned')
        else:
            atomic_json(marker, {'key': key})


def forget(store, key):
    """Discard a bad/nondeterministic entry; never bless either conflicting result."""
    with store.lock(exclusive=True):
        from .artifact_snapshot import retention
        retained = retention(store)
        if retained['invalid_snapshots'] or key in retained['snapshot_actions']:
            raise ValueError('Unpin snapshot roots explicitly before forgetting a retained action')
        action = store.action(key)
        for path in (action, action.with_suffix('.conflict.json'), action.with_suffix('.pin')):
            path.unlink(missing_ok=True)


def configure(sub):
    parser = sub.add_parser('cache', help='inspect, prune and import signed portable products')
    commands = parser.add_subparsers(dest='action', required=True)
    local = commands.add_parser('configure', help='set the private checkpoint repository in machine-local configuration')
    local.add_argument('--repository', required=True)
    commands.add_parser('status')
    commands.add_parser('abandon-transfer', help='remove a journaled partial transfer left by an older client').add_argument('game')
    create = commands.add_parser('snapshot-create', help='pin an unsigned local selection of current portable products')
    create.add_argument('game')
    create.add_argument('steps', nargs='+', help='target step names/prefixes; full dependency closure is mandatory')
    create.add_argument('--grants', type=Path, required=True, help='schema-1 per-action/product redistribution grants')
    create.add_argument('--public', action='store_true', help='require public rights for every selected product; does not publish')
    show = commands.add_parser('snapshot-show', help='verify and inspect a local unsigned snapshot')
    show.add_argument('key')
    show.add_argument('--metadata-only', action='store_true', help='inspect the manifest without requiring retained CAS members')
    restore = commands.add_parser('snapshot-restore', help='restore an exact portable snapshot without executing actions')
    restore.add_argument('key')
    restore.add_argument('game')
    for name in ('snapshot-pin', 'snapshot-unpin', 'snapshot-remove'):
        commands.add_parser(name).add_argument('key')
    gc = commands.add_parser('gc')
    gc.add_argument('--max-gib', type=float, default=10, help='unique retained blob bytes (default: 10 GiB)')
    gc.add_argument('--max-age-days', type=float, default=30, help='keep unpinned hits/publications this recent')
    gc.add_argument('--dry-run', action='store_true')
    bundle = commands.add_parser('import-bundle', help='verify a signed offline bundle and add it to the local store')
    bundle.add_argument('directory', type=Path)
    bundle.add_argument('--trust', type=Path, required=True, help='explicit allowlist of publisher public keys')
    bundle.add_argument('--dry-run', action='store_true', help='verify without changing the local store')
    remote = commands.add_parser('fetch-bundle', help='download signed source products over HTTPS into the local store')
    remote.add_argument('endpoint', help='HTTPS object-store prefix; no credentials, query or fragment')
    remote.add_argument('key', help='exact action key to fetch')
    remote.add_argument('--trust', type=Path, required=True, help='explicit allowlist of publisher public keys')
    remote.add_argument('--timeout', type=float, default=30, help='total transfer deadline in seconds (max 300)')
    remote.add_argument('--dry-run', action='store_true', help='download and verify without changing the local store')
    export = commands.add_parser('export-bundle', help='freshly build an approved audited Python action and export a signed directory')
    export.add_argument('game')
    export.add_argument('step')
    export.add_argument('directory', type=Path)
    export.add_argument('--profile', type=Path, required=True, help='protected operator publisher profile outside the checkout')
    upload = commands.add_parser('upload-bundle', help='explicitly upload a signed public V2 source bundle over HTTPS')
    upload.add_argument('directory', type=Path)
    upload.add_argument('--trust', type=Path, required=True, help='explicit allowlist of publisher public keys')
    upload.add_argument('--profile', type=Path, required=True, help='protected operator endpoint/credential profile')
    upload.add_argument('--timeout', type=float, default=30, help='total verification/transfer deadline (max 300 seconds)')
    upload.add_argument('--dry-run', action='store_true', help='verify snapshot/profile without credentials or network')
    for name in ('pin', 'unpin', 'forget'):
        commands.add_parser(name).add_argument('key')


def main(args):
    if args.action == 'configure':
        from .build_checkpoints import configure_repository
        result = configure_repository(args.repository)
        print(json.dumps(result))
        return 0
    if args.action == 'abandon-transfer':
        from .legacy_transfer import abandon
        return abandon(args.game)
    store = Store()
    try:
        if args.action == 'status':
            if store.root.exists():
                with store.lock():
                    state = snapshot(store)
            else:
                state = snapshot(store)
            print(json.dumps({**state, 'blobs': len(state['blobs']),
                              'actions': [{**a, 'blobs': len(a['blobs'])} for a in state['actions']]}, indent=2))
        elif args.action.startswith('snapshot-'):
            from . import artifact_snapshot
            if args.action == 'snapshot-create':
                result = artifact_snapshot.create(args.game, args.steps, args.grants, store=store, public=args.public)
            elif args.action == 'snapshot-restore':
                result = artifact_snapshot.restore(args.game, args.key, store=store)
            elif args.action == 'snapshot-show':
                with store.lock():
                    result = artifact_snapshot.load(store, args.key, verify=not args.metadata_only)
            elif args.action == 'snapshot-remove':
                result = artifact_snapshot.remove(store, args.key)
            else:
                result = artifact_snapshot.pin(store, args.key, args.action == 'snapshot-pin')
            if result is not None:
                print(json.dumps(result, indent=2))
        elif args.action == 'gc':
            print(json.dumps(prune(store, max_bytes=int(args.max_gib * 2**30), max_age_days=args.max_age_days,
                                   dry=args.dry_run), indent=2))
        elif args.action == 'forget':
            forget(store, args.key)
        elif args.action == 'import-bundle':
            from .artifact_bundle import import_bundle
            print(json.dumps(import_bundle(args.directory, args.trust, store=store, dry_run=args.dry_run), indent=2))
        elif args.action == 'fetch-bundle':
            from .artifact_remote import fetch_bundle, stderr_progress
            print(json.dumps(fetch_bundle(args.endpoint, args.key, args.trust, store=store, dry_run=args.dry_run,
                                          timeout=args.timeout, echo=stderr_progress), indent=2))
        elif args.action == 'export-bundle':
            from .artifact_publisher import publish
            print(json.dumps(publish(args.game, args.step, args.directory, profile=args.profile,
                                     echo=lambda message: print(message, file=sys.stderr)), indent=2))
        elif args.action == 'upload-bundle':
            from .artifact_upload import upload_bundle
            print(json.dumps(upload_bundle(args.directory, args.trust, profile=args.profile, dry_run=args.dry_run,
                                           timeout=args.timeout,
                                           echo=lambda message: print(message, file=sys.stderr)), indent=2))
        else:
            pin(store, args.key, args.action == 'pin')
        return 0
    except (OSError, ValueError) as error:
        print(f'cache: {error}')
        return 1
