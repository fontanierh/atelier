"""Independent consumed views of a region's model library and runtime records.

The producer can remain monolithic while consumers use the exact part they read.
These views inventory real source membership and bytes; they never certify native packages.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from atelier.model_files import member, source_records, regular_files


def source(root, member):
    if not isinstance(member, str) or not member or '\\' in member:
        raise ValueError('Region source must be a canonical relative member')
    name = PurePosixPath(member)
    if (name.is_absolute()
            or name.as_posix() != member or any(p in ('.', '..') for p in name.parts)):
        raise ValueError('Region source must be a canonical relative member')
    path = root / member
    parents = [root.joinpath(*name.parts[:i]) for i in range(1, len(name.parts))]
    if any(p.is_symlink() for p in [path, *parents]) or not path.is_file():
        raise ValueError('Region source is absent or linked: ' + member)
    return path


def file_record(root, member):
    path = source(root, member)
    raw = path.read_bytes()
    return dict(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))


def texture_members(report):
    names = {entry['texture'] for entry in report['materials'].values() if entry['texture']}
    for entry in report['materials'].values():
        names.update(value for field in ('layers', 'normals')
                     for value in entry.get(field, {}).values() if isinstance(value, str) and value)
    return sorted({member('textures/' + name) for name in names})


def texture_files(folder, report, inventory):
    """@cc [owner:fontanierh,label:correctness] exact-selected-texture-snapshot
    A supplied snapshot MUST come from the ordinary selected-byte action and match the
    current report's exact selected membership with valid complete byte records. The
    projection MUST NOT reopen undeclared texture files when consuming that snapshot.
    Direct programmatic views without a snapshot MUST read the selected actual files.
    """
    selected = texture_members(report)
    if inventory is None:
        return {name: file_record(folder, name) for name in selected}
    inventory = Path(inventory)
    snapshot = json.loads(source(inventory.parent, inventory.name).read_text())
    if (not isinstance(snapshot, dict) or type(snapshot.get('schema')) is not int or snapshot['schema'] != 1
            or set(snapshot) != {'schema', 'files'} or not isinstance(snapshot['files'], dict)
            or set(snapshot['files']) != set(selected)):
        raise ValueError('Region texture snapshot membership differs from the current report')
    for record in snapshot['files'].values():
        if (not isinstance(record, dict) or set(record) != {'sha256', 'size'}
                or type(record['size']) is not int or record['size'] < 0
                or not isinstance(record['sha256'], str) or len(record['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in record['sha256'])):
            raise ValueError('Invalid region texture byte inventory')
    return snapshot['files']


def group_view(group):
    return {key: group[key] for key in ('asset', 'plant', 'transforms')}


def library_views(folder, *, collision_basename=False, bindings=False, preserve_mesh_order=False, texture_inventory=None):
    """@cc [owner:fontanierh,label:correctness] complete-region-library-views
    Library identities MUST bind every consumed mesh, collision source, texture and material
    binding. Instance transforms and unused runtime fields MUST NOT enter model identities.
    Collision relocation MUST match the importer's declared basename mapping and verify its
    actual bytes. Required default bindings MUST retain the first non-plant group per model.
    """
    report = json.loads(source(folder, 'build-report.json').read_text())
    runtime = json.loads(source(folder, 'runtime.json').read_text())
    meshes = list(report['meshes']) if preserve_mesh_order else sorted(report['meshes'], key=lambda value: value['name'])
    names = {mesh['name']: mesh for mesh in meshes}
    if len(names) != len(meshes) or not names:
        raise ValueError('Region model inventory is empty or has duplicate owners')
    records = source_records(meshes, collision_directory='glb' if collision_basename else None)
    model_files = {name for _, name in records}
    actual_models = {'glb/' + name for name in regular_files(folder / 'glb')}
    if model_files != actual_models:
        raise ValueError('Region model inventory differs from generated membership')
    model_inventory = {name: file_record(folder, name) for name in sorted(model_files)}
    for entry, member in records:
        if entry['sha256'] != model_inventory[member]['sha256']:
            raise ValueError('Region model differs from its producer report: ' + member)
    materials = dict(schema=1, materials=report['materials'],
                     files=texture_files(folder, report, texture_inventory))
    if bindings:
        defaults = {}
        for group in runtime['groups']:
            if not group['plant']:
                defaults.setdefault(group['asset'].split('.')[-1], group['materials'])
        if not names.keys() <= defaults.keys():
            raise ValueError('Region model is missing its required material bindings')
        materials['bindings'] = {name: defaults[name] for name in sorted(names)}
    return dict(geometry=dict(schema=1, meshes=meshes, files=model_inventory),
                materials=materials, runtime=runtime)


def views(folder, *, ground_prefix, plant_prefix, texture_inventory=None):
    """@cc [owner:fontanierh,label:correctness] independent-region-consumed-views
    Geometry/material views MUST include complete consumed model/texture membership and actual
    bytes. Runtime placements MUST NOT enter geometry identity. Clearance MUST retain all
    non-plant placements and geometry currently read by the probe; ground, origin and real
    collision/footprint changes MUST invalidate those consumers. Missing/deleted source members
    MUST fail rather than preserve an old identity. Map foliage placements remain real map reads.
    """
    library = library_views(folder, texture_inventory=texture_inventory)
    meshes, runtime = library['geometry']['meshes'], library['runtime']
    groups = runtime['groups']
    plant_groups = [group_view(group) for group in groups
                    if group['asset'].rsplit('.', 1)[-1].startswith(plant_prefix)]
    solid_groups = [group_view(group) for group in groups if not group['plant']]
    solid_names = {group['asset'].rsplit('.', 1)[-1] for group in solid_groups}
    ground = [{key: mesh[key] for key in ('name', 'path', 'sha256', 'bounds_m')}
              for mesh in meshes if mesh['name'].startswith(ground_prefix)]
    if not ground:
        raise ValueError('Region has no final exported ground')
    # Probe code reads every non-plant placement, including non-colliding decorative solids.
    # Keep their placement, mesh bounds and actual model bytes; exclude material bindings only.
    clearance_meshes = [{key: mesh[key] for key in ('name', 'path', 'sha256', 'bounds_m')}
                       for mesh in meshes if mesh['name'] in solid_names]
    boundary = {key: runtime[key] for key in ('origin_cm', 'bounds_m', 'clearance_m')}
    return dict(
        geometry=library['geometry'], materials=library['materials'],
        runtime=runtime,
        map=dict(schema=1, **boundary, zones=runtime['zones'], groups=plant_groups, meshes=ground),
        clearance=dict(schema=1, origin_cm=runtime['origin_cm'], groups=solid_groups, meshes=clearance_meshes),
    )


def publish(folder, destination, *, ground_prefix, plant_prefix, texture_inventory=None):
    result = views(Path(folder), ground_prefix=ground_prefix, plant_prefix=plant_prefix,
                   texture_inventory=texture_inventory)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in result.items():
        (destination / (name + '.json')).write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    print('REGION PRODUCTS COMPLETE: geometry, materials, runtime, map and clearance', flush=True)


def publish_library(folder, destination, *, texture_inventory=None):
    result = library_views(Path(folder), collision_basename=True, bindings=True, preserve_mesh_order=True,
                           texture_inventory=texture_inventory)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in result.items():
        (destination / (name + '.json')).write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    print('REGION LIBRARY COMPLETE: geometry, materials and runtime', flush=True)


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    if len(args) < 4 or args[-2] != '--texture-inventory':
        raise ValueError('Expected a report-selected --texture-inventory path')
    inventory = Path(args[-1]); args = args[:-2]
    if len(args) == 3 and args[2] == '--mesh-library':
        publish_library(Path(args[0]), Path(args[1]), texture_inventory=inventory)
    elif len(args) == 6 and args[2] == '--ground-prefix' and args[4] == '--plant-prefix':
        publish(Path(args[0]), Path(args[1]), ground_prefix=args[3], plant_prefix=args[5],
                texture_inventory=inventory)
    else:
        raise ValueError('Expected a mesh library or both ground/plant prefixes')
