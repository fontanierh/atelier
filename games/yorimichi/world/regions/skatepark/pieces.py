"""Bound generated pier meshes while keeping the committed logical park and riding queries whole."""
import copy
import hashlib
import json
import re
import stat
from pathlib import Path

from atelier.mesh_cells import cell_face_groups

TRIANGLE_LIMIT = 32768
CELL_METRES = 128
PARENTS = ('SM_SkatePier', 'SM_SkatePierPilings', 'SM_SkateParkFeatures', 'SM_SkatePath',
           'SM_SkateParkFurniture', 'SM_SkateParkPlanting', 'SM_SkateParkDecals')


def validate_logical_contract(path, current):
    """@cc [owner:fontanierh,label:correctness] pier-build-keeps-authored-contract-immutable
    The normal generator MUST NOT rewrite the committed logical park consumed by maps and queries.
    Recomputed logical geometry MUST agree with that authored input; a mismatch MUST fail explicitly
    rather than publish runtime data that disagrees with consumers built from the old source.
    """
    if json.loads(Path(path).read_text()) != json.loads(json.dumps(current, allow_nan=False)):
        raise ValueError('Pier logical contract changed; update the authored park.json and its query consumers explicitly')


def owned_name(name):
    return isinstance(name, str) and any(name == parent or re.fullmatch(re.escape(parent) + r'_Piece[0-9a-f]{16}', name)
                                         for parent in PARENTS)


def preflight_root(folder):
    """Refuse foreign/link outputs before an exporter can overwrite a prior path."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Invalid generated pier export root')
    for path in folder.iterdir():
        if path.suffix == '.fbx' and (not owned_name(path.stem) or not stat.S_ISREG(path.lstat().st_mode)):
            raise ValueError('Foreign or linked pier export: ' + path.name)


def groups(parent, positions, faces):
    """@cc [owner:fontanierh,label:correctness] bounded-pier-model-membership
    Every complete face MUST belong to exactly one bounded child, in source order, with its original
    corner stream and pivot. Small parents MUST retain their existing name. Large parents MUST be
    replaced in the generated runtime roster, never kept as a second render/collision mesh.
    """
    if parent not in PARENTS or not faces:
        raise ValueError('Invalid bounded pier source')
    # Validate small meshes through the same partitioner, without renaming or splitting them.
    cells = cell_face_groups(positions, faces, CELL_METRES, triangle_limit=TRIANGLE_LIMIT)
    if sum(len(face) - 2 for face in faces) <= TRIANGLE_LIMIT:
        return [(parent, tuple(range(len(faces))))]
    result = []
    for x, y, suffix, members in cells:
        token = hashlib.sha256(json.dumps([CELL_METRES, x, y, suffix], separators=(',', ':')).encode()).hexdigest()[:16]
        result.append((parent + '_Piece' + token, members))
    if (len({name for name, _ in result}) != len(result)
            or sorted(i for _, members in result for i in members) != list(range(len(faces)))):
        raise ValueError('Incomplete or duplicate bounded pier membership')
    return result


def runtime_park(logical, members):
    """@cc [owner:fontanierh,label:correctness] pier-runtime-and-logical-surface-ownership
    Only the generated runtime mesh roster MAY expand. The committed logical park, rails, clearance,
    board, spawns, trees, transforms and offline riding triangles MUST remain unchanged. Every child
    MUST inherit its logical parent's collision policy and original actor-local placement.
    """
    entries = logical['meshes']
    if (not isinstance(entries, list) or {entry['name'] for entry in entries} != set(PARENTS)
            or len(entries) != len(PARENTS) or set(members) != set(PARENTS)):
        raise ValueError('Incomplete logical pier membership')
    result = copy.deepcopy(logical)
    expanded = []
    for entry in entries:
        parent = entry['name']
        if entry.get('asset') != '/Game/SkatePark/' + parent or type(entry.get('blocks')) is not bool:
            raise ValueError('Invalid logical pier asset/collision policy')
        names = members[parent]
        if (not isinstance(names, (list, tuple)) or not names or len(set(names)) != len(names)
                or any(not owned_name(name) or (name != parent and not name.startswith(parent + '_Piece')) for name in names)
                or (parent in names and len(names) != 1)):
            raise ValueError('Invalid runtime pier piece roster')
        for name in names:
            expanded.append({**entry, 'name': name, 'asset': '/Game/SkatePark/' + name})
    result['meshes'] = expanded
    return result


def export_mesh(original, folder, export_fbx):
    """Capture the whole source once; the shared copier validates actual Blender children before export."""
    import bpy
    from mesh_pieces import capture, subset, create_mesh
    whole = capture(original.data)
    faces = [whole['vertex_indices'][start:start + count].tolist()
             for start, count in zip(whole['starts'], whole['counts'])]
    result = []
    for name, members in groups(original.name, whole['positions'], faces):
        piece = subset(whole, members)
        data, obj = None, original
        try:
            if name != original.name:
                data = create_mesh(name, piece)
                obj = bpy.data.objects.new(name, data)
                bpy.context.collection.objects.link(obj)
                obj.matrix_world = original.matrix_world.copy()
                export_fbx(obj, Path(folder) / (name + '.fbx'))
            path = Path(folder) / (name + '.fbx')
            used_slots = set(piece['materials'].tolist())
            result.append(dict(name=name, parent=original.name, triangles=piece['triangles'],
                               vertices=len(piece['positions']), min=piece['positions'].min(axis=0).tolist(),
                               max=piece['positions'].max(axis=0).tolist(),
                               material_slots=[slot.name for i, slot in enumerate(whole['slots']) if i in used_slots],
                               source_material_slots=[slot.name for slot in whole['slots']],
                               sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        finally:
            if data is not None:
                if obj is not original:
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.meshes.remove(data)
    return result


def retire_exports(folder, records):
    """@cc [owner:fontanierh,label:correctness] retire-pier-exports-after-complete-current-set
    Only canonical generated pier parent/piece FBXs MAY retire, after every current FBX is regular and
    matches its fresh export receipt. Full preflight MUST precede deletion; unknown FBXs, links, changed
    bytes or deletion errors MUST fail publication. Committed models and board exports stay outside scope.
    """
    folder = Path(folder)
    preflight_root(folder)
    expected = {row['name']: row['sha256'] for row in records}
    if (not expected or len(expected) != len(records) or any(not owned_name(name) for name in expected)
            or {row['parent'] for row in records} != set(PARENTS)
            or any(row['name'] != row['parent'] and not row['name'].startswith(row['parent'] + '_Piece') for row in records)):
        raise ValueError('Invalid current pier export membership')
    for name, digest in expected.items():
        path = folder / (name + '.fbx')
        if (not stat.S_ISREG(path.lstat().st_mode)
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError('Incomplete or changed current pier export: ' + name)
    obsolete = []
    for path in sorted(folder.iterdir()):
        if path.suffix != '.fbx':
            continue
        if not owned_name(path.stem) or not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Foreign or linked pier export: ' + path.name)
        if path.stem not in expected:
            obsolete.append(path)
    for path in obsolete:
        path.unlink()
    return [path.name for path in obsolete]
