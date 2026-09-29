"""Bone names: Tripo's auto-rig returns Mixamo names; every humanoid here uses the humanoid contract's names
(platform/conventions/rigs/humanoid.toml). Standard library only."""
import re


def slug(name):
    """Asset-safe name: runs of anything but letters and digits become one underscore."""
    return re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')


def mixamo_aliases():
    """{mixamo bone name: contract bone name} for the 23 core bones and 30 finger bones (plus Blender's `Root`)."""
    result = {'Root': 'root', 'mixamorig:Hips': 'pelvis', 'mixamorig:Spine': 'spine',
              'mixamorig:Spine1': 'spine_mid', 'mixamorig:Spine2': 'chest',
              'mixamorig:Neck': 'neck', 'mixamorig:Head': 'head'}
    for side, suffix in [('Left', 'L'), ('Right', 'R')]:
        for source, dest in [('Shoulder', 'clavicle'), ('Arm', 'upperarm'), ('ForeArm', 'forearm'),
                             ('Hand', 'hand'), ('UpLeg', 'thigh'), ('Leg', 'shin'), ('Foot', 'foot'), ('ToeBase', 'toe')]:
            result['mixamorig:' + side + source] = dest + '_' + suffix
        for digit, finger in enumerate(['Index', 'Middle', 'Ring', 'Pinky']):
            for level, dest in [(1, 'finger_' + str(digit)), (2, 'finger_tip_' + str(digit)), (3, 'finger_end_' + str(digit))]:
                result['mixamorig:' + side + 'Hand' + finger + str(level)] = dest + '_' + suffix
        for level, dest in [(1, 'thumb'), (2, 'thumb_tip'), (3, 'thumb_end')]:
            result['mixamorig:' + side + 'HandThumb' + str(level)] = dest + '_' + suffix
    return result
