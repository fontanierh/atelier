"""Hidamari ferry berth, manoeuvres and terminal assembly in the owning region frame."""
import math

import numpy as np

HIDAMARI_X = 855.0                    # berth centre x: the jetty clears the canal mouth (x 840-856 stays open at the quay)
HIDAMARI_QUAY_FACE = -127.7           # quay coping outer face (hidamari/build.py harbor(): 3.4 m coping on y -126)
HIDAMARI_PIVOT = (872.0, -190.0)      # deep water inside the mouth, clear of the workboats and the headland shelf
HIDAMARI_STANDOFF = -156.0            # the glide line off the berth
HIDAMARI_TIMETABLE_DX = -6.5         # the timetable board, west of the jetty axis on the quay
QUAY_RAIL = 2.9                       # quay surfaces sit below the timber rail (posts 2.45-3.55)



def layout(world, geometry):
    """Berth, gate, jetty and the walk levels it stands on, from the exported seabed and quay."""
    g = geometry.Grid(*world['bounds']); z = g.surface_max(world['ground'])
    z = np.where(np.isnan(z), np.inf, z)
    cy = geometry.berth_offshore(g, z, HIDAMARI_X, 180.0, HIDAMARI_QUAY_FACE - geometry.FENDER - geometry.ship.BEAM)
    face_y = cy + geometry.ship.BEAM + geometry.FENDER     # jetty fender face; the hull side is FENDER outside it
    berth = (HIDAMARI_X, cy, 180.0)      # bow west; starboard side to the jetty
    gx, gy = geometry.gate_point(berth, -1)
    jetty = [(gx - 8.0, HIDAMARI_QUAY_FACE), (gx + 8.0, HIDAMARI_QUAY_FACE), (gx + 8.0, face_y), (gx - 8.0, face_y)]
    quay = geometry.levels(world, geometry.rect_points(gx - 8, HIDAMARI_QUAY_FACE + 0.1, gx + 8, HIDAMARI_QUAY_FACE + 3.3), QUAY_RAIL)
    house = geometry.levels(world, geometry.rect_points(gx - 21.3, -122.3, gx - 8.7, -114.2, 0.25), QUAY_RAIL + 0.5)   # the plinth
    q = float(np.nanmedian(quay))
    # The waiting house's door (south wall, 1.2-2.2 m from its west end) steps down to the quay; the timetable board
    # stands on the quay west of the jetty root (x 840-856 east of it is the canal mouth, water at the quay).
    door = geometry.levels(world, geometry.rect_points(gx - 21.0 + 1.0, -123.0, gx - 21.0 + 2.4, -122.3, 0.2), QUAY_RAIL + 0.5)
    tx, ty = gx + HIDAMARI_TIMETABLE_DX, -122.5
    board = geometry.levels(world, geometry.rect_points(tx - 1.5, ty - 0.3, tx + 1.5, ty + 0.3, 0.2), QUAY_RAIL + 0.5)
    for what, zs in (('waiting house door step', door), ('timetable board', board)):
        if np.isnan(zs).any():
            raise ValueError(f'Hidamari {what}: no exported surface under part of its footprint')
    # The jetty root crosses the quay's timber rail (posts 2.45-3.55, top beam 3.5): B3 cuts it over the jetty's width.
    cuts = [geometry.world_cut("the quay's timber rail and posts across the jetty root", (gx - 8.0, gx + 8.0), (-126.3, -125.7),
                      q - 0.1)]
    walk = {'world_cuts': cuts, 'quay_top_z': round(q, 3), 'quay_top_range': [round(float(np.nanmin(quay)), 3), round(float(np.nanmax(quay)), 3)],
            'promenade_z': round(float(np.nanmax(house)), 3), 'promenade_range': [round(float(np.nanmin(house)), 3), round(float(np.nanmax(house)), 3)],
            'waiting_house': [gx - 21.0, -122.0, gx - 9.0, -114.5], 'door_ground_z': round(float(np.nanmin(door)), 3),
            'timetable': [round(tx, 3), ty, round(float(np.nanmax(board)), 3)],
            'timetable_ground_range': [round(float(np.nanmin(board)), 3), round(float(np.nanmax(board)), 3)]}
    zone = jetty
    return berth, (gx, gy), jetty, face_y, zone, walk


def moves(berth):
    bx, by, _ = berth
    px, py = HIDAMARI_PIVOT
    # Arrival: in through the harbour mouth heading north, stop in deep water, pivot to port onto west, glide
    # north-west to the stand-off line, then crab onto the fenders. Departure is the same in reverse.
    arrive = (px, -290.0, 90.0)
    arrival = [('ahead', py + 290.0), ('pivot', 90.0), ('move', bx - px, HIDAMARI_STANDOFF - py), ('berth', -(by - HIDAMARI_STANDOFF))]
    departure = [('berth', by - HIDAMARI_STANDOFF), ('move', px - bx, py - HIDAMARI_STANDOFF), ('pivot', 90.0), ('ahead', py + 290.0)]
    return (arrive, arrival), (berth, departure)

def assemble(kit):
    b = kit.SITE['hidamari']['berth']; gx, gy, _ = b['gate']; face = b['face']; quay = b['quay_top_z']
    QF = -127.7                       # quay coping outer face
    world = kit.FS.load_world('hidamari')  # the exported quay, for feet and bases set on it
    meshes = {k: kit.F.Mesh(k) for k in ('FT_HD_Jetty', 'FT_HD_Stage', 'FT_HD_Brow', 'FT_HD_WaitingHouse', 'FT_HD_Timetable')}
    J, S, B, W, T = meshes.values()
    deck_t = 0.3
    x0, x1 = gx - 8.0, gx + 8.0
    # Jetty: plank deck flush with the coping, on timber piles, with a dark fascia, black fender piles on its face and
    # railings along its open sides.
    J.prism(kit.F.rect(x0, face, x1, QF), quay - deck_t, quay, kit.TIMBER_DARK, top=kit.PLANK)
    for k in range(int((x1 - x0) / 0.5)):     # (5 mm off the half-metre grid: clear of the stair posts' faces)
        xx = x0 + 0.255 + k * 0.5
        J.box((xx, (face + QF) / 2, quay + 0.004), (0.02, QF - face - 0.1, 0.012), kit.TIMBER_DARK)   # plank seams
    kit.piles_under(J, [x0 + 0.3 + k * (x1 - x0 - 0.6) / 5 for k in range(6)], [face + 0.3, (face + QF) / 2, QF - 0.4], quay - deck_t)
    for k in range(9):
        xx = x0 + 0.5 + k * (x1 - x0 - 1.0) / 8
        J.box((xx, face - 0.25, (quay + 0.35 - 3.5) / 2), (0.36, 0.36, quay + 0.35 + 3.5), kit.BLACK, bevel=0.03)
        J.box((xx, face - 0.27, quay + 0.4), (0.42, 0.42, 0.1), kit.TIMBER_DARK)
    for xx in (gx - 5.6, gx + 5.6):  # cylindrical fenders hung on chains between the piles, FENDER_GAP off the hull
        fy = face - (kit.FS.FENDER - kit.FENDER_GAP) + 0.38
        J.tube([(xx - 1.1, fy, 0.9), (xx + 1.1, fy, 0.9)], 0.38, kit.BLACK, n=10)
        for x_ in (xx - 0.9, xx + 0.9):
            J.beam((x_, fy, 1.25), (x_, face - 0.25, quay - 0.4), 0.03, 0.03, kit.IRON)
    kit.rail_line(J, [(x0 + 0.15, QF - 0.3), (x0 + 0.15, face + 0.12), (x1 - 0.15, face + 0.12), (x1 - 0.15, QF - 0.3)], quay)
    for xx in (x0 + 0.7, x1 - 0.7):
        kit.bollard(J, xx, face + 0.7, quay)
    # Boarding stage: a timber stage on tall posts tied with nuki beams (a little Kiyomizu), its gallery flush with the
    # ship's sill; the stair climbs from the jetty straight to the gate on its axis; a kawara roof covers both.
    gal0, gal1 = face, face + 3.0
    sx0, sx1 = gx - 5.5, gx + 5.5
    foot_y = gal1 + kit.stair_run([10, 9])
    st = kit.solid_stair(S, (gx, foot_y), (0, -1), 2.2, quay, [10, 9], (kit.SILL - quay) / 19, landing=1.2)
    S.prism(kit.F.rect(sx0, gal0, sx1, gal1), kit.SILL - 0.3, kit.SILL, kit.TIMBER_DARK, top=kit.PLANK)
    ze = kit.SILL + 2.6                            # tie beams clear the gallery by 2.25 m
    posts = [(x, y) for x in (sx0 + 0.2, gx - 1.45, gx + 1.45, sx1 - 0.2) for y in (gal0 + 0.2, gal1 - 0.1)]
    posts += [(x, foot_y - 0.2) for x in (sx0 + 0.2, sx1 - 0.2)]
    for x, y in posts:
        kit.post(S, x, y, quay, ze, s=0.3)
    for y in (gal0 + 0.2, gal1 - 0.1):          # nuki ties through the posts, clear of the stair head
        for zz in (quay + 2.45, kit.SILL - 0.45):
            spans = [(sx0, sx1)] if (y < gal1 - 1.0 or zz < quay + (kit.SILL - quay) * 0.4) else [(sx0, gx - 1.25), (gx + 1.25, sx1)]
            for xa, xb in spans:
                S.beam((xa, y, zz), (xb, y, zz), 0.14, 0.24, kit.TIMBER)
    for x in (sx0 + 0.2, sx1 - 0.2):             # side ties, 1 cm deeper than the nuki they cross; at the eaves the
        S.beam((x, gal0, quay + 2.45), (x, foot_y - 0.2, quay + 2.45), 0.14, 0.25, kit.TIMBER)   # end trusses' tie beams
    for x in (gx - 1.45, gx + 1.45):             # stair landing posts
        kit.post(S, x, gal1 + 9 * kit.TREAD + 0.6, quay, quay + (kit.SILL - quay) * 10 / 19 - 0.05, s=0.22)
    land_y0 = gal1 + 8 * kit.TREAD; land_y1 = land_y0 + 1.2
    # Gallery and stair railings, open at the brow and the stair head.
    kit.rail_line(S, [(gx - 1.2, gal1 - 0.05), (sx0 + 0.1, gal1 - 0.05), (sx0 + 0.1, gal0 + 0.1), (gx - kit.BROW_W / 2 - 0.1, gal0 + 0.1)], kit.SILL)
    kit.rail_line(S, [(gx + kit.BROW_W / 2 + 0.1, gal0 + 0.1), (sx1 - 0.1, gal0 + 0.1), (sx1 - 0.1, gal1 - 0.05), (gx + 1.2, gal1 - 0.05)], kit.SILL)
    for s in (-1, 1):                            # stair handrails following the pitch
        xs = gx + s * 1.2
        for (ua, za), (ub, zb) in (((foot_y, quay), (land_y1, quay + (kit.SILL - quay) * 10 / 19)),
                                   ((land_y0, quay + (kit.SILL - quay) * 10 / 19), (gal1, kit.SILL))):
            S.beam((xs, ua, za + 0.95), (xs, ub, zb + 0.95), 0.08, 0.1, kit.TIMBER)
            for yy, zz in ((ua, za), (ub, zb)):       # 1 cm into the floor, clear of the railing posts' feet
                S.box((xs, yy, zz + 0.495), (0.12, 0.12, 1.01), kit.TIMBER)
    for x in (sx0 + 0.2, gx - 1.45, gx + 1.45, sx1 - 0.2):   # knee braces under the gallery
        kit.knee(S, (x, gal0 + 0.2, kit.SILL - 1.2), (x, gal0 + 1.4, kit.SILL - 0.3))
    kit.bench(S, (sx0 + 0.6, gal1 + 0.6), (sx0 + 0.6, foot_y - 0.6), quay)
    kit.bench(S, (sx1 - 0.6, gal1 + 0.6), (sx1 - 0.6, foot_y - 0.6), quay)
    zr = kit.gable_roof(S, sx0, gal0, sx1, foot_y - 0.2, ze, 0.55, over=(0.9, 0.9, 0.0, 0.9))
    for x in (sx0 + 0.2, gx, sx1 - 0.2):
        kit.tie_truss(S, x, gal0, foot_y - 0.2, ze, zr)
    for x in (gx - 1.0, gx + 1.0):
        kit.lantern(S, x, gal1 - 0.3, ze - 0.55, h=0.3)
        S.beam((x, gal1 - 0.3, ze - 0.245), (x, gal1 - 0.3, ze - 0.2), 0.03, 0.03, kit.IRON)
        # An iron arm from the middle truss's tie beam carries the hanger.
        S.beam((gx, gal1 - 0.3, ze - 0.2), (x + math.copysign(0.02, x - gx), gal1 - 0.3, ze - 0.2), 0.04, 0.04, kit.IRON)
    # Brow: hinged on the gallery's south edge, over the fender gap to the hull, its lip on the ship's landing plate.
    br = kit.brow(B, (gx, face), (gx, gy), (0.0, -1.0), kit.SILL)
    # Waiting house on the promenade west of the jetty root: white plaster between dark timber, sliding windows,
    # a door to the jetty side, a bench and lamp in front, kawara roof.
    hx0, hx1, hy0, hy1 = gx - 21.0, gx - 9.0, -122.0, -114.5
    hz = b['promenade_z']                      # the highest exported promenade under the plinth (site.py)
    hb = b['promenade_range'][0] - 0.15        # the plinth reaches below the lowest ground under it
    W.prism(kit.F.rect(hx0 - 0.3, hy0 - 0.3, hx1 + 0.3, hy1 + 0.3), hb, hz + 0.18, kit.STONE)
    wh = 2.9
    kit.wall(W, (hx0, hy0), (hx1, hy0), hz + 0.18, wh, 0.18, kit.PLASTER, [(1.2, 2.2, 0.0, 2.15, 'open door'), (3.0, 6.0, 0.85, 2.2), (7.0, 10.6, 0.85, 2.2)], end_post=False)
    kit.wall(W, (hx1, hy0), (hx1, hy1), hz + 0.18, wh, 0.18, kit.PLASTER, [(1.4, 6.1, 0.85, 2.2)], end_post=False)
    kit.wall(W, (hx1, hy1), (hx0, hy1), hz + 0.18, wh, 0.18, kit.PLASTER, [(1.0, 4.0, 0.85, 2.2), (8.0, 11.0, 0.85, 2.2)], end_post=False)
    kit.wall(W, (hx0, hy1), (hx0, hy0), hz + 0.18, wh, 0.18, kit.PLASTER, [(2.2, 5.3, 0.85, 2.2)], end_post=False)
    W.prism(kit.F.rect(hx0 + 0.1, hy0 + 0.1, hx1 - 0.1, hy1 - 0.1), hz + 0.175, hz + 0.2, kit.PLANK)   # 5 mm into the plinth
    kit.gable_roof(W, hx0, hy0, hx1, hy1, hz + 0.18 + wh, 0.6, over=(0.7, 0.7, 1.1, 0.8))
    for u0, u1 in ((3.2, 5.8), (7.4, 10.0)):   # feet on the exported quay under each bench
        kit.bench(W, (hx0 + u0, hy0 - 0.7), (hx0 + u1, hy0 - 0.7), kit.ground_under(world, hx0 + u0, hy0 - 0.91, hx0 + u1, hy0 - 0.49))
    kit.lantern(W, hx0 + 2.5, hy0 - 0.18, hz + 2.3, h=0.36)
    # The door steps down from the plinth (hz + 0.18) to the quay at the door (site.py door_ground_z): equal risers
    # no taller than DOOR_RISER, 0.35 m treads, 1.2 m wide.
    gd = b['door_ground_z']; dx = hx0 + 1.7; top = hz + 0.18
    n = max(1, math.ceil((top - gd) / kit.DOOR_RISER - 1e-9)); r = (top - gd) / n
    for k in range(1, n):
        y1, y0 = hy0 - 0.3 - (k - 1) * 0.35, hy0 - 0.3 - k * 0.35
        W.prism(kit.F.rect(dx - 0.6, y0, dx + 0.6, y1), gd - 0.1, top - k * r, kit.STONE)
        kit.col_box(dx - 0.6, y0, dx + 0.6, y1, gd - 0.1, top - k * r)
    for xx in (hx0 + 0.6, hx1 - 0.9):         # potted plants either side, as in the concept (west one clear of the step)
        pz = kit.ground_under(world, xx - 0.3, hy0 - 1.1, xx + 0.3, hy0 - 0.5)
        with W.fitting('plant pot') as base:
            W.lathe((xx, hy0 - 0.8, pz), [(0, 0.22), (0.45, 0.3), (0.5, 0.0)], kit.TERRACOTTA, n=10)
            W.lathe((xx, hy0 - 0.8, pz + 0.45), [(0, 0.3), (0.3, 0.36), (0.6, 0.0)], kit.MOSS, n=10)
            base.append((xx, hy0 - 0.8, pz))
    # Timetable board on the promenade at the jetty root, facing the city.
    tx, ty, tz = b['timetable']
    kit.timetable(T, tx, ty, tz - 0.02, 0.0)
    kit.col_box(tx - 1.6, ty - 0.3, tx + 1.6, ty + 0.3, tz, tz + 3.2)
    # Collision for the decks, posts, benches and the waiting house (rails, stairs and brow add their own).
    kit.col_box(x0, QF, x1, face, quay - deck_t, quay)
    kit.col_box(sx0, gal0, sx1, gal1, kit.SILL - 0.3, kit.SILL)
    for x, y in posts:
        kit.col_box(x - 0.15, y - 0.15, x + 0.15, y + 0.15, quay, ze)
    for x in (sx0 + 0.6, sx1 - 0.6):
        kit.col_box(x - 0.25, gal1 + 0.6, x + 0.25, foot_y - 0.6, quay, quay + 0.48)
    kit.col_box(hx0 - 0.3, hy0 - 0.3, hx1 + 0.3, hy1 + 0.3, hb, hz + 0.18)
    for a_, b_, cuts in (((hx0, hy0), (hx1, hy0), [(1.2, 2.2)]), ((hx1, hy0), (hx1, hy1), []), ((hx1, hy1), (hx0, hy1), []),
                         ((hx0, hy1), (hx0, hy0), [])):
        L_ = math.dist(a_, b_); t_ = [(b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_]; u_ = 0.0
        for c0, c1 in cuts + [(L_, L_)]:
            kit.col_seg((a_[0] + t_[0] * u_, a_[1] + t_[1] * u_), (a_[0] + t_[0] * c0, a_[1] + t_[1] * c0), 0.2, hz + 0.18, hz + 0.18 + wh)
            u_ = c1
    kit.col_box(hx0 + 0.2, hy0 - 0.19, hx0 + 1.2, hy0 - 0.13, hz + 0.18, hz + 0.18 + 2.15)   # the open door leaf
    # From the waiting house out of its door, along the quay clear of the benches, then onto the jetty axis. The jetty
    # root is beside the canal's west wall (x 840, railing posts every 2 m north of y -122), so the walk does not
    # start on that line.
    walk = {'name': 'hidamari', 'route': [(dx, hy0 + 1.5, hz + 0.2), (dx, -123.6, None), (gx - 1.0, -123.6, None),
                                         (gx, QF + 0.2, quay), (gx, foot_y + 1.0, quay),
                                         (gx, foot_y - 0.05, quay)] +
            [(gx, y, quay + (kit.SILL - quay) * 10 / 19) for y in (land_y1, land_y0)] + [(gx, gal1, kit.SILL), (gx, gal0 + 0.5, kit.SILL), (gx, face, kit.SILL),
                                                          (gx, gy, None), (gx, gy - 1.5, None)],
            'gate': [gx, gy, kit.SILL], 'stair': {k: v for k, v in st.items() if k != 'treads'}, 'brow': br,
            'anchor': [gx, face, 0.0], 'frame': 'world'}
    walk['board'] = {'position': [tx, ty - .095, tz + 2.3], 'yaw': 0., 'text_size_m': .14}
    return meshes, walk
