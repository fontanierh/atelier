"""Kiyo's 23-bone core humanoid rig plus readable prop and cloth extras."""
import bpy


def build_rig():
    data = bpy.data.armatures.new('Kiyo_Skeleton')
    arm = bpy.data.objects.new('Kiyo_Rig', data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bones = data.edit_bones

    def bone(name, head, tail, parent=None, roll=0):
        b = bones.new(name)
        b.head, b.tail, b.roll = head, tail, roll
        if parent:
            b.parent = bones[parent]
        return b

    # Core humanoid contract: 23 bones named exactly as platform/conventions/rigs/humanoid.toml.
    bone('root', (0, 0, 0), (0, 0, .08))
    bone('pelvis', (0, 0, .54), (0, 0, .65), 'root')
    bone('spine', (0, 0, .65), (0, 0, .76), 'pelvis')
    bone('spine_mid', (0, 0, .76), (0, 0, .87), 'spine')
    bone('chest', (0, 0, .87), (0, 0, 1.00), 'spine_mid')
    bone('neck', (0, 0, 1.00), (0, 0, 1.08), 'chest')
    bone('head', (0, 0, 1.08), (0, 0, 1.34), 'neck')
    for s, side in ((1, 'L'), (-1, 'R')):
        bone('clavicle_' + side, (0, 0, .985), (s * .095, 0, 1.005), 'chest')
        bone('upperarm_' + side, (s * .095, 0, 1.005), (s * .185, -.003, .815), 'clavicle_' + side)
        bone('forearm_' + side, (s * .185, -.003, .815), (s * .240, -.010, .655), 'upperarm_' + side)
        bone('hand_' + side, (s * .240, -.010, .655), (s * .260, -.016, .555), 'forearm_' + side)
        bone('thigh_' + side, (s * .075, 0, .555), (s * .085, -.006, .305), 'pelvis')
        bone('shin_' + side, (s * .085, -.006, .305), (s * .095, .002, .083), 'thigh_' + side)
        bone('foot_' + side, (s * .095, .002, .083), (s * .095, -.118, .044), 'shin_' + side)
        bone('toe_' + side, (s * .095, -.118, .044), (s * .095, -.176, .040), 'foot_' + side)

    # Cloth and props that need to read as separate low-poly pieces in motion.
    bone('hat', (0, 0, 1.405), (0, 0, 1.552), 'head')
    bone('hair_bun', (0, .075, 1.185), (0, .155, 1.115), 'head')
    for s, side in ((1, 'L'), (-1, 'R')):
        bone('cape_' + side, (s * .085, 0, 1.015), (s * .250, -.015, .905), 'chest')
    bone('staff', (-.340, .060, .015), (-.340, .060, 1.345), 'hand_R')
    bone('tide_board', (.160, -.125, .770), (.160, -.125, .555), 'pelvis')
    bone('satchel', (.175, -.030, .705), (.175, -.030, .515), 'pelvis')

    bpy.ops.object.mode_set(mode='OBJECT')
    arm.show_in_front = True
    data.display_type = 'OCTAHEDRAL'
    arm['rig_contract'] = 'humanoid'
    arm['character'] = 'Kiyo, the tide-reader'
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return arm
