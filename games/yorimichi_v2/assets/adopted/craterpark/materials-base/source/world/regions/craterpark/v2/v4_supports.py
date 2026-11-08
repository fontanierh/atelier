"""Exact convex support/material contacts, plus closed ride-envelope containment.

Supports MUST supply their actual closed material boundary, not a visual proxy.
Nonconvex supports need an explicit decomposition into independently checked convex bodies.
No mesh sampling is used to establish surface clearance.
"""
import math

import numpy as np

from . import dsl


class SupportError(ValueError):
    pass


def _triangles(value):
    t = np.asarray(value, 'f8')
    if t.ndim != 3 or t.shape[1:] != (3, 3) or not len(t) or not np.isfinite(t).all():
        raise SupportError('material/envelope boundary must contain finite triangles')
    return t


def _closed(t, tol):
    """Require a consistently wound welded two-manifold, including every component."""
    points, ids = np.unique(np.round(t.reshape(-1, 3) / tol).astype('i8'), axis=0, return_inverse=True)
    f = ids.reshape(-1, 3)
    if np.any(np.diff(np.sort(f, axis=1), axis=1) == 0):
        raise SupportError('closed body has a degenerate welded face')
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    keys = np.sort(edges, axis=1)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    orientation = np.bincount(inverse, weights=np.where(edges[:, 0] < edges[:, 1], 1., -1.))
    if np.any(counts != 2) or np.any(orientation != 0):
        raise SupportError('body must be closed and consistently wound')
    return points


def _convex(t, tol, max_work=2_000_000):
    _closed(t, tol)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    length = np.linalg.norm(n, axis=1)
    if np.any(length <= tol * tol):
        raise SupportError('support boundary has degenerate faces')
    n /= length[:, None]
    vertices = np.unique(t.reshape(-1, 3), axis=0)
    if len(vertices) * len(n) > max_work:
        raise SupportError('support convex verification budget exceeded')
    centre = vertices.mean(0)
    # A convex body's centre is strictly inside every face. Orient independent of input winding.
    signed = np.einsum('ij,ij->i', n, centre - t[:, 0])
    if np.any(np.abs(signed) <= tol):
        raise SupportError('support body has no resolved three-dimensional interior')
    n[signed > 0] *= -1
    offset = np.einsum('ij,ij->i', n, t[:, 0])
    # A face on a concavity would exclude another body vertex: never approximate it with a hull.
    for start in range(0, len(n), 128):
        if np.any(vertices @ n[start:start + 128].T - offset[start:start + 128] > tol):
            raise SupportError('nonconvex support needs an explicit convex decomposition')
    planes = np.c_[n, offset]
    _, first = np.unique(np.round(planes / tol).astype('i8'), axis=0, return_index=True)
    planes = planes[np.sort(first)]
    return planes, vertices


def _clip(poly, planes, tol):
    """Convex polygon intersected with exact material halfspaces; boundary is retained."""
    poly = np.asarray(poly, 'f8')
    for plane in planes:
        if not len(poly):
            break
        d = poly @ plane[:3] - plane[3]
        result = []
        for i, a in enumerate(poly):
            j = (i + 1) % len(poly)
            b, da, db = poly[j], d[i], d[j]
            inside_a, inside_b = da <= tol, db <= tol
            if inside_a:
                result.append(a)
            if inside_a != inside_b:
                denominator = da - db
                if abs(denominator) <= np.finfo(float).eps:
                    raise SupportError('unresolved near-parallel material contact')
                # Snap to the exact plane, rather than admitting an epsilon-thick penetration.
                result.append(a + np.clip(da / denominator, 0., 1.) * (b - a))
        poly = np.asarray(result, 'f8').reshape(-1, 3)
    return poly


def _patch(allowance, tol):
    key = 'polygon' if 'polygon' in allowance else 'chain'
    p = np.asarray(allowance.get(key), 'f8')
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < (3 if key == 'polygon' else 2) or not np.isfinite(p).all():
        raise SupportError('bearing needs a finite polygon or chain in native xyz')
    if key == 'chain':
        return key, p, None
    n = None
    for i in range(1, len(p) - 1):
        candidate = np.cross(p[i] - p[0], p[i + 1] - p[0])
        if np.linalg.norm(candidate) > tol * tol:
            n = candidate / np.linalg.norm(candidate)
            break
    if n is None or np.max(np.abs((p - p[0]) @ n)) > tol:
        raise SupportError('bearing polygon must be planar with nonzero area')
    for a, b in zip(p, np.roll(p, -1, axis=0)):
        edge = b - a
        if np.linalg.norm(edge) <= tol:
            raise SupportError('bearing polygon has a zero-length edge')
        if np.min(np.cross(edge, p - a) @ n) < -tol * np.linalg.norm(edge):
            raise SupportError('bearing polygon must be convex and consistently ordered')
    return key, p, n


def _bearing_contains(contact, patch, tol):
    kind, p, normal = patch
    if kind == 'polygon':
        if np.max(np.abs((contact - p[0]) @ normal)) > tol:
            return False
        return all(np.min(np.cross(b - a, contact - a) @ normal) >= -tol * np.linalg.norm(b - a)
                   for a, b in zip(p, np.roll(p, -1, axis=0)))
    # A convex contact can lie on a chain only if it is one point or one fully covered interval.
    a = contact[0]
    distances = np.linalg.norm(contact - a, axis=1)
    b = contact[int(np.argmax(distances))]
    length = float(np.linalg.norm(b - a))
    if length <= tol:
        return any(_segment_distance(a, u, v) <= tol for u, v in zip(p[:-1], p[1:]))
    axis = (b - a) / length
    if np.max(np.linalg.norm(np.cross(contact - a, axis), axis=1)) > tol:
        return False
    low, high = float(np.min((contact - a) @ axis)), float(np.max((contact - a) @ axis))
    intervals = []
    for u, v in zip(p[:-1], p[1:]):
        if max(np.linalg.norm(np.cross(u - a, axis)), np.linalg.norm(np.cross(v - a, axis))) <= tol:
            intervals.append(sorted([float((u - a) @ axis), float((v - a) @ axis)]))
    covered = low
    for lo, hi in sorted(intervals):
        if hi < covered - tol:
            continue
        if lo > covered + tol:
            return False
        covered = max(covered, hi)
        if covered >= high - tol:
            return True
    return False


def _segment_distance(p, a, b):
    d = b - a
    return float(np.linalg.norm(p - (a + np.clip(float((p - a) @ d) / max(float(d @ d), 1e-30), 0., 1.) * d)))


def _closed_components(triangles, features, tol):
    """Find closed connected boundaries even when their faces have different feature owners."""
    if not len(triangles):
        return []
    _, ids = np.unique(np.round(triangles.reshape(-1, 3) / tol).astype('i8'), axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    parent = np.arange(len(triangles))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first = {}
    for face, row in enumerate(ids):
        for vertex in row:
            if vertex in first:
                parent[find(face)] = find(first[vertex])
            else:
                first[vertex] = face
    groups = {}
    for face in range(len(triangles)):
        groups.setdefault(find(face), []).append(face)
    closed = []
    for faces in groups.values():
        owners = set(features[faces].tolist())
        if len(owners) < 2:
            continue  # already checked as a single feature
        body = triangles[faces]
        try:
            _closed(body, tol)
        except SupportError:
            continue
        closed.append((sorted(owners), body))
    return closed


def _inside_closed(point, triangles, tol):
    """Generalized winding of a closed oriented boundary; ambiguous results fail closed."""
    t = triangles - point
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    la, lb, lc = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1), np.linalg.norm(c, axis=1)
    if min(float(la.min()), float(lb.min()), float(lc.min())) <= tol:
        raise SupportError('unresolved containment at a boundary vertex')
    numerator = np.einsum('ij,ij->i', a, np.cross(b, c))
    denominator = la * lb * lc + np.einsum('ij,ij->i', a, b) * lc + np.einsum('ij,ij->i', b, c) * la + np.einsum('ij,ij->i', c, a) * lb
    winding = abs(float(np.arctan2(numerator, denominator).sum() / (2 * math.pi)))
    if abs(winding - round(winding)) > 1e-5 or winding > 1. + 1e-5:
        raise SupportError('unresolved closed-body winding')
    return winding > .5


def check(mesh, checks=(), *, envelopes=(), envelope_coverage=None, require_envelopes=True, tolerance=1e-7, max_pairs=2_000_000):
    """@cc [owner:fontanierh,label:correctness] v4-support-contact-proof
    Every support MUST have a closed convex actual-material boundary. Every protected triangle
    MUST be clipped against it in full; only exact declared boundary bearings MAY touch it.
    Missing ride envelopes MUST fail when requested. Unresolved geometry MUST fail closed.
    """
    tol = float(tolerance)
    if not math.isfinite(tol) or tol <= 0:
        raise SupportError('contact tolerance must be finite and positive')
    specs = [s for s in checks if s.get('kind') == 'v4_support']
    report = {'ok': True, 'method': 'convex material clipping; closed-body solid-angle containment',
              'tolerance_m': tol, 'support_count': len(specs), 'envelope_count': len(envelopes),
              'candidate_pairs': 0, 'broadphase_tests': 0, 'allowed_contacts': 0, 'failures': [],
              'scope': 'all riding/side/coping/rail faces plus supplied closed ride envelopes; convex supports only'}
    def fail(kind, support=None, target=None, **extra):
        report['failures'].append(dict(kind=kind, support=support, target=target, **extra))
        report['ok'] = False
    if specs and require_envelopes and not envelopes and not (envelope_coverage or {}).get('coverage_complete'):
        fail('missing_ride_envelopes')
    if envelope_coverage is not None:
        report['envelope_coverage'] = envelope_coverage
        if not envelope_coverage.get('ok') or not envelope_coverage.get('coverage_complete'):
            fail('incomplete_ride_envelopes')
    triangles = mesh.triangles()
    protected = np.isin(mesh.role, [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL)])
    targets = []
    for i, feature in enumerate(mesh.features):
        mask = mesh.feature == i
        surface = triangles[mask & protected]
        if not len(surface):
            continue
        closed = triangles[mask]
        try:
            _closed(closed, tol)
        except SupportError:
            closed = None
        targets.append((feature, surface, closed, None))
    try:
        for envelope in envelopes:
            body = _triangles(envelope['triangles'])
            _closed(body, tol)
            targets.append((envelope['feature'], body, body, envelope))
    except (SupportError, KeyError, TypeError) as error:
        fail('unresolved_envelope', detail=str(error))
        return report
    for spec in specs:
        name = spec.get('feature')
        try:
            if name not in mesh.features:
                raise SupportError('support feature is absent from the actual mesh')
            body = _triangles(spec.get('body_triangles'))
            planes, vertices = _convex(body, tol, max_pairs)
            patches = [(b['target_feature'], _patch(b, tol)) for b in spec.get('bearings', [])]
            # Metadata must describe the exposed support geometry itself.
            own = triangles[mesh.feature == mesh.features.index(name)]
            for tri in own:
                d = tri @ planes[:, :3].T - planes[:, 3]
                if np.max(d) > tol or not np.any(np.max(np.abs(d), axis=0) <= tol):
                    raise SupportError('actual support face does not lie on its declared material boundary')
            lo, hi = body.min((0, 1)), body.max((0, 1))
            material = np.isin(mesh.role, [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL, dsl.BASE)])
            material &= mesh.feature != mesh.features.index(name)
            if int(material.sum()) > max_pairs:
                raise SupportError('closed-material broadphase budget exceeded')
            for owners, closed_body in _closed_components(triangles[material], mesh.feature[material], tol):
                if np.all(hi >= closed_body.min((0, 1)) - tol) and np.all(lo <= closed_body.max((0, 1)) + tol):
                    if _inside_closed(vertices.mean(0), closed_body, tol):
                        fail('support_inside_closed_target', name,
                             '+'.join(mesh.features[i] for i in owners))
            for target, surface, closed, envelope in targets:
                if target == name:
                    continue
                report['broadphase_tests'] += len(surface)
                if report['broadphase_tests'] > max_pairs:
                    raise SupportError('support broadphase budget exceeded; no clearance conclusion')
                a, b = surface.min(1), surface.max(1)
                candidates = np.flatnonzero(np.all(b >= lo - tol, axis=1) & np.all(a <= hi + tol, axis=1))
                report['candidate_pairs'] += len(candidates)
                if report['candidate_pairs'] > max_pairs:
                    raise SupportError('support broadphase budget exceeded; no clearance conclusion')
                for index in candidates:
                    contact = _clip(surface[index], planes, tol)
                    if not len(contact):
                        continue
                    boundary = np.any(np.max(np.abs(contact @ planes[:, :3].T - planes[:, 3]), axis=0) <= tol)
                    bearing_target = envelope.get('bearing_feature') if envelope else target
                    on_floor = True
                    if envelope:
                        plane = envelope.get('bearing_plane')
                        on_floor = plane is not None and np.max(np.abs(contact @ np.asarray(plane[0]) - plane[1])) <= tol
                    allowed = boundary and on_floor and any(bearing_target == declared and _bearing_contains(contact, patch, tol)
                                                            for declared, patch in patches)
                    if allowed:
                        report['allowed_contacts'] += 1
                    else:
                        fail('ride_envelope_intersection' if envelope else 'support_surface_intersection', name, target,
                             face=int(index), contact=contact.tolist(), material_boundary_only=bool(boundary))
                # If surfaces do not cross, a support can still be wholly enclosed in another solid.
                if closed is not None and np.all(hi >= closed.min((0, 1)) - tol) and np.all(lo <= closed.max((0, 1)) + tol):
                    if _inside_closed(vertices.mean(0), closed, tol):
                        fail('support_inside_ride_envelope' if envelope else 'support_inside_closed_target', name, target)
        except (SupportError, KeyError, TypeError, ValueError) as error:
            fail('unresolved_support', name, detail=str(error))
            if 'budget exceeded' in str(error):
                return report
    return report


def require_clear(mesh, checks=(), **kwargs):
    report = check(mesh, checks, **kwargs)
    if not report['ok']:
        kinds = sorted({failure['kind'] for failure in report['failures']})
        raise SupportError('v4 support clearance failed: ' + ', '.join(kinds))
    return report


def _prism(loop, vector):
    p = np.asarray(loop, 'f8')
    vector = np.asarray(vector, 'f8')
    if np.cross(p[1] - p[0], p[2] - p[0]) @ vector < 0:
        p = p[::-1]
    q = p + vector
    t = []
    for i in range(1, len(p) - 1):
        t += [[p[0], p[i + 1], p[i]], [q[0], q[i], q[i + 1]]]
    for i in range(len(p)):
        j = (i + 1) % len(p)
        t += [[p[i], p[j], q[j]], [p[i], q[j], q[i]]]
    return np.asarray(t)


def _expanded_triangle(triangle, radius):
    """Triangle plus an in-plane square containing the rider's radius disk."""
    a, b, c = triangle
    u = b - a
    u /= np.linalg.norm(u)
    normal = np.cross(b - a, c - a)
    normal /= np.linalg.norm(normal)
    v = np.cross(normal, u)
    coordinates = np.c_[(triangle - a) @ u, (triangle - a) @ v]
    points = np.unique(np.concatenate([coordinates + [i * radius, j * radius]
                                      for i in (-1, 1) for j in (-1, 1)]), axis=0)
    ordered = sorted(map(tuple, points.tolist()))
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    lower, upper = [], []
    for p in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    xy = np.asarray(lower[:-1] + upper[:-1])
    return a + xy[:, :1] * u + xy[:, 1:] * v, normal


def derive_envelopes(mesh, checks=(), *, headroom=4., rider_radius=1.5, flight_step=2., max_envelopes=100_000):
    """Build conservative facet-front rider prisms and analytic ballistic speed-band slabs.

    Grounded prisms expand each complete riding facet by an in-plane square covering
    the rider radius, then extend headroom toward its front normal. Ballistic boxes
    cover every speed in an explicit band until the receiver's declared end; unknown
    bands/directions/receiver extents fail instead of inventing flight geometry.
    These are geometric planning envelopes, not certification of native physics.
    """
    specs = [s for s in checks if s.get('kind') == 'v4_support']
    report = {'ok': True, 'coverage_complete': True, 'grounded_facets': 0, 'grounded_far_clear': 0,
              'flight_slabs': 0, 'failures': [], 'headroom_m': headroom, 'rider_radius_m': rider_radius,
              'physics_status': 'ballistic planning model; native flight and wall riding remain unverified'}
    envelopes = []
    if not specs:
        return envelopes, report
    if headroom <= 0 or rider_radius <= 0 or flight_step <= 0:
        raise SupportError('rider envelope dimensions must be positive')
    bodies = [_triangles(s.get('body_triangles')) for s in specs]
    bounds = [(b.min((0, 1)), b.max((0, 1))) for b in bodies]
    def relevant(lo, hi):
        return any(np.all(hi >= a - 1e-7) and np.all(lo <= b + 1e-7) for a, b in bounds)
    def add(envelope):
        if len(envelopes) >= max_envelopes:
            raise SupportError('ride envelope budget exceeded; no acceptance conclusion')
        envelopes.append(envelope)
    t = mesh.triangles()
    for face in np.flatnonzero(mesh.role == dsl.ROLE[dsl.RIDING]):
        triangle = t[face]
        n = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        length = float(np.linalg.norm(n))
        if length <= 1e-14:
            report['ok'] = report['coverage_complete'] = False
            report['failures'].append({'kind': 'degenerate_riding_facet', 'face': int(face)})
            continue
        n /= length
        report['grounded_facets'] += 1
        # The in-plane square lies within radius*sqrt(2) of its source facet.
        expansion = rider_radius * math.sqrt(2.)
        lo = triangle.min(0) - expansion + np.minimum(0., n * headroom)
        hi = triangle.max(0) + expansion + np.maximum(0., n * headroom)
        if not relevant(lo, hi):
            report['grounded_far_clear'] += 1
            continue
        loop, n = _expanded_triangle(triangle, rider_radius)
        source_feature = mesh.features[int(mesh.feature[face])]
        add({'feature': f'grounded:{source_feature}:{face}', 'triangles': _prism(loop, n * headroom),
             'bearing_feature': source_feature, 'bearing_plane': [n.tolist(), float(n @ triangle[0])]})
    for air in (s for s in checks if s.get('kind') == 'air'):
        name = air.get('feature', 'unnamed-air')
        try:
            band = np.asarray(air.get('band'), 'f8')
            width = float(air['width'])
            lip = np.asarray(air['lip'], 'f8')
            landing = np.asarray(air['landing_start'], 'f8')
            station = np.asarray(air['landing_t'], 'f8')
            theta = math.radians(float(air['lip_degrees']))
            if band.shape != (2,) or not np.isfinite(band).all() or not 0 < band[0] <= band[1]:
                raise SupportError('air needs an explicit positive speed band')
            if lip.shape != (3,) or landing.shape != (3,) or station.shape != (2,) or width <= 0:
                raise SupportError('air needs finite lip/landing, receiver extent and width')
            direction = (landing - lip)[[0, 2]]
            gap = float(np.linalg.norm(direction))
            if gap <= 0 or station[1] <= station[0] or abs(theta) >= math.pi / 2:
                raise SupportError('air flight direction or receiver extent is unresolved')
            direction /= gap
            lateral = np.array([-direction[1], direction[0]])
            distance = gap + float(station[1] - station[0])
            if not np.isfinite([width, distance, theta, *lip, *landing]).all():
                raise SupportError('air envelope contains nonfinite parameters')
            apex = band[1] ** 2 * math.sin(theta) * math.cos(theta) / 9.81
            def y(x, speed):
                return lip[1] + math.tan(theta) * x - 9.81 * x * x / (2 * speed * speed * math.cos(theta) ** 2)
            for a in np.arange(0., distance, flight_step):
                b = min(float(a + flight_step), distance)
                bottom = min(y(a, band[0]), y(b, band[0]))
                top = y(float(np.clip(apex, a, b)), band[1]) + headroom
                half = width / 2 + rider_radius
                points = []
                for x, side in ((a - rider_radius, -half), (b + rider_radius, -half),
                                (b + rider_radius, half), (a - rider_radius, half)):
                    q = lip[[0, 2]] + direction * x + lateral * side
                    points.append([q[0], bottom, q[1]])
                body = _prism(points, [0., top - bottom, 0.])
                report['flight_slabs'] += 1
                if relevant(body.min((0, 1)), body.max((0, 1))):
                    add({'feature': f'flight:{name}:{a:g}', 'triangles': body})
        except (SupportError, KeyError, ValueError, TypeError) as error:
            report['ok'] = report['coverage_complete'] = False
            report['failures'].append({'kind': 'unresolved_air_envelope', 'feature': name, 'detail': str(error)})
    return envelopes, report
