"""Faceted geometry for Kiyo, the tide-reader, built from her approved sheet."""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'wanderer' / 'kit'))
import mesh_tools as G  # noqa: E402


PALETTE = {
    'skin': 'C4875B', 'skin_light': 'D79A6C', 'skin_shadow': 'A16543', 'skin_deep': '855033',
    'hair': '98948B', 'hair_light': 'AEA99F', 'hair_dark': '74716B', 'ink': '2F2927',
    'indigo': '303C52', 'indigo_light': '3C4B65', 'indigo_dark': '242D3F',
    'cream': 'E1D2B6', 'cream_light': 'F0E1C6', 'cream_shadow': 'C5B38F',
    'rust': 'A64C32', 'rust_light': 'B95B3B', 'rust_dark': '7E3523',
    'leather': '694832', 'leather_light': '80583D', 'leather_dark': '493024',
    'wood': '443027', 'wood_light': '684936', 'wood_dark': '2E201A',
    'straw': 'B69A64', 'straw_light': 'CEB27A', 'straw_dark': '92764C',
    'brass': 'B88B42', 'brass_light': 'D9AF60', 'brass_dark': '805B27',
    'shell': 'DCC9A7', 'shell_shadow': 'BAA47F',
}


def kiyo_material():
    material = bpy.data.materials.get('M_Kiyo_Palette')
    if material:
        return material
    material = bpy.data.materials.new('M_Kiyo_Palette')
    material.use_nodes = True
    material.use_backface_culling = False
    shader = material.node_tree.nodes.get('Principled BSDF')
    vertex_colour = material.node_tree.nodes.new('ShaderNodeVertexColor')
    vertex_colour.layer_name = 'Colour'
    material.node_tree.links.new(vertex_colour.outputs['Color'], shader.inputs['Base Color'])
    material.node_tree.links.new(vertex_colour.outputs['Color'], shader.inputs['Emission Color'])
    shader.inputs['Emission Strength'].default_value = .16
    shader.inputs['Roughness'].default_value = .95
    shader.inputs['Specular IOR Level'].default_value = .1
    return material


def weights_z(points, levels):
    return G.weights_z(points[2], levels)


def torso_weights(p):
    return weights_z(p, [(.54, 'pelvis'), (.64, 'spine'), (.76, 'spine_mid'), (.88, 'chest'), (1.03, 'chest')])


def skirt_weights(p):
    x, z = p[0], p[2]
    if z >= .565:
        return {'pelvis': 1}
    share = max(0.0, min(1.0, (.565 - z) / .13)) * .72
    if abs(x) < .018:
        return {'pelvis': 1 - share, 'thigh_L': share * .5, 'thigh_R': share * .5}
    return {'pelvis': 1 - share, ('thigh_L' if x > 0 else 'thigh_R'): share}


def leg_weights(p, side):
    return G.weights_z(p[2], [(.06, 'foot_' + side), (.095, 'shin_' + side), (.285, 'shin_' + side),
                              (.33, 'thigh_' + side), (.57, 'thigh_' + side)])


def arm_weights(p, side):
    return G.weights_z(p[2], [(.62, 'hand_' + side), (.68, 'forearm_' + side), (.80, 'forearm_' + side),
                              (.84, 'upperarm_' + side), (1.02, 'upperarm_' + side)])


def colour_table(faces, names):
    return [names[i % len(names)] for i in range(len(faces))]


def open_shell(name, rings, angles, col, weight, thickness=.014):
    """A faceted open cape/hair band with real thickness and closed rim."""
    m = len(angles)
    outer, inner = [], []
    for rx, ry, z in rings:
        for a in angles:
            outer.append((rx * math.sin(a), -ry * math.cos(a), z))
            inner.append((rx * .92 * math.sin(a), -ry * .92 * math.cos(a), z - thickness))
    n = len(outer)
    verts = outer + inner
    faces = []
    for j in range(len(rings) - 1):
        for i in range(m - 1):
            a = j * m + i
            b = j * m + i + 1
            faces.append((a, b, b + m, a + m))
            faces.append((n + a, n + a + m, n + b + m, n + b))
    for i in range(m - 1):
        faces.append((i, n + i, n + i + 1, i + 1))
        a = (len(rings) - 1) * m + i
        faces.append((a, a + 1, n + a + 1, n + a))
    for j in range(len(rings) - 1):
        a, b = j * m, (j + 1) * m
        faces.append((a, b, n + b, n + a))
        a, b = j * m + m - 1, (j + 1) * m + m - 1
        faces.append((a, n + a, n + b, b))
    return G.mesh(name, verts, faces, col, weight, face_colours=colour_table(faces, [col, col + '_light', col, col + '_dark']))


def closed_band(name, rings, col, weight, inner=.94):
    """A closed hollow belt: outer and inner walls with narrow top and bottom rims."""
    n = 12
    outer, inner_ring = [], []
    for rx, ry, z in rings:
        for i in range(n):
            angle = 2 * math.pi * i / n
            outer.append((rx * math.sin(angle), -ry * math.cos(angle), z))
            inner_ring.append((rx * inner * math.sin(angle), -ry * inner * math.cos(angle), z))
    count = len(outer)
    verts = outer + inner_ring
    faces, colours = [], []
    for j in range(len(rings) - 1):
        for i in range(n):
            nxt = (i + 1) % n
            a, b = j * n + i, j * n + nxt
            faces.append((a, b, b + n, a + n))
            colours.append('rust_dark' if j == 0 else ('rust_light' if i % 4 == 0 else 'rust' if i % 4 != 3 else 'rust_dark'))
            faces.append((count + a, count + a + n, count + b + n, count + b))
            colours.append('rust_dark')
    top, bottom = (len(rings) - 1) * n, 0
    for i in range(n):
        nxt = (i + 1) % n
        faces.append((top + i, count + top + i, count + top + nxt, top + nxt))
        colours.append('rust_light')
        faces.append((bottom + i, bottom + nxt, count + bottom + nxt, count + bottom + i))
        colours.append('rust_dark')
    return G.mesh(name, verts, faces, col, weight, face_colours=colours)


def head_and_face():
    head = G.loft('Broad angular head', [
        (0, -.006, 1.095, .036, .025),
        (0, -.018, 1.118, .100, .079),
        (0, -.015, 1.170, .143, .108),
        (0, -.006, 1.245, .158, .122),
        (0, .002, 1.322, .162, .126),
        (0, .006, 1.394, .143, .114),
        (0, .008, 1.440, .098, .079),
    ], 'skin', 'head', n=16)
    for polygon in head.data.polygons:
        polygon.use_smooth = True
    neck = G.loft('Short neck', [(0, .004, .995, .043, .039), (0, .005, 1.115, .052, .045)],
                  'skin_shadow', 'neck', n=10)
    for polygon in neck.data.polygons:
        polygon.use_smooth = True

    # A small faceted nose is the only projecting feature on the quiet face.
    nose = G.mesh('Rounded triangular nose', [
        (-.018, -.122, 1.248), (.018, -.122, 1.248), (0, -.123, 1.286),
        (0, -.148, 1.239), (0, -.130, 1.217),
    ], [(0, 1, 3), (1, 4, 3), (4, 0, 3), (0, 2, 1), (2, 0, 3), (2, 3, 1)], 'skin_light', 'head',
        face_colours=['skin_light', 'skin_shadow', 'skin_shadow', 'skin_light', 'skin_shadow', 'skin_shadow'])

    for s, side in ((1, 'L'), (-1, 'R')):
        G.box('Vertical pill eye ' + side, (s * .061, -.128, 1.276), (.017, .003, .034), 'ink', 'head', .002,
              rotation=(0, 0, s * .06))
        G.ribbon('Level grey brow ' + side, [(s * .032, -.127, 1.315), (s * .096, -.102, 1.316)], .005,
                 'hair_dark', 'head', thickness=.0015)
        G.ribbon('Crow foot outer ' + side, [(s * .101, -.108, 1.281), (s * .122, -.088, 1.291)], .0018,
                 'skin_shadow', 'head', thickness=.0008)
        G.ribbon('Crow foot lower ' + side, [(s * .100, -.108, 1.272), (s * .118, -.090, 1.270)], .0018,
                 'skin_shadow', 'head', thickness=.0008)
        G.ribbon('Smile crease ' + side, [(s * .056, -.122, 1.196), (s * .076, -.107, 1.187)], .0022,
                 'skin_shadow', 'head', thickness=.0006)
        ear_points = [(s * .150, -.035, 1.275), (s * .157, -.060, 1.286), (s * .160, -.058, 1.244),
                      (s * .157, -.027, 1.216), (s * .149, -.006, 1.236), (s * .149, -.008, 1.270)]
        G.panel('Faceted ear ' + side, ear_points, [(0, 1, 2, 3, 4, 5)], 'skin_shadow', 'head', .013, (s, 0, 0))
        inner = [(s * .160, -.035, 1.263), (s * .164, -.048, 1.270), (s * .164, -.043, 1.244),
                 (s * .158, -.024, 1.232)]
        G.panel('Ear hollow ' + side, inner, [(0, 1, 2, 3)], 'skin_deep', 'head', .001, (s, 0, 0))
        # Cream shell earring with a brass pin, as on the sheet.
        ring = [(s * .154, -.033, 1.186), (s * .160, -.052, 1.180), (s * .159, -.049, 1.153),
                (s * .152, -.030, 1.140), (s * .146, -.011, 1.153), (s * .147, -.014, 1.180)]
        G.panel('Scallop shell earring ' + side, ring, [(0, 1, 2, 3, 4, 5)], 'shell', 'head', .009, (s, 0, 0))
        G.box('Earring brass pin ' + side, (s * .154, -.032, 1.190), (.010, .009, .009), 'brass', 'head', .002)

    G.ribbon('Quiet closed mouth', [(-.027, -.125, 1.174), (0, -.132, 1.169), (.028, -.124, 1.176)],
             [.003, .004, .003], 'rust_dark', 'head', thickness=.001)
    G.ribbon('Lower lip light', [(-.020, -.126, 1.166), (0, -.133, 1.161), (.021, -.125, 1.166)],
             [.002, .003, .002], 'skin_light', 'head', thickness=.0007)


def hat():
    n = 12
    apex = (0, 0, 1.555)
    inner_top = [(.120 * math.sin(2 * math.pi * i / n), -.120 * math.cos(2 * math.pi * i / n), 1.487) for i in range(n)]
    outer_top = []
    outer_bottom = []
    for i in range(n):
        radius = .292 + (.009 if i % 3 == 0 else 0)
        x = radius * math.sin(2 * math.pi * i / n)
        y = -radius * math.cos(2 * math.pi * i / n) - .010
        z = 1.389 + (.007 if i % 2 else 0)
        outer_top.append((x, y, z))
        outer_bottom.append((x * .985, y * .985, z - .020))
    inner_bottom = [(.094 * math.sin(2 * math.pi * i / n), -.094 * math.cos(2 * math.pi * i / n), 1.404) for i in range(n)]
    verts = [apex] + inner_top + outer_top + outer_bottom + inner_bottom
    A, T, O, B, I = 0, 1, 1 + n, 1 + 2 * n, 1 + 3 * n
    faces, colours = [], []
    for i in range(n):
        faces.append((A, T + i, T + (i + 1) % n))
        colours.append('indigo_light' if i % 3 == 0 else 'indigo')
    for i in range(n):
        j = (i + 1) % n
        faces.append((T + i, O + i, O + j, T + j))
        colours.append(['indigo', 'indigo_light', 'indigo_dark'][i % 3])
    for i in range(n):
        j = (i + 1) % n
        faces.append((O + i, B + i, B + j, O + j))
        colours.append('indigo_dark')
    for i in range(n):
        j = (i + 1) % n
        faces.append((B + i, I + i, I + j, B + j))
        colours.append('indigo_dark' if i % 2 else 'indigo_light')
    G.mesh('Twelve-panel indigo weather hat', verts, faces, 'indigo', 'hat', face_colours=colours)

    for i in range(6):
        a = 2 * math.pi * i / 6
        G.box('Brass brim rivet %d' % i, (.225 * math.sin(a), -.225 * math.cos(a) - .008, 1.384),
              (.014, .014, .013), 'brass', 'hat', .002, rotation=(0, 0, a))
    # Rust chin cord, with a readable knot below the chin.
    for s in (-1, 1):
        G.tube('Hat chin cord ' + str(s), [(s * .170, -.075, 1.386), (s * .154, -.076, 1.140),
                                            (s * .044, -.127, 1.064)], [.0028, .0028, .0028],
               'rust_dark', 'head', sides=5)
    G.box('Chin cord knot', (0, -.137, 1.058), (.021, .018, .022), 'rust_dark', 'head', .003,
          rotation=(0, 0, .18))
    G.ribbon('Short cord tail', [(.008, -.143, 1.052), (.016, -.143, 1.023)], [.006, .003], 'rust_dark', 'head', thickness=.002)


def hair():
    angles = [1.02 + (2 * math.pi - 2.04) * i / 13 for i in range(14)]
    open_shell('Silver hair under hat', [(.145, .120, 1.125), (.157, .132, 1.245),
                                         (.154, .134, 1.360), (.118, .108, 1.427)], angles, 'hair', 'head', .015)
    # Broad side locks, not strands.
    for s, side in ((1, 'L'), (-1, 'R')):
        G.panel('Temple lock ' + side, [
            (s * .126, -.058, 1.398), (s * .171, -.035, 1.344), (s * .174, -.023, 1.265),
            (s * .141, -.030, 1.276), (s * .128, -.044, 1.330),
        ], [(0, 1, 2, 3, 4)], 'hair', 'head', .015, (s, 0, 0))
        G.panel('Lower side lock ' + side, [
            (s * .148, -.030, 1.282), (s * .177, -.012, 1.214), (s * .164, .010, 1.145),
            (s * .145, -.005, 1.168), (s * .138, -.022, 1.235),
        ], [(0, 1, 2, 3, 4)], 'hair_dark', 'head', .013, (s, 0, 0))
        G.panel('Nape side lock ' + side, [
            (s * .140, .020, 1.400), (s * .184, .042, 1.350), (s * .188, .070, 1.260),
            (s * .165, .082, 1.160), (s * .145, .050, 1.180), (s * .138, .015, 1.280),
        ], [(0, 1, 2, 3, 4, 5)], 'hair', 'head', .018, (s, 0, 0))
        G.panel('Forward silver wedge ' + side, [
            (s * .074, -.113, 1.412), (s * .130, -.098, 1.403), (s * .153, -.073, 1.350),
            (s * .111, -.097, 1.356), (s * .065, -.117, 1.380),
        ], [(0, 1, 2, 3, 4)], 'hair', 'head', .014, (0, -1, 0))
    G.panel('Swept centre fringe', [(-.026, -.126, 1.425), (.040, -.126, 1.426), (.095, -.104, 1.400),
                                    (.050, -.116, 1.389), (-.006, -.127, 1.397), (-.050, -.118, 1.407)],
            [(0, 1, 2, 3, 4, 5)], 'hair_light', 'head', .012, (0, -1, 0))
    # Low faceted bun at the nape, visible in the back view and under the brim.
    bun = G.loft('Low silver bun', [(0, .090, 1.205, .052, .038), (0, .124, 1.172, .076, .055),
                                    (0, .144, 1.136, .054, .040), (0, .150, 1.116, .018, .014)],
                 'hair', 'hair_bun', n=8)
    for polygon in bun.data.polygons:
        polygon.use_smooth = False
    G.loft('Rust bun tie', [(0, .086, 1.207, .055, .041), (0, .098, 1.220, .049, .037)], 'rust', 'hair_bun', n=8)
    G.ribbon('Short nape lock', [(-.035, .105, 1.188), (-.020, .143, 1.089)], [.022, .010], 'hair_dark', 'head',
             thickness=.010)


def shoulder_cape():
    rings = [(.108, .088, 1.048), (.222, .165, .985), (.282, .208, .905)]
    angles = [.72 + (2 * math.pi - 1.44) * i / 15 for i in range(16)]
    def cape_weights(p):
        if abs(p[0]) < .018:
            return {'chest': .5, 'cape_L': .25, 'cape_R': .25}
        return {('cape_L' if p[0] > 0 else 'cape_R'): 1}
    open_shell('Layered shoulder mantle', rings, angles, 'indigo', cape_weights, .018)


def coat_and_torso():
    G.loft('Deep indigo wrapped coat', [(0, 0, .525, .158, .103), (0, 0, .610, .181, .115),
                                        (0, 0, .735, .180, .109), (0, 0, .850, .171, .102),
                                        (0, 0, .955, .183, .113), (0, 0, 1.010, .138, .088)],
           'indigo', torso_weights, n=12)
    # Flared coat skirt; the two front flaps sit proud of the volume underneath.
    G.loft('Flared coat skirt', [(0, 0, .525, .158, .103), (0, 0, .480, .207, .146),
                                 (0, 0, .430, .226, .159)], 'indigo_dark', skirt_weights, n=12, cap=False)
    for s, side in ((1, 'L'), (-1, 'R')):
        G.panel('Coat front flap ' + side, [
            (s * .010, -.108, .785), (s * .169, -.096, .785), (s * .213, -.104, .463),
            (s * .105, -.146, .430), (s * .021, -.148, .492),
        ], [(0, 1, 2, 3, 4)], 'indigo_light' if s > 0 else 'indigo', skirt_weights, .010, (0, -1, 0))
    G.ribbon('Coat centre seam', [(0, -.149, .780), (0, -.154, .620), (0, -.150, .450)],
             [.012, .013, .009], 'indigo_dark', skirt_weights, thickness=.004)
    # Cream under-collar makes the V on the sheet.
    G.ribbon('Cream collar left', [(-.078, -.083, 1.050), (-.034, -.130, .992), (-.004, -.146, .952)],
             [.024, .022, .015], 'cream', 'chest', thickness=.005)
    G.ribbon('Cream collar right', [(.078, -.083, 1.050), (.034, -.130, .992), (.004, -.146, .952)],
             [.024, .022, .015], 'cream', 'chest', thickness=.005)
    G.ribbon('Indigo lapel left', [(-.124, -.099, 1.030), (-.064, -.134, .952), (-.028, -.145, .884)],
             [.032, .028, .018], 'indigo_dark', 'chest', thickness=.007)
    G.ribbon('Indigo lapel right', [(.124, -.099, 1.030), (.064, -.134, .952), (.026, -.145, .884)],
             [.032, .028, .018], 'indigo_dark', 'chest', thickness=.007)
    G.ribbon('Coat wrap edge left', [(-.124, -.116, .984), (-.065, -.130, .897), (-.026, -.139, .803)],
             [.012, .011, .008], 'indigo_dark', torso_weights, thickness=.004)
    G.ribbon('Coat wrap edge right', [(.124, -.116, .984), (.065, -.130, .897), (.030, -.138, .803)],
             [.012, .011, .008], 'indigo_dark', torso_weights, thickness=.004)

    # Double rust sash with a compact knot.
    closed_band('Double rust sash', [(.184, .116, .759), (.188, .120, .794), (.180, .115, .836)],
                'rust', torso_weights)
    G.ribbon('Sash front overlap', [(-.148, -.121, .808), (.004, -.132, .806), (.146, -.120, .800)],
             [.007, .009, .007], 'rust_light', torso_weights, thickness=.003)


def arms_and_hands():
    for s, side in ((1, 'L'), (-1, 'R')):
        shoulder = (s * .112, 0, 1.000)
        elbow = (s * .188, -.004, .812)
        wrist = (s * .238, -.010, .663)
        G.tube('Wide coat sleeve ' + side, [shoulder, elbow, wrist], [.058, .068, .050], 'indigo',
               lambda p, side=side: arm_weights(p, side), sides=8)
        G.tube('Cream turned cuff ' + side, [(s * .224, -.008, .707), (s * .237, -.009, .673),
                                             (s * .242, -.010, .650)], [.060, .063, .058], 'cream_light',
               'forearm_' + side, sides=8)
        G.tube('Bare forearm ' + side, [(s * .235, -.009, .691), (s * .243, -.010, .655)],
               [.026, .024], 'skin', 'hand_' + side, sides=7)
        # Faceted palm and five digits; all digits ride the hand bone.
        x = s * .247
        G.loft('Faceted palm ' + side, [(x, -.011, .656, .021, .018), (x + s * .005, -.015, .618, .028, .021),
                                         (x + s * .006, -.020, .583, .024, .017)], 'skin', 'hand_' + side, n=8)
        for i in range(4):
            fx = x + s * (-.016 + i * .011)
            G.tube('Finger %d %s' % (i, side), [(fx, -.021, .598), (fx + s * .002, -.028, .563),
                                                 (fx + s * .001, -.026, .535)], [.006, .0055, .0045], 'skin_light',
                   'hand_' + side, sides=5)
        G.tube('Thumb ' + side, [(x - s * .017, -.006, .621), (x - s * .033, -.024, .596),
                                  (x - s * .035, -.036, .576)], [.009, .007, .005], 'skin', 'hand_' + side, sides=6)


def legs_and_feet():
    for s, side in ((1, 'L'), (-1, 'R')):
        G.loft('Wide cropped trouser ' + side, [(s * .075, 0, .570, .082, .088), (s * .083, -.002, .495, .094, .100),
                                                 (s * .087, -.006, .390, .090, .095), (s * .085, -.006, .318, .071, .073)],
               'indigo', lambda p, side=side: leg_weights(p, side), n=8, cap=False, phase=math.pi / 8)
        G.loft('Trouser dark hem ' + side, [(s * .085, -.006, .300, .073, .075), (s * .085, -.006, .324, .075, .077)],
               'indigo_dark', 'shin_' + side, n=8, phase=math.pi / 8)
        G.ribbon('Broad trouser crease ' + side, [(s * .102, -.088, .548), (s * .112, -.096, .420), (s * .099, -.083, .322)],
                 [.028, .026, .018], 'indigo_light', lambda p, side=side: leg_weights(p, side), thickness=.002)
        G.loft('Cream shin wrap ' + side, [(s * .095, .002, .075, .047, .042), (s * .096, .002, .150, .045, .041),
                                            (s * .092, .000, .245, .049, .044), (s * .087, -.004, .302, .053, .048)],
               'cream', 'shin_' + side, n=8)
        for z, tilt in ((.105, .18), (.155, -.14), (.205, -.10), (.255, .12), (.292, -.06)):
            G.ribbon('Wrap crossing %s %.3f' % (side, z), [(s * .140, -.027, z + tilt), (s * .119, -.044, z + .014),
                                                           (s * .095, -.048, z + tilt * .3), (s * .071, -.036, z - .010),
                                                           (s * .050, -.018, z + tilt * .5)], [.010, .012, .014, .012, .008],
                     'cream_shadow' if int(z * 1000) % 2 else 'cream_light', 'shin_' + side, thickness=.0025)
        # Flat straw sole, bare foot and two broad dark straps.
        G.box('Straw sandal sole ' + side, (s * .095, -.052, .022), (.115, .272, .030), 'straw', 'foot_' + side, .005)
        G.box('Sandal pale top ' + side, (s * .095, -.052, .039), (.107, .258, .007), 'straw_light', 'foot_' + side, .002)
        G.box('Bare foot ' + side, (s * .095, -.060, .064), (.081, .180, .046), 'skin', 'foot_' + side, .014)
        G.box('Big toe ' + side, (s * .068, -.154, .058), (.026, .052, .034), 'skin_light', 'toe_' + side, .010)
        for i in range(3):
            G.box('Toe %d %s' % (i, side), (s * (.101 + i * .018), -.153 + i * .004, .056),
                  (.017, .043, .028), 'skin', 'toe_' + side, .007)
        for y, width in ((-.020, .018), (-.070, .020)):
            G.box('Sandal strap %s %.3f' % (side, y), (s * .095, y, .088), (width, .080, .012), 'leather', 'foot_' + side, .002,
                  rotation=(.16, 0, 0))
        G.ribbon('Sandal toe thong ' + side, [(s * .095, -.016, .094), (s * .095, -.060, .086), (s * .095, -.119, .062)],
                 [.008, .008, .005], 'leather_dark', 'foot_' + side, thickness=.002)


def shell_counter(name, x, y, z, size=.024):
    points = [(x, y, z + size), (x + size * .62, y - .002, z + size * .58),
              (x + size * .62, y - .003, z + size * .08), (x, y - .004, z - size * .14),
              (x - size * .62, y - .003, z + size * .08), (x - size * .62, y - .002, z + size * .58)]
    G.panel(name, points, [(0, 1, 2, 3, 4, 5)], 'shell', 'tide_board', .005, (0, -1, 0))
    for dx in (-.008, 0, .008):
        G.ribbon(name + ' groove %.3f' % dx, [(x + dx, y - .006, z - .004), (x + dx * 1.4, y - .005, z + size * .56)],
                 [.0018, .0012], 'shell_shadow', 'tide_board', thickness=.0008)


def tide_board_and_bag():
    G.box('Wooden tide-board', (.160, -.142, .650), (.105, .027, .235), 'wood', 'tide_board', .006, rotation=(0, .02, 0))
    G.box('Tide-board top rail', (.160, -.145, .759), (.112, .033, .018), 'wood_light', 'tide_board', .003)
    G.panel('Tide-board carved face', [(.115, -.157, .745), (.205, -.157, .745), (.200, -.160, .545),
                                        (.120, -.160, .545)], [(0, 1, 2, 3)], 'wood_light', 'tide_board', .003, (0, -1, 0))
    for x in (.130, .190):
        G.box('Brass tide pin %.3f' % x, (x, -.161, .728), (.014, .009, .014), 'brass', 'tide_board', .004)
    for z in (.694, .634, .574, .514):
        shell_counter('Tide shell counter %.3f' % z, .160, -.160, z, .023)
    # Rope loop from the board to the sash.
    G.tube('Tide-board rope loop', [(.108, -.137, .760), (.104, -.144, .792), (.132, -.150, .807),
                                     (.164, -.146, .790), (.177, -.137, .760)], [.005, .005, .005, .005, .005],
           'straw_dark', 'tide_board', sides=5)

    # Satchel on the opposite hip, with a diagonal shoulder strap.
    G.ribbon('Satchel shoulder strap', [(-.080, -.072, 1.018), (-.015, -.130, .930), (.088, -.126, .818),
                                         (.178, -.090, .702)], [.026, .027, .026, .022], 'leather', torso_weights,
             thickness=.006)
    G.box('Leather satchel', (.190, -.012, .590), (.132, .078, .150), 'leather', 'satchel', .010, rotation=(0, .08, .05))
    G.panel('Satchel flap', [(.123, -.013, .660), (.258, -.013, .660), (.252, -.005, .610),
                              (.190, -.002, .590), (.128, -.005, .610)], [(0, 1, 2, 3, 4)], 'leather_light',
            'satchel', .008, (0, -1, 0))
    G.box('Satchel brass clasp', (.190, -.057, .626), (.025, .012, .018), 'brass', 'satchel', .003)
    G.box('Rolled chart at hip', (.221, -.042, .632), (.041, .112, .041), 'cream_shadow', 'satchel', .014, rotation=(.08, 0, 0))
    G.box('Bamboo chart case', (.245, -.064, .560), (.034, .083, .034), 'straw_dark', 'satchel', .010, rotation=(.05, 0, 0))
    G.box('Bamboo case brass cap', (.245, -.108, .557), (.038, .015, .038), 'brass', 'satchel', .005, rotation=(.05, 0, 0))


def tide_staff():
    x, y = -.340, .060
    G.tube('Dark bamboo tide staff', [(x, y, .018), (x, y, .360), (x + .002, y, .820), (x, y, 1.328)],
           [.014, .0145, .014, .0135], 'wood', 'staff', sides=8)
    for z in (.240, .430, .620, .810, 1.000, 1.175):
        G.tube('Staff pale segment %.3f' % z, [(x, y, z - .006), (x, y, z + .006)], [.016, .016],
               'wood_light', 'staff', sides=8)
    # Eight broad carved notches on the front face, matching the construction sheet.
    for i, z in enumerate((.280, .385, .495, .605, .715, .825, .935, 1.045)):
        G.panel('Carved tide notch %d' % i, [(x - .010, y - .015, z + .013), (x + .010, y - .015, z + .006),
                                              (x + .010, y - .015, z - .013), (x - .010, y - .015, z - .006)],
                [(0, 1, 2, 3)], 'wood_light', 'staff', .003, (0, -1, 0))
        G.panel('Side tide notch %d' % i, [(x - .0145, y - .010, z + .013), (x - .0145, y + .010, z + .006),
                                           (x - .0145, y + .010, z - .013), (x - .0145, y - .010, z - .006)],
                [(0, 1, 2, 3)], 'wood_light', 'staff', .003, (-1, 0, 0))
    G.loft('Bell-metal staff cap', [(x, y, 1.318, .021, .021), (x, y, 1.352, .022, .022),
                                     (x, y, 1.365, .017, .017)], 'brass', 'staff', n=8)
    G.tube('Staff cap rope', [(x - .018, y, 1.320), (x, y - .022, 1.310), (x + .018, y, 1.318)],
           [.004, .004, .004], 'rust_dark', 'staff', sides=5)
    # A tied cream shell/tassel under the cap.
    G.loft('Staff shell tassel', [(x, y - .026, 1.286, .010, .010), (x, y - .033, 1.246, .021, .017),
                                   (x, y - .030, 1.205, .012, .010)], 'shell', 'staff', n=6)
    G.ribbon('Staff shell ties', [(x - .010, y - .020, 1.305), (x - .003, y - .033, 1.265),
                                  (x + .009, y - .026, 1.228)], [.0025, .0025, .002], 'cream_shadow', 'staff', thickness=.001)


def build_model():
    G.PARTS.clear()
    G.PALETTE.update(PALETTE)
    G.material = kiyo_material
    head_and_face()
    hair()
    hat()
    coat_and_torso()
    shoulder_cape()
    arms_and_hands()
    legs_and_feet()
    tide_board_and_bag()
    tide_staff()
    return list(G.PARTS)
