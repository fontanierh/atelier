"""File-only service assembly from a complete current bounded train library."""
import json
from pathlib import Path
import tempfile

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory, sha, name
from atelier.file_copy import copy_file
from atelier.model_files import member, regular_files, retain_files
from atelier.gltf import glb_parts
from train.carriage_mesh import geometry


def copy_to_service(root, train, folder, library):
    """@cc [owner:fontanierh,label:correctness;performance] current-bounded-train-service-library
    Production service assembly MUST consume the explicit complete current library,
    validate every body/door/LOD byte binding and destination before writes, and copy
    only. Never rediscover doors from stripped bodies or silently fall back to an old
    combined export. Preserve every existing runtime filename, leaf identity and the
    original closed LOD2. Retire only previously declared owned service files after
    every current primary has copied and revalidated.
    """
    root, folder = real_directory(root), real_directory(folder)
    if not folder.is_relative_to(root): raise ValueError('Bounded train service output must remain within its library root')
    library = Path(library); real_directory(library.parent)
    if library.is_symlink() or not library.is_file(): raise ValueError('Missing current bounded train library')
    raw = library.read_bytes(); value = json.loads(raw)
    if (value.get('schema') != 1 or value.get('complete') is not True
            or set(value.get('coaches', {})) != {v['id'] for v in train['vehicles']}):
        raise ValueError('Incomplete current bounded train library')
    manifest_path = root / 'atomic/manifest.json'
    real_directory(manifest_path.parent)
    if manifest_path.is_symlink() or sha(manifest_path) != value['atomic_manifest_sha256']:
        raise ValueError('Changed atomic train library inventory')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != 1 or manifest.get('complete') is not True: raise ValueError('Incomplete atomic train library')
    receipts = {row['asset']: row for row in manifest['exports']}
    if len(receipts) != len(manifest['exports']): raise ValueError('Aliased train library primaries')
    seen = set(); copies = []; updates = []; expected = set()
    def primary(key, digest):
        key = name(key); row = receipts[key]; source = root / 'atomic' / (key + '.glb')
        if (row['primary'] != key + '.glb' or row['sha256'] != digest or sha(source) != digest
                or not source.stat().st_size): raise ValueError('Changed bounded train primary')
        actual = geometry(*glb_parts(source.read_bytes()))
        if (row.get('schema') != 1 or actual['triangles'] != row['triangles'] or actual['bounds'] != row['bounds']
                or actual['slots'] != row['metadata']['slots'] or digest != row['metadata']['geometry_sha256']):
            raise ValueError('Current train primary differs from bounded source geometry')
        seen.add(key)
        return source
    for vehicle in train['vehicles']:
        entry = value['coaches'][vehicle['id']]; mesh = name(vehicle['name'])
        placements = root / vehicle['id'] / (vehicle['id'] + '-placements.json')
        real_directory(placements.parent)
        if entry['mesh'] != mesh or sha(placements) != entry['placements_sha256'] or len(entry['levels']) != 3:
            raise ValueError('Changed coach source/placement binding')
        levels = []
        for level, row in enumerate(entry['levels']):
            key = f'{mesh}_LOD{level}'; relative = f'{vehicle["id"]}/{key}.glb'
            source = primary(key, row['sha256'])
            if row['path'] != relative or sha(root / member(relative)) != row['sha256']:
                raise ValueError('Changed authored train LOD file')
            if level == 2: levels.append(relative); continue
            target = folder / (key + '.glb'); expected.add(target.relative_to(folder).as_posix())
            copies.append((source, target, row['sha256'])); levels.append(target.relative_to(root).as_posix())
        leaves = [leaf for door in vehicle['doors'] for leaf in door['leaves']]
        if set(entry['doors']) != {leaf['node'] for leaf in leaves}: raise ValueError('Current moving-door source membership differs')
        leaf_updates = []
        for leaf in leaves:
            row = entry['doors'][leaf['node']]
            key = name(leaf['mesh'].rsplit('/', 1)[1].split('.')[0])
            if row['asset'] != key or row['path'] != 'atomic/' + key + '.glb': raise ValueError('Changed moving-door identity/frame')
            source = primary(key, row['sha256']); target = folder / 'doors' / (key + '.glb')
            expected.add(target.relative_to(folder).as_posix()); copies.append((source, target, row['sha256']))
            leaf_updates.append((leaf, target.relative_to(root).as_posix()))
        updates.append((vehicle, levels, leaf_updates))
    if seen != set(receipts) or regular_files(root / 'atomic') != {'manifest.json', *(key + '.glb' for key in seen)}:
        raise ValueError('Foreign or incomplete train library membership')
    previous = folder / 'source-manifest.json'; owned = set(expected)
    if previous.exists():
        old = json.loads(previous.read_text())
        if old.get('schema') != 1 or old.get('complete') is not True: raise ValueError('Invalid previous service file inventory')
        owned.update(member(item) for item in old['files'])
    elif (root / 'service/service.json').is_file():
        old = json.loads((root / 'service/service.json').read_text())
        for vehicle in old.get('consist', {}).get('vehicles', []):
            paths = [*vehicle.get('levels', []), *(leaf.get('glb') for door in vehicle.get('doors', []) for leaf in door['leaves'])]
            for relative in paths:
                if not relative: continue
                source = root / member(relative)
                if source.is_relative_to(folder): owned.add(source.relative_to(folder).as_posix())
    actual = regular_files(folder) if folder.exists() else set()
    if actual - owned - {'source-manifest.json'}: raise ValueError('Foreign existing train service file')
    for source, target, digest in copies:
        real_directory(target.parent)
        if target.is_symlink() or (target.exists() and not target.is_file()) or sha(source) != digest:
            raise ValueError('Foreign or changed train service target/source')
    for source, target, digest in copies:
        real_directory(target.parent, create=True)
        if target.exists() and sha(target) == digest: continue
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.service-', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.unlink(); copy_file(source, temporary)
            if sha(temporary) != digest or sha(source) != digest: raise ValueError('Train source changed during service copy')
            temporary.replace(target)
        finally: temporary.unlink(missing_ok=True)
    if library.read_bytes() != raw: raise ValueError('Train library changed during service assembly')
    for source, target, digest in copies:
        if sha(source) != digest or sha(target) != digest: raise ValueError('Train service member changed before publication')
    atomic_json(previous, dict(schema=1, complete=True, library_sha256=sha(library),
        files={target.relative_to(folder).as_posix(): digest for _, target, digest in copies}))
    retain_files(folder, [*expected, 'source-manifest.json'])
    for vehicle, levels, leaves in updates:
        vehicle['levels'] = levels
        for leaf, relative in leaves: leaf['glb'] = relative
