"""Suzu's compact rig: the villager kit's bone names and gait conventions at her own proportions.

The skinning is procedural, so the rig carries only what the mesh and the kit's clip builder need: the spine chain,
the eyes, arms with fingers, short legs, and three secondary bodies (the bun, the hand bell and the hip cloth).
"""
import bpy

from rig import build_rig as build_compact_rig


def build_rig():
    arm = build_compact_rig()
    arm.name = 'Suzu_Rig'
    arm.data.name = 'Suzu_Skeleton'
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    bones = arm.data.edit_bones
    for name in ('hood', 'bag', 'sash_L', 'sash_R'):
        bones.remove(bones[name])
    # The spine chain, shortened and lowered for a 1.40 m body.
    bones['pelvis'].head = (0, 0, .600)
    bones['pelvis'].tail = (0, 0, .700)
    bones['spine'].head = (0, 0, .700)
    bones['spine'].tail = (0, 0, .820)
    bones['chest'].head = (0, 0, .820)
    bones['chest'].tail = (0, 0, .950)
    bones['neck'].head = (0, 0, .950)
    bones['neck'].tail = (0, 0, 1.035)
    bones['head'].head = (0, 0, 1.035)
    bones['head'].tail = (0, 0, 1.350)
    for s, suf in ((1, 'L'), (-1, 'R')):
        bones['upperarm_'+suf].head = (s*.172, 0, .905)
        bones['upperarm_'+suf].tail = (s*.232, -.010, .755)
        bones['forearm_'+suf].head = (s*.232, -.010, .755)
        bones['forearm_'+suf].tail = (s*.272, -.020, .585)
        bones['hand_'+suf].head = (s*.294, -.021, .588)
        bones['hand_'+suf].tail = (s*.304, -.026, .518)
        for i in range(4):
            name = 'finger_%d_%s' % (i, suf)
            bones[name].head = (s*(.278+i*.014), -.027, .530)
            bones[name].tail = (s*(.279+i*.014), -.047, .482)
        bones['thumb_'+suf].head = (s*.270, -.031, .550)
        bones['thumb_'+suf].tail = (s*.248, -.059, .512)
        bones['eye_'+suf].head = (s*.073, -.116, 1.165)
        bones['eye_'+suf].tail = (s*.073, -.116, 1.228)
        bones['thigh_'+suf].head = (s*.086, 0, .600)
        bones['thigh_'+suf].tail = (s*.103, -.005, .305)
        bones['shin_'+suf].head = (s*.103, -.005, .305)
        bones['shin_'+suf].tail = (s*.122, 0, .135)
        bones['foot_'+suf].head = (s*.122, 0, .135)
        bones['foot_'+suf].tail = (s*.122, -.095, .062)

    def bone(name, a, b, parent):
        eb = bones.new(name)
        eb.head, eb.tail = a, b
        eb.parent = bones[parent]

    bone('bun', (0, .150, 1.134), (0, .236, 1.134), 'head')
    bone('bell', (.162, -.148, .700), (.162, -.148, .560), 'pelvis')
    bone('cloth', (-.150, -.132, .784), (-.155, -.158, .594), 'pelvis')
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    arm.show_in_front = True
    return arm
