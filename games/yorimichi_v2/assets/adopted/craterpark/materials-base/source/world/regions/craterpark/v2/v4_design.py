"""Portable v4 JSON design compiler; no mesh generation, runtime or acceptance proof.

Headings are degrees from native +x toward +z; native y is up. Profiles use
horizontal plan metres, including circular vertical arcs. Terrain-dependent
paths require an explicit contour resolver; they never silently become straights.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
from typing import Callable

import numpy as np

DESIGN_ENV = 'ATELIER_CRATERPARK_V4_DESIGN'
KINDS = {'rollin', 'straight', 'shared', 'turn', 'half_bowl', 'gap', 'elbow', 'bowl_entry', 'contour', 'link'}


class DesignError(ValueError):
    """Malformed design, graph or unresolved reference (compiler error)."""


class UnsupportedDesignError(DesignError):
    """An explicit resolver or unsupported schema feature is required."""


class DesignAcceptanceError(ValueError):
    """Well-formed parameters cannot meet the requested geometric constraint."""


@dataclass(frozen=True)
class Diagnostic:
    category: str
    status: str
    item: str
    message: str


@dataclass
class ResolvedDesign:
    document: dict
    segments: dict
    order: list[str]
    geo: dict
    lines: list[dict]
    preds: dict
    line_of: dict
    diagnostics: list[Diagnostic] = field(default_factory=list)
    source: Path | None = None
    terrain: Terrain | None = None
    inputs: list[Path] = field(default_factory=list)

    def ground_at(self, x, z):
        if self.terrain is None:
            raise DesignError("no terrain loaded")
        return self.terrain(x, z)

    @property
    def seg(self):
        """Checker-compatible alias, without importing the private checker."""
        return self.segments

    @property
    def lift(self):
        return float(self.document.get('frame', {}).get('lift', 680.))


def _number(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, bool):
        raise DesignError(f'{label}: expected finite number')
    try:
        v = float(value)
    except (TypeError, ValueError) as error:
        raise DesignError(f'{label}: expected finite number') from error
    if not math.isfinite(v) or (positive and v <= 0) or (nonnegative and v < 0):
        raise DesignError(f'{label}: invalid numeric range')
    return v


def _unit(heading):
    a = math.radians(heading)
    return np.array([math.cos(a), math.sin(a)])


def _wrap(a):
    return (a + 180.) % 360. - 180.


def _merge(*values):
    """Merge fields, including per-side wall properties, without aliasing inputs."""
    out = {}
    for value in values:
        if not isinstance(value, dict):
            raise DesignError('defaults, templates and elements must be objects')
        for key, v in value.items():
            if key == 'walls':
                if not isinstance(v, dict) or set(v) - {'L', 'R'}:
                    raise DesignError('walls must contain only L/R objects')
                walls = out.setdefault('walls', {})
                for side, wall in v.items():
                    if not isinstance(wall, dict):
                        raise DesignError('wall must be an object')
                    walls[side] = {**walls.get(side, {}), **deepcopy(wall)}
            else:
                out[key] = deepcopy(v)
    return out


def _topological(dependencies, label):
    result, active, visited = [], set(), set()

    def visit(node):
        if node in active:
            raise DesignError(f'{label}: cyclic reference at {node}')
        if node in visited:
            return
        if node not in dependencies:
            raise DesignError(f'{label}: dangling reference {node}')
        active.add(node)
        for dep in dependencies[node]:
            visit(dep)
        active.remove(node)
        visited.add(node)
        result.append(node)

    for node in dependencies:
        visit(node)
    return result


def sample_profile(y0, a0, parts, *, step=.5):
    """@cc [owner:fontanierh,label:correctness] v4-exact-profile
    Profile stations MUST be horizontal metres with analytic circle heights,
    include every part endpoint, and remain strictly increasing. Impossible
    requested lengths MUST fail explicitly, never be clamped into a new shape.
    """
    step = _number(step, 'step', positive=True)
    y, a = _number(y0, 'profile y'), _number(a0, 'profile slope')
    if abs(a) >= 89.9:
        raise DesignError('longitudinal profiles require slope below 89.9 degrees')
    s = 0.
    rows, breaks, normalized = [(s, y, a, 0.)], [0.], []
    for part in parts:
        if not isinstance(part, (list, tuple)) or not part:
            raise DesignError('profile part must be line/arc tuple')
        kind = part[0]
        if kind == 'line' and len(part) == 2:
            length = _number(part[1], 'profile line length', nonnegative=True)
            normalized.append(('line', length))
            if length == 0:
                continue
            n = max(1, math.ceil(length / step))
            for j in range(1, n + 1):
                ds = length * j / n
                rows.append((s + ds, y + ds * math.tan(math.radians(a)), a, 0.))
            s, y = rows[-1][:2]
        elif kind == 'arc' and len(part) == 3:
            radius = _number(part[1], 'profile arc radius', positive=True)
            target = _number(part[2], 'profile arc target')
            if abs(target) >= 89.9:
                raise DesignError('longitudinal profiles require slope below 89.9 degrees')
            normalized.append(('arc', radius, target))
            if abs(target - a) < 1e-12:
                continue
            sign = 1. if target > a else -1.
            ar = math.radians(a)
            n = max(1, math.ceil(radius * math.radians(abs(target - a)) / step))
            for j in range(1, n + 1):
                angle = a + (target - a) * j / n
                rad = math.radians(angle)
                rows.append((s + radius * abs(math.sin(rad) - math.sin(ar)),
                             y + sign * radius * (math.cos(ar) - math.cos(rad)), angle, sign * radius))
            s, y, a = rows[-1][:3]
        else:
            raise DesignError(f'unknown or malformed profile part {kind!r}')
        breaks.append(s)
    data = np.asarray(rows, dtype='f8')
    if len(data) > 1 and not (np.diff(data[:, 0]) > 0).all():
        raise DesignError('profile stations are not strictly increasing')
    return data, sorted(set(breaks)), normalized


def _arc_dx(radius, a, b):
    return radius * abs(math.sin(math.radians(b)) - math.sin(math.radians(a)))


def _straight_parts(y0, a0, length, radius, grade, end, y1=None):
    def parts(g):
        dx = _arc_dx(radius, a0, g) + (0. if end is None else _arc_dx(radius, g, end))
        if dx > length + 1e-8:
            raise DesignAcceptanceError('segment too short for its requested vertical transitions')
        return [('arc', radius, g), ('line', max(0., length - dx))] + ([] if end is None else [('arc', radius, end)])

    if y1 is not None:
        # Search only geometrically feasible grades; no fallback approximation.
        candidates = []
        for g in np.linspace(-40., 40., 801):
            try:
                p = parts(float(g))
            except DesignAcceptanceError:
                continue
            value = sample_profile(y0, a0, p, step=max(1., length))[0][-1, 1]
            candidates.append((float(g), float(value)))
        bracket = next(((ga, gb) for (ga, ya), (gb, yb) in zip(candidates, candidates[1:])
                        if min(ya, yb) - 1e-9 <= y1 <= max(ya, yb) + 1e-9), None)
        if bracket is None:
            raise DesignAcceptanceError(f'target y={y1:g} unreachable from y={y0:g}, slope={a0:g}, length={length:g}, radius={radius:g}')
        lo, hi = bracket
        for _ in range(60):
            mid = (lo + hi) / 2
            ym = sample_profile(y0, a0, parts(mid), step=max(1., length))[0][-1, 1]
            if ym < y1:
                lo = mid
            else:
                hi = mid
        grade = (lo + hi) / 2
    return parts(grade), grade


def _normalize(document):
    if not isinstance(document, dict) or not isinstance(document.get('lines'), list):
        raise DesignError('design must contain a lines array')
    templates, elements = document.get('templates', {}), document.get('elements', {})
    if not isinstance(templates, dict) or not isinstance(elements, dict):
        raise DesignError('templates/elements must be objects')
    resolved_templates = {}

    def template(name, active=()):
        if name not in templates:
            raise DesignError(f'unknown template {name}')
        if name in active:
            raise DesignError(f'cyclic template reference {name}')
        if name not in resolved_templates:
            t = templates[name]
            if not isinstance(t, dict):
                raise DesignError(f'template {name} must be an object')
            parent = template(t['template'], active + (name,)) if 'template' in t else {}
            resolved_templates[name] = _merge(parent, t)
        return resolved_templates[name]

    for name in templates:
        template(name)
    segments, line_of, lines = {}, {}, deepcopy(document['lines'])
    line_ids = set()
    for line in lines:
        lid = line.get('id')
        if not isinstance(lid, str) or not lid or lid in line_ids:
            raise DesignError('line IDs must be nonempty unique strings')
        line_ids.add(lid)
        if not isinstance(line.get('segments'), list) or not line['segments']:
            raise DesignError(f'{lid}: segments must be a nonempty array')
        previous, ids = None, []
        for raw in line['segments']:
            if not isinstance(raw, dict):
                raise DesignError(f'{lid}: segment must be an object')
            tp = template(raw['template']) if 'template' in raw else {}
            kind = raw.get('kind', tp.get('kind', line.get('defaults', {}).get('kind')))
            value = _merge(elements.get(kind, {}), line.get('defaults', {}), tp, raw)
            sid = value.get('id')
            if not isinstance(sid, str) or not sid or sid.startswith('@') or sid in segments:
                raise DesignError('segment IDs must be nonempty unique strings without leading @')
            if value.get('kind') not in KINDS:
                raise UnsupportedDesignError(f'{sid}: unknown segment kind {value.get("kind")}')
            if 'after' not in value:
                if previous is None and not isinstance(line.get('start'), str):
                    raise DesignError(f'{lid}: first segment needs after or a line start')
                value['after'] = previous if previous else '@' + line['start']
            value['walls'] = _merge({'walls': {'L': {'type': 'bowl', 'h': 3., 'R': 3.5},
                                                         'R': {'type': 'bowl', 'h': 3., 'R': 3.5}}},
                                    {'walls': value.get('walls', {})})['walls']
            for wall in value['walls'].values():
                wall.setdefault('cap', 1.5)
                wall.setdefault('deck', 2.)
                wall.setdefault('fade', [0., 0.])
                wall.setdefault('outer', 'ground')
            value['_line'] = lid
            segments[sid], line_of[sid] = value, lid
            ids.append(sid)
            previous = sid
        for i, sid in enumerate(ids):
            s = segments[sid]
            if 'next' not in s:
                nxt = ids[i + 1] if i + 1 < len(ids) else None
                s['next'] = [nxt] if nxt and segments[nxt]['after'] == sid else []
            if not isinstance(s['next'], list) or any(not isinstance(n, str) for n in s['next']):
                raise DesignError(f'{sid}: next must be an array of segment IDs')
        line['segments'] = [segments[sid] for sid in ids]
    return segments, lines, line_of


def resolve_design(document, *, step=.5, contour_resolver: Callable | None = None, terrain=None):
    """@cc [owner:fontanierh,label:correctness] v4-portable-resolution
    Resolution MUST use only the supplied document and explicit callbacks. Unknown,
    dangling and cyclic references MUST fail explicitly. Air intervals MUST remain
    non-riding intervals; planning geometry MUST NOT claim native acceptance.
    """
    step = _number(step, 'step', positive=True)
    d = deepcopy(document)
    segments, lines, line_of = _normalize(d)
    starts = {}
    for r in d.get('tower', {}).get('roll_ins', []):
        rid = r.get('id')
        if not isinstance(rid, str) or rid in starts:
            raise DesignError('tower roll-in IDs must be unique strings')
        try:
            x, z = r['pos']
            y = r.get('deck_y', _number(d['tower']['deck_y'], 'tower deck') - _number(r.get('deck_drop', 0.), 'deck drop'))
            starts[rid] = dict(x=_number(x, 'start x'), z=_number(z, 'start z'),
                               y=_number(y, 'start y'), h=_number(r['heading'], 'start heading'), a=0.)
        except (KeyError, TypeError, ValueError) as error:
            raise DesignError(f'{rid}: malformed tower start') from error
    dependencies, preds = {}, {sid: [] for sid in segments}
    for sid, s in segments.items():
        after = s['after']
        if not isinstance(after, str):
            raise DesignError(f'{sid}: after must name a segment or @tower start')
        if after.startswith('@'):
            if after[1:] not in starts:
                raise DesignError(f'{sid}: dangling tower start {after}')
            deps = []
        else:
            deps = [after]
        if s['kind'] == 'link':
            target = s.get('to')
            if not isinstance(target, str) or not target.startswith('@') or target[1:] not in segments:
                raise DesignError(f'{sid}: dangling link target {target}')
            deps.append(target[1:])
        for key in ('len', 'y1'):
            value = s.get(key)
            if isinstance(value, str):
                if not value.startswith('@') or value[1:] not in segments:
                    raise DesignError(f'{sid}: dangling {key} reference {value}')
                deps.append(value[1:])
        dependencies[sid] = deps
        for nxt in s['next']:
            if nxt not in segments:
                raise DesignError(f'{sid}: dangling next reference {nxt}')
            preds[nxt].append(sid)
    order = _topological(dependencies, 'pose graph')
    _topological({sid: s['next'] for sid, s in segments.items()}, 'route graph')
    result = ResolvedDesign(d, segments, order, {}, lines, preds, line_of)
    result.terrain = terrain
    if contour_resolver is None and terrain is not None:
        contour_resolver = resolve_contour
    for sid in order:
        s = segments[sid]
        p0 = dict(starts[s['after'][1:]] if s['after'].startswith('@') else result.geo[s['after']]['end'])
        try:
            result.geo[sid] = _layout(s, p0, result, step, contour_resolver, terrain)
        except DesignAcceptanceError as error:
            raise DesignAcceptanceError(f'{sid}: {error}') from error
    result.diagnostics.append(Diagnostic('evidence', 'UNVERIFIED', 'design',
                                         'Resolved planning geometry; native gameplay and design acceptance are separate.'))
    return result


def _layout(s, p0, result, step, contour_resolver, terrain):
    sid, kind = s['id'], s['kind']
    y0, a0 = p0['y'], p0['a']
    radius = _number(s.get('vR', 80.), f'{sid}.vR', positive=True)
    width = _number(s.get('width', 16.), f'{sid}.width', positive=True)
    info, air_intervals, corner, turn = {}, [], None, 0.
    link_curve = None
    if kind == 'link':
        target = result.geo[s['to'][1:]]['start']
        origin = np.array([p0['x'], p0['z']])
        destination = np.array([target['x'], target['z']])
        tension = _number(s.get('tension', 1.), 'link tension', positive=True)
        scale = float(np.linalg.norm(destination-origin)) * tension
        if scale < 1e-8:
            raise DesignAcceptanceError(f'{sid}: link endpoints coincide')
        m0, m1 = scale*_unit(p0['h']), scale*_unit(target['h'])
        t = np.linspace(0., 1., 801)[:, None]
        curve = (2*t**3-3*t**2+1)*origin + (t**3-2*t**2+t)*m0 + (-2*t**3+3*t**2)*destination + (t**3-t**2)*m1
        cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(curve, axis=0),axis=1))]
        if not (np.diff(cumulative)>0).all():
            raise DesignAcceptanceError(f'{sid}: degenerate link curve')
        link_curve = curve,cumulative
        s = {**s, 'len':float(cumulative[-1]), 'y1':target['y'], 'end_deg':target['a']}
    if kind == 'rollin':
        steep = _number(s.get('steep_deg', 35.), 'steep_deg', positive=True)
        cr = _number(s.get('crest_R', 80.), 'crest_R', positive=True)
        fr = _number(s.get('foot_R', 60.), 'foot_R', positive=True)
        out = _number(s.get('out_deg', -5.), 'out_deg')
        drop = _number(s.get('drop'), 'drop', positive=True)
        arcs = sample_profile(y0, 0., [('arc', cr, -steep), ('arc', fr, out)], step=step)[0]
        straight = (drop + arcs[-1, 1] - y0) / math.tan(math.radians(steep))
        if straight < -1e-8:
            raise DesignAcceptanceError(f'{sid}: rollin drop smaller than its two arcs')
        parts = [('arc', cr, -steep), ('line', max(0., straight)), ('arc', fr, out), ('line', s.get('run', 0.))]
        p, breaks, parts = sample_profile(y0, 0., parts, step=step)
    elif kind in {'straight', 'shared', 'bowl_entry', 'contour', 'turn', 'half_bowl', 'link'}:
        if kind in {'turn', 'half_bowl'}:
            plan_r = _number(s.get('R'), f'{sid}.R', positive=True)
            turn = _wrap(_number(s['to_heading'], 'to_heading') - p0['h']) if 'to_heading' in s else _number(s.get('angle'), 'angle')
            length = plan_r * math.radians(abs(turn))
        else:
            length = s.get('len', 20.)
            if isinstance(length, str):
                target = result.geo[length[1:]]['start']
                length = (np.array([target['x'] - p0['x'], target['z'] - p0['z']]) @ _unit(p0['h'])) + _number(s.get('len_add', 0.), 'len_add')
                if length <= 0:
                    raise DesignAcceptanceError(f'{sid}: referenced endpoint is behind start')
            length = _number(length, f'{sid}.len', positive=True)
        end = s.get('end_deg', 0. if kind == 'bowl_entry' and s.get('entry', 'floor') == 'floor' else None)
        end = None if end is None else _number(end, 'end_deg')
        y1 = s.get('y1')
        if isinstance(y1, str):
            y1 = result.geo[y1[1:]]['start']['y']
        if kind == 'bowl_entry' and y1 is None:
            bowl = result.document.get('bowl', {})
            if s.get('entry', 'floor') == 'rim':
                y1 = _number(bowl.get('floor_y'), 'bowl.floor_y') + _number(bowl.get('wall', {}).get('h'), 'bowl.wall.h')
            else:
                endpoint = np.array([p0['x'], p0['z']]) + length * _unit(p0['h'])
                y1 = float(bowl_floor_at(result.document, endpoint)[0])
        if y1 is not None:
            y1 = _number(y1, 'y1') + _number(s.get('y1_add', 0.), 'y1_add')
        grade = _number(s.get('grade', 0. if kind == 'half_bowl' else -6.5), 'grade')
        parts, solved = _straight_parts(y0, a0, length, radius, grade, end, y1)
        p, breaks, parts = sample_profile(y0, a0, parts, step=step)
        info.update(grade_solved=solved, requested_y1=y1)
    elif kind == 'gap':
        run = _number(s.get('run', 0.), 'run', nonnegative=True)
        pre = [('arc', radius, s['run_deg'])] if run and 'run_deg' in s else []
        pre += [('line', run)] if run else []
        kick = s.get('kicker') or [('arc', s.get('kick_R', 25.), s.get('lip_deg', 18.)), ('line', s.get('lip_len', 3.))]
        kp, kb, kparts = sample_profile(y0, a0, pre + list(kick), step=step)
        lip_s, lip_y = kp[-1, :2]
        opening = _number(s.get('open'), 'open', positive=True)
        drop = _number(s.get('drop'), 'drop', nonnegative=True)
        receiver = s.get('receiver') or [('line', s.get('land_len', 24.)), ('arc', s.get('out_R', 40.), s.get('out_deg', -6.5)), ('line', s.get('out_len', 0.))]
        rp, rb, rparts = sample_profile(lip_y - drop, 0. if s.get('receiver') else -_number(s.get('land_deg', 26.), 'land_deg'), receiver, step=step)
        air_s = np.linspace(lip_s, lip_s + opening, max(2, math.ceil(opening / step)) + 1)[1:-1]
        chord = np.c_[air_s, lip_y - (air_s - lip_s) / opening * drop, np.full(len(air_s), np.nan), np.zeros(len(air_s))]
        rp[:, 0] += lip_s + opening
        p = np.concatenate([kp, chord, rp])
        breaks = kb + [lip_s + opening + q for q in rb]
        parts = {'kicker': kparts, 'receiver': rparts}
        air_intervals = [(float(lip_s), float(lip_s + opening))]
        info.update(lip_s=float(lip_s), lip_y=float(lip_y), knuckle_s=float(lip_s + opening), knuckle_y=float(lip_y - drop),
                    launch_parts=kparts, landing_parts=rparts, launch_y=y0, landing_y=float(lip_y-drop),
                    launch_deg=a0, landing_deg=0. if s.get('receiver') else -float(s.get('land_deg',26.)))
    elif kind == 'elbow':
        turn = _number(s.get('angle'), 'angle')
        approach = _number(s.get('approach', 8.), 'approach', nonnegative=True)
        transition = _arc_dx(radius, a0, 0.)
        corner = max(approach, transition)
        mouth = _number(s.get('mouth_len', 40.), 'mouth_len', positive=True)
        p, breaks, parts = sample_profile(y0, a0, [('arc', radius, 0.), ('line', corner - transition), ('line', max(approach, mouth))], step=step)
        breaks = sorted(set(breaks + [corner]))
        info['qp'] = deepcopy(s.get('qp', {'h': 7., 'R': 6., 'vert': 1., 'deck': 2.}))
    else:
        raise UnsupportedDesignError(f'{sid}: unsupported kind {kind}')
    sv, yv, angles, vr = p.T
    if len(sv) < 2 or not np.isfinite(yv).all() or not (np.diff(sv) > 0).all():
        raise DesignError(f'{sid}: empty or nonfinite profile')
    origin, heading = np.array([p0['x'], p0['z']]), p0['h']
    if kind == 'link':
        curve, cumulative = link_curve
        xy = np.c_[np.interp(sv,cumulative,curve[:,0]),np.interp(sv,cumulative,curve[:,1])]
        delta = np.gradient(xy,axis=0)
        hh = np.degrees(np.unwrap(np.arctan2(delta[:,1],delta[:,0])))
        hh -= 360.*np.round((hh[0]-heading)/360.)
        hh[0] = heading
        hh[-1] = heading + _wrap(target['h']-heading)
        info['plan_source'] = '801-station cubic Hermite chord-length parameterization'
    elif kind == 'contour' or s.get('follow'):
        if contour_resolver is None:
            raise UnsupportedDesignError(f'{sid}: terrain-dependent contour/follow requires contour_resolver; no straight fallback')
        resolved = contour_resolver(segment=deepcopy(s), start=dict(p0), stations=sv.copy(), heights=yv.copy(), design=result, terrain=terrain)
        xy, hh = np.asarray(resolved['xz'], dtype='f8'), np.asarray(resolved['heading'], dtype='f8')
        if xy.shape != (len(sv), 2) or hh.shape != sv.shape or not np.isfinite(xy).all() or not np.isfinite(hh).all():
            raise DesignError(f'{sid}: contour resolver must return finite xz(N,2), heading(N)')
        if not np.allclose(xy[0], origin, atol=1e-8, rtol=0) or abs(_wrap(hh[0] - heading)) > 1e-8:
            raise DesignError(f'{sid}: contour resolver moved the start port')
        info['plan_source'] = 'explicit contour resolver; terrain-dependent'
    elif kind in {'turn', 'half_bowl'}:
        sign = 1. if turn > 0 else -1.
        theta = heading + np.degrees(sv / plan_r) * sign
        xy = origin + plan_r / sign * np.c_[np.sin(np.radians(theta)) - math.sin(math.radians(heading)), -np.cos(np.radians(theta)) + math.cos(math.radians(heading))]
        hh = theta
    elif kind == 'elbow':
        corner_point = origin + corner * _unit(heading)
        xy = np.where((sv <= corner)[:, None], origin + sv[:, None] * _unit(heading), corner_point + (sv - corner)[:, None] * _unit(heading + turn))
        hh = np.where(sv <= corner, heading, heading + turn)
    else:
        xy, hh = origin + sv[:, None] * _unit(heading), np.full(len(sv), heading)
    air = np.zeros(len(sv), dtype=bool)
    for lo, hi in air_intervals:
        air |= (sv > lo) & (sv < hi)
    return dict(id=sid, kind=kind, start=dict(p0), end=dict(x=float(xy[-1, 0]), z=float(xy[-1, 1]), h=float(hh[-1]), y=float(yv[-1]), a=float(angles[-1])),
                s=sv, y=yv, deg=angles, vR=vr, x=xy[:, 0], z=xy[:, 1], h=hh, air=air, air_intervals=air_intervals,
                L=float(sv[-1]), W=width, wl=deepcopy(s['walls']['L']), wr=deepcopy(s['walls']['R']),
                profile_parts=parts, breakpoints=sorted(set(breaks)), turn=turn, corner=corner, info=info,
                metadata=deepcopy(s),
                **{key: info[key] for key in ('launch_parts', 'landing_parts', 'launch_y', 'landing_y', 'launch_deg', 'landing_deg') if key in info})


def load_design(path=None, *, step=.5, contour_resolver=None, terrain=None):
    """Load caller-selected JSON (or DESIGN_ENV); external elements are relative to it.

    Site/ground/physics files remain metadata for their explicit downstream owners.
    In particular, this loader never imports a design's speed_model Python file.
    """
    path = path or os.environ.get(DESIGN_ENV)
    if not path:
        raise DesignError(f'provide design path or set {DESIGN_ENV}')
    source = Path(path).expanduser().resolve()
    try:
        document = json.loads(source.read_text())
        if not isinstance(document, dict):
            raise DesignError('design JSON must be an object')
        if document.get('elements_file'):
            external = json.loads((source.parent / document['elements_file']).read_text())
            document['elements'] = _merge(external, document.get('elements', {}))
    except (OSError, json.JSONDecodeError) as error:
        raise DesignError('cannot read design JSON or its elements file') from error
    needs_terrain = any(s.get('kind') == 'contour' or s.get('follow') for line in document.get('lines', []) for s in line.get('segments', []))
    if terrain is None and (needs_terrain or document.get('ground', {}).get('heightmap')):
        terrain = terrain_from_document(document, source.parent)
    result = resolve_design(document, step=step, contour_resolver=contour_resolver, terrain=terrain)
    result.source = source
    result.inputs = [source]
    if isinstance(terrain, Terrain):
        result.inputs.append(terrain.source)
    if document.get('elements_file'):
        result.inputs.append((source.parent / document['elements_file']).resolve())
    return result


@dataclass
class Terrain:
    """Regular native terrain; heights are indexed [z,x]. Edge queries clamp."""
    x: np.ndarray
    z: np.ndarray
    heights: np.ndarray
    original_heights: np.ndarray
    source: Path

    def __call__(self, x, z):
        x, z = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(z, 'f8'))
        fi, fj = (x - self.x[0]) / (self.x[1] - self.x[0]), (z - self.z[0]) / (self.z[1] - self.z[0])
        i = np.clip(np.floor(fi).astype(int), 0, len(self.x) - 2)
        j = np.clip(np.floor(fj).astype(int), 0, len(self.z) - 2)
        tx, tz = np.clip(fi - i, 0, 1), np.clip(fj - j, 0, 1)
        h = self.heights
        return h[j, i] * (1-tx) * (1-tz) + h[j, i+1] * tx * (1-tz) + h[j+1, i] * (1-tx) * tz + h[j+1, i+1] * tx * tz


def terrain_from_document(document, base_dir):
    """Load native axes or legacy cell-centred NPZ grids and optional DEPTH layer."""
    ground = document.get('ground', {})
    if not isinstance(ground, dict) or not isinstance(ground.get('heightmap'), str):
        raise DesignError('terrain-dependent design needs ground.heightmap')
    source = (Path(base_dir) / Path(ground['heightmap']).expanduser()).resolve()
    try:
        with np.load(source, allow_pickle=False) as data:
            layer = ground.get('layer', 'mount')
            h = np.asarray(data[layer], 'f8').copy()
            if 'native_x' in data:
                x, z = np.asarray(data['native_x'], 'f8'), np.asarray(data['native_z'], 'f8')
            else:
                cell = _number(data['G'], 'ground cell', positive=True)
                x = float(data['x0']) + (np.arange(h.shape[1]) + .5) * cell
                z = float(data['z0']) + (np.arange(h.shape[0]) + .5) * cell
            original = h.copy()
            dig = ground.get('dig')
            if dig:
                if dig.get('kind') != 'depth':
                    raise UnsupportedDesignError('ground dig supports explicit depth layers only')
                depth = _number(dig.get('DEPTH'), 'DEPTH', positive=True)
                if depth != int(depth):
                    raise DesignError('DEPTH must be an integer layer')
                if depth != 45:
                    h = np.asarray(data[f'natural_d{int(depth)}'], 'f8').copy()
    except (OSError, KeyError, IndexError) as error:
        raise DesignError('missing/invalid terrain grid or requested depth layer') from error
    if (x.ndim != 1 or z.ndim != 1 or min(len(x), len(z)) < 2 or h.shape != (len(z), len(x))
            or original.shape != h.shape or not np.isfinite(x).all() or not np.isfinite(z).all()
            or not (np.diff(x) > 0).all() or not (np.diff(z) > 0).all()
            or not np.allclose(np.diff(x), x[1]-x[0]) or not np.allclose(np.diff(z), z[1]-z[0])):
        raise DesignError('terrain must be a regular increasing native [z,x] grid')
    threshold = _number(ground.get('valid_min', -1000.), 'ground valid_min')
    h[h < threshold], original[original < threshold] = np.nan, np.nan
    if not np.isfinite(h).any():
        raise DesignError('terrain has no valid heights')
    return Terrain(x, z, h, original, source)


def resolve_contour(*, segment, start, stations, heights, design, terrain):
    """Pure port of the planning checker's contour steering, including lookahead.

    Integrates the supplied profile stations; it is a sampled plan, not an exact
    circular path or a gameplay controller. Unknown radial terrain is an error.
    """
    if terrain is None or not callable(terrain):
        raise UnsupportedDesignError(f'{segment["id"]}: contour requires explicit terrain')
    s, sv, yv = segment, stations, heights
    off = _number(s.get('offset', 0.), 'offset')
    minimum = _number(s.get('Rmin', 80.), 'Rmin', positive=True)
    gain, bias = _number(s.get('gain', 1.5), 'gain'), _number(s.get('bias_deg', 0.), 'bias_deg')
    centre = np.asarray(design.document.get('crater_centre', [1300., 1008.6]), 'f8')
    if centre.shape != (2,) or not np.isfinite(centre).all():
        raise DesignError('crater_centre must be finite [x,z]')
    radial = np.arange(150., 600., 2.)
    p, heading = np.array([start['x'], start['z']], 'f8'), start['h']
    xy, hh = [p.copy()], [heading]
    nxt = None
    if s.get('next') and s.get('aim', True) is not False:
        ns = design.segments[s['next'][0]]
        if (ns['kind'] in {'gap', 'straight', 'shared', 'bowl_entry'} and not ns.get('follow')
                and not isinstance(ns.get('len'), str) and not isinstance(ns.get('y1'), str)):
            dry_start = dict(x=0., z=0., h=0., y=float(yv[-1]), a=float(s.get('grade', -6.5)))
            try:
                dry = _layout(ns, dry_start, design, .5, None, None)
                nxt = (dry['L'], float(yv[-1] - dry['end']['y']))
            except DesignAcceptanceError:
                pass
    window = _number(s.get('aim_window', 60.), 'aim_window', positive=True)

    def profile(q):
        v = q - centre
        r = float(np.linalg.norm(v))
        if r < 1e-9:
            raise DesignAcceptanceError('contour reaches its radial centre')
        rd = v / r
        raw = np.asarray(terrain(centre[0] + radial * rd[0], centre[1] + radial * rd[1]), 'f8')
        if raw.shape != radial.shape or not np.isfinite(raw).any():
            raise DesignError('contour radial terrain query has no valid heights')
        pr = np.where(np.isfinite(raw), raw, -1e3)
        return r, rd, pr, int(np.argmax(pr))

    def rtarget(q, yt):
        r, rd, pr, peak = profile(q)
        if pr[peak] <= yt + 1.:
            return r, radial[peak]
        below = np.nonzero(pr[:peak+1] <= yt)[0]
        if not len(below):
            return r, r
        j = below[-1]
        rt = radial[j] + (2. * (yt-pr[j]) / (pr[j+1]-pr[j]) if j+1 <= peak and pr[j+1] != pr[j] else 0.)
        return r, rt

    for i in range(1, len(sv)):
        ds = sv[i] - sv[i-1]
        if nxt and sv[-1] - sv[i-1] < window:
            length, drop = nxt
            best = None
            for dh in np.arange(-40., 40.1, 2.):
                candidate = heading + dh
                q = p + (sv[-1]-sv[i-1]+length) * _unit(candidate)
                qm = p + (sv[-1]-sv[i-1]+length/2) * _unit(candidate)
                r1, rt1 = rtarget(q, yv[-1]-drop-off)
                r2, rt2 = rtarget(qm, yv[-1]-drop/2-off)
                error = abs(r1-rt1) + .5*abs(r2-rt2) + .2*abs(dh)
                if best is None or error < best[0]:
                    best = (error, candidate)
            desired = best[1] + bias
        else:
            r, rd, pr, peak = profile(p)
            yt, target = yv[i-1]-off, None
            desired = heading
            if pr[peak] > yt + 1.:
                below = np.nonzero(pr[:peak+1] <= yt)[0]
                if len(below):
                    j = below[-1]
                    target = radial[j] + (2.*(yt-pr[j])/(pr[j+1]-pr[j]) if j+1 <= peak and pr[j+1] != pr[j] else 0.)
            elif pr[peak] > -500.:
                target = radial[peak] - _number(s.get('crest_in', 6.), 'crest_in')
            if target is not None:
                tangent = np.array([-rd[1], rd[0]])
                if tangent @ _unit(heading) < 0:
                    tangent = -tangent
                beta = np.clip(math.atan(gain*(target-r)/10.), -math.radians(40.), math.radians(40.))
                direction = tangent*math.cos(beta) + rd*math.sin(beta)
                desired = math.degrees(math.atan2(direction[1], direction[0]))
            desired += bias
        limit = math.degrees(ds / minimum)
        heading += float(np.clip(_wrap(desired-heading), -limit, limit))
        p = p + ds * _unit(heading)
        xy.append(p.copy())
        hh.append(heading)
    return {'xz': np.asarray(xy), 'heading': np.asarray(hh)}


def bowl_floor_at(document, points):
    """Checker's shallow-pocket quintic in the bowl's scaled local +x axis."""
    bowl = document.get('bowl', {})
    floor = _number(bowl.get('floor_y'), 'bowl.floor_y')
    shallow = _number(bowl.get('shallow_y', floor), 'bowl.shallow_y')
    if shallow == floor:
        return np.full(len(np.atleast_2d(points)), floor)
    centre, scale = np.asarray(bowl.get('centre'), 'f8'), np.asarray(bowl.get('scale', [1., 1.]), 'f8')
    if centre.shape != (2,) or scale.shape != (2,) or not np.isfinite(centre).all() or not np.isfinite(scale).all() or (scale<=0).any():
        raise DesignError('bowl centre/scale must be finite positive 2D frame')
    angle = math.radians(_number(bowl.get('axis_deg', 0.), 'bowl.axis_deg'))
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    x = (((np.atleast_2d(points)-centre) @ rotation)/scale)[:,0]
    blend = _number(bowl.get('floor_blend_m', 18.), 'bowl.floor_blend_m', positive=True)
    t = np.clip(x/blend,0.,1.)
    return floor + (shallow-floor)*t**3*(t*(t*6.-15.)+10.)
