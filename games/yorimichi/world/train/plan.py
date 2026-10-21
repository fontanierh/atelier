"""Dimensioned plans of the Belmonte train (plain Python, SVG): `atelier build yorimichi world.belmonte_train_plan`.

For each coach a floor plan (rooms, partitions, doors, windows, furniture footprints, seats, dimension chains) and
one shared cross-section (heights of the envelope). Output: build/yorimichi/belmonte-train/plan/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401

from train import layout as L  # noqa: E402

OUT = yori.OUT / 'belmonte-train' / 'plan'
S = 60                     # pixels per metre
FILL = {'vestibule': '#e8e2d6', 'corridor': '#cfe0d4', 'cabin': '#a9cdb5', 'wc': '#dde3ea', 'luggage': '#e6dccb',
        'pantry': '#e6dccb', 'lobby': '#e8e2d6', 'salon': '#e6b9b4', 'bar': '#e9cfa8', 'galley': '#d4dde6',
        'saloon': '#c9cdb8', 'canteen': '#e4e2da', 'guard': '#e6dccb', 'balcony': '#efe7d6', 'hold': '#e2d6c0'}
ASSET = {'restaurant-banquette': '#8c2a2f', 'restaurant-table': '#f4efe2', 'first-class-sofa': '#1f6b4b',
         'first-class-table': '#7a4a24', 'table-lamp': '#d9a441', 'wall-sconce': '#d9a441',
         'second-class-bench': '#6b5a3e', 'canteen-pot': '#9aa0a6',
         'second-class-bench-carved': '#8a6a3e', 'canteen-stove': '#2b2b2b'}


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.items = w, h, []

    def add(self, s):
        self.items.append(s)

    def text(self, x, y, s, size=11, anchor='middle', weight='normal', color='#222', rotate=None):
        tr = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ''
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}"{tr}>{s}</text>')

    def rect(self, x, y, w, h, fill='none', stroke='#222', sw=1., op=1., dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" fill-opacity="{op}"{d}/>')

    def line(self, x0, y0, x1, y1, stroke='#222', sw=1., dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def save(self, path):
        body = '\n'.join(self.items)
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                        f'font-family="Helvetica, Arial, sans-serif"><rect width="100%" height="100%" fill="white"/>\n{body}\n</svg>\n')


def plan(c):
    margin_x, top = 90, 150
    bd = c.body
    w = int(bd.length * S + 2 * margin_x)
    h = int(2 * L.HALF * S + top + 260)
    svg = Svg(w, h)
    X = lambda x: margin_x + (x - bd.buffer_a) * S
    Y = lambda y: top + (L.HALF - y) * S            # +Y (compartment / galley side) drawn at the top
    svg.text(margin_x, 40, f'{c.title} — dimensioned plan (m)', 22, 'start', 'bold')
    svg.text(margin_x, 64, 'Coach frame: x along the coach (end A on the left, end B on the right), +Y up (compartment / galley side), '
             'z from the top of the rail. Design dimensions, not a survey.', 12, 'start', color='#555')
    # body, buffers, gangways
    svg.rect(X(bd.x_a), Y(L.HALF), (bd.x_b - bd.x_a) * S, 2 * L.HALF * S, '#20283c', '#20283c', 1)
    for sx in (-1, 1):
        x0, x1 = sorted((bd.headstock(sx), bd.buffer(sx)))
        if bd.end(sx) == 'gangway':
            svg.rect(X(x0), Y(L.GANGWAY_W / 2 + .18), (x1 - x0) * S, (L.GANGWAY_W + .36) * S, '#333', '#111', .5)
        else:
            h0, h1 = sorted((bd.headstock(sx), bd.face(sx)))
            svg.rect(X(h0), Y(L.IN), (h1 - h0) * S, 2 * L.IN * S, '#e6dccb', '#b38b3c', 1)
            for x0r, x1r, y0r, y1r in L.railings(bd):
                svg.rect(X(x0r), Y(y1r), (x1r - x0r) * S, (y1r - y0r) * S, '#b38b3c', 'none', 0)
        for sy in (-1, 1):
            svg.rect(X(x0), Y(sy * L.BUFFER_Y + .2), (x1 - x0) * S, .4 * S, '#666', '#111', .5)
    for r in c.rooms:
        svg.rect(X(r.x0), Y(r.y1), (r.x1 - r.x0) * S, (r.y1 - r.y0) * S, FILL.get(r.kind, '#eee'), 'none', 0)
        svg.text(X((r.x0 + r.x1) / 2), Y((r.y0 + r.y1) / 2) + (26 if r.kind in ('cabin', 'salon') else 4), r.name, 10, color='#333')
    for w_ in c.walls:
        spans, a = [], w_.a0
        for o in sorted(w_.openings, key=lambda o: o.a0):
            spans.append((a, o.a0)); a = o.a1
        spans.append((a, w_.a1))
        for a0, a1 in spans:
            if a1 - a0 < 1e-6:
                continue
            if w_.axis == 'x':
                svg.rect(X(a0), Y(w_.c1), (a1 - a0) * S, (w_.c1 - w_.c0) * S, '#3b2414', 'none', 0)
            else:
                svg.rect(X(w_.c0), Y(a1), (w_.c1 - w_.c0) * S, (a1 - a0) * S, '#3b2414', 'none', 0)
    # windows on the side walls, exterior doors
    for win in c.windows:
        y = win.side * (L.IN + L.WALL / 2)
        col = '#9ad3f0' if win.kind == 'clear' else '#c9d6dd'
        svg.rect(X(win.x - win.width / 2), Y(y) - 3, win.width * S, 6, col, '#2a6f97', .8)
    for name, sy, x0, x1, *_ in L.exterior_openings(c):
        svg.rect(X(x0), Y(sy * L.HALF) - (0 if sy > 0 else L.WALL * S), (x1 - x0) * S, L.WALL * S, '#f2e6c9', '#b38b3c', 1)
    for d in c.doors:
        if d.wall.startswith('side'):
            continue
        w_ = c.wall(d.wall); o = next(o for o in w_.openings if o.name == d.opening)
        if d.kind == 'sliding':
            a0 = (o.a1 - .025) if d.slide > 0 else (o.a0 + .025 - d.width)
            face = (w_.c1 if d.face > 0 else w_.c0) + d.face * .025
            if w_.axis == 'x':
                svg.line(X(a0), Y(face), X(a0 + d.width), Y(face), '#b38b3c', 2.5)
            else:
                svg.line(X(face), Y(a0), X(face), Y(a0 + d.width), '#b38b3c', 2.5)
    for p in c.placements:
        if p.z - L.FLOOR_Z < .05:
            x0, x1, y0, y1 = L.footprint(p)
            svg.rect(X(x0), Y(y1), (x1 - x0) * S, (y1 - y0) * S, ASSET[p.asset], '#222', .6, .85)
        elif p.asset == 'table-lamp':
            svg.add(f'<circle cx="{X(p.x):.1f}" cy="{Y(p.y):.1f}" r="4" fill="{ASSET[p.asset]}" stroke="#222" stroke-width=".5"/>')
        else:
            svg.add(f'<circle cx="{X(p.x):.1f}" cy="{Y(p.y):.1f}" r="3" fill="#fff" stroke="#b38b3c" stroke-width="1.2"/>')
    for s in c.seats:
        svg.add(f'<circle cx="{X(s.x):.1f}" cy="{Y(s.y):.1f}" r="2.4" fill="#fff"/>')
    for b in c.reservations:
        svg.rect(X(b.x0), Y(b.y1), (b.x1 - b.x0) * S, (b.y1 - b.y0) * S, '#3b6fd8', '#2a4f9e', .6, .25, '3,2')
    # dimension chains
    def chain(marks, y, label_above=True):
        marks = sorted(set(round(m, 4) for m in marks))
        svg.line(X(marks[0]), y, X(marks[-1]), y, '#444', .7)
        for m in marks:
            svg.line(X(m), y - 5, X(m), y + 5, '#444', .7)
        for a, b in zip(marks, marks[1:]):
            if b - a > .12:
                svg.text(X((a + b) / 2), y + (-6 if label_above else 14), f'{b - a:.2f}', 10 if b - a > .5 else 8)
    room_marks = [bd.x_a, bd.x_b, bd.in_a, bd.in_b]
    for r in c.rooms:
        if r.y1 >= L.IN - 1e-6:
            room_marks += [r.x0, r.x1]
    chain(room_marks, Y(L.HALF) - 30)
    chain([bd.buffer_a, bd.buffer_b], Y(L.HALF) - 60)
    win_marks = [bd.in_a, bd.in_b]
    for win in c.windows:
        if win.side > 0:
            win_marks += [win.x - win.width / 2, win.x + win.width / 2]
    chain(win_marks, Y(-L.HALF) + 34, False)
    corr = [bd.x_a, bd.x_b] + [x + d * L.EXT_DOOR_W / 2 for _, x in bd.exterior_doors for d in (-1, 1)]
    chain(corr, Y(-L.HALF) + 64, False)
    svg.text(X((bd.buffer_a + bd.buffer_b) / 2), Y(-L.HALF) + 96, 'Windows on the +Y side (2nd chain) · exterior doors 0.75 m (3rd chain)', 11, color='#555')
    # transverse chain at the left end
    xa = X(bd.buffer_a) - 40
    if c.name == 'first-class':
        ys = [-L.HALF, -L.IN, L.CORR_Y, L.ROOM_Y, L.IN, L.HALF]
    elif c.name != 'restaurant':
        ys = [-L.HALF, -L.IN, L.IN, L.HALF]
    else:
        tb = [p for p in c.placements if p.asset == 'restaurant-banquette' and p.y > 0][0]
        x0, x1, y0, y1 = L.footprint(tb)
        ys = [-L.HALF, -L.IN, -y0, y0, L.IN, L.HALF]
    for y in ys:
        svg.line(xa - 5, Y(y), xa + 5, Y(y), '#444', .7)
    svg.line(xa, Y(ys[0]), xa, Y(ys[-1]), '#444', .7)
    for a, b in zip(ys, ys[1:]):
        if b - a > .04:
            svg.text(xa - 8, Y((a + b) / 2) + 3, f'{b - a:.3f}', 9, 'end')
    # legend and key numbers
    ly = Y(-L.HALF) + 130
    items = [('#3b2414', '50 mm partitions'), ('#9ad3f0', 'glazing (real opening)'), ('#b38b3c', 'sliding leaf (open)'),
             ('#3b6fd8', 'fixed reservation (bar, galley, WC…)')] + [(v, k) for k, v in ASSET.items() if k in {p.asset for p in c.placements}]
    x = margin_x
    for col, label in items:
        svg.rect(x, ly, 14, 10, col, '#222', .5)
        svg.text(x + 20, ly + 9, label, 10, 'start')
        x += 30 + 6.2 * len(label)
    seats = len(c.seats)
    svg.text(margin_x, ly + 36, f'Seats: {seats} · doors: {len(c.doors)} · clear interior 2.95 m · headroom 2.30 m at the centre, '
             f'2.05 m at the walls · floor {L.FLOOR_Z:.2f} m above the rail', 12, 'start')
    return svg


def section():
    S2 = 110
    w, h = 960, 680
    svg = Svg(w, h)
    cx, base = 330, 600
    Yy = lambda y: cx + y * S2
    Z = lambda z: base - z * S2
    svg.text(30, 34, 'Common cross-section (m above the rail)', 20, 'start', 'bold')
    pts = [(-L.HALF, L.SKIRT_Z), (L.HALF, L.SKIRT_Z), (L.HALF, L.CANT_Z)]
    pts += [(L.HALF - 2 * L.HALF * k / 30, L.roof_z(L.HALF - 2 * L.HALF * k / 30)) for k in range(31)]
    svg.add('<polygon points="' + ' '.join(f'{Yy(y):.1f},{Z(z):.1f}' for y, z in pts) + '" fill="#e8e2d6" stroke="#20283c" stroke-width="2"/>')
    inner = [(-L.IN, L.FLOOR_Z), (L.IN, L.FLOOR_Z)] + [(L.IN - 2 * L.IN * k / 30, L.ceiling_z(L.IN - 2 * L.IN * k / 30)) for k in range(31)]
    svg.add('<polygon points="' + ' '.join(f'{Yy(y):.1f},{Z(z):.1f}' for y, z in inner) + '" fill="#fff" stroke="#3b2414" stroke-width="1.5"/>')
    for sy in (-1, 1):
        svg.rect(Yy(min(sy * L.IN, sy * L.HALF)), Z(L.HEAD), L.WALL * S2, (L.HEAD - L.SILL) * S2, '#9ad3f0', '#2a6f97', 1)
    svg.rect(Yy(L.CORR_Y), Z(L.ceiling_z(L.CORR_Y)), L.PART * S2, (L.ceiling_z(L.CORR_Y) - L.FLOOR_Z) * S2, '#3b2414', 'none', 0, .8, None)
    svg.line(Yy(-L.GAUGE / 2), Z(0), Yy(L.GAUGE / 2), Z(0), '#555', 3)
    for sy in (-1, 1):            # wheels seen edge-on, the axle between them
        y0 = min(sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .11))
        svg.rect(Yy(y0), Z(2 * L.WHEEL_R), .13 * S2, 2 * L.WHEEL_R * S2, '#bbb', '#555', 1)
    svg.rect(Yy(-.98), Z(L.WHEEL_R + .075), 1.96 * S2, .15 * S2, '#999', '#555', .6)
    # Cairo and the adult gauge in the corridor
    for y, hgt, col, label in ((-1.13, L.HUMAN['height'], '#c0392b', 'adult 1.75'), (-.80, L.CAIRO['height'], '#8e44ad', 'Cairo 1.48')):
        svg.rect(Yy(y) - 12, Z(L.FLOOR_Z + hgt), 24, hgt * S2, col, col, 1, .35)
        svg.text(Yy(y), Z(L.FLOOR_Z + hgt) - 6, label, 9, color=col)
    levels = [('rail', 0), ('skirt', L.SKIRT_Z), ('buffers', L.BUFFER_Z), ('floor', L.FLOOR_Z), ('blue/ivory belt', L.BELT_Z),
              ('window sill', L.SILL), ('window head', L.HEAD), ('ceiling spring', L.CEIL_SPRING), ('cants (top of the walls)', L.CANT_Z),
              ('ceiling at the centre', L.CEIL_APEX), ('roof', L.ROOF_TOP), ('ventilators', L.VENT_TOP)]
    last = None
    for name, z in levels:          # labels pushed apart where two levels are close
        ty = Z(z) + 4 if last is None else min(Z(z) + 4, last - 13)
        svg.line(Yy(L.HALF) + 10, Z(z), 690, Z(z), '#999', .6, '3,3')
        svg.line(690, Z(z), 694, ty - 4, '#999', .6)
        svg.text(698, ty, f'{z:.3f}  {name}', 11, 'start')
        last = ty
    svg.line(Yy(-L.HALF), Z(-.18), Yy(L.HALF), Z(-.18), '#444', .7)
    svg.text(Yy(0), Z(-.18) + 15, f'{L.WIDTH:.2f} outside · {2 * L.IN:.2f} inside · gauge {L.GAUGE:.3f}', 11)
    svg.text(30, 70, 'First class: corridor 0.90 · partition 0.05 · cabin 2.00 = 2.95', 12, 'start', color='#555')
    svg.text(30, 88, 'Gauge 1.435 and platform heights: assumptions to validate against the map', 12, 'start', color='#555')
    return svg


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for c in L.coaches():
        plan(c).save(OUT / f'{c.name}-plan.svg')
    section().save(OUT / 'section.svg')
    print('BELMONTE TRAIN PLAN COMPLETE', flush=True)


if __name__ == '__main__':
    main()
