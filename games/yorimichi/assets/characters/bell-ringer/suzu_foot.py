"""Tabi socks and the wooden geta, on the kit's shared sole footprint (SOLE_Z, HEEL_Y, TOE_Y)."""
import mesh_tools as G
import shoe

# The tabi volume in plan: y, half width, top height. It sits on the geta platform at .058 and wraps the ankle.
SECTIONS = [(.052, .032, .150), (.022, .038, .152), (-.014, .042, .132), (-.056, .044, .112),
            (-.098, .042, .094), (-.126, .037, .082), (-.138, .028, .074), (-.142, .014, .070)]
PLATFORM_TOP = .068
PLATFORM_BOTTOM = .0395
TOOTH_BOTTOM = shoe.SOLE_Z


def build_foot(s, suf):
    """One foot at x = s*.118: tabi, geta board, two teeth, the thong straps and the split-toe crease."""
    x = s*.122
    # Tabi: one continuous rounded upper. Six points per station (sole left/right, side right, top right,
    # top left, side left) read as a soft foot.
    verts = []
    for y, width, top in SECTIONS:
        verts += [(x-width, y, PLATFORM_TOP), (x+width, y, PLATFORM_TOP), (x+width*.96, y, top*.62),
                  (x+width*.60, y, top), (x-width*.60, y, top), (x-width*.96, y, top*.62)]
    faces = [(j*6+i, j*6+(i+1) % 6, (j+1)*6+(i+1) % 6, (j+1)*6+i)
             for j in range(len(SECTIONS)-1) for i in range(6)]
    faces += [tuple(range(5, -1, -1)), tuple((len(SECTIONS)-1)*6+i for i in range(6))]
    tabi = G.mesh('Tabi '+suf, verts, faces, 'tabi', 'foot_'+suf)
    for p in tabi.data.polygons:
        p.use_smooth = True
    # The split-toe crease on the top of the big toe.
    G.ribbon('Tabi toe split '+suf, [(x-s*.015, -.146, .070), (x-s*.015, -.108, .092),
                                     (x-s*.014, -.072, .112)], .005, 'tabi_shadow', 'foot_'+suf,
             normal=(0, -.2, .98), thickness=.002)
    G.ribbon('Tabi ankle fold '+suf, [(x-.040, .020, .150), (x+.040, .020, .150)],
             .013, 'tabi_shadow', 'foot_'+suf, normal=(0, -.1, .99), thickness=.002)

    # The geta board: a rounded wooden platform with a bevelled top edge.
    board = [(-.066, .056), (.066, .056), (.073, -.010), (.066, -.110), (.040, -.146),
             (-.040, -.146), (-.066, -.110), (-.073, -.010)]
    n = len(board)
    verts = [(x+dx, y, PLATFORM_BOTTOM) for dx, y in board]+[(x+dx, y, PLATFORM_TOP) for dx, y in board]
    faces = [(i, (i+1) % n, (i+1) % n+n, i+n) for i in range(n)]
    faces += [tuple(range(n-1, -1, -1)), tuple(range(n, 2*n))]
    G.mesh('Geta board '+suf, verts, faces, 'wood', 'foot_'+suf,
           face_colours=['wood_light']*n+['wood']*n)
    # Two teeth, so the sole contact stays on the kit's SOLE_Z plane.
    for index, (cy, half, length) in enumerate(((.032, .044, .026), (-.100, .044, .026))):
        G.box('Geta tooth %d %s' % (index, suf), (x, cy, (TOOTH_BOTTOM+PLATFORM_BOTTOM)/2),
              (half*2, length, PLATFORM_BOTTOM-TOOTH_BOTTOM), 'wood_dark', 'foot_'+suf, .002)
    # The thong: a toe post and two straps to the sides of the board.
    G.tube('Geta toe post '+suf, [(x, -.112, PLATFORM_TOP), (x, -.110, .094)], [.007, .006], 'cord',
           'foot_'+suf, sides=5)
    for side in (-1, 1):
        G.tube('Geta thong '+suf+' '+str(side),
               [(x, -.110, .094), (x+side*.030, -.062, .118), (x+side*.052, -.014, .132),
                (x+side*.062, .012, .128)],
               [.006, .0055, .005, .006], 'cord', 'foot_'+suf, sides=5)
