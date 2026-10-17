"""Suzu, the bell-ringer of Hidamari: the procedural model built from references/sheet.jpg.

Proportions are measured from the design sheet (front, right profile and back figures) at 2.76 mm to the pixel:
the sole is at 0, the crown of the hair at 1.40 m, the chin at 1.01, the eyes at 1.19, the obi from .69 to .79 and
the coat hem at .385. She is a little over four heads tall, round through the hips and narrow at the shoulders, so
the haori and the trousers carry the silhouette and the head carries the character.
"""
import math

import bpy
from mathutils import Vector

import mesh_tools as G
import shoe
from suzu_hair import build_hair
from suzu_shapes import ball, pill, rope

PALETTE = {
    'skin': 'E7B185', 'skin_shadow': 'D09A68', 'skin_warm': 'E1AA7C', 'ear': 'D7A070',
    'hair': 'B7AA9E', 'hair_light': 'C7BAAF', 'hair_dark': '9C9084',
    'ink': '2E2C2C', 'brow': 'A89D92', 'mouth': '6E4C3D',
    'indigo': '3E4557', 'indigo_light': '4A5266', 'indigo_dark': '323847',
    'trousers': '3B3B44', 'trousers_light': '474754', 'trousers_dark': '32323A',
    'rust': 'A0563C', 'rust_light': 'AC6247', 'rust_dark': '86452F',
    'cream': 'DDD0B8', 'cream_light': 'E6D9C2', 'cream_shadow': 'C2B49B',
    'rope': 'C09A66', 'rope_light': 'C8A874', 'rope_dark': 'B08C5E',
    'bell': 'C6A05F', 'bell_light': 'D4B172', 'bell_dark': '9C7B44',
    'wood': '6A4E3A', 'wood_dark': '4C3727', 'wood_light': '87664D',
    'cord': '4A3A2E', 'cord_light': '5C4A3B',
    'tabi': 'EDE6DA', 'tabi_shadow': 'D8CFC0',
}

# The face is an ellipse in plan; these are its radii at each height, so features can be placed on it.
FACE = [(1.006, .068, .076, .004), (1.030, .114, .106, .004), (1.062, .154, .122, .006),
        (1.100, .172, .131, .008), (1.150, .180, .137, .010), (1.205, .180, .141, .010),
        (1.265, .172, .140, .012), (1.320, .128, .118, .012), (1.350, .060, .061, .012)]


def face_y(x, z):
    """The front surface of the face at (x, z), for placing eyes, brows and mouth on the curve."""
    table = FACE
    for (z0, rx0, ry0, cy0), (z1, rx1, ry1, cy1) in zip(table, table[1:]):
        if z0 <= z <= z1:
            t = (z-z0)/(z1-z0)
            rx, ry, cy = (rx0+(rx1-rx0)*t, ry0+(ry1-ry0)*t, cy0+(cy1-cy0)*t)
            ratio = min(1., abs(x)/rx)
            return cy-ry*math.sqrt(max(0., 1-ratio*ratio))
    return -.13


def torso_weights(p):
    return G.weights_z(p[2], [(.60, 'pelvis'), (.74, 'spine'), (.90, 'chest'), (.99, 'chest')])


def coat_weight(p):
    # The skirt follows the hips, and its front panels yield to the thighs so the legs do not spear it.
    if p[2] >= .705:
        return torso_weights(p)
    thigh = max(0., min(.78, (.705-p[2])/.16)) if p[1] < .03 else 0.
    side = 'L' if p[0] > 0 else 'R'
    return {'pelvis': 1-thigh, 'thigh_'+side: thigh}


def arm_weight(p, suf):
    return G.weights_z(p[2], [(.56, 'hand_'+suf), (.625, 'forearm_'+suf), (.75, 'forearm_'+suf),
                              (.83, 'upperarm_'+suf), (.95, 'upperarm_'+suf)])


def leg_weight(p, suf):
    return G.weights_z(p[2], [(.165, 'shin_'+suf), (.23, 'shin_'+suf), (.335, 'thigh_'+suf),
                              (.58, 'thigh_'+suf), (.65, 'pelvis')])


def smooth(*parts):
    for ob in parts:
        for p in ob.data.polygons:
            p.use_smooth = True
    return parts


def head():
    ob = G.loft('Suzu round face', [(0, cy, z, rx, ry) for z, rx, ry, cy in FACE], 'skin', 'head', n=16)
    smooth(ob)
    # The nose: one front vertex of the cheek ring, lifted clear of the face without a seam.
    nose = ob.data.vertices[4*16+12]
    nose.co.y, nose.co.z = -.152, 1.138
    ob.data.update()
    G.ribbon('Nose shadow', [(0, -.128, 1.116), (.012, -.126, 1.112)], [.008, .004], 'skin_shadow', 'head',
             thickness=.001)
    G.loft('Neck', [(0, .014, .936, .062, .056), (0, .012, 1.030, .054, .050)], 'skin', 'neck', n=10)
    # The throat opening of the crossed collar: a narrow V of skin between the cream bands.
    G.panel('Throat', [(-.036, -.104, .998), (.036, -.104, .998), (0., -.152, .908)],
            [(0, 1, 2)], 'skin', torso_weights, .010)
    for s, suf in ((1, 'L'), (-1, 'R')):
        # A small ear dish, half hidden by the hair.
        rim = [(s*.172, -.024, 1.206), (s*.178, .006, 1.212), (s*.182, .028, 1.192),
               (s*.178, .028, 1.158), (s*.172, .006, 1.142), (s*.168, -.020, 1.154)]
        centre = Vector((s*.175, .006, 1.176))
        inner = [tuple(centre+(Vector(p)-centre)*.58+Vector((-s*.012, 0, 0))) for p in rim]
        n = len(rim)
        faces = [(i, (i+1) % n, (i+1) % n+n, i+n) for i in range(n)]+[tuple(range(n, 2*n))]
        ear = G.mesh('Ear '+suf, rim+inner, faces, 'skin', 'head', face_colours=['skin']*n+['skin_shadow'])
        smooth(ear)
        # Pill eyes bent onto the face, two millimetres proud of the skin.
        pill('Eye '+suf, (s*.076, 0, 1.190), .013, .028, .004, 'ink', 'eye_'+suf, sides=3,
             surface=lambda x, z: face_y(x, z)-.002, corner=.005)
        brow = [(s*.026, face_y(s*.026, 1.238)-.004, 1.238), (s*.050, face_y(s*.050, 1.246)-.004, 1.246),
                (s*.074, face_y(s*.074, 1.248)-.004, 1.248), (s*.096, face_y(s*.096, 1.242)-.004, 1.242),
                (s*.112, face_y(s*.112, 1.234)-.004, 1.234)]
        G.ribbon('Brow '+suf, brow, [.006, .009, .010, .008, .004], 'brow', 'head', thickness=.0035)
        G.ribbon('Smile line '+suf,
                 [(s*.041, face_y(s*.041, 1.108)-.002, 1.108), (s*.049, face_y(s*.049, 1.094)-.002, 1.094),
                  (s*.053, face_y(s*.053, 1.078)-.002, 1.078)], [.005, .004, .002], 'skin_shadow', 'head',
                 thickness=.002)
    mouth = [(x, face_y(x, z)-.003, z) for x, z in
             ((-.033, 1.087), (-.019, 1.079), (0., 1.0765), (.019, 1.079), (.033, 1.087))]
    G.ribbon('Small smile', mouth, [.003, .005, .006, .005, .003], 'mouth', 'head', thickness=.003)
    G.ribbon('Lower lip', [(-.018, face_y(.018, 1.068)-.0015, 1.068), (0, face_y(0, 1.065)-.0015, 1.065),
                           (.018, face_y(.018, 1.068)-.0015, 1.068)], [.003, .004, .003], 'skin_shadow',
             'head', thickness=.0015)
    # A soft shadow under the little nose, so the profile's bump reads from the front too.
    G.panel('Nose shadow', [(-.011, face_y(.011, 1.126)-.002, 1.126), (.011, face_y(.011, 1.126)-.002, 1.126),
                            (0, face_y(0, 1.112)-.002, 1.112)], [(0, 1, 2)], 'skin_shadow', 'head', .002)
    build_hair()


def clothes():
    G.loft('Suzu haori body', [
        (0, .012, 1.005, .076, .070), (0, .012, .962, .164, .108), (0, .010, .928, .190, .119),
        (0, .010, .880, .204, .129), (0, .010, .820, .212, .137), (0, .008, .760, .216, .143),
        (0, .006, .700, .220, .149), (0, .006, .560, .230, .155), (0, .008, .455, .238, .159),
        (0, .010, .385, .242, .161)], 'indigo', coat_weight, n=16)
    # The collar turns round the nape and crosses in a broad cream V at the chest.
    G.ribbon('Nape collar', [(-.086, .084, 1.008), (0, .106, 1.024), (.086, .084, 1.008)], .042,
             'cream_light', torso_weights, normal=(0, 1, 0), thickness=.010)
    for s in (1, -1):
        band = [(s*.068, -.090, 1.006), (s*.080, -.116, .960), (s*.072, -.138, .906),
                (s*.042, -.150, .866), (s*.008, -.154, .846)]
        G.ribbon('Cream collar '+str(s), band, [.032, .044, .048, .040, .026], 'cream_light', torso_weights,
                 normal=(0, -.96, -.28), thickness=.012)
        inner = [(s*.056, -.086, 1.002), (s*.066, -.108, .960), (s*.060, -.128, .910),
                 (s*.034, -.140, .872), (s*.008, -.146, .854)]
        G.ribbon('Under-robe collar '+str(s), inner, [.014, .018, .020, .016, .010], 'indigo_dark', torso_weights,
                 normal=(0, -.98, -.20), thickness=.008)
    G.ribbon('Coat front seam', [(0, -.150, .690), (0, -.154, .560), (0, -.157, .440), (0, -.158, .388)],
             .005, 'indigo_dark', coat_weight, thickness=.002)
    G.ribbon('Coat back seam', [(0, .150, .690), (0, .154, .560), (0, .157, .440), (0, .158, .388)],
             .005, 'indigo_dark', coat_weight, thickness=.002)
    # Wide sleeves with the cream lining turned back at the cuff.
    for s, suf in ((1, 'L'), (-1, 'R')):
        sleeve = G.tube('Wide sleeve '+suf,
                        [(s*.166, -.004, .925), (s*.208, -.010, .852), (s*.252, -.014, .772),
                         (s*.296, -.018, .694), (s*.322, -.020, .644)],
                        [.072, .086, .100, .112, .116], 'indigo', lambda p, suf=suf: arm_weight(p, suf),
                        sides=10, depth=1.04)
        smooth(sleeve)
        cuff = G.tube('Cream cuff '+suf,
                      [(s*.312, -.020, .660), (s*.322, -.021, .620), (s*.328, -.022, .584),
                       (s*.326, -.022, .572)],
                      [.115, .121, .109, .100], 'cream_light', lambda p, suf=suf: arm_weight(p, suf), sides=10,
                      depth=1.0)
        smooth(cuff)
        G.ribbon('Cuff fold '+suf, [(s*.272, -.096, .606), (s*.312, -.088, .604), (s*.344, -.030, .600)],
                 .006, 'cream_shadow', lambda p, suf=suf: arm_weight(p, suf), thickness=.002)
        fore = G.tube('Forearm '+suf,
                      [(s*.240, -.010, .752), (s*.270, -.016, .680), (s*.290, -.020, .620),
                       (s*.294, -.021, .590)],
                      [.038, .032, .028, .026], 'skin', lambda p, suf=suf: arm_weight(p, suf), sides=8)
        smooth(fore)
    G.loft('Suzu obi', [(0, .006, .688, .212, .148), (0, .006, .700, .216, .151),
                        (0, .006, .780, .212, .147), (0, .006, .792, .208, .144)], 'rust', 'pelvis', n=16)
    G.loft('Obi lower edge', [(0, .006, .686, .213, .149), (0, .006, .698, .217, .152)], 'rust_dark', 'pelvis',
           n=16)
    G.loft('Obi upper edge', [(0, .006, .782, .213, .148), (0, .006, .794, .209, .145)], 'rust_dark', 'pelvis',
           n=16)
    # The folded cream cloth tucked into the obi on her right hip.
    panel = [(-.190, -.134, .790), (-.140, -.150, .786), (-.144, -.158, .712),
             (-.150, -.164, .636), (-.166, -.164, .624), (-.185, -.154, .634), (-.190, -.142, .712)]
    G.panel('Hip cloth', panel, [(0, 1, 2, 6), (2, 3, 4, 5, 6)], 'cream', 'cloth', .007)
    G.ribbon('Hip cloth fold', [(-.152, -.156, .784), (-.155, -.164, .712), (-.160, -.168, .628)],
             .009, 'cream_shadow', 'cloth', thickness=.002)
    # Baggy trousers, gathered above the ankle.
    for s, suf in ((1, 'L'), (-1, 'R')):
        leg = G.loft('Baggy trousers '+suf, [
            (s*.095, .004, .650, .095, .100), (s*.104, .002, .560, .112, .118),
            (s*.112, 0, .460, .125, .128), (s*.118, 0, .360, .128, .126),
            (s*.120, 0, .270, .118, .118), (s*.120, 0, .208, .096, .098),
            (s*.120, 0, .176, .070, .074), (s*.120, 0, .158, .062, .066)],
            'trousers', lambda p, suf=suf: leg_weight(p, suf), n=12, cap=False)
        smooth(leg)
        G.loft('Trouser gather '+suf, [(s*.120, 0, .150, .058, .062), (s*.120, 0, .172, .068, .072)],
               'trousers_dark', 'shin_'+suf, n=12)
        G.ribbon('Trouser crease '+suf, [(s*.108, -.108, .452), (s*.116, -.112, .360), (s*.119, -.098, .250),
                                         (s*.120, -.082, .194)], [.004, .006, .005, .003], 'trousers_light',
                 lambda p, suf=suf: leg_weight(p, suf), thickness=.002)
        G.ribbon('Trouser fold '+suf, [(s*.140, -.052, .410), (s*.150, -.030, .320), (s*.148, -.010, .232)],
                 [.003, .005, .004], 'trousers_dark',
                 lambda p, suf=suf: leg_weight(p, suf), thickness=.002)
    G.panel('Trouser seat', [(-.095, -.096, .652), (.095, -.096, .652), (.078, -.108, .580),
                             (0, -.112, .556), (-.078, -.108, .580)], [(0, 1, 2, 3, 4)], 'trousers', 'pelvis', .006)
    # The rope over the right shoulder, across the chest and back, knotted at her left hip.
    rope('Suzu bell rope', [
        (-.162, -.112, .992), (-.130, -.146, .940), (-.056, -.164, .882), (.028, -.166, .822),
        (.108, -.154, .762), (.158, -.142, .706), (.196, -.080, .706), (.198, .040, .706),
        (.158, .136, .706), (.116, .158, .766), (.030, .170, .836), (-.056, .166, .900),
        (-.128, .144, .958), (-.162, .092, 1.000), (-.170, -.010, 1.010), (-.162, -.112, .992)],
        .021, lambda p: torso_weights(p) if p[1] < 0 else 'chest', sides=8, samples=5)


def accessories():
    # The knot at her left hip: a rounded lump of rope with two short loose ends.
    ball('Rope knot', (.164, -.150, .704), .036, .032, .036, 'rope', 'bell', n=10, rings=4,
         face_colours=['rope', 'rope_light', 'rope_dark'])
    rope('Rope loose end A', [(.160, -.152, .694), (.168, -.158, .654), (.176, -.154, .618)],
         .013, 'bell', sides=6, samples=4)
    rope('Rope loose end B', [(.154, -.156, .690), (.146, -.162, .656), (.142, -.156, .628)],
         .012, 'bell', sides=6, samples=4)
    # The dull-gold bell-metal hand bell, its cord, clapper and little tassel.
    G.tube('Bell cord', [(.167, -.155, .698), (.170, -.159, .668), (.171, -.160, .656)],
           [.007, .006, .006], 'cord', 'bell', sides=5)
    G.loft('Hand bell', [(.178, -.164, .656, .010, .010), (.178, -.164, .648, .026, .026),
                         (.178, -.164, .630, .033, .033), (.178, -.164, .610, .037, .037),
                         (.178, -.164, .594, .041, .041), (.178, -.164, .586, .043, .043)],
           'bell', 'bell', n=12, cap=True)
    G.loft('Bell mouth rim', [(.178, -.164, .584, .044, .044), (.178, -.164, .592, .041, .041)],
           'bell_dark', 'bell', n=12, cap=False)
    ball('Bell clapper', (.178, -.164, .582), .012, .012, .012, 'cord', 'bell', n=8, rings=3)
    rope('Bell tassel', [(.178, -.164, .576), (.178, -.166, .558), (.178, -.166, .542)],
         .010, 'bell', col='rope', light='rope_light', dark='rope_dark', sides=6, samples=3)


def hands(s, suf):
    G.loft('Palm '+suf, [(s*.294, -.021, .588, .030, .024), (s*.300, -.024, .550, .034, .026),
                         (s*.301, -.026, .518, .030, .022)], 'skin', 'hand_'+suf, n=8)
    for i in range(4):
        x = s*(.277+i*.015)
        G.tube('Finger %d %s' % (i, suf),
               [(x, -.028, .526), (x+s*.002, -.038, .496), (x+s*.001, -.049, .474)],
               [.010, .009, .0065], 'skin', 'finger_%d_%s' % (i, suf), sides=5, depth=.88)
    G.tube('Thumb '+suf, [(s*.270, -.032, .548), (s*.250, -.050, .526), (s*.245, -.062, .506)],
           [.013, .011, .007], 'skin', 'thumb_'+suf, sides=6)


def build_model():
    G.PARTS.clear()
    G.PALETTE.update(PALETTE)
    head()
    clothes()
    accessories()
    for s, suf in ((1, 'L'), (-1, 'R')):
        hands(s, suf)
        from suzu_foot import build_foot
        build_foot(s, suf)
    return list(G.PARTS)
