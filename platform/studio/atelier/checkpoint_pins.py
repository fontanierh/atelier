"""Remote explicit retention roots and durable releases, serialized by the private writer claim."""
import json
import re
import uuid

from . import release
from .checkpoint_store import CheckpointError, HEX, identity, read_json

RETRY_SECONDS = 7 * 86400


def clock(remote):
    value = remote.github.server_time()
    if type(value) not in (int, float) or not 0 < value < 1e12:
        raise CheckpointError('Invalid GitHub UTC; pin expiry cannot be determined')
    return value


def prefix(remote):
    return 'tags/atelier-cache-' + remote.game + '-pin-'


def valid(value, name):
    if (type(value) is not dict or value.get('schema') != 1 or value.get('id') != name
            or value.get('state') not in ('active', 'released')
            or not re.fullmatch('[A-Za-z0-9_-]{1,100}', name)):
        raise CheckpointError('Invalid remote retention pin; no pack deletion allowed')
    if value['state'] == 'released':
        if not isinstance(value.get('reason'), str) or not value['reason']:
            raise CheckpointError('Invalid pin release evidence')
        return value
    if (type(value.get('checkpoints', [])) is not list
            or any(not isinstance(key, str) or not HEX.fullmatch(key) for key in value.get('checkpoints', []))
            or not isinstance(value.get('release_when'), str) or not value['release_when']
            or ('expires' in value and (type(value['expires']) not in (int, float) or not 0 < value['expires'] < 1e12))):
        raise CheckpointError('Retention pins need a valid explicit release condition or expiry')
    publication = value.get('publication')
    if publication is not None and (type(publication) is not dict or not HEX.fullmatch(publication.get('key', ''))
                                    or not isinstance(publication.get('tag'), str)):
        raise CheckpointError('Invalid interrupted-publication pin')
    if publication:
        release.leaf(publication['tag'])
    return value


def all_records(remote):
    refs = remote.github.read('git/matching-refs/' + prefix(remote) + '?refresh=' + uuid.uuid4().hex)
    result = {}
    for ref in refs:
        name = ref['ref'].removeprefix('refs/' + prefix(remote))
        commit = remote.github.read('git/commits/' + ref['object']['sha'])
        try:
            value = json.loads(commit['message'])
        except (ValueError, KeyError, TypeError):
            raise CheckpointError('Unverifiable remote pin; no pack deletion allowed') from None
        result[name] = valid(value, name)
    return result


def put(remote, value, *, previous=None):
    if not getattr(remote, '_transaction_active', False):
        raise CheckpointError('Retention changes require the private writer claim')
    valid(value, value['id'])
    metadata = remote.require_private()
    base = remote.github.read('git/ref/heads/' + metadata['default_branch'])['object']['sha']
    tree = remote.github.read('git/commits/' + base)['tree']['sha']
    commit = remote.github.api('git/commits', method='POST', data=dict(tree=tree, parents=[base], message=json.dumps(value, sort_keys=True)))
    ref = prefix(remote) + value['id']
    if previous is None:
        remote.github.api('git/refs', method='POST', data=dict(ref='refs/' + ref, sha=commit['sha']))
    else:
        remote.github.api('git/refs/' + ref, method='PATCH', data=dict(sha=commit['sha'], force=True))


def live(remote):
    now = clock(remote)
    return {name: value for name, value in all_records(remote).items()
            if value['state'] == 'active' and value.get('expires', now + 1) > now}


def sync_local(remote, store):
    records = all_records(remote)
    for path in sorted(store.directory.glob('pins/*.json')):
        local = read_json(path)
        if type(local) is not dict:
            raise CheckpointError('Invalid local retention pin')
        value = dict(schema=1, id=path.stem, state='active', checkpoints=local.get('checkpoints', []),
                     release_when=local.get('release_when', local.get('reason', '')))
        if 'expires' in local:
            value['expires'] = local['expires']
        valid(value, path.stem)
        previous = records.get(path.stem)
        if previous and previous['state'] == 'released':
            continue  # An older machine cannot resurrect a deliberately released pin.
        if previous is not None and previous != value:
            raise CheckpointError('Local retention pin conflicts with published lifecycle')
        if previous is None:
            put(remote, value)


def upload(remote, key, tag):
    name = 'upload-' + identity([key, tag])[:24]
    previous = all_records(remote).get(name)
    value = dict(schema=1, id=name, state='active', checkpoints=[], publication=dict(key=key, tag=tag),
                 release_when='successful private publication or retry-window expiry',
                 expires=clock(remote) + RETRY_SECONDS)
    put(remote, value, previous=previous)
    return name


def release_pin(remote, name, reason):
    previous = all_records(remote).get(name)
    if previous is None:
        raise CheckpointError('Unknown remote retention pin')
    if previous['state'] == 'released':
        return
    value = dict(schema=1, id=name, state='released', reason=reason, released=clock(remote))
    put(remote, value, previous=previous)

