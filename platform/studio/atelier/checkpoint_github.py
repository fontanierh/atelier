"""Private GitHub Release storage for immutable, deduplicated build checkpoints.

Packed blobs are bounded below GitHub's per-asset limit. A checkpoint directly names every
pack it needs, including packs rehomed in immutable storage releases; restoring never replays a delta chain.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

from . import build_products, release
from .checkpoint_store import CheckpointError, HEX, MAX_BYTES, MAX_MANIFEST, canonical, identity, read_json, validate

PACK_BYTES = 128 * 1024**2
INDEX = 'checkpoint.json'


class Remote:
    def __init__(self, repository, game, *, github=None, echo=print):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise CheckpointError('Checkpoint repository must be OWNER/REPOSITORY')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', game):
            raise CheckpointError('Invalid checkpoint game name')
        self.repository, self.game, self.echo = repository, game, echo
        self.github = github or release.GitHub(repository, threading.Event())
        self.prefix = game + '-checkpoint-'

    def require_private(self):
        metadata = self.github.read('')
        if metadata.get('private') is not True:
            raise CheckpointError('Build checkpoints require the configured private repository; no public upload allowed')
        return metadata

    def download(self, asset, destination):
        """Stream authenticated downloads without printing URLs, tokens or response bodies."""
        if (type(asset.get('id')) is not int or asset['id'] <= 0
                or not isinstance(asset.get('digest'), str) or not asset['digest'].startswith('sha256:')
                or not HEX.fullmatch(asset['digest'][7:])
                or type(asset.get('size')) is not int or not 0 <= asset['size'] <= PACK_BYTES + MAX_MANIFEST):
            raise CheckpointError('Invalid GitHub checkpoint asset identity')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('wb') as output, tempfile.TemporaryFile() as errors:
            command = ['gh', 'api', f'repos/{self.repository}/releases/assets/{asset["id"]}',
                       '--hostname', 'github.com', '--header', 'Accept: application/octet-stream']
            child = subprocess.Popen(command, stdout=output, stderr=errors, stdin=subprocess.DEVNULL)
            deadline, spoken = time.monotonic() + 600, time.monotonic()
            try:
                while child.poll() is None:
                    if self.github.stop.wait(.25) or time.monotonic() >= deadline:
                        raise CheckpointError('Checkpoint download interrupted or timed out; rerun the build')
                    if time.monotonic() - spoken >= 25:
                        self.echo(f'checkpoint download: {destination.stat().st_size / 2**20:.0f} MiB received')
                        spoken = time.monotonic()
                if child.returncode:
                    raise CheckpointError('Checkpoint download failed; check gh authentication and repository access')
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill(); child.wait(timeout=3)
        if (destination.stat().st_size != asset['size']
                or build_products.file_digest(destination) != asset['digest'][7:]):
            destination.unlink(missing_ok=True)
            raise CheckpointError('Checkpoint download checksum differs')

    def candidates(self):
        self.require_private()
        pages = self.github.read('releases?per_page=100', pages=True)
        releases = [r for page in pages for r in page
                    if not r.get('draft') and r.get('tag_name', '').startswith(self.prefix)]
        return sorted(releases, key=lambda r: r.get('published_at', ''), reverse=True)

    def descriptor(self, item, directory):
        assets = release.asset_map(self.github, item)
        if INDEX not in assets or assets[INDEX]['size'] > MAX_MANIFEST:
            raise CheckpointError('Published checkpoint has no bounded completion manifest')
        path = directory / INDEX
        self.download(assets[INDEX], path)
        data = read_json(path)
        manifest = data.get('checkpoint')
        validate(manifest, self.game)
        if data.get('key') != identity(manifest) or type(data.get('blobs')) is not dict:
            raise CheckpointError('Checkpoint index identity differs')
        return data

    def fetch(self, item, descriptor, store, *, save=True):
        """@cc [owner:fontanierh,label:security] verified-private-checkpoint-download
        Only the configured authenticated private repository MAY supply checkpoint data. Every
        pack and unpacked blob MUST match its declared length and digest before store publication.
        A release's final manifest is its completion marker; partial drafts MUST NOT be restored.
        """
        validate(descriptor['checkpoint'], self.game)
        needed = blob_inventory(descriptor['checkpoint'], store)
        if set(descriptor['blobs']) != set(needed):
            raise CheckpointError('Checkpoint blob inventory differs')
        packs, total, missing = {}, 0, set()
        for digest, size in needed.items():
            blob = store.blob(digest)
            if blob.is_file() and not blob.is_symlink() and blob.stat().st_size == size and build_products.file_digest(blob) == digest:
                continue
            parts = descriptor['blobs'][digest]
            missing.add(digest)
            if not isinstance(parts, list) or not parts or len(parts) > MAX_BYTES // min(25 * 1024**2, PACK_BYTES) + 1:
                raise CheckpointError('Invalid checkpoint blob parts')
            observed = 0
            for part in parts:
                if (type(part) is not dict or type(part.get('release')) is not int or part['release'] <= 0
                        or not HEX.fullmatch(part.get('pack', '')) or type(part.get('offset')) is not int
                        or type(part.get('size')) is not int or not 0 <= part['offset'] <= PACK_BYTES
                        or not 0 <= part['size'] <= PACK_BYTES - part['offset']):
                    raise CheckpointError('Invalid checkpoint pack range')
                packs[(part['release'], part['pack'])] = None
                observed += part['size']
            if observed != size:
                raise CheckpointError('Checkpoint blob size differs')
            total += size
        if len(packs) > 30000 or total > MAX_BYTES:
            raise CheckpointError('Checkpoint transfer exceeds its bounds')
        with tempfile.TemporaryDirectory(dir=store.directory) as temporary:
            directory = Path(temporary)
            assets_by_release = {}
            for release_id, digest in packs:
                if release_id not in assets_by_release:
                    assets_by_release[release_id] = release.asset_map(self.github, dict(id=release_id))
                asset = assets_by_release[release_id].get('pack-' + digest + '.bin')
                if asset is None or asset.get('digest') != 'sha256:' + digest or asset.get('size', PACK_BYTES + 1) > PACK_BYTES:
                    raise CheckpointError('Referenced checkpoint pack is missing or changed')
                target = directory / digest
                self.download(asset, target)
                packs[(release_id, digest)] = target
            for digest, size in needed.items():
                if digest not in missing:
                    continue
                target = directory / ('blob-' + digest)
                with target.open('wb') as output:
                    for part in descriptor['blobs'][digest]:
                        with packs[(part['release'], part['pack'])].open('rb') as source:
                            source.seek(part['offset'])
                            left = part['size']
                            while left:
                                block = source.read(min(left, 1024 * 1024))
                                if not block:
                                    raise CheckpointError('Checkpoint pack is truncated')
                                output.write(block); left -= len(block)
                if target.stat().st_size != size or build_products.file_digest(target) != digest:
                    raise CheckpointError('Unpacked checkpoint blob checksum differs')
                store.put(target, digest)
        if save:
            from .checkpoint_actions import install
            for action in descriptor['checkpoint'].get('actions', {}).values():
                install(store, action)
            return store.save(descriptor['checkpoint'])
        return None

    def publish(self, store, key, tag, *, revision, revalidate=lambda: None):
        """@cc [owner:fontanierh,label:correctness] release-checkpoint-completion
        A checkpoint release MUST be private, immutable by convention, and bound to its source
        revision and input manifest. Uploads MUST resume by verified digest without clobbering.
        The complete index MUST upload last. Publication MUST revalidate its retained manifest
        and captured source binding; a present captured revision MUST match the queued revision.
        An immutable capture MUST NOT depend on continued existence of its producing checkout.
        Newest-only retirement MUST preserve referenced packs, action history and retention pins.
        """
        from . import checkpoint_archive as archive, checkpoint_packs as packs
        with packs.writer(self):
            metadata = self.require_private()
            self.default_branch = metadata['default_branch']
            manifest = store.load(key)
            if manifest.get('source_revision', revision) != revision:
                raise CheckpointError('Captured checkpoint source differs from the publication request')
            tag = self.prefix + release.leaf(tag)
            body = f'Build checkpoint {key}\nSource {revision}\nRetain this release: later checkpoints may reference its packs.'
            expected = dict(tag_name=tag, name=tag, body=body, prerelease=False,
                            target_commitish=self.default_branch)
            found = release.find_release(self.github, tag)
            if found is None:
                found = self.github.api('releases', method='POST', data={**expected, 'draft': True})
            release.check_release(found, expected)
            with tempfile.TemporaryDirectory(dir=store.directory) as temporary:
                directory = Path(temporary)
                actions, known, retained, old = archive.accumulate(self, store, manifest, directory)
                if not found['draft']:
                    data = self.descriptor(found, directory)
                    if data['key'] != key:
                        raise CheckpointError('Checkpoint tag already describes different results')
                    archive.retire(self, found, data, old)
                    return data
                needed = blob_inventory(manifest, store)
                blobs = packs.pack(self, store, needed, known, directory, key, legacy=found)
                history = {}
                for action in actions.values():
                    for entry in action['files'].values():
                        if entry['kind'] == 'file':
                            digest = entry['sha256']
                            parts = blobs.get(digest, known.get(digest))
                            if parts is None:
                                raise CheckpointError('Retained action has no complete remote blob inventory')
                            history[digest] = parts
                data = dict(schema=1, key=key, source_revision=revision, checkpoint=manifest, blobs=blobs,
                            history=dict(actions=actions, blobs=history), retained=retained)
                if len(canonical(data)) > MAX_MANIFEST:
                    raise CheckpointError('Checkpoint history exceeds index size limit; previous checkpoints preserved')
                archive.verify(self, data)
                index = directory / INDEX
                index.write_bytes(canonical(data))
                revalidate()
                release.ensure_asset(self.github, found, index, build_products.file_digest(index))
                revalidate()
                self.github.api(f'releases/{found["id"]}', method='PATCH', data={'draft': False})
                archive.retire(self, found, data, old)
            self.echo(f'published private build checkpoint: {tag}')
            return data


def blob_inventory(manifest, store):
    from .checkpoint_actions import validate as validate_action
    files = list(manifest['files'].values())
    actions = manifest.get('actions', {})
    if type(actions) is not dict:
        raise CheckpointError('Invalid checkpoint action catalogue')
    for key, action in actions.items():
        validate_action(action, store, key)
        files.extend(action['files'].values())
    needed = {}
    for entry in files:
        if entry['kind'] != 'file':
            continue
        if entry['sha256'] in needed and needed[entry['sha256']] != entry['size']:
            raise CheckpointError('Conflicting checkpoint blob lengths')
        needed[entry['sha256']] = entry['size']
    return needed
