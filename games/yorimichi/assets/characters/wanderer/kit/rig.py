"""Compact, independent deformation rig for the child's proportions."""
import math
import bpy
from mathutils import Vector

def build_rig(articulated_fingers=False):
    data=bpy.data.armatures.new('CapeBoy_Skeleton')
    arm=bpy.data.objects.new('CapeBoy_Rig',data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active=arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    def bone(name,a,b,parent=None):
        eb=data.edit_bones.new(name)
        eb.head,eb.tail=a,b
        if parent: eb.parent=data.edit_bones[parent]
    bone('root',(0,0,0),(0,0,.10))
    bone('pelvis',(0,0,.660),(0,0,.770),'root')
    bone('spine',(0,0,.770),(0,0,.899),'pelvis')
    bone('chest',(0,0,.899),(0,0,1.017),'spine')
    bone('neck',(0,0,1.017),(0,0,1.093),'chest')
    bone('head',(0,0,1.093),(0,0,1.389),'neck')
    bone('hood',(0,.09,1.020),(0,.17,.922),'chest')
    bone('bag',(-.098,.126,.766),(-.098,.126,.618),'pelvis')
    bone('sash_L',(.01,-.126,.706),(-.043,-.132,.596),'pelvis')
    bone('sash_R',(.033,-.128,.706),(.064,-.135,.554),'pelvis')
    for s,suf in ((1,'L'),(-1,'R')):
        bone('eye_'+suf,(s*.049,-.098,1.184),(s*.049,-.098,1.219),'head')
        bone('upperarm_'+suf,(s*.105,0,.969),(s*.190,-.002,.808),'chest')
        bone('forearm_'+suf,(s*.190,-.002,.808),(s*.260,-.011,.650),'upperarm_'+suf)
        bone('hand_'+suf,(s*.260,-.011,.650),(s*.270,-.016,.590),'forearm_'+suf)
        for i in range(4):
            top=(s*(.247+i*.015),-.016,.603-(.004 if i==3 else 0))
            mid=(s*(.250+i*.015),-.025,.571+abs(i-1)*.007)
            end=(s*(.248+i*.015),-.04,.553+abs(i-1)*.007)
            name='finger_%d_%s'%(i,suf)
            bone(name,top,mid if articulated_fingers else end,'hand_'+suf)
            if articulated_fingers:bone('finger_tip_%d_%s'%(i,suf),mid,end,name)
        bone('thumb_'+suf,(s*.247,-.009,.626),(s*.221,-.041,.580),'hand_'+suf)
        bone('thigh_'+suf,(s*.083,0,.661),(s*.099,-.016,.371),'pelvis')
        bone('shin_'+suf,(s*.099,-.016,.371),(s*.130,.005,.112),'thigh_'+suf)
        bone('foot_'+suf,(s*.130,.005,.112),(s*.130,-.139,.048),'shin_'+suf)
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.show_in_front=True
    for pb in arm.pose.bones: pb.rotation_mode='QUATERNION'
    return arm

def two_bone(a,c,l1,l2,bend):
    a,c=Vector(a),Vector(c)
    axis=(c-a).normalized()
    d=max(.001,min((c-a).length,l1+l2-.0001))
    along=(l1*l1-l2*l2+d*d)/(2*d)
    pole=Vector(bend)
    pole=(pole-axis*pole.dot(axis)).normalized()
    return a+axis*along+pole*math.sqrt(max(0,l1*l1-along*along))

def aim_matrix(rest,a,b):
    rot=rest.to_3x3().col[1].normalized().rotation_difference((Vector(b)-Vector(a)).normalized()).to_matrix()
    m=(rot@rest.to_3x3()).to_4x4()
    m.translation=Vector(a)
    return m
