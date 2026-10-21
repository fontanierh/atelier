"""Newest-only checkpoint metadata with complete action history and reachable immutable packs."""
from pathlib import Path
import tempfile
from types import SimpleNamespace

from . import release
from .checkpoint_store import CheckpointError, HEX, identity, read_json, validate
from .native_protocol import validate_action
from .checkpoint_packs import VAULT_BODY


def records(index):
    """Validate action history independently of the current workspace's manifest identity."""
    history = index.get('history', {})
    if type(history) is not dict or type(history.get('actions', {})) is not dict or type(history.get('blobs', {})) is not dict:
        raise CheckpointError('Invalid retained action history')
    return history.get('actions', {}), history.get('blobs', {})


def validate_inventory(index, game):
    """Complete metadata proof without downloading or rehashing already retained payloads."""
    from .checkpoint_github import blob_inventory
    store = SimpleNamespace(game=game)
    def check(manifest, blobs):
        validate(manifest, game)
        needed = blob_inventory(manifest, store)
        if type(blobs) is not dict or set(blobs) != set(needed):
            raise CheckpointError('Retained checkpoint blob inventory differs')
        for digest, size in needed.items():
            parts = blobs[digest]
            if (type(parts) is not list or not parts or any(type(p) is not dict or type(p.get('size')) is not int for p in parts)
                    or sum(p['size'] for p in parts) != size):
                raise CheckpointError('Retained checkpoint blob lengths differ')
    check(index['checkpoint'], index['blobs'])
    actions, blobs = records(index)
    check(dict(schema=1, game=game, context={}, checkout='0' * 64, files={}, stamps={}, actions=actions), blobs)
    retained = index.get('retained', {})
    if type(retained) is not dict:
        raise CheckpointError('Invalid retained checkpoint catalogue')
    for key, value in retained.items():
        if type(value) is not dict or value.get('key') != key or identity(value['checkpoint']) != key:
            raise CheckpointError('Pinned checkpoint identity differs')
        check(value['checkpoint'], value['blobs'])


def merge_actions(target, incoming, store):
    from .checkpoint_actions import equivalent
    for key, value in incoming.items():
        validate_action(value, store, key)
        prior = target.get(key)
        stable = lambda action: {k: v for k, v in action.items() if k not in ('files', 'stamp')}
        if prior is not None and (stable(prior) != stable(value) or not equivalent(prior['files'], value['files'])):
            raise CheckpointError('Conflicting historical action outputs; previous checkpoints preserved')
        target[key] = value


def pin_keys(store, remote):
    from .checkpoint_pins import live
    return {key for value in live(remote).values() for key in value.get('checkpoints', [])}


def accumulate(remote, store, manifest, directory):
    actions, known, retained, old = {}, {}, {}, []
    pins = pin_keys(store, remote)
    for item in remote.candidates():
        index = remote.descriptor(item, directory)
        validate_inventory(index, remote.game)
        old.append((item, index))
        history_actions, history_blobs = records(index)
        merge_actions(actions, history_actions, store)
        merge_actions(actions, index['checkpoint'].get('actions', {}), store)
        known.update(history_blobs); known.update(index['blobs'])
        previous = index.get('retained', {})
        if type(previous) is not dict:
            raise CheckpointError('Invalid retained checkpoint index')
        for key, value in {**previous, index['key']: index}.items():
            if key in pins:
                validate(value['checkpoint'], remote.game)
                if value.get('key') != key or identity(value['checkpoint']) != key:
                    raise CheckpointError('Pinned checkpoint identity differs')
                # Prevent recursively growing metadata; retained entries are standalone.
                retained[key] = {k: value[k] for k in ('schema', 'key', 'source_revision', 'checkpoint', 'blobs')}
                known.update(value['blobs'])
    merge_actions(actions, manifest.get('actions', {}), store)
    return actions, known, retained, old


def references(index):
    maps = [index['blobs'], records(index)[1]]
    for key, value in index.get('retained', {}).items():
        if identity(value['checkpoint']) != key:
            raise CheckpointError('Pinned checkpoint identity differs')
        maps.append(value['blobs'])
    result = {}
    for blobs in maps:
        if type(blobs) is not dict:
            raise CheckpointError('Invalid checkpoint blob map')
        for digest, parts in blobs.items():
            if not isinstance(digest, str) or not HEX.fullmatch(digest) or type(parts) is not list or not parts:
                raise CheckpointError('Invalid checkpoint blob range list')
            for part in parts:
                if (type(part) is not dict or type(part.get('release')) is not int or part['release'] <= 0
                        or not isinstance(part.get('pack'), str) or not HEX.fullmatch(part['pack'])
                        or type(part.get('offset')) is not int or part['offset'] < 0
                        or type(part.get('size')) is not int or part['size'] < 0):
                    raise CheckpointError('Invalid retained pack reference')
                result.setdefault(part['release'], {}).setdefault(part['pack'], []).append(part)
    return result


def verify(remote, index):
    from .checkpoint_github import PACK_BYTES
    validate_inventory(index, remote.game)
    refs = references(index)
    for number, packs in refs.items():
        item = remote.github.read(f'releases/{number}')
        if (type(item) is not dict or item.get('id') != number
                or not (item.get('tag_name', '').startswith(remote.prefix)
                        or item.get('tag_name', '').startswith(remote.game + '-cache-packs-'))):
            raise CheckpointError('Pack owner is outside this game checkpoint namespace')
        assets = release.asset_map(remote.github, item)
        for digest, parts in packs.items():
            asset = assets.get('pack-' + digest + '.bin', {})
            if (asset.get('state') != 'uploaded' or asset.get('digest') != 'sha256:' + digest
                    or type(asset.get('size')) is not int or not 0 <= asset['size'] <= PACK_BYTES
                    or any(p['offset'] + p['size'] > asset['size'] for p in parts)):
                raise CheckpointError('Referenced checkpoint pack is missing or changed')
    return refs


def covers(index, old, store, remote):
    """Replaying a completed tag must never retire results absent from its immutable index."""
    from .checkpoint_actions import equivalent
    available = dict(records(index)[0])
    merge_actions(available, index['checkpoint'].get('actions', {}), store)
    required, pinned = {}, pin_keys(store, remote)
    for _, prior in old:
        merge_actions(required, records(prior)[0], store)
        merge_actions(required, prior['checkpoint'].get('actions', {}), store)
        for key in (set(prior.get('retained', {})) | {prior['key']}) & pinned:
            if key != index['key'] and key not in index.get('retained', {}):
                return False
    for key, action in required.items():
        current = available.get(key)
        if current is None or current['roots'] != action['roots'] or not equivalent(current['files'], action['files']):
            return False
    return True


def retire(remote, current, index, old, *, store):
    """@cc [owner:fontanierh,label:correctness] newest-private-checkpoint-retention
    An older checkpoint release MAY retire only after the new completed index and every pack
    it references are freshly verified. Every older release owning pack assets MUST be rehomed
    as immutable pack storage without changing its numeric ID, even when this index does not
    reference those bytes: another machine may be publishing a reference. Pack deletion requires
    separate global coordination. All historical certified actions and pinned
    checkpoint descriptors MUST remain reachable. Drafts, unknown metadata, other games/repos
    and public releases MUST NOT be deleted. Failure MUST preserve the new usable checkpoint.
    """
    if pin_keys(store, remote) - ({index['key']} | set(index.get('retained', {}))):
        raise CheckpointError('Live checkpoint pin lacks complete descriptor; old metadata preserved')
    if not covers(index, old, store, remote):
        raise CheckpointError('Completed index lacks historical results or current pins; older checkpoints preserved')
    # Observe the published completion again, rather than trusting the preceding PATCH response.
    fresh = remote.github.read(f'releases/{current["id"]}')
    if fresh.get('draft') is not False or fresh.get('tag_name') != current['tag_name']:
        raise CheckpointError('New checkpoint publication is not yet observable')
    with tempfile.TemporaryDirectory() as directory:
        if remote.descriptor(fresh, Path(directory)) != index:
            raise CheckpointError('Published checkpoint completion changed; older checkpoints preserved')
    verify(remote, index)
    for item, descriptor in old:
        if item['id'] == current['id']:
            continue
        fresh = remote.github.read(f'releases/{item["id"]}')
        body = f'Build checkpoint {descriptor["key"]}\nSource {descriptor.get("source_revision")}\nRetain this release: later checkpoints may reference its packs.'
        if (fresh.get('draft') is not False or fresh.get('tag_name') != item['tag_name']
                or not fresh.get('tag_name', '').startswith(remote.prefix) or fresh.get('body') != body):
            raise CheckpointError('Older checkpoint metadata changed; retained without deletion')
        assets = release.asset_map(remote.github, item)
        if any(name.startswith('pack-') for name in assets):
            tag = remote.game + '-cache-packs-retained-' + str(item['id'])
            remote.github.api(f'releases/{item["id"]}', method='PATCH', data=dict(
                tag_name=tag, name=tag, body=VAULT_BODY))
            # The numeric release and pack assets stay intact; the newest index carries all
            # retained descriptors/action history. Remove only its superseded completion asset.
            completion = assets.get('checkpoint.json')
            if completion:
                try:
                    remote.github.api(f'releases/assets/{completion["id"]}', method='DELETE')
                except BaseException:
                    remote._checkpoint_mutation_uncertain = True
                    raise
        else:
            try:
                remote.github.api(f'releases/{item["id"]}', method='DELETE')
            except BaseException:
                remote._checkpoint_mutation_uncertain = True
                raise
    # Detect unexpected external pack mutations after rehoming before reporting success.
    verify(remote, index)


def history_locations(actions, known):
    result = {}
    for action in actions.values():
        for entry in action['files'].values():
            if entry['kind'] == 'file':
                if entry['sha256'] not in known:
                    raise CheckpointError('Historical action has no verified blob location')
                result[entry['sha256']] = known[entry['sha256']]
    return result


def consolidate(remote, store, directory):
    """Publish a new immutable metadata index when history or live pin roots change."""
    from .checkpoint_github import INDEX
    from .checkpoint_store import canonical, MAX_MANIFEST
    from .build_products import file_digest
    candidates = remote.candidates()
    if not candidates:
        raise CheckpointError('No completed checkpoint observed for consolidation')
    current = candidates[0]
    prior = remote.descriptor(current, directory)
    actions, known, retained, old = accumulate(remote, store, prior['checkpoint'], directory)
    retained.pop(prior['key'], None)  # The primary workspace already carries its complete descriptor.
    missing = pin_keys(store, remote) - ({prior['key']} | set(retained))
    if missing:
        raise CheckpointError('Live checkpoint pin has no complete verified descriptor: ' + ', '.join(sorted(missing)))
    data = dict(schema=1, key=prior['key'], source_revision=prior['source_revision'],
                checkpoint=prior['checkpoint'], blobs=prior['blobs'],
                history=dict(actions=actions, blobs=history_locations(actions, known)), retained=retained)
    if data != prior:
        if len(canonical(data)) > MAX_MANIFEST:
            raise CheckpointError('Consolidated checkpoint exceeds its metadata bound')
        tag = remote.prefix + 'index-' + identity(data)
        body = f'Build checkpoint {data["key"]}\nSource {data["source_revision"]}\nRetain this release: later checkpoints may reference its packs.'
        expected = dict(tag_name=tag, name=tag, body=body, prerelease=False, target_commitish=remote.default_branch)
        selected = release.find_release(remote.github, tag)
        if selected is None:
            selected = remote.github.api('releases', method='POST', data=dict(**expected, draft=True))
        release.check_release(selected, expected)
        assets = release.asset_map(remote.github, selected)
        if INDEX in assets:
            if remote.descriptor(selected, directory) != data:
                raise CheckpointError('Existing consolidated completion differs; previous metadata preserved')
        else:
            if not selected['draft']:
                raise CheckpointError('Published consolidated checkpoint has no completion')
            verify(remote, data)
            index = directory / INDEX; index.write_bytes(canonical(data))
            release.ensure_asset(remote.github, selected, index, file_digest(index))
        if selected['draft']:
            try:
                remote.github.api(f'releases/{selected["id"]}', method='PATCH', data=dict(draft=False))
            except BaseException:
                # A delayed completion must not become visible after another owner
                # retires the seed packs. Preserve exclusion until its outcome resolves.
                remote._checkpoint_mutation_uncertain = True
                raise
        current = selected
    retire(remote, current, data, old, store=store)
    return current, data
