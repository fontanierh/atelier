"""Retire unreferenced private pack assets after a verified checkpoint save."""
from . import checkpoint_archive as archive, checkpoint_pins as pins, release
from .checkpoint_store import CheckpointError, HEX


def collect(remote, current, index):
    """@cc [owner:fontanierh,label:safety] collect-only-unreferenced-private-packs
    Collection MUST hold the cross-machine writer claim excluding every publisher and reader.
    The newest completed index and all explicit live pins MUST remain readable. Pin expiry MUST
    use GitHub UTC and malformed evidence MUST abort deletion. A whole pack stays if any live
    range uses it. Only owned game-cache assets MAY retire. Freed bytes MUST count only remotely
    observed deletion; public releases and other repositories MUST never be changed.
    """
    if not getattr(remote, '_transaction_active', False):
        raise CheckpointError('Private collection requires exclusive writer ownership')
    archive.verify(remote, index)
    references = archive.references(index)
    live = pins.live(remote)
    checkpoints = {key for value in live.values() for key in value.get('checkpoints', [])}
    publications = [v['publication'] for v in live.values() if 'publication' in v]
    resolved = {index['key'], *index.get('retained', {})}
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        for item in remote.candidates():
            descriptor = remote.descriptor(item, Path(directory))
            if descriptor['key'] in checkpoints:
                resolved.add(descriptor['key'])
                archive.verify(remote, descriptor)
                for number, packs in archive.references(descriptor).items():
                    references.setdefault(number, {}).update(packs)
    unresolved = checkpoints - resolved
    if unresolved:
        raise CheckpointError('Live checkpoint pin cannot be resolved: ' + ', '.join(sorted(unresolved)))
    freed = removed = 0
    for page in remote.github.read('releases?per_page=100', pages=True):
        for item in page:
            tag = item.get('tag_name', '')
            storage = tag.startswith(remote.game + '-cache-packs-') and item.get('body') == 'Immutable build cache packs; retain while referenced by a checkpoint index.'
            checkpoint = tag.startswith(remote.prefix) and item.get('body', '').startswith('Build checkpoint ')
            if not storage and not checkpoint:
                continue
            # Pins cover incomplete captures too, before a completion INDEX exists.
            protected = any(tag == remote.prefix + p['tag'] or tag.startswith(remote.game + '-cache-packs-' + p['key'][:24] + '-')
                            for p in publications)
            if checkpoint and any(item.get('body', '').startswith('Build checkpoint ' + key + '\n') for key in checkpoints - resolved):
                protected = True
            if storage and any(tag.startswith(remote.game + '-cache-packs-' + key[:24] + '-') for key in checkpoints - resolved):
                protected = True
            assets = release.asset_map(remote.github, item)
            if any(name != 'checkpoint.json' and not name.startswith('pack-') for name in assets):
                raise CheckpointError('Unknown cache storage assets; deletion refused')
            if not protected:
                for name, asset in assets.items():
                    if not name.startswith('pack-') or name[5:-4] in references.get(item['id'], {}):
                        continue
                    starter = asset.get('state') == 'starter' and asset.get('size') == 0 and asset.get('digest') is None
                    if (not name.endswith('.bin') or not HEX.fullmatch(name[5:-4])
                            or (not starter and asset.get('digest') != 'sha256:' + name[5:-4])
                            or type(asset.get('size')) is not int or asset['size'] < 0):
                        raise CheckpointError('Invalid owned pack identity; deletion refused')
                    try:
                        remote.github.api(f'releases/assets/{asset["id"]}', method='DELETE')
                        if name in release.asset_map(remote.github, item):
                            raise CheckpointError('Pack deletion is not observable; cleanup remains pending')
                    except BaseException:
                        # A timed-out server DELETE may still commit after client exit.
                        # Do not allow another owner to reuse the still-visible asset.
                        remote._checkpoint_mutation_uncertain = True
                        raise
                    freed += asset['size']; removed += 1
            remaining = release.asset_map(remote.github, item)
            if not remaining and item['id'] != current['id'] and not protected:
                try:
                    remote.github.api(f'releases/{item["id"]}', method='DELETE')
                except BaseException:
                    remote._checkpoint_mutation_uncertain = True
                    raise
    remote.echo(f'private cache cleanup: {removed} packs removed, {freed} bytes freed (remote confirmation)')
    return dict(removed_packs=removed, freed_bytes=freed)
