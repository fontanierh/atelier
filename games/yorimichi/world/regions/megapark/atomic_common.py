"""Park-specific metadata over the shared lossless bounded mesh planner.

The old native origin is retained for every child. Assembly copies independently
exported files; it never constructs geometry or changes riding/query surfaces.
"""
import json
from pathlib import Path

import numpy as np
from atelier import export_assembly, export_manifest, mesh_ir
from atelier.atomic_files import atomic_json
from atelier.model_files import regular_files

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
               axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='FACE',
               add_leaf_bones=False, path_mode='STRIP')


def capture(obj, entry, root, metadata, *, colours=False, materials=None):
    from region_mesh_parts import plan
    options = dict(OPTIONS, use_tspace=bool(obj.data.uv_layers))
    if colours:
        options['colors_type'] = 'SRGB'
    value = plan(obj, root, options=options)
    atomic_json(metadata, dict(schema=1, entry=entry, materials=materials or {}))
    return value


def entries(out, region, parents):
    """Validate complete source plans and separately exported primaries before publication."""
    from region_mesh_parts import validate
    result, items, extra = {}, [], {}
    for parent in parents:
        root = out / 'planned_exports' / region / parent
        plan = validate(root)
        info = json.loads((out / (region + '-data') / (parent + '.json')).read_text())
        if info.get('schema') != 1 or info['entry']['name'] != parent:
            raise ValueError('Foreign logical park metadata')
        source = info['entry']; group = []
        for row in plan['pieces']:
            key = row['name']
            product = out / 'exports' / ('world.' + region + '.export') / key
            receipt = export_manifest.validate(product, key=key)
            meta, piece = mesh_ir.decode((root / row['payload']).read_bytes())
            if (receipt['triangles'] != row['triangles'] or
                    receipt['metadata']['geometry_sha256'] != row['sha256']):
                raise ValueError('Export differs from current logical park input')
            # Matrix is identity: original exporters keep the stable pivot in park.json.
            if not np.array_equal(meta['matrix'], np.eye(4)):
                raise ValueError('Unexpected park local-frame transform')
            vertices = piece['positions'][:, [0, 2, 1]].astype('f8')
            vertices[:, 2] *= -1
            vertices += np.asarray(source['native_origin'])
            entry = dict(source, name=key, logical_parent=parent, source_faces=row['source_faces'], fbx='fbx/' + receipt['primary'],
                         sha256=receipt['sha256'], vertices=len(vertices), triangles=row['triangles'],
                         bounds=dict(minimum=vertices.min(0).tolist(), maximum=vertices.max(0).tolist()))
            # A spatial child can omit a source material without changing its parent's grouping.
            entry['materials'] = [slot for i, slot in enumerate(meta['slots']) if i in set(piece['materials'])]
            group.append(entry); items.append(export_assembly.Item(key, product))
        result[parent] = group
        extra.update(info.get('materials', {}))
    return result, items, extra


def assemble_files(out, region, parents):
    groups, items, materials = entries(out, region, parents)
    destination = out / region / 'fbx'
    # Migrate an older ordinary park folder only with its complete recorded build membership.
    if destination.exists() and not (destination / 'manifest.json').exists():
        actual = regular_files(destination)
        previous = out / region / 'build.json'
        if actual:
            if not previous.is_file() or previous.is_symlink():
                raise ValueError('Unrecorded previous park exports')
            old = json.loads(previous.read_text())
            members = [e for field in ('render', 'collision', 'seam') for e in old.get(field, [])]
            expected = {Path(e['fbx']).name for e in members} | {
                'SM_MP_ImportSeed.fbx' if region == 'megapark' else 'SM_CP_ImportSeed.fbx'}
            if not actual <= expected:
                raise ValueError('Foreign previous park export members')
            # Record ownership first. Shared assembly validates all current products before any retirement.
            atomic_json(destination / 'manifest.json', dict(schema=1, complete=True,
                exports=[dict(asset=Path(p).stem, primary=p) for p in sorted(actual)]))
    export_assembly.assemble(items, destination)
    return groups, materials
