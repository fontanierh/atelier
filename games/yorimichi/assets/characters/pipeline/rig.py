"""Open a character's source in Blender as the game's body: the humanoid contract's bone names, a `root` at the floor,
facing +X, scaled to its height with the soles 0.65 cm under the floor. Every exporter and retargeter starts here.

    character = rig.load('nox')          # its definition (definition.py) and these steps
    prepared = character.prepare()       # record, native, scene, arm, meshes, transform, scale, floor, ...

The steps are the same for every character; character.toml [export] says what its source needs (definition.py EXPORT).
"""
from pathlib import Path
import hashlib
import json
import math
import sys
from types import SimpleNamespace

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import definition  # noqa: E402
import yori  # noqa: E402
from atelier.character.names import mixamo_aliases, slug  # noqa: E402

SOLE = .0065   # metres of sole under the floor, as every character's
# The FBX settings every humanoid body and clip in the game shares.
FBX = dict(use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
           add_leaf_bones=False, use_armature_deform_only=False, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
           bake_anim_simplify_factor=0, bake_anim_step=1, mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='ABSOLUTE')


def set_clip(arm, action):
    """Play `action` on the armature and on every mesh whose shape keys have a slot in it (keys['clip_slots']).

    Slotted actions: Blender only picks a slot whose identifier matches the last one used, so a clip authored under
    another slot name would otherwise play with no channels."""
    arm.animation_data_create()
    arm.animation_data.action = action
    if arm.animation_data.action_slot is None:
        slot = next((s for s in action.slots if s.identifier.startswith('OB')), None)
        if slot is not None:
            arm.animation_data.action_slot = slot
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        keys = obj.data.shape_keys
        if 'clip_slots' not in keys:
            continue
        identifier = keys['clip_slots'].get(action.name)
        if identifier:
            keys.animation_data_create()
            keys.animation_data.action = action
            keys.animation_data.action_slot = next(s for s in action.slots if s.identifier == identifier)


def fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield from bag.fcurves


def select(objects, active, reveal=False):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        if reveal:
            obj.hide_viewport = False
            obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def open_source(c, native):
    """The source in a fresh scene: a .blend opened, a .glb imported with its meshes unparented in place."""
    if native.suffix == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(native))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(native))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.fps = c.fps
    armatures = [o for o in scene.objects if o.type == 'ARMATURE']
    assert len(armatures) == 1, (c.id, 'one armature', [o.name for o in armatures])
    return scene, armatures[0]


def pick_meshes(c, scene):
    rule = c.export['meshes']
    if rule == 'skinned':
        return [o for o in scene.objects if o.type == 'MESH' and o.vertex_groups and not o.get('not_exported')]
    if rule == 'armature':
        return [o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
    if rule == 'outfit':   # the body swap's dressed slots and the body regions the outfit leaves visible
        return [o for o in scene.objects if o.type == 'MESH' and
                (o.get('outfit_slot') or (o.get('body_region') and not o.get('hidden_by_slot')))]
    raise ValueError((c.id, 'unknown [export] meshes', rule))


def bone_names(c, arm):
    """{source bone: contract bone} for the contract's bones, the extra bones and how they are handled."""
    aliases = mixamo_aliases()
    present = {b.name for b in arm.data.bones}
    missing = sorted(set(aliases) - present - {'Root', 'root'})
    assert not missing, (c.id, 'bones the humanoid contract needs', missing)
    extra = sorted(present - set(aliases))
    policy = c.export['extra_bones']
    assert policy in ('none', 'drop', 'follow'), (c.id, 'unknown [export] extra_bones', policy)
    assert policy != 'none' or not extra, (c.id, 'bones the contract has no name for ([export] extra_bones)', extra)
    return aliases, extra


def drop_bones(arm, meshes, extra):
    """The extra bones' vertex groups go; they must carry no weights."""
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for name in extra:
            group = obj.vertex_groups.get(name)
            if group is not None:
                assert not any(g.group == group.index and g.weight > 0 for v in obj.data.vertices for g in v.groups), \
                    (obj.name, name, 'a dropped bone carries weights')
                obj.vertex_groups.remove(group)


def edit_rig(arm, drop, add_root):
    """Remove `drop` and give the rig a `Root` at the floor under the hips (Blender's name, the contract's root)."""
    if not drop and not add_root:
        return
    select([arm], arm)
    bpy.ops.object.mode_set(mode='EDIT')
    bones = arm.data.edit_bones
    for name in drop:
        bones.remove(bones[name])
    if add_root:
        hips = bones['mixamorig:Hips' if 'mixamorig:Hips' in bones else 'pelvis']
        root = bones.new('Root')
        root.head = (0., 0., 0.)
        root.tail = (0., 0., max(.01, hips.head.z * .5))
        root.roll = 0.
        hips.parent = root
    bpy.ops.object.mode_set(mode='OBJECT')


def measure(c, scene, arm, meshes):
    """The floor and the top of the body, in the source's world space."""
    if c.export['measure_pose']:
        set_clip(arm, bpy.data.actions[c.export['measure_pose']])
        scene.frame_set(1)
        bpy.context.view_layer.update()
    rule = c.export['measure']
    points = []
    for obj in meshes:
        if rule == 'raw':
            points.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
            continue
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        if rule == 'evaluated-faces':   # loose vertices (a fitting body's leftovers) do not count
            used = {i for f in ev.data.polygons for i in f.vertices}
            points.extend(ev.matrix_world @ ev.data.vertices[i].co for i in used)
        else:
            points.extend(ev.matrix_world @ v.co for v in ev.data.vertices)
    return min(p.z for p in points), max(p.z for p in points)


def facing_turn(arm, aliases):
    """The quarter turns (radians about Z) that face the rig +X, the game's forward: its toes ahead of its ankles."""
    source = {new: old for old, new in aliases.items()}
    bones = arm.data.bones
    step = [(arm.matrix_world @ bones[source['toe_' + s]].head_local) - (arm.matrix_world @ bones[source['foot_' + s]].head_local)
            for s in 'LR']
    step = step[0] + step[1]
    if abs(step.x) >= abs(step.y):
        return 0. if step.x > 0 else math.pi
    return math.pi / 2 if step.y < 0 else -math.pi / 2


def name_meshes(c, meshes):
    """Each mesh named `<Asset>_<part>` by the first [export] mesh_names rule that matches it."""
    for index, obj in enumerate(meshes):
        for rule in c.export['mesh_names']:
            if 'property' in rule:
                value = obj.get(rule['property'])
                if not value:
                    continue
                part = slug(value)
            elif 'group' in rule:
                if not obj.vertex_groups.get(rule['group']):
                    continue
                part = rule['name']
            elif 'group_prefix' in rule:
                groups = {g.index for g in obj.vertex_groups if g.name.startswith(rule['group_prefix'])}
                if not any(w.group in groups and w.weight > 0 for v in obj.data.vertices for w in v.groups):
                    continue
                part = rule['name']
            else:
                part = rule['name'].format(index=index)
            obj.name = c.name + '_' + part
            break
        else:
            raise AssertionError((c.id, obj.name, 'no [export] mesh_names rule matches'))


def name_morphs(c, meshes):
    """Shape keys renamed by c.export['morph_names'] ('{slot}_{key}'), in their clips too: {slot: {old: new}}."""
    template = c.export['morph_names']
    morphs = {}
    if not template:
        return morphs
    for obj in meshes:
        slot = obj.get('outfit_slot') or obj.get('body_region') or obj.name
        if not obj.data.shape_keys:
            continue
        morphs[slot] = {}
        for key in obj.data.shape_keys.key_blocks[1:]:
            old = key.name
            key.name = template.format(slot=slug(slot), key=slug(old))
            morphs[slot][old] = key.name
    for action in bpy.data.actions:
        for obj in meshes:
            keys = obj.data.shape_keys
            if not keys or 'clip_slots' not in keys:
                continue
            identifier = keys['clip_slots'].get(action.name)
            slot = next((s for s in action.slots if s.identifier == identifier), None)
            if not slot:
                continue
            renames = morphs[obj.get('outfit_slot') or obj.get('body_region') or obj.name]
            for layer in action.layers:
                for strip in layer.strips:
                    bag = strip.channelbag(slot)
                    if bag:
                        for fc in bag.fcurves:
                            for old, new in renames.items():
                                fc.data_path = fc.data_path.replace('key_blocks["' + old + '"]', 'key_blocks["' + new + '"]')
    return morphs


def measure_rest(before, bones):
    """How far an edit-mode round trip moved each bone's rest matrix (Blender keeps head, tail and roll in float32)."""
    import numpy as np
    rows = []
    for bone in bones:
        a, b = np.array(before[bone.name], dtype=np.float64), np.array(bone.matrix_local, dtype=np.float64)
        rotations = []
        for matrix in (a, b):
            u, _, vt = np.linalg.svd(matrix[:3, :3])
            rotation = u @ vt
            assert np.linalg.det(rotation) > 0, 'Reflected rest bone: ' + bone.name
            rotations.append(rotation)
        relative = rotations[1] @ rotations[0].T
        sine = np.linalg.norm([relative[2, 1] - relative[1, 2], relative[0, 2] - relative[2, 0],
                               relative[1, 0] - relative[0, 1]]) / 2
        angle = math.degrees(math.atan2(sine, (np.trace(relative) - 1) / 2))
        head = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
        matrix_error = float(np.max(np.abs(a - b)))
        assert head <= 1e-5 and angle <= .01 and matrix_error <= 1e-4, (bone.name, head, angle, matrix_error)
        rows.append(dict(bone=bone.name, head_m=head, degrees=angle, matrix_error=matrix_error))
    return dict(max_head_m=max(row['head_m'] for row in rows), max_deg=max(row['degrees'] for row in rows),
                max_matrix=max(row['matrix_error'] for row in rows),
                worst_rotation_bone=max(rows, key=lambda row: row['degrees'])['bone'])


def branch_followers(arm, followers):
    """Make every follower a leaf: a contract bone under one is re-parented to its nearest contract ancestor, so a
    retargeter posing the contract bones in order never has a follower between two of them. Returns the rest-matrix
    round trip, or None when nothing needed moving."""
    def ancestor(bone):
        parent = bone.parent
        while parent is not None and parent.name in followers:
            parent = parent.parent
        return parent
    if not any(b.name not in followers and b.parent is not None and b.parent.name in followers for b in arm.data.bones):
        return None
    rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
    select([arm], arm)
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.data.edit_bones:
        if bone.name in followers:
            continue
        parent = ancestor(bone)
        if parent != bone.parent:
            bone.use_connect = False
            bone.parent = parent
    bpy.ops.object.mode_set(mode='OBJECT')
    roundtrip = measure_rest(rest, arm.data.bones)
    assert all(not arm.data.bones[name].children for name in followers), 'Followers must be leaf branches'
    return roundtrip


class Rig:
    """A character's definition and the steps that open its source as the game's body."""

    FBX = FBX

    def __init__(self, character):
        self.definition = character if isinstance(character, definition.Character) else definition.load(character)
        self.id = self.definition.id
        self.SOURCE = self.definition.folder
        self.OUT = yori.OUT / self.definition.output

    set_clip = staticmethod(set_clip)

    def prepare(self, source=None):
        """Open the revision in `source` (default the character's folder; an archived revision's folder works too).
        Returns record, native, scene, arm, meshes, transform, scale, floor, original_names (source -> contract),
        secondary_bones (followers, left neutral under their parents), dropped, rest_roundtrip and morphs."""
        c = self.definition
        source = Path(source or self.SOURCE)
        record = json.loads((source / c.toml.get('manifest', 'source-manifest.json')).read_text())
        native = source / (c.toml['source'] if source == c.folder else Path(record['native']).name)
        assert hashlib.sha256(native.read_bytes()).hexdigest() == record['native_sha256'], (c.id, 'the source differs from its manifest')
        scene, arm = open_source(c, native)
        meshes = pick_meshes(c, scene)
        assert meshes, (c.id, 'no body meshes')
        if native.suffix != '.blend':
            # Importers may parent meshes to the armature: keep every world transform, then detach.
            world = {o: o.matrix_world.copy() for o in [arm, *meshes]}
            for obj in [arm, *meshes]:
                obj.parent = None
                obj.matrix_world = world[obj]
        authored = c.export['actions'] == 'authored'
        if not authored:
            if native.suffix == '.blend':
                arm.animation_data_create()
                arm.animation_data.action = None
                for action in list(bpy.data.actions):
                    bpy.data.actions.remove(action)
            else:
                arm.animation_data_clear()
        elif not c.export['measure_pose']:
            arm.animation_data_create()
            arm.animation_data.action = None
        if c.export['strip_simulation']:
            for obj in meshes:
                for modifier in [m for m in obj.modifiers if m.type in ('CLOTH', 'COLLISION')]:
                    obj.modifiers.remove(modifier)
        if not c.export['measure_pose']:
            arm.data.pose_position = 'REST'
            bpy.context.view_layer.update()
        aliases, extra = bone_names(c, arm)
        drop = extra if c.export['extra_bones'] == 'drop' else []
        if drop:
            drop_bones(arm, meshes, drop)
        root = next((n for n in ('Root', 'root') if n in arm.data.bones), None)
        edit_rig(arm, drop, root is None)
        floor, top = measure(c, scene, arm, meshes)
        scale = c.height / (top - floor)
        turn = facing_turn(arm, aliases)
        # Evaluated left to right, as the matrices always were: the products are bit-for-bit the same.
        if turn:
            transform = Matrix.Rotation(turn, 4, 'Z') @ Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor + SOLE / scale))
        else:
            transform = Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -floor + SOLE / scale))
        world = {o: o.matrix_world.copy() for o in [arm, *meshes]}
        for obj in [arm, *meshes]:
            obj.matrix_world = transform @ world[obj]
        if not authored:
            # Bake the turn and scale into the data: the rest pose, the clips and the FBX start from identity objects.
            select([arm, *meshes], arm)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        arm.data.pose_position = 'POSE'
        followers = extra if c.export['extra_bones'] == 'follow' else []
        names = {b.name: aliases.get(b.name, slug(b.name)) for b in arm.data.bones}
        assert len(set(names.values())) == len(names), (c.id, 'bone rename collision')
        # Vertex groups explicitly: a glTF mesh need not be parented to the armature that deforms it.
        for obj in meshes:
            for group in obj.vertex_groups:
                if group.name in names:
                    group.name = names[group.name]
        for old, new in names.items():
            if old != new:
                arm.data.bones[old].name = new
        for action in bpy.data.actions:   # Blender repairs only the attached clip
            for fc in fcurves(action):
                for old, new in names.items():
                    if old != new:
                        fc.data_path = fc.data_path.replace('pose.bones["' + old + '"]', 'pose.bones["' + new + '"]')
        arm.name = 'Armature'   # Unreal recognises and omits the FBX armature node
        secondary = {names[b] for b in followers}
        for prefix, count in c.export['followers'].items():
            assert len([n for n in secondary if n.startswith(prefix)]) == count, (c.id, 'followers lost', prefix, count)
        roundtrip = branch_followers(arm, secondary) if secondary else None
        bones = arm.data.bones
        assert bones['pelvis'].parent and bones['pelvis'].parent.name == 'root', (c.id, 'the pelvis hangs under root')
        name_meshes(c, meshes)
        morphs = name_morphs(c, meshes)
        bpy.context.view_layer.update()
        assert all((arm.matrix_world @ bones['toe_' + s].head_local).x > (arm.matrix_world @ bones['foot_' + s].head_local).x
                   for s in 'LR'), (c.id, 'must face +X')
        return SimpleNamespace(record=record, native=native, scene=scene, arm=arm, meshes=meshes, transform=transform,
                               scale=scale, floor=floor, original_names=names, secondary_bones=secondary,
                               dropped=drop, rest_roundtrip=roundtrip, morphs=morphs)


def load(character):
    return Rig(character)
