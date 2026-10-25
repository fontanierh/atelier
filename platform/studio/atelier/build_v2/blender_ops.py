"""D2 job bodies: existing MeshIR to one independent explicitly selected FBX or GLB export.

Project entry scripts call these functions inside C2b's fresh, declared-code job. They do not
create tasks, cache entries, workers or installed files. MeshSet remains unsupported; encoded
GLB uses its separate lossless body. Nothing here imports a v1 build/cache controller.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

from atelier import mesh_ir, mesh_collision
from atelier.export_manifest import TRIANGLE_LIMIT, name
from .blender_validate import MAX_RECEIPT_BYTES, PLAN_FIELDS, MEMBER_FIELDS, decode_mesh_payload, mesh_facts, validate_member_row, validate_export_receipt, validate_mesh_options, selected_policy


def _json(raw):
    from .blender_validate import _pairs
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('Nonfinite plan')))


def _member(value):
    if type(value) is not str or not value or PurePosixPath(value).name != value or '\\' in value or value in ('.', '..'):
        raise ValueError('Expected a single canonical member name')
    return value


def verify_plan(root, *, parent, limits, output_format='fbx', plan_encoding='mesh_ir'):
    """@cc [owner:fontanierh,label:correctness] d2-producer-verifies-emitted-plan
    The producer MUST verify its complete emitted set before Completed, fully decoding each
    selected MeshIR with the existing decoder, binding hashes and preserving exact face/material/
    collision ownership against the explicitly declared export format and plan encoding.
    Mesh sets MUST retain independent object slot tables and the complete semantic roster;
    they MUST NOT invent a shared face partition or material-index table. Unknown, missing, aliased
    or linked files and over-limit groups MUST fail.
    B2 MUST independently check the later frozen inventory and bindings; this is in-job proof only.
    See test_build_v2_blender_ops.py.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected an owned real plan directory')
    required = {'max_pieces', 'max_manifest_bytes', 'max_member_bytes', 'max_total_bytes'}
    if (not isinstance(limits, dict) and not hasattr(limits, 'keys')) or set(limits) != required:
        raise ValueError('Missing fixed plan limits')
    if any(type(v) is not int or v <= 0 for v in limits.values()) or limits['max_member_bytes'] > mesh_ir.MAX_BYTES:
        raise ValueError('Invalid plan limits')
    paths = list(root.iterdir())
    if any(p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1 for p in paths):
        raise ValueError('Plan contains a link, directory or unsupported member')
    if output_format not in ('fbx', 'glb'):
        raise ValueError('Producer requires an explicit FBX or GLB export format')
    manifest_path = root / 'plan.json'
    if not manifest_path.is_file() or manifest_path.stat().st_size > limits['max_manifest_bytes']:
        raise ValueError('Missing or oversized plan manifest')
    manifest = _json(manifest_path.read_bytes())
    if plan_encoding not in ('mesh_ir', 'mesh_set'):
        raise ValueError('Unsupported declared geometry encoding')
    mesh_set = plan_encoding == 'mesh_set'
    fields = (PLAN_FIELDS - {'partition', 'collision_owner'} | {'kind', 'metadata', 'diagnostics'}
              if mesh_set else PLAN_FIELDS)
    if (type(manifest) is not dict or set(manifest) != fields or type(manifest.get('schema')) is not int or manifest['schema'] != 1
            or (manifest.get('kind') != 'mesh_set' if mesh_set else 'kind' in manifest)
            or manifest.get('complete') is not True
            or manifest.get('parent') != name(parent) or manifest.get('triangle_limit') != TRIANGLE_LIMIT
            or (not mesh_set and manifest.get('partition') not in ('whole', 'spatial', 'logical', 'explicit'))):
        raise ValueError('Unsupported or incomplete MeshIR plan')
    if (type(manifest['source_triangles']) is not int or manifest['source_triangles'] <= 0
            or type(manifest['source_collision_hulls']) is not int or manifest['source_collision_hulls'] < 0
            or (manifest.get('collision_owner') is not None and type(manifest['collision_owner']) is not str)
            or not isinstance(manifest['slots'], list) or not manifest['slots']
            or any(type(slot) is not str or not slot for slot in manifest['slots'])
            or not isinstance(manifest['matrix'], list) or len(manifest['matrix']) != 4
            or any(not isinstance(row, list) or len(row) != 4
                   or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                   for row in manifest['matrix'])):
        raise ValueError('Mistyped source plan metadata')
    rows = manifest.get('pieces')
    if not isinstance(rows, list) or not 0 < len(rows) <= limits['max_pieces']:
        raise ValueError('Invalid plan piece count')
    names, files, faces, all_slots = set(), {'plan.json'}, set(), set()
    member_fields = MEMBER_FIELDS - {'source_faces', 'source_material_indices'} if mesh_set else MEMBER_FIELDS
    total_bytes = manifest_path.stat().st_size
    triangles = polygons = 0
    source_polygons = manifest.get('source_polygons')
    if type(source_polygons) is not int or source_polygons <= 0:
        raise ValueError('Missing complete source polygon inventory')
    for row in rows:
        if type(row) is not dict or set(row) != member_fields:
            raise ValueError('Invalid plan member')
        if (any(type(row[field]) is not int or row[field] < minimum
                for field, minimum in [('triangles', 1), ('polygons', 1), ('collision_hulls', 0)])
                or any(not isinstance(row[field], list) or len(row[field]) != 3
                       or any(type(v) not in (int, float) or not math.isfinite(v) for v in row[field])
                       for field in ('min', 'max'))
                or not isinstance(row['slots'], list) or not row['slots']
                or any(type(slot) is not str or not slot for slot in row['slots'])
                or (not mesh_set and not isinstance(row['source_material_indices'], list))):
            raise ValueError('Mistyped piece metadata')
        asset = name(row.get('name'))
        if mesh_set and not (asset == parent or asset.startswith(parent + '_')):
            raise ValueError('Mesh-set member lies outside its declared parent')
        if asset.casefold() in names:
            raise ValueError('Aliased plan identity')
        names.add(asset.casefold())
        relative = _member(row.get('payload'))
        if relative != asset + '.npz' or relative in files:
            raise ValueError('Noncanonical or duplicate plan payload')
        files.add(relative)
        path = root / relative
        if not path.is_file() or path.stat().st_size > limits['max_member_bytes']:
            raise ValueError('Missing or oversized plan payload')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row.get('sha256'):
            raise ValueError('Emitted payload hash differs from the plan')
        facts = mesh_facts(raw, expected_asset=asset, output_format=output_format)
        validate_member_row(facts, row, manifest)
        all_slots.update(facts['slots'])
        if not mesh_set:
            membership = row.get('source_faces')
            if (not isinstance(membership, list) or len(membership) != facts['polygons']
                    or any(type(i) is not int or not 0 <= i < source_polygons for i in membership)
                    or membership != sorted(set(membership)) or faces.intersection(membership)):
                raise ValueError('Missing, duplicated or overlapping source-face ownership')
            faces.update(membership)
        triangles += facts['triangles']
        polygons += facts['polygons']
        total_bytes += len(raw)
    if {p.name for p in paths} != files:
        raise ValueError('Incomplete or foreign plan membership')
    if total_bytes > limits['max_total_bytes']:
        raise ValueError('Plan total byte budget exceeded')
    if (triangles != manifest.get('source_triangles') or polygons != source_polygons
            or (not mesh_set and faces != set(range(source_polygons)))):
        raise ValueError('Incomplete geometry ownership')
    hulls = manifest.get('source_collision_hulls')
    if type(hulls) is not int or hulls < 0:
        raise ValueError('Invalid source collision inventory')
    if (hulls and manifest.get('collision_owner') != rows[0]['name']) or (not hulls and manifest.get('collision_owner') is not None):
        raise ValueError('Whole collision owner must be the explicit first piece')
    if mesh_set and (hulls != 0 or sorted(all_slots) != manifest['slots']
                     or not isinstance(manifest['metadata'], dict)
                     or set(manifest['metadata']) != {row['name'] for row in rows}
                     or any(not isinstance(value, dict) for value in manifest['metadata'].values())
                     or not isinstance(manifest['diagnostics'], dict)):
        raise ValueError('Mesh-set material or semantic inventory is incomplete')
    if mesh_set:
        json.dumps({'metadata': manifest['metadata'], 'diagnostics': manifest['diagnostics']}, allow_nan=False)
    if manifest.get('partition') == 'whole' and [row['name'] for row in rows] != [parent]:
        raise ValueError('Whole geometry must retain its existing whole owner')
    return manifest


def emit_whole_payload(root, payload, *, parent):
    """Adapt one existing immutable schema-2 whole payload without re-encoding its geometry.

    Project planners that discover multiple pieces still supply their existing typed producer;
    this bounded whole route makes no geometry extraction or current-source equivalence claim.
    """
    parent = name(parent)
    _meta, _piece, facts = decode_mesh_payload(payload, expected_asset=parent)
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or any(root.iterdir()):
        raise ValueError('Whole adapter requires the fresh owned empty output group')
    member = parent + '.npz'
    row = dict(name=parent, payload=member, sha256=hashlib.sha256(payload).hexdigest(),
               triangles=facts['triangles'], polygons=facts['polygons'],
               source_faces=list(range(facts['polygons'])), min=facts['min'], max=facts['max'],
               collision_hulls=facts['collision_hulls'], slots=facts['slots'],
               source_material_indices=list(range(len(facts['slots']))))
    manifest = dict(schema=1, parent=parent, complete=True, triangle_limit=TRIANGLE_LIMIT,
                    partition='whole', source_triangles=facts['triangles'],
                    source_polygons=facts['polygons'], source_collision_hulls=facts['collision_hulls'],
                    collision_owner=parent if facts['collision_hulls'] else None,
                    slots=facts['slots'], matrix=facts['matrix'], pieces=[row])
    (root / member).write_bytes(payload)
    (root / 'plan.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return manifest


def run_plan(context, producer):
    """A declared project adapter supplies its existing planner as `producer(output_root)`."""
    raw = context.params['output_root']
    path = PurePosixPath(raw)
    if (type(raw) is not str or str(path) != raw or path.is_absolute() or '\\' in raw
            or len(path.parts) < 2 or path.parts[0] != 'output' or '..' in path.parts):
        raise ValueError('Planner output root must match its keyed output/<root> contract')
    root = Path(raw)
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise ValueError('Linked planner output ancestor')
    root.mkdir(parents=True, exist_ok=False)
    producer(root)
    return verify_plan(root, parent=context.params['parent'], limits=context.params['plan_limits'],
                       output_format=context.params.get('format', 'fbx'))


def run_export_piece(context):
    """Fully decode one selected payload, restore exactly its geometry and emit FBX + receipt."""
    output_format = context.params['format']
    if (output_format not in ('fbx', 'glb') or context.params['payload_encoding'] not in ('mesh_ir', 'mesh_set')
            or context.params['payload_role'] != 'geometry' or set(context.inputs) != {'payload'}):
        raise ValueError('Only one selected MeshIR geometry payload to FBX or GLB is supported')
    policy = None
    if context.params['payload_encoding'] == 'mesh_set':
        policy = selected_policy(context.params.get('payload_metadata'))
    elif 'payload_metadata' in context.params:
        raise ValueError('Semantic projection metadata requires its mesh-set encoding')
    root = context.inputs['payload']
    member = _member(context.params['payload_member'])
    if root is None or root.is_symlink() or not root.is_dir():
        raise ValueError('Expected the selected member directory')
    payload_path = root / member
    if {path.name for path in root.iterdir()} != {member}:
        raise ValueError('Selected payload directory contains unowned members')
    if (payload_path.is_symlink() or not payload_path.is_file() or payload_path.stat().st_nlink != 1
            or payload_path.stat().st_size > mesh_ir.MAX_BYTES):
        raise ValueError('Missing or invalid selected geometry payload')
    original = payload_path.read_bytes()
    meta, piece, facts = decode_mesh_payload(original, output_format=output_format)
    asset = name(meta['asset'])
    primary_names = [path for path in context.outputs if path.endswith('.' + output_format)]
    if (member != asset + '.npz' or len(context.outputs) != 2 or len(primary_names) != 1
            or set(context.outputs) != {primary_names[0], 'export.json'}):
        raise ValueError('Selected member and complete export outputs differ')
    primary_name = _member(primary_names[0])
    name(primary_name[:-4])
    options = export_options(meta['options'], context.params.get('options', {}),
                             output_format=output_format, finite_materials=meta['schema'] == 3)
    _export_mesh(asset, meta, piece, context.output(primary_name), options)
    if output_format == 'fbx':
        verify_emitted_fbx(context.output(primary_name), expected_meshes=1 + len(meta['collisions']))
    else:
        verify_emitted_glb(context.output(primary_name), expected_meshes=1 + len(meta['collisions']))
    primary = context.output(primary_name).read_bytes()
    primary_digest = hashlib.sha256(primary).hexdigest()
    payload_digest = hashlib.sha256(original).hexdigest()
    receipt = dict(schema=1, asset=asset, primary=primary_name, triangles=facts['triangles'],
                   bounds=[facts['min'], facts['max']], sha256=primary_digest,
                   metadata=dict(geometry_sha256=payload_digest, slots=meta['slots'], polygons=len(piece['faces']),
                                 collision_hulls=len(meta['collisions']), uv_channels=facts['uv_channels']))
    if policy is not None:
        receipt['metadata']['native_policy'] = policy
    raw = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    validate_export_receipt(raw, primary, asset=asset, primary_digest=primary_digest,
                            payload_digest=payload_digest, facts=facts, primary_name=primary_name, native_policy=policy)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('Export receipt exceeds its fixed bound')
    context.output('export.json').write_bytes(raw)
    if payload_path.read_bytes() != original:
        raise ValueError('Selected payload changed during the export')


def verify_emitted_fbx(path, *, expected_meshes):
    """Parse the emitted artifact before Completed, using Blender's existing FBX parser.

    This catches malformed/truncated serialization and incomplete selected mesh ownership. Full
    normals/UV/material/collision equivalence remains the independent native fixture's job.
    """
    from io_scene_fbx import parse_fbx
    root, _version = parse_fbx.parse(str(path))
    if root is None:
        raise ValueError('Emitted FBX did not parse')
    sections = [element for element in root.elems if element.id == b'Objects']
    if len(sections) != 1 or sum(e.id == b'Geometry' for e in sections[0].elems) != expected_meshes:
        raise ValueError('Emitted FBX mesh inventory differs from the selected render/UCX set')


def verify_emitted_glb(path, *, expected_meshes):
    """Check complete GLB framing and the selected render/collision inventory before completion."""
    from atelier.gltf import glb_parts
    data = path.read_bytes()
    doc, _binary = glb_parts(data)
    if (len(doc.get('meshes', [])) != expected_meshes or doc.get('skins') or doc.get('animations')
            or doc.get('images') or any('uri' in row for row in doc.get('buffers', []))):
        raise ValueError('Emitted GLB differs from the image-free selected mesh inventory')


def _export_mesh(asset, meta, piece, primary, options):
    import bpy
    from mathutils import Matrix
    from atelier.blender.fbx import export_atomic_fbx
    from .blender_geometry import create_mesh
    output_format = primary.suffix[1:]
    actual = export_options(meta['options'], options, output_format=output_format,
                            finite_materials=meta['schema'] == 3)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if meta['schema'] == 3:
        from atelier.mesh_materials import restore
        piece['slots'] = [restore(label, spec) for label, spec in zip(meta['slots'], meta['material_specs'])]
    else:
        piece['slots'] = [bpy.data.materials.get(label) or bpy.data.materials.new(label) for label in meta['slots']]
    obj = bpy.data.objects.new(asset, create_mesh(asset, piece))
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = Matrix(meta['matrix'])
    selected = [obj]
    for index, collision in enumerate(meta['collisions']):
        label = f'UCX_{asset}_{index:02d}'
        if 'corner_payload' in collision:
            source = mesh_collision.decode(collision)
            source['slots'] = [bpy.data.materials.get(slot) or bpy.data.materials.new(slot) for slot in source['slots']]
            data = create_mesh(label, source)
        else:
            data = bpy.data.meshes.new(label)
            data.from_pydata(collision['vertices'], [], collision['faces'])
            data.update()
        hull = bpy.data.objects.new(label, data)
        bpy.context.collection.objects.link(hull)
        if 'transform' in collision:
            import numpy as np
            pose = collision['transform']
            hull.rotation_mode = pose['rotation_mode']
            hull.location, hull.scale = pose['location'], pose['scale']
            field = 'rotation_quaternion' if pose['rotation_mode'] == 'QUATERNION' else (
                'rotation_axis_angle' if pose['rotation_mode'] == 'AXIS_ANGLE' else 'rotation_euler')
            setattr(hull, field, pose[field])
            bpy.context.view_layer.update()
            if np.asarray(hull.matrix_world, dtype='<f4').tobytes() != np.asarray(collision['matrix'], dtype='<f4').tobytes():
                raise ValueError('Original collision pose no longer reproduces its exact frame')
        else:
            hull.matrix_world = Matrix(collision['matrix'])
        selected.append(hull)
    bpy.ops.object.select_all(action='DESELECT')
    for item in selected:
        item.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if output_format == 'glb':
        from atelier.blender.gltf import export_atomic_glb
        export_atomic_glb(primary, options=actual, finite_materials=meta['schema'] == 3)
    else:
        actual.update(filepath=str(primary), use_selection=True, object_types={'MESH'}, bake_anim=False)
        export_atomic_fbx(**actual)


def export_options(payload_options, declared_options, *, output_format='fbx', finite_materials=False):
    """Per-piece settings may not widen the fixed export ownership or enable another format."""
    if not hasattr(payload_options, 'items') or not hasattr(declared_options, 'items'):
        raise ValueError('Export options must be explicit objects')
    check = lambda value: validate_mesh_options(value, output_format=output_format, finite_materials=finite_materials)
    actual = check(payload_options)
    actual.update(check(declared_options))
    if output_format == 'glb':
        return check(actual)
    if any(key in actual for key in ('filepath', 'use_selection', 'object_types', 'bake_anim')):
        raise ValueError('Export options cannot override fixed selected-mesh ownership')
    if (actual.get('path_mode', 'RELATIVE') not in ('RELATIVE', 'STRIP')
            or actual.get('batch_mode', 'OFF') != 'OFF' or actual.get('use_batch_own_dir', False) is not False):
        raise ValueError('This FBX slice supports one relative-media primary, not batched/copied resources')
    return validate_mesh_options(actual)
