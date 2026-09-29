"""Portable cloth pose corrections, sampled into the same slotted rig actions."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import math
import bpy
from mathutils import Vector

def smooth(a,b,v):
    t=max(0,min(1,(v-a)/(b-a)));return t*t*(3-2*t)

def make_correctives(items):
    for slot in ['sweatshirt','shorts']:
        obj=items[slot];obj.shape_key_add(name='Basis');obj.data.shape_keys.name='Cloth · '+slot
        for side,sgn in [('Left',1),('Right',-1)]:
            key=obj.shape_key_add(name=side+' · cloth compression')
            for v,k in zip(obj.data.vertices,key.data):
                p=v.co.copy();u=p.y*sgn
                if slot=='sweatshirt':
                    # The outer yellow sleeve flattens under arm pull. Preserve
                    # neck, torso, long white sleeves and their clearances.
                    mask=smooth(.090,.160,u)*(1-smooth(.235,.270,u))*smooth(.035,.080,p.z)
                    if obj.data.attributes['yellow_layer'].data[v.index].value<.5:mask=0
                    p.z-=(p.z-.127)*.15*mask
                    p.z-=.003*math.exp(-((u-.130)/.06)**2)*smooth(.135,.172,p.z)*mask
                    p.x-=(p.x-.017)*.10*mask
                    p.x+=.0022*math.sin(u*155+math.atan2(p.z-.127,p.x-.017))*mask
                else:
                    mask=smooth(.015,.044,u)*(1-smooth(.105,.14,u))*smooth(-.10,-.18,p.z)
                    zline=-.178+.22*(u-.06)
                    p.x+=mask*(.004*math.exp(-((p.z-zline)/.010)**2)-.002*math.exp(-((p.z-zline+.015)/.011)**2))*smooth(.018,.05,p.x)
                k.co=p
        obj['cloth_correctives']='Sampled sleeve/shorts compression; existing skeleton and choreography unchanged'


def author_correctives(items,arm,scene,action,standing=False):
    slots={}
    for slot in ['sweatshirt','shorts']:
        keys=items[slot].data.shape_keys;keys.animation_data_create();keys.animation_data.action=action
        target=action.slots.new(id_type='KEY',name=keys.name)
        keys.animation_data.action_slot=target
        mapping=dict(keys.get('clip_slots',{}));mapping[action.name]=target.identifier;keys['clip_slots']=mapping
        slots[slot]=keys
    for frame in range(1,42):
        scene.frame_set(frame);bpy.context.view_layer.update()
        for slot,keys in slots.items():
            for side in ['Left','Right']:
                p=arm.pose.bones['mixamorig:'+side+('Arm' if slot=='sweatshirt' else 'UpLeg')]
                direction=(arm.matrix_world@p.tail)-(arm.matrix_world@p.head)
                value=0 if standing else (smooth(.030,.145,abs(direction.x)) if slot=='sweatshirt' else smooth(.025,.14,direction.x))
                key=keys.key_blocks[side+' · cloth compression'];key.value=value;key.keyframe_insert('value',frame=frame)
    if not standing:
        for keys in slots.values():
            track=keys.animation_data.nla_tracks.new();track.name=action.name;track.mute=True
            strip=track.strips.new(action.name,1,action)
            strip.action_slot=keys.animation_data.action_slot
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for point in fc.keyframe_points:point.interpolation='LINEAR'


def set_clip(arm,action):
    arm.animation_data.action=action
    # Slotted actions: Blender only auto-selects a slot whose identifier matches the last one used on this
    # armature. Clips authored under another slot name would otherwise assign silently with no channels.
    if arm.animation_data.action_slot is None:
        slot=next((s for s in action.slots if s.identifier.startswith('OB')),None)
        if slot is not None: arm.animation_data.action_slot=slot
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH' or not obj.data.shape_keys:continue
        keys=obj.data.shape_keys
        if 'clip_slots' not in keys:continue
        identifier=keys['clip_slots'].get(action.name)
        if identifier:
            keys.animation_data_create();keys.animation_data.action=action
            keys.animation_data.action_slot=next(s for s in action.slots if s.identifier==identifier)
