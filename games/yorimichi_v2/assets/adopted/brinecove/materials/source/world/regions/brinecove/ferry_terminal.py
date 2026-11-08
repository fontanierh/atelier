"""Brinecove ferry berth, manoeuvres and terminal assembly in the owning region frame."""
import math

import numpy as np

BRINECOVE_PIER = (-238.0, 13.0)       # west pier centre x and width (brinecove/layout.py PIERS)
BRINECOVE_BERTH_Y = 10.0
BRINECOVE_LANE = 4.0                  # the arrival's first leg runs this far west of the berth line, east of the rowboat
                                      # moored at (-270, -145)
BRINECOVE_JOG_Y = -95.0               # once the stern has passed that rowboat, the ship glides west...
BRINECOVE_STANDOFF = 13.0             # ...to this line west of the berth, clear of the rowboat moored at (-250, -40)
BRINECOVE_CRAB = 40.0                 # west of the berth, a 180-degree pivot clears the west pier by its full radius



def layout(world, geometry):
    px, pw = BRINECOVE_PIER
    tris = world['solid']
    if len(tris):
        lo, hi = tris.min(1), tris.max(1)
        relocated_boat = (hi[:, 0] >= -255.0) & (lo[:, 0] <= -245.0) & (hi[:, 1] >= -46.0) & (lo[:, 1] <= -34.0)
        world['solid'] = tris[~relocated_boat]
        world['solid_label'] = world['solid_label'][~relocated_boat]
    face_x = px - pw / 2 - 0.5            # fender piles on the pier's west face
    cx = face_x - geometry.FENDER - geometry.ship.BEAM
    berth = (cx, BRINECOVE_BERTH_Y, 90.0)  # bow north; starboard (east) side to the pier
    gx, gy = geometry.gate_point(berth, -1)
    landing = [(face_x, gy - 3.6), (face_x + 3.4, gy - 3.6), (face_x + 3.4, gy + 3.6), (face_x, gy + 3.6)]
    # The berth is the pier's west face along the hull: fender piles, pier deck edge and its piles.
    half = (geometry.ship.STEM - geometry.ship.STERN) / 2 + 4.0
    zone = [(face_x - 0.05, BRINECOVE_BERTH_Y - half - 20.0), (px + pw / 2, BRINECOVE_BERTH_Y - half - 20.0),
            (px + pw / 2, BRINECOVE_BERTH_Y + half), (face_x - 0.05, BRINECOVE_BERTH_Y + half)]
    deck = geometry.levels(world, geometry.rect_points(face_x + 0.6, gy - 12.0, face_x + 12.5, gy + 18.0), 5.6)
    walk = {'world_cuts': [], 'pier_deck_z': round(float(np.nanmedian(deck)), 3), 'pier_deck_range': [round(float(np.nanmin(deck)), 3), round(float(np.nanmax(deck)), 3)]}
    return berth, (gx, gy), landing, face_x, zone, walk


def moves(berth):
    bx, by, _ = berth
    # Arrival: straight north up the channel 4 m west of the berth line, then a 16 m aligned berthing leg easing
    # starboard onto the fenders as the ship decelerates to rest.
    arrival_start = (bx - BRINECOVE_LANE, -250.0, 90.0)
    arrival = [('ahead', (by - 16.0) - (-250.0)), ('berth', 16.0, -BRINECOVE_LANE)]
    # Departure: ease astern 16 m off the pier while drifting 4 m to port, curve astern past the pier tip into the
    # west basin (total astern < 116 m <= 120 m) to a full stop, then swing ahead on an 80 m radius port arc to south.
    l1 = 1800.0 * math.radians(2.0)
    l2 = 80.0 * math.radians(27.0)
    departure = [
        ('berth', -16.0, BRINECOVE_LANE),
        ('arc', -1800.0, -2.0, round(l1 * 0.20, 4)),
        ('arc', -80.0, 27.0, round(l2 * 0.20, 4)),
        ('ahead', -2.5, 0.5),
        ('ahead', 2.5),
        ('arc', 80.0, 155.0),
        ('ahead', 110.305024),
    ]
    return (arrival_start, arrival), (berth, departure)

CONSTRUCTORS = {'FT_BC_Landing': 'make_landing', 'FT_BC_Brow': 'make_brow', 'FT_BC_Fenders': 'make_fenders', 'FT_BC_Pavilion': 'make_pavilion', 'FT_BC_TicketHut': 'make_ticket_hut', 'FT_BC_Props': 'make_props'}
MESH_ORDER = ('FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Fenders', 'FT_BC_Props')
CONSTRUCTION_FIELDS = {'FT_BC_Landing': ['deck', 'foot_y', 'gy', 'lx0', 'lx1', 'ly0', 'ly1', 'sx_'], 'FT_BC_Brow': ['gx', 'gy', 'lx0'], 'FT_BC_Fenders': ['PW', 'deck', 'face', 'px_'], 'FT_BC_Pavilion': ['deck', 'px0', 'px1', 'py0', 'py1'], 'FT_BC_TicketHut': ['deck', 'hx0', 'hx1', 'hy0', 'hy1', 'wh', 'z1'], 'FT_BC_Props': ['PW', 'deck', 'gy'], 'collision': ['PW', 'deck', 'hx0', 'hx1', 'hy0', 'hy1', 'lx0', 'lx1', 'ly0', 'ly1', 'px0', 'px1', 'px_', 'py0', 'py1', 'wh', 'z1'], 'walk': ['PW', 'deck', 'face', 'foot_y', 'gx', 'gy', 'hx0', 'hx1', 'hy1', 'lx0', 'ly1', 'sx_']}


def construction_plan(kit):
    """Shared exact scalar/layout data; this function never constructs geometry."""
    b = kit.SITE['brinecove']['berth']; gx, gy, _ = b['gate']; face = b['face']; deck = b['pier_deck_z']
    PW = face + 0.5
    lx0, lx1, ly0, ly1 = PW, PW + 3.4, gy - 3.6, gy + 3.6
    sx_ = (lx0 + lx1) / 2; foot_y = ly1 + 6 * 0.30
    px_ = face - 0.07
    px0, px1, py0, py1 = PW + 6.0, PW + 12.2, gy - 9.0, gy + 3.0
    hx0, hx1, hy0, hy1 = PW + 6.0, PW + 11.0, gy + 6.0, gy + 10.5
    wh = 2.3; z1 = deck + 0.85
    return {'PW': PW, 'b': b, 'deck': deck, 'face': face, 'foot_y': foot_y, 'gx': gx, 'gy': gy, 'hx0': hx0, 'hx1': hx1, 'hy0': hy0, 'hy1': hy1, 'lx0': lx0, 'lx1': lx1, 'ly0': ly0, 'ly1': ly1, 'px0': px0, 'px1': px1, 'px_': px_, 'py0': py0, 'py1': py1, 'sx_': sx_, 'wh': wh, 'z1': z1}


def make_landing(kit, data):
    deck = data['deck']
    foot_y = data['foot_y']
    gy = data['gy']
    lx0 = data['lx0']
    lx1 = data['lx1']
    ly0 = data['ly0']
    ly1 = data['ly1']
    sx_ = data['sx_']
    Lm = kit.F.Mesh('FT_BC_Landing')
    # Boarding landing at sill height on the pier's west edge, a 7-riser stair down to the pier deck to the east.
    # A framed timber stage, closed underneath (nobody walks into the 1.7 m void): a plank deck overhanging a fascia,
    # posts on stone footings, recessed board infill and one diagonal brace per bay, so its faces read as joinery.
    # No two of its members share a face plane: the core stands 1 cm into the plinth; the posts' heads run 2.5 cm
    # into the deck; each corner has one post, inset from both edges; boards and fascias along the x-facing sides sit
    # 5 mm lower than those along the y-facing sides where they cross at the corners, and the fascias stop 1 cm short
    # of the deck's edges.
    ins, fz = 0.16, kit.SILL - 0.22
    Lm.prism(kit.F.rect(lx0 + ins, ly0 + ins, lx1 - ins, ly1 - ins), deck + 0.17, fz, kit.TIMBER_DARK)
    Lm.prism(kit.F.rect(lx0, ly0, lx1, ly1), fz, kit.SILL, kit.TIMBER, top=kit.PLANK)
    Lm.prism(kit.F.rect(lx0 + 0.04, ly0 + 0.04, lx1 - 0.04, ly1 - 0.04), deck, deck + 0.18, kit.STONE)    # plinth
    corners = set()
    for (ax, ay), (bx, by_) in (((lx0, ly0), (lx1, ly0)), ((lx1, ly0), (lx1, ly1)), ((lx0, ly1), (lx1, ly1)),
                                ((lx0, ly0), (lx0, ly1))):
        L = math.dist((ax, ay), (bx, by_)); n = max(1, round(L / 2.0))
        ox, oy = (0.0, -1.0) if ay == by_ == ly0 else (1.0, 0.0) if ax == bx == lx1 else (0.0, 1.0) if ay == by_ else (-1.0, 0.0)
        tx, ty = (bx - ax) / L, (by_ - ay) / L
        dz = -0.005 if ax == bx else 0.0
        for k in range(int(L / 0.32)):                      # infill boards, proud of the core, behind the posts
            u = (k + 0.5) * L / int(L / 0.32)
            Lm.box((ax + tx * u - ox * (ins - 0.03), ay + ty * u - oy * (ins - 0.03), (deck + 0.18 + fz) / 2 + dz),
                   (abs(tx) * 0.26 + abs(ox) * 0.03 + 0.001, abs(ty) * 0.26 + abs(oy) * 0.03 + 0.001, fz - deck - 0.18), kit.TIMBER_DARK)
        for k in range(n + 1):
            u = k * L / n; px, py = ax + tx * u - ox * 0.06, ay + ty * u - oy * 0.06
            if k in (0, n):                                  # a corner: one post, inset from both edges
                c = (round(px + tx * (0.06 if k == 0 else -0.06), 4), round(py + ty * (0.06 if k == 0 else -0.06), 4))
                if c not in corners:
                    corners.add(c); kit.post(Lm, c[0], c[1], deck, fz + 0.025, s=0.22, footing=True)
            else:
                kit.post(Lm, px, py, deck, fz + 0.025, s=0.22, footing=True)
            if k < n:                                          # one brace per bay, alternating
                v = (k + 1) * L / n; qx, qy = ax + tx * v - ox * 0.06, ay + ty * v - oy * 0.06
                lo, hi = (deck + 0.3, fz - 0.08) if k % 2 == 0 else (fz - 0.08, deck + 0.3)
                Lm.beam((px + tx * 0.12, py + ty * 0.12, lo), (qx - tx * 0.12, qy - ty * 0.12, hi), 0.09, 0.12, kit.TIMBER)
        Lm.beam((ax - ox * 0.05 + tx * 0.01, ay - oy * 0.05 + ty * 0.01, fz - 0.08 + dz),
                (bx - ox * 0.05 - tx * 0.01, by_ - oy * 0.05 - ty * 0.01, fz - 0.08 + dz), 0.12, 0.18, kit.TIMBER)
    # The stair runs north along the pier's west edge, so the walkway between it and the pavilion stays 2.6 m wide.
    r = (kit.SILL - deck) / 7
    st = kit.solid_stair(Lm, (sx_, foot_y), (0, -1), 2.4, deck, [7], r, tread=0.30)
    kit.rail_line(Lm, [(sx_ - 1.25, ly1 - 0.1), (lx0 + 0.1, ly1 - 0.1), (lx0 + 0.1, gy + kit.BROW_W / 2 + 0.1)], kit.SILL)
    kit.rail_line(Lm, [(lx0 + 0.1, gy - kit.BROW_W / 2 - 0.1), (lx0 + 0.1, ly0 + 0.1), (lx1 - 0.1, ly0 + 0.1), (lx1 - 0.1, ly1 - 0.1),
                   (sx_ + 1.25, ly1 - 0.1)], kit.SILL)
    for s in (-1, 1):
        xx = sx_ + s * 1.27
        Lm.beam((xx, foot_y + 0.1, deck + 0.95), (xx, ly1, kit.SILL + 0.95), 0.08, 0.1, kit.TIMBER)
        Lm.box((xx, foot_y + 0.1, deck + 0.5), (0.12, 0.12, 1.0), kit.TIMBER)
    return Lm, {'stair': st}


def make_brow(kit, data):
    gx = data['gx']
    gy = data['gy']
    lx0 = data['lx0']
    B = kit.F.Mesh('FT_BC_Brow')
    br = kit.brow(B, (lx0, gy), (gx, gy), (-1.0, 0.0), kit.SILL)
    return B, {'brow': br}


def make_fenders(kit, data):
    PW = data['PW']
    deck = data['deck']
    face = data['face']
    px_ = data['px_']
    Fd = kit.F.Mesh('FT_BC_Fenders')
    # Fenders along the pier's west face where the hull lies (y -30..50): black piles standing off the pier edge on
    # timber chocks, and tyres between them hung on ropes made fast to the pier's deck edge, FENDER_GAP off the hull.
    tx_ = face - (kit.FS.FENDER - kit.FENDER_GAP) + 0.13       # tyre centre: its outer face FENDER_GAP off the hull
    for k in range(11):
        yy = -30 + k * 8.0
        Fd.box((px_, yy, (deck + 0.3 - 3.0) / 2), (0.36, 0.36, deck + 0.3 + 3.0), kit.BLACK, bevel=0.03)
        for zc in (1.6, deck - 0.6):
            Fd.box(((px_ + 0.18 + PW + 0.05) / 2, yy, zc), (PW + 0.05 - px_ - 0.18 + 0.02, 0.3, 0.25), kit.TIMBER_DARK)
        for j in (0, 1):
            ty = yy + 2.7 + j * 2.6
            kit.tyre(Fd, (tx_, ty, 1.9), (-1, 0, 0))
            Fd.beam((tx_ + 0.05, ty, 2.3), (PW + 0.03, ty, deck - 0.3), 0.04, 0.04, kit.ROPE)   # tied into the pier's face
    for yy in (-22.0, 45.0):
        kit.bollard(Fd, PW + 0.6, yy, deck)
        kit.rope_coil(Fd, PW + 1.4, yy + 0.9, deck)
    return Fd, {}


def make_pavilion(kit, data):
    deck = data['deck']
    px0 = data['px0']
    px1 = data['px1']
    py0 = data['py0']
    py1 = data['py1']
    P = kit.F.Mesh('FT_BC_Pavilion')
    # Pavilion on the pier beside the landing: six posts on stone footings, a long bench facing the ship, an exposed
    # truss and a kawara gable roof with its ridge along the pier.
    for x in (px0 + 0.2, px1 - 0.2):
        for y in (py0 + 0.2, (py0 + py1) / 2, py1 - 0.2):
            kit.post(P, x, y, deck, deck + 3.1, s=0.28, footing=True)
    for x in (px0 + 0.2, px1 - 0.2):
        # Eave beams on the post heads, their outer top edge 5 mm into the roof slab (which they carry).
        P.beam((x, py0, deck + 3.1 - 0.055), (x, py1, deck + 3.1 - 0.055), 0.2, 0.28, kit.TIMBER)
    for y in (py0 + 0.2, (py0 + py1) / 2, py1 - 0.2):
        for x, dx in ((px0 + 0.2, 1), (px1 - 0.2, -1)):
            kit.knee(P, (x, y, deck + 2.3), (x + dx * 0.7, y, deck + 2.9))
    zr = kit.gable_roof(P, px0, py0, px1, py1, deck + 3.1, 0.6, axis='y', over=(0.8, 0.8, 0.9, 0.9))
    for y in (py0 + 0.2, (py0 + py1) / 2, py1 - 0.2):
        with P._push(kit.F.Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))):
            kit.tie_truss(P, y, px0, px1, deck + 3.1, zr)
    kit.bench(P, (px0 + 0.6, py0 + 1.0), (px0 + 0.6, py1 - 1.0), deck)
    kit.bench(P, (px1 - 0.6, py0 + 1.0), (px1 - 0.6, py1 - 1.0), deck)
    return P, {}


def make_ticket_hut(kit, data):
    deck = data['deck']
    hx0 = data['hx0']
    hx1 = data['hx1']
    hy0 = data['hy0']
    hy1 = data['hy1']
    wh = data['wh']
    z1 = data['z1']
    H = kit.F.Mesh('FT_BC_TicketHut')
    # Ticket hut north of the pavilion: stone base, dark vertical boarding, a counter window facing the walkway,
    # a door to the north, a lantern and a timetable board, kawara roof.
    H.prism(kit.F.rect(hx0, hy0, hx1, hy1), deck, deck + 0.85, kit.STONE, bevel=0.04)
    for k in range(6):                           # coursed blocks
        H.box((hx0 - 0.02, hy0 + 0.4 + k * 0.75, deck + 0.42), (0.04, 0.02, 0.8), kit.INK)
    kit.wall(H, (hx0, hy0), (hx1, hy0), z1, wh, 0.16, kit.TIMBER_DARK, [], end_post=False)
    kit.wall(H, (hx1, hy0), (hx1, hy1), z1, wh, 0.16, kit.TIMBER_DARK, [], end_post=False)
    kit.wall(H, (hx1, hy1), (hx0, hy1), z1, wh, 0.16, kit.TIMBER_DARK, [(1.0, 1.95, 0.0, 2.0, 'door')], end_post=False)
    kit.wall(H, (hx0, hy1), (hx0, hy0), z1, wh, 0.16, kit.TIMBER_DARK, [(1.1, 3.4, 0.35, 1.5, 'counter')], end_post=False)
    for k in range(int((hy1 - hy0) / 0.3)):      # vertical boards on the walkway face
        yy = hy0 + 0.15 + k * 0.3
        if not (hy1 - 3.4 - 0.1 < yy < hy1 - 1.1 + 0.1):
            H.box((hx0 - 0.1, yy, z1 + wh / 2), (0.03, 0.05, wh - 0.4), kit.TIMBER)
    kit.gable_roof(H, hx0, hy0, hx1, hy1, z1 + wh, 0.55, axis='y', over=(0.9, 0.6, 0.6, 0.6))
    kit.lantern(H, hx0 - 0.3, hy1 - 0.6, z1 + 1.9, h=0.34)
    H.beam((hx0 - 0.08, hy1 - 0.6, z1 + 2.35), (hx0 - 0.3, hy1 - 0.6, z1 + 2.35), 0.04, 0.04, kit.IRON)
    kit.timetable(H, (hx0 + hx1) / 2, hy1 + 1.4, deck, 180.0, w=1.4, h=1.3)      # facing passengers coming down the pier
    H.prism(kit.F.rect(hx0 - 1.0, hy0 + 0.2, hx0 - 0.3, hy0 + 1.4), deck, deck + 0.45, kit.CRATE)    # flower box
    H.prism(kit.F.rect(hx0 - 0.95, hy0 + 0.25, hx0 - 0.35, hy0 + 1.35), deck + 0.45, deck + 0.62, kit.MOSS)
    return H, {}


def make_props(kit, data):
    PW = data['PW']
    deck = data['deck']
    gy = data['gy']
    Pr = kit.F.Mesh('FT_BC_Props')
    # Harbour props as in the concept: crates, a barrel, nets with orange floats and rope coils, each clear of the
    # others (none runs through another).
    for x, y, s, yaw in ((PW + 1.0, gy - 8.0, 0.9, 10), (PW + 1.0, gy - 9.1, 0.8, -6), (PW + 2.0, gy - 8.6, 0.7, 30),
                         (PW + 12.0, gy + 13.0, 0.9, 4), (PW + 12.1, gy + 12.0, 0.75, 22)):
        kit.crate(Pr, x, y, deck, s, yaw)
    kit.barrel(Pr, PW + 2.2, gy - 7.0, deck)
    kit.net_pile(Pr, PW + 11.8, gy + 15.6, deck)
    kit.net_pile(Pr, PW + 11.5, gy + 14.4, deck, r=0.6)
    kit.rope_coil(Pr, PW + 0.9, gy - 6.0, deck)
    kit.rope_coil(Pr, PW + 12.0, gy - 10.6, deck, R=0.5)
    return Pr, {}


def fixed_collision(kit, data):
    PW = data['PW']
    deck = data['deck']
    hx0 = data['hx0']
    hx1 = data['hx1']
    hy0 = data['hy0']
    hy1 = data['hy1']
    lx0 = data['lx0']
    lx1 = data['lx1']
    ly0 = data['ly0']
    ly1 = data['ly1']
    px0 = data['px0']
    px1 = data['px1']
    px_ = data['px_']
    py0 = data['py0']
    py1 = data['py1']
    wh = data['wh']
    z1 = data['z1']
    kit.col_box(lx0, ly0, lx1, ly1, deck, kit.SILL)
    for x in (px0 + 0.2, px1 - 0.2):
        for y in (py0 + 0.2, (py0 + py1) / 2, py1 - 0.2):
            kit.col_box(x - 0.14, y - 0.14, x + 0.14, y + 0.14, deck, deck + 3.1)
    for x in (px0 + 0.6, px1 - 0.6):
        kit.col_box(x - 0.25, py0 + 1.0, x + 0.25, py1 - 1.0, deck, deck + 0.48)
    kit.col_box(hx0, hy0, hx1, hy1, deck, z1 + wh)
    kit.col_box((hx0 + hx1) / 2 - 0.9, hy1 + 1.15, (hx0 + hx1) / 2 + 0.9, hy1 + 1.65, deck, deck + 3.2)
    for k in range(11):
        yy = -30 + k * 8.0
        kit.col_box(px_ - 0.18, yy - 0.18, PW, yy + 0.18, -3.0, deck + 0.3)


def walk_plan(kit, data, st, br):
    PW = data['PW']
    deck = data['deck']
    face = data['face']
    foot_y = data['foot_y']
    gx = data['gx']
    gy = data['gy']
    hx0 = data['hx0']
    hx1 = data['hx1']
    hy1 = data['hy1']
    lx0 = data['lx0']
    ly1 = data['ly1']
    sx_ = data['sx_']
    walk = {'name': 'brinecove', 'route': [(PW + 4.7, gy + 18.0, deck), (PW + 4.7, foot_y + 1.6, deck), (sx_, foot_y + 0.7, deck),
                                          (sx_, foot_y - 0.05, deck), (sx_, ly1 - 0.3, kit.SILL), (sx_, gy + 0.6, kit.SILL),
                                          (lx0 + 0.5, gy, kit.SILL), (lx0, gy, kit.SILL), (gx, gy, None), (gx - 1.5, gy, None)],
            'gate': [gx, gy, kit.SILL], 'stair': {k: v for k, v in st.items() if k != 'treads'}, 'brow': br,
            'anchor': [face, gy, 0.0], 'frame': 'brinecove-local (world = local + (-1500, -120))'}
    walk['board'] = {'position': [(hx0 + hx1) / 2, hy1 + 1.495, deck + 2.05], 'yaw': 180., 'text_size_m': .09}
    return walk


def assemble(kit):
    """Diagnostic whole terminal; production selects the explicit constructors above."""
    data = construction_plan(kit)
    meshes, metadata = {}, {}
    for key, function in CONSTRUCTORS.items():
        mesh, row = globals()[function](kit, data)
        meshes[key] = mesh; metadata.update(row)
    fixed_collision(kit, data)
    walk = walk_plan(kit, data, metadata['stair'], metadata['brow'])
    return {key: meshes[key] for key in MESH_ORDER}, walk
