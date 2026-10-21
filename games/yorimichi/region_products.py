"""Independent consumed views of a region's model library and runtime records.

The producer can remain monolithic while consumers use the exact part they read.
These views inventory real source membership and bytes; they never certify native packages.
"""
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


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


def paths(value, suffixes):
    if isinstance(value, dict):
        return set().union(*(paths(item, suffixes) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(paths(item, suffixes) for item in value)) if value else set()
    return {value} if isinstance(value, str) and PurePosixPath(value).suffix.lower() in suffixes else set()


def group_view(group):
    return {key: group[key] for key in ('asset', 'plant', 'transforms')}


def views(folder, *, ground_prefix, plant_prefix):
    """@cc [owner:fontanierh,label:correctness] independent-region-consumed-views
    Geometry/material views MUST include complete consumed model/texture membership and actual
    bytes. Runtime placements MUST NOT enter geometry identity. Clearance MUST retain all
    non-plant placements and geometry currently read by the probe; ground, origin and real
    collision/footprint changes MUST invalidate those consumers. Missing/deleted source members
    MUST fail rather than preserve an old identity. Map foliage placements remain real map reads.
    """
    report = json.loads(source(folder, 'build-report.json').read_text())
    runtime = json.loads(source(folder, 'runtime.json').read_text())
    meshes = sorted(report['meshes'], key=lambda value: value['name'])
    names = {mesh['name']: mesh for mesh in meshes}
    if len(names) != len(meshes) or not names:
        raise ValueError('Region model inventory is empty or has duplicate owners')
    model_files = paths(meshes, {'.glb', '.fbx'})
    actual_models = {p.relative_to(folder).as_posix() for p in (folder / 'glb').rglob('*') if p.is_file()}
    if model_files != actual_models:
        raise ValueError('Region model inventory differs from generated membership')
    model_inventory = {name: file_record(folder, name) for name in sorted(model_files)}
    for mesh in meshes:
        if mesh['sha256'] != model_inventory[mesh['path']]['sha256']:
            raise ValueError('Region model differs from its producer report: ' + mesh['name'])
    texture_names = {entry['texture'] for entry in report['materials'].values() if entry['texture']}
    for entry in report['materials'].values():
        texture_names.update(value for field in ('layers', 'normals')
                             for value in entry.get(field, {}).values() if value)
    textures = {'textures/' + name for name in texture_names}
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
        geometry=dict(schema=1, meshes=meshes, files=model_inventory),
        materials=dict(schema=1, materials=report['materials'],
                       files={name: file_record(folder, name) for name in sorted(textures)}),
        runtime=runtime,
        map=dict(schema=1, **boundary, zones=runtime['zones'], groups=plant_groups, meshes=ground),
        clearance=dict(schema=1, origin_cm=runtime['origin_cm'], groups=solid_groups, meshes=clearance_meshes),
    )


def publish(folder, destination, *, ground_prefix, plant_prefix):
    result = views(Path(folder), ground_prefix=ground_prefix, plant_prefix=plant_prefix)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in result.items():
        (destination / (name + '.json')).write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    print('REGION PRODUCTS COMPLETE: geometry, materials, runtime, map and clearance', flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) != 6 or args[2] != '--ground-prefix' or args[4] != '--plant-prefix':
        raise ValueError('Expected FOLDER DESTINATION --ground-prefix PREFIX --plant-prefix PREFIX')
    publish(Path(args[0]), Path(args[1]), ground_prefix=args[3], plant_prefix=args[5])
