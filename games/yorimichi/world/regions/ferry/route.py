"""The ferry's sea crossing between Hidamari and Brinecove, as the moves site.py sweeps (pure Python).

A crossing joins the end of one harbour's departure manoeuvre to the start of the other's arrival manoeuvre (site.py
records both poses in site.json). It is a polyline whose corners are rounded with circular arcs: it leaves along the
departure's heading for LEAD_OUT metres, passes the open-sea corners, and comes in along the arrival's heading for
LEAD_IN metres. fillet() turns it into site.py's move language, ('ahead', metres) and ('arc', radius, degrees), so the
same sweep checks the crossing and the manoeuvres, and the timetable sails exactly what was checked.

World metres, x east, y north, heading in degrees (0 east, 90 north). The corners keep the crossing in open water:
south of Hidamari's breakwater, well south of Temple Island (its model at (-150, -530)), round the headland east of
Brinecove's cove (its tip near (-860, -830)) and up the middle of the cove. The single ferry sails these two
audited paths in turn.
"""
import math

CROSSINGS = {
    # name: from harbour, to harbour, metres out along the departure heading, open-sea corners, metres in along the
    # arrival heading, and each corner's turning radius (out corner, sea corners..., in corner).
    'westbound': {'from': 'hidamari', 'to': 'brinecove', 'lead_out': 430.0, 'corners': [(-700.0, -960.0)], 'lead_in': 390.0,
                  'radii': [260.0, 400.0, 260.0]},
    'eastbound': {'from': 'brinecove', 'to': 'hidamari', 'lead_out': 430.0, 'corners': [(-700.0, -1020.0)], 'lead_in': 470.0,
                  'radii': [260.0, 400.0, 260.0]},
}
# The crossing's swept area: everything the probe exports for it (world metres, x0, y0, x1, y1).
BOUNDS = (-2000.0, -1080.0, 1000.0, -220.0)


def polyline(start, end, spec):
    """Corner points of a crossing from pose start to pose end ((x, y, heading deg) each)."""
    sx, sy, sh = start
    ex, ey, eh = end
    out = (sx + math.cos(math.radians(sh)) * spec['lead_out'], sy + math.sin(math.radians(sh)) * spec['lead_out'])
    inn = (ex - math.cos(math.radians(eh)) * spec['lead_in'], ey - math.sin(math.radians(eh)) * spec['lead_in'])
    return [(sx, sy), out, *[tuple(c) for c in spec['corners']], inn, (ex, ey)]


def _heading(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def fillet(points, radii):
    """Moves along a polyline with each interior corner rounded by an arc of its radius, tangent to both legs.

    Returns (heading of the first leg in degrees, moves). Fails when two arcs overlap on a leg (the corners are too
    close for their radii)."""
    if len(radii) != len(points) - 2:
        raise ValueError(f'{len(points) - 2} corners need as many radii, got {len(radii)}')
    legs = [_heading(a, b) for a, b in zip(points, points[1:])]
    moves, used = [], 0.0
    for i, R in enumerate(radii):
        turn = (legs[i + 1] - legs[i] + math.pi) % (2 * math.pi) - math.pi
        cut = R * math.tan(abs(turn) / 2)
        straight = math.dist(points[i], points[i + 1]) - used - cut
        if straight < -1e-6:
            raise ValueError(f'corner {i + 1}: its arc and the previous one overlap by {-straight:.1f} m')
        moves.append(('ahead', max(0.0, straight)))
        moves.append(('arc', R, math.degrees(turn)))
        used = cut
    last = math.dist(points[-2], points[-1]) - used
    if last < -1e-6:
        raise ValueError(f'the last corner\'s arc overruns the end by {-last:.1f} m')
    moves.append(('ahead', max(0.0, last)))
    return math.degrees(legs[0]), [m for m in moves if not (m[0] == 'ahead' and m[1] < 1e-9)]


def crossing(start, end, spec):
    """(start pose, moves) of a crossing; the moves end on pose end (the caller's sweep records where they end)."""
    heading, moves = fillet(polyline(start, end, spec), spec['radii'])
    if abs((heading - start[2] + 180.0) % 360.0 - 180.0) > 1e-6:
        raise ValueError(f'the crossing leaves at {heading:.3f} deg, the departure ends heading {start[2]:.3f}')
    return (start[0], start[1], start[2]), moves


def length(moves):
    """Metres sailed along the moves (ahead and arc)."""
    return sum(abs(m[1]) if m[0] == 'ahead' else abs(m[1] * math.radians(m[2])) for m in moves)
