"""Grind contacts derived from the same recovered pieces as the visible park."""
from collections import defaultdict
import numpy as np
from communitypark.source import FRAME, scene


def paths():
    source = scene(); result = []; seen = set()
    for instance in source.instances:
        mesh = source.gltf['meshes'][instance['mesh']]
        name = mesh['name']; primitive = mesh['primitives'][0]
        v = source.accessor(primitive['attributes']['POSITION']).astype(float)
        matrix = instance['matrix']; lines = []
        if '/rails/' in name:
            # The round rail's longitudinal apex is a source vertex row.
            top = v[:, 1].max(); lines = [('rail', np.array([[0, top, v[:, 2].min()], [0, top, v[:, 2].max()]]), .045)]
        elif '/ledges/' in name:
            top = v[:, 1].max()
            rim = v[abs(v[:, 1]-top) < 1e-5]
            for side in (rim[:, 0].min(), rim[:, 0].max()):
                lines.append(('ledge', np.array([[side, top, rim[:, 2].min()], [side, top, rim[:, 2].max()]]), .025))
        elif ('/bowl/' in name and 'floor' not in name) or 'quarterpipe' in name:
            # Weld UV seams before finding the actual rim. Closed pieces have a
            # sharp edge between cap and wall; open transition sheets have a
            # boundary edge. Interior triangulation is never registered.
            _, first, remap = np.unique(np.round(v, 5), axis=0, return_index=True, return_inverse=True)
            vertices = v[first]; f = remap[source.accessor(primitive['indices']).ravel().astype(int).reshape(-1, 3)]
            t = vertices[f]; normal = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
            lengths = np.linalg.norm(normal, axis=1); normal /= np.maximum(lengths[:, None], 1e-12)
            edges = defaultdict(list)
            for face, indices in enumerate(f):
                if lengths[face] < 1e-10:
                    continue
                for a, b in zip(indices, np.roll(indices, -1)):
                    edges[tuple(sorted((int(a), int(b))))].append(face)
            top = v[:, 1].max()
            for (a, b), adjacent in edges.items():
                p = vertices[[a, b]]
                if not np.all(abs(p[:, 1]-top) < .001) or np.linalg.norm(p[1]-p[0]) < .05:
                    continue
                sharp = len(adjacent) == 1 or any(np.dot(normal[adjacent[0]], normal[j]) < .7 for j in adjacent[1:])
                if sharp:
                    lines.append(('coping', p, .025))
        for kind, p, radius in lines:
            placed = (p @ matrix[:3, :3].T+matrix[:3, 3]) @ FRAME.T
            key = tuple(sorted(tuple(np.round(q, 4)) for q in placed))
            if key in seen:
                continue
            seen.add(key)
            result.append({'id': f'community_{instance["node"]}_{kind}_{len(result)}', 'kind': kind,
                           'radius': radius, 'points': placed.tolist()})
    # Join neighbouring rim edges into continuous contacts, including seams
    # between recovered bowl pieces. Thousands of individual little edge paths
    # would create false rail endpoints during a grind.
    coping = [r for r in result if r['kind'] == 'coping']
    result = [r for r in result if r['kind'] != 'coping']
    points = {}; neighbours = defaultdict(set); unused = set()
    for rail in coping:
        keys = [tuple(np.round(p, 4)) for p in rail['points']]
        a, b = keys
        points[a], points[b] = rail['points']
        neighbours[a].add(b); neighbours[b].add(a); unused.add(tuple(sorted((a, b))))
    def follow(start, next_point):
        line = [start]; current, following = start, next_point
        while tuple(sorted((current, following))) in unused:
            unused.remove(tuple(sorted((current, following)))); line.append(following)
            previous, current = current, following
            if len(neighbours[current]) != 2:
                break
            following = next(p for p in neighbours[current] if p != previous)
        return line
    starts = sorted(p for p, n in neighbours.items() if len(n) != 2)
    chains = []
    for p in starts:
        for q in sorted(neighbours[p]):
            if tuple(sorted((p, q))) in unused:
                chains.append(follow(p, q))
    while unused:
        a, b = min(unused); chains.append(follow(a, b))
    for chain in chains:
        p = np.array([points[k] for k in chain])
        if np.linalg.norm(np.diff(p, axis=0), axis=1).sum() < .6:
            continue
        result.append({'id': f'community_coping_{len(result)}', 'kind': 'coping', 'radius': .025, 'points': p.tolist()})
    return result
