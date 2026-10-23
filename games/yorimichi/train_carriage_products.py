"""Current complete carriage source validation and file-only train library assembly."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import tomllib

from atelier import export_assembly
from atelier.atomic_files import atomic_json
from atelier.export_manifest import name, real_directory, sha, validate
from atelier.file_copy import copy_file
from atelier.model_files import member, regular_files, retain_files

GAME = Path(__file__).resolve().parent
sys.path.insert(0, str(GAME / 'world'))
from train.carriage_source import read  # noqa: E402
from train.carriage_mesh import glb  # noqa: E402
from train import budgets as B, textures as T  # noqa: E402

COACHES = ('locomotive', 'tender', 'baggage-van', 'restaurant', 'first-class', 'second-class', 'brake-van')


def fitted_sources():
    root = GAME / 'assets/vehicles/belmonte-train'
    manifest = tomllib.loads((root / 'source.toml').read_text())
    contract = json.loads((root / 'planning/furniture-dimensions.json').read_text())
    if manifest['version'] != 1 or set(manifest['assets']) != {asset['id'] for asset in contract['assets']}:
        raise ValueError('Current train furniture source/fit contract differs')
    result = {}
    for asset, row in manifest['assets'].items():
        for field, suffix, digest in [('path', 'glb', 'sha256'), ('report', 'json', 'report_sha256')]:
            if row[field] != f'furniture/{asset}.{suffix}': raise ValueError('Escaping registered fitted train source')
            result[f'{asset}.{suffix}'] = row[digest]
    return result


def source(folder, coach):
    folder = real_directory(folder)
    path = folder / 'source.json'
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing current coach source inventory')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('coach') != coach or value.get('complete') is not True
            or not value.get('files') or regular_files(folder) != set(value['files']) | {'source.json'}):
        raise ValueError('Incomplete or foreign current coach source')
    for relative, row in value['files'].items():
        path = folder / member(relative)
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']: raise ValueError('Changed coach source member')
    inventory = json.loads((folder / 'packets/inventory.json').read_text())
    placements = json.loads((folder / 'packets/placements.json').read_text())
    info = json.loads((folder / 'packets/info.json').read_text())
    if (inventory.get('schema') != 1 or inventory.get('coach') != coach or inventory.get('complete') is not True
            or info != value['info'] or info['layout_checks'] or inventory['mesh'] != info['mesh']):
        raise ValueError('Incomplete coach source/check census')
    mesh = info['mesh']; name(mesh)
    doors = {leaf['name']: 'SM_BTD_' + mesh.removeprefix('SM_BT_') + '_' +
             ''.join(c if c.isalnum() else '_' for c in leaf['name'].removeprefix('Door_'))
             for door in placements['doors'] for leaf in door['leaves']}
    expected = {f'{mesh}_LOD{k}' for k in (0, 1, 2)} | set(doors.values())
    rows = inventory['pieces']
    if (len(rows) != len(expected) or {row['name'] for row in rows} != expected or inventory['doors'] != doors
            or inventory['original_triangles'] != info['triangles']):
        raise ValueError('Incomplete authored coach LOD/door ownership')
    for row in rows:
        key = name(row['name'])
        if row['source'] != key + '.source': raise ValueError('Escaping coach mesh source')
        packet = folder / 'packets' / row['source']; data, _ = read(packet, key=key)
        if sha(packet) != row['sha256'] or data['triangles'] != row['triangles']: raise ValueError('Changed selected coach source packet')
    fitted = fitted_sources()
    expected_files = {'packets/inventory.json', 'packets/info.json', 'packets/placements.json',
                      *(f"packets/{row['source']}" for row in rows),
                      *(f'authoring/furniture/{label}' for label in fitted),
                      *(f'textures/{tex}.{"jpg" if tex in T.JPEG else "png"}' for tex in T.ALL)}
    if any(window['kind'] == 'clear' for window in placements['windows']):
        atlas = 'textures/T_BT_' + mesh.removeprefix('SM_BT_') + 'Interior'
        expected_files.update({atlas + '.png', atlas + '.json'})
    if set(value['files']) != expected_files:
        raise ValueError('Incomplete source atlas/texture/furniture/mesh membership')
    if any(value['files']['authoring/furniture/' + label]['sha256'] != digest for label, digest in fitted.items()):
        raise ValueError('Fitted source differs from the current signed source inventory')
    if any(info['triangles'][level] > cap for level, cap in B.SHELL.items()): raise ValueError('Original signed shell budget exceeded')
    return value, inventory, placements


def present(folder, coach):
    try: source(folder, coach); return True
    except (OSError, ValueError, KeyError, TypeError): return False


def copy(source, target, expected):
    """Copy one bound regular file and preserve a byte-identical target's mtime."""
    source, target = Path(source), Path(target)
    real_directory(source.parent); real_directory(target.parent, create=True)
    if source.is_symlink() or not source.is_file() or sha(source) != expected:
        raise ValueError('Changed source file before carriage assembly')
    if target.is_symlink() or (target.exists() and not target.is_file()): raise ValueError('Foreign carriage file target')
    if not target.exists() or sha(target) != expected:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.carriage-', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.unlink(); copy_file(source, temporary)
            if sha(temporary) != expected or sha(source) != expected: raise ValueError('Carriage copy source changed')
            temporary.replace(target)
        finally: temporary.unlink(missing_ok=True)
    if sha(source) != expected: raise ValueError('Carriage assembly source changed')


def members(folder):
    folder = real_directory(folder)
    return regular_files(folder) if folder.exists() else set()


def old_members(root, coaches, textures):
    """One complete foreign-reference/membership preflight before any assembly write."""
    previous = root / 'manifest.json'
    prior = json.loads(previous.read_text()) if previous.exists() else {}
    if prior and (prior.get('version') != 1 or set(prior.get('coaches', {})) != set(COACHES)
                  or not isinstance(prior.get('textures'), dict)):
        raise ValueError('Invalid previous complete train library inventory')
    for coach, info in prior.get('coaches', {}).items():
        if not isinstance(info.get('files'), dict) or any(member(label) != Path(label).name for label in info['files']):
            raise ValueError('Invalid previous owned coach inventory')
    for coach in COACHES:
        folder = root / coach
        allowed = set(coaches[coach]) | set(prior.get('coaches', {}).get(coach, {}).get('files', {}))
        if members(folder) - allowed: raise ValueError('Foreign existing coach library member')
    allowed = set(textures)
    for tex in prior.get('textures', {}): allowed.update({tex + '.jpg', tex + '.png'})
    for coach in prior.get('coaches', {}):
        mesh = prior['coaches'][coach]['mesh'].removeprefix('SM_BT_')
        allowed.update({'T_BT_' + mesh + 'Interior.png', 'T_BT_' + mesh + 'Interior.json'})
    if members(root / 'textures') - allowed: raise ValueError('Foreign existing train texture member')


def assemble(out):
    """@cc [owner:fontanierh,label:correctness;performance] complete-carriage-file-assembly
    Validate all seven source owners, every independent current primary and all prior
    owned destinations before writes. Preserve source bytes, authored LOD membership,
    material/texture bindings, doors/pivots/collision/seating/boarding/sockets and current
    runtime filenames. Each primary MUST match the exact current packet GLB encoding,
    including same-count attribute/material changes. Assembly MUST never construct, export
    or join geometry; obsolete
    authoring members may retire only after every current member is copied and checked.
    """
    out = Path(out); root = real_directory(out / 'belmonte-train')
    sources = {coach: source(out / 'belmonte-train-sources' / coach, coach) for coach in COACHES}
    items = []; exports = {}; coach_files = {}; textures = {}; fitted = {}; ready = {}
    common = {tex + ('.jpg' if tex in T.JPEG else '.png') for tex in T.ALL}
    for coach, (value, inventory, placements) in sources.items():
        folder = out / 'belmonte-train-sources' / coach; mesh = inventory['mesh']
        coach_files[coach] = {f'{mesh}_LOD{k}.glb' for k in (0, 1, 2)} | {coach + '-placements.json'}
        for row in inventory['pieces']:
            key = row['name']; product = out / 'exports/world.belmonte_train.export' / key
            receipt = validate(product, key=key)
            packet, binary = read(folder / 'packets' / row['source'], key=key)
            expected = hashlib.sha256(glb(packet['document'], binary)).hexdigest()
            if receipt['triangles'] != row['triangles'] or receipt['sha256'] != expected:
                raise ValueError('Carriage export differs from current source packet')
            items.append(export_assembly.Item(key, product)); exports[key] = receipt
        for relative, identity in value['files'].items():
            if relative.startswith('textures/'):
                label = Path(relative).name
                if label in common and label in textures and textures[label][1] != identity['sha256']:
                    raise ValueError('Shared original train texture differs between owners')
                textures[label] = folder / relative, identity['sha256']
            elif relative.startswith('authoring/furniture/'):
                label = Path(relative).name
                if label in fitted and fitted[label][1] != identity['sha256']: raise ValueError('Verified furniture input differs between owners')
                fitted[label] = folder / relative, identity['sha256']
        levels = [dict(path=f'{coach}/{mesh}_LOD{k}.glb', sha256=exports[f'{mesh}_LOD{k}']['sha256']) for k in (0, 1, 2)]
        doors = {node: dict(asset=key, path='atomic/' + key + '.glb', sha256=exports[key]['sha256'])
                 for node, key in inventory['doors'].items()}
        ready[coach] = dict(mesh=mesh, levels=levels, doors=doors,
            placements_sha256=sha(folder / 'packets/placements.json'))
    if not common <= set(textures) or set(fitted) != set(fitted_sources()): raise ValueError('Incomplete original shared source/texture closure')
    from PIL import Image
    for path, _ in textures.values():
        if path.suffix.lower() not in ('.png', '.jpg'): continue
        with Image.open(path) as image:
            if not all(B.is_power_of_two(v) for v in image.size) or max(image.size) > 2048:
                raise ValueError('Original signed train texture budget exceeded')
    policies = sources[COACHES[0]][1]['policies']
    if any(inventory['policies'] != policies for _, inventory, _ in sources.values()):
        raise ValueError('Shared original train policy differs between owners')
    old_members(root, coach_files, textures)
    export_assembly.destination_members(root / 'atomic', {receipt['primary'] for receipt in exports.values()})
    # Preflight every owned direct destination before any copy.
    direct = [(path, root / 'textures' / label, digest) for label, (path, digest) in textures.items()]
    direct.extend((path, root / 'furniture' / label, digest) for label, (path, digest) in fitted.items())
    for coach in COACHES:
        folder = out / 'belmonte-train-sources' / coach
        direct.append((folder / 'packets/placements.json', root / coach / (coach + '-placements.json'),
                       ready[coach]['placements_sha256']))
        for row in ready[coach]['levels']:
            key = Path(row['path']).stem
            direct.append((out / 'exports/world.belmonte_train.export' / key / (key + '.glb'), root / row['path'], row['sha256']))
    for source_path, target, digest in direct:
        real_directory(target.parent)
        if target.is_symlink() or (target.exists() and not target.is_file()) or sha(source_path) != digest:
            raise ValueError('Foreign or changed carriage assembly input/target')
    export_assembly.assemble(items, root / 'atomic')
    for source_path, target, digest in direct: copy(source_path, target, digest)
    manifest = dict(policies, coaches={}, textures={})
    for coach, (value, _, _) in sources.items():
        info = dict(value['info'])
        info['files'] = {label: dict(bytes=(root / coach / label).stat().st_size, sha256=sha(root / coach / label))
                         for label in sorted(coach_files[coach])}
        manifest['coaches'][coach] = info
    for label in sorted(common):
        path = root / 'textures' / label
        manifest['textures'][path.stem] = dict(bytes=path.stat().st_size, sha256=sha(path))
    atomic_json(root / 'service-meshes.json', dict(schema=1, complete=True, coaches=ready,
        atomic_manifest_sha256=sha(root / 'atomic/manifest.json')))
    atomic_json(root / 'manifest.json', manifest)
    for coach in COACHES: retain_files(root / coach, coach_files[coach])
    retain_files(root / 'textures', textures)
    for coach in COACHES: source(out / 'belmonte-train-sources' / coach, coach)
    return manifest
