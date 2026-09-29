"""Compact Wanderer rig, using the same limb convention as Cape Boy."""
import bpy
from rig import build_rig as build_compact_rig


def build_rig():
    arm=build_compact_rig()
    arm.name='Wanderer_Rig'
    arm.data.name='Wanderer_Skeleton_V2'
    arm['character_version']='wanderer_v2'
    bpy.context.view_layer.objects.active=arm
    bpy.ops.object.mode_set(mode='EDIT')
    bones=arm.data.edit_bones
    for name in ('hood','sash_L','sash_R','bag'):
        bones.remove(bones[name])
    bones['neck'].tail=(0,0,1.064)
    bones['head'].head=(0,0,1.064)
    bones['head'].tail=(0,0,1.390)
    for s,suf in ((1,'L'),(-1,'R')):
        shoulder=(s*.112,0,.985)
        elbow=(s*.195,-.002,.800)
        wrist=(s*.271,-.011,.613)
        bones['upperarm_'+suf].head=shoulder
        bones['upperarm_'+suf].tail=elbow
        bones['forearm_'+suf].head=elbow
        bones['forearm_'+suf].tail=wrist
        bones['hand_'+suf].head=wrist
        bones['hand_'+suf].tail=(s*.281,-.016,.554)
        for name in ['finger_%d_%s'%(i,suf) for i in range(4)]+['thumb_'+suf]:
            bones[name].head.x+=s*.011; bones[name].tail.x+=s*.011
            bones[name].head.z-=.036; bones[name].tail.z-=.036
        bones['eye_'+suf].head=(s*.055,-.104,1.153)
        bones['eye_'+suf].tail=(s*.055,-.104,1.188)
    def bone(name,a,b,parent):
        eb=bones.new(name);eb.head=a;eb.tail=b;eb.parent=bones[parent]
    bone('hat',(0,.119,1.005),(0,.239,.802),'chest')
    bone('scarf_L',(-.020,-.124,1.003),(-.039,-.142,.862),'chest')
    bone('scarf_R',(.027,-.127,1.003),(.058,-.145,.882),'chest')
    bone('bag',(.153,-.089,.697),(.169,-.113,.580),'pelvis')
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:pb.rotation_mode='QUATERNION'
    return arm
