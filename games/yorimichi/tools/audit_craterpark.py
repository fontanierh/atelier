"""Compare absolute native-frame NPZ park meshes without Blender or Unreal.

Usage: python audit_craterpark.py REFERENCE CANDIDATE --out report.json
See park_audit_README.md for measured quantities, tolerances and limitations.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import time
import numpy as np
from park_audit_geometry import BVH, normals, pairs, projected_overlap, progress


class MeshSet:
    def __init__(self, path, domain):
        self.path = Path(path)
        root = self.path/'npz' if (self.path/'npz').is_dir() else self.path
        manifest = root/'build.json'
        if not manifest.exists():
            manifest = root.parent/'build.json'
        self.metadata, self.manifest_hash = {}, None
        if manifest.exists():
            raw = manifest.read_bytes()
            self.manifest_hash = hashlib.sha256(raw).hexdigest()
            self.metadata = {entry['name']: entry for entry in json.loads(raw).get(domain, [])}
        prefix = 'UC_CP_' if domain == 'collision' else 'SM_CP_'
        self.names, self.ranges, tris, owners, self.attrs, self.hashes = [], [], [], [], [], {}
        count = 0
        for file in sorted(root.glob(prefix+'*.npz')):
            if 'ImportSeed' in file.name:
                continue
            raw = file.read_bytes()
            with np.load(io.BytesIO(raw), allow_pickle=False) as data:
                p, f = np.asarray(data['positions'], 'f8'), np.asarray(data['triangles'])
                if p.ndim != 2 or p.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,):
                    raise ValueError(f'{file.name}: expected positions (V,3), triangles (F,3)')
                if not np.isfinite(p).all() or f.dtype.kind not in 'iu' or (len(f) and (f.min() < 0 or f.max() >= len(p))):
                    raise ValueError(f'{file.name}: nonfinite vertices or invalid indices')
                t = p[f]
                tris.append(t)
                owners.append(np.full(len(t), len(self.names), dtype='i4'))
                self.names.append(file.stem)
                self.ranges.append((count, count+len(t)))
                count += len(t)
                attrs = {}
                for name, shape in (('corner_ao', (len(t), 3)), ('corner_normal', (len(t), 3, 3))):
                    if name in data:
                        attrs[name] = np.asarray(data[name], 'f8')
                        if attrs[name].shape != shape or not np.isfinite(attrs[name]).all():
                            raise ValueError(f'{file.name}: invalid {name}')
                self.attrs.append(attrs)
                self.hashes[file.name] = hashlib.sha256(raw).hexdigest()
            progress(f'loaded {domain}: {len(self.names)} meshes, {count} triangles')
        self.tri = np.concatenate(tris) if tris else np.empty((0, 3, 3))
        self.owner = np.concatenate(owners) if owners else np.zeros(0, 'i4')
        self.normal, self.area = normals(self.tri)
        self._bvh = None

    @property
    def bvh(self):
        if self._bvh is None:
            self._bvh = BVH(self.tri)
        return self._bvh

    def selected(self, box):
        if box is None:
            return np.ones(len(self.tri), bool)
        c = self.tri.mean(axis=1)
        x0, z0, x1, z1 = box
        return (c[:, 0] >= x0) & (c[:, 0] <= x1) & (c[:, 2] >= z0) & (c[:, 2] <= z1)

    def location(self, face, point):
        mesh = int(self.owner[face])
        return dict(mesh=self.names[mesh], face=int(face-self.ranges[mesh][0]), point_m=np.asarray(point).tolist())


def distribution(values):
    if not len(values):
        return dict(count=0, p50=None, p99=None, p99_9=None, max=None)
    return dict(count=len(values), p50=float(np.percentile(values, 50)), p99=float(np.percentile(values, 99)),
                p99_9=float(np.percentile(values, 99.9)), max=float(np.max(values)))


def sample_faces(mesh, selected, maximum, spacing=None):
    """Deterministic seven-point stencil or regular barycentric lattice, with explicit thinning."""
    ids = np.flatnonzero(selected)
    if spacing is not None:
        lengths = np.linalg.norm(mesh.tri[ids][:, [1,2,0]]-mesh.tri[ids], axis=2).max(axis=1)
        divisions = np.maximum(1, np.ceil(lengths/spacing)).astype('i8')
        counts = (divisions+1)*(divisions+2)//2
        cumulative = np.cumsum(counts)
        total = int(cumulative[-1]) if len(cumulative) else 0
        if maximum == 0 and total > 10_000_000:
            raise ValueError(f'dense lattice has {total} points; use a smaller --box or a finite --max-samples budget')
        ranks = np.arange(total) if maximum == 0 or total <= maximum else np.linspace(0,total-1,maximum,dtype='i8')
        chosen = np.searchsorted(cumulative, ranks, side='right')
        start = np.r_[0, cumulative[:-1]]
        local, n = ranks-start[chosen], divisions[chosen]
        # Row r contains n+1-r points; invert its triangular cumulative count.
        row = np.floor((2*n+3-np.sqrt((2*n+3).astype('f8')**2-8*local))*.5).astype('i8')
        prefix = lambda r: r*(2*n+3-r)//2
        row = np.where(prefix(row) > local, row-1, row)
        row = np.where(prefix(row+1) <= local, row+1, row)
        col = local-prefix(row)
        bary = np.column_stack((1-(row+col)/n, row/n, col/n))
        face = ids[chosen]
        return np.sum(mesh.tri[face]*bary[:, :, None], axis=1), face, bary, total
    total = len(ids)*7
    ranks = np.arange(total) if maximum == 0 or total <= maximum else np.linspace(0, total-1, maximum, dtype='i8')
    weights = np.array([[1,0,0], [0,1,0], [0,0,1], [.5,.5,0], [0,.5,.5], [.5,0,.5], [1/3]*3])
    face = ids[ranks//7]
    bary = weights[ranks%7]
    points = np.sum(mesh.tri[face]*bary[:, :, None], axis=1)
    return points, face, bary, total


def distance_report(source, target, args):
    """@cc [owner:fontanierh,label:correctness] region-preserves-target-and-exposure
    A source-region filter MUST NOT remove possible target matches or source occluders outside that region.
    A sampled pass MUST NOT claim continuous surface certification without verified identical triangle arrays.
    """
    chosen = source.selected(args.box) & (source.normal[:, 1] > .2) & (source.area > 1e-12)
    spacing = getattr(args, 'spacing', None)
    p, face, _, total = sample_faces(source, chosen, args.max_samples, spacing=spacing)
    visible = source.bvh.exposed(p)
    p, face = p[visible], face[visible]
    identical = source.names == target.names and np.array_equal(source.tri, target.tri)
    if identical:
        # These points are convex combinations of the very same target triangle.
        ds, target_face = np.zeros(len(p)), face.copy()
    else:
        ds, target_face, _ = target.bvh.nearest(p)
    finite = np.isfinite(ds)
    valid_normals = finite & (target_face >= 0)
    valid_normals[valid_normals] &= target.area[target_face[valid_normals]] > 1e-12
    source_n, target_n = source.normal[face[valid_normals]], target.normal[target_face[valid_normals]]
    normal_angle = np.rad2deg(np.arctan2(np.linalg.norm(np.cross(source_n,target_n),axis=1),
                                       np.sum(source_n*target_n,axis=1)))
    slope_angle = np.minimum(normal_angle, 180-normal_angle)
    worst = []
    for i in np.argsort(ds)[-20:][::-1]:
        entry = source.location(face[i], p[i])
        entry['distance_m'] = float(ds[i]) if finite[i] else None
        entry['target_mesh'] = target.names[target.owner[target_face[i]]] if target_face[i] >= 0 else None
        worst.append(entry)
    result = distribution(ds[finite])
    result.update(method='sampled point-to-triangle distance; not continuous Hausdorff',
                  source_upward_faces=int(chosen.sum()), possible_stencil_points=total,
                  points_tested_for_exposure=len(visible), buried_samples=int((~visible).sum()),
                  unmatched_samples=int((~finite).sum()), worst=worst,
                  stencil_complete=(len(visible) == total),
                  sampling='barycentric lattice' if spacing else 'seven points per triangle',
                  requested_spacing_m=spacing,
                  sampling_fraction=(len(visible)/total if total else 0.),
                  full_spacing_coverage=bool(spacing and len(visible) == total),
                  tolerance_m=args.tolerance,
                  sampled_within_tolerance=bool(len(ds) and finite.all() and np.max(ds) <= args.tolerance),
                  identical_triangle_arrays=identical,
                  continuous_surface_certified=identical,
                  contact_plane_angle_degrees=distribution(slope_angle),
                  oriented_normal_angle_degrees=distribution(normal_angle),
                  samples_without_valid_target_normal=int((~valid_normals).sum()),
                  normal_comparison='Geometric face normals at closest surface points. Contact-plane angle ignores '
                                    'winding; oriented angle preserves it. These are geometric diagnostics, not rider simulation.')
    return result


def overlap_report(mesh, args):
    """@cc [owner:fontanierh,label:correctness] incomplete-overlap-scan-is-explicit
    If a pair budget stops a scan, its report MUST mark it incomplete and describe its counts as lower bounds.
    """
    selected = mesh.selected(args.box)
    report = dict(complete=True, aabb_pairs=0, near_plane_pairs=0, overlapping_pairs=0,
                  within_mesh_pairs=0, between_mesh_pairs=0, pair_area_m2=0., examples=[], mesh_pairs={})
    by_mesh = Counter()
    for i, j in pairs(mesh.bvh, epsilon=args.plane_tolerance):
        keep = selected[i] | selected[j]
        i, j = i[keep], j[keep]
        report['aabb_pairs'] += len(i)
        if args.max_pairs and report['aabb_pairs'] > args.max_pairs:
            report['complete'] = False
            report['stop_reason'] = 'AABB pair budget exceeded; counts are lower bounds'
            break
        if not len(i):
            continue
        n, m = mesh.normal[i], mesh.normal[j]
        keep = (np.abs(np.sum(n*m, axis=1)) >= np.cos(np.deg2rad(args.angle_tolerance)))
        keep &= (mesh.area[i] > 1e-12) & (mesh.area[j] > 1e-12)
        i, j, n, m = i[keep], j[keep], n[keep], m[keep]
        a, b = mesh.tri[i], mesh.tri[j]
        keep = np.max(np.abs(np.sum((b-a[:, :1])*n[:, None], axis=2)), axis=1) <= args.plane_tolerance
        keep &= np.max(np.abs(np.sum((a-b[:, :1])*m[:, None], axis=2)), axis=1) <= args.plane_tolerance
        i, j, a, b, n = i[keep], j[keep], a[keep], b[keep], n[keep]
        report['near_plane_pairs'] += len(i)
        areas = projected_overlap(a, b, n)
        for u, v, area in zip(i[areas > 1e-8], j[areas > 1e-8], areas[areas > 1e-8]):
            same = mesh.owner[u] == mesh.owner[v]
            report['overlapping_pairs'] += 1
            report['within_mesh_pairs' if same else 'between_mesh_pairs'] += 1
            report['pair_area_m2'] += float(area)
            names = sorted((mesh.names[mesh.owner[u]], mesh.names[mesh.owner[v]]))
            by_mesh[' | '.join(names)] += 1
            if len(report['examples']) < 100:
                report['examples'].append(dict(first=mesh.location(u, mesh.tri[u].mean(axis=0)),
                                                second=mesh.location(v, mesh.tri[v].mean(axis=0)), area_m2=float(area)))
        progress(f"overlaps: {report['aabb_pairs']} AABB pairs; {report['overlapping_pairs']} positive-area pairs")
    report['mesh_pairs'] = dict(by_mesh.most_common())
    report['area_semantics'] = 'sum of pairwise projected intersection areas; multiply-covered regions counted per pair'
    return report


def topology_report(mesh, args):
    selected = mesh.selected(args.box)
    # Use the complete mesh to count edge incidence: a region boundary is not an open edge.
    points, inverse = np.unique(np.rint(mesh.tri.reshape(-1, 3)/args.weld).astype('i8'), axis=0, return_inverse=True)
    points = points.astype('f8')*args.weld
    faces = inverse.reshape(-1, 3)
    edges = np.sort(np.stack((faces[:, [0,1]], faces[:, [1,2]], faces[:, [2,0]]), axis=1).reshape(-1, 2), axis=1)
    unique, first, counts = np.unique(edges, axis=0, return_index=True, return_counts=True)
    # Mark an edge selected if any of its incident faces is in the region.
    _, edge_ids = np.unique(edges, axis=0, return_inverse=True)
    active = np.zeros(len(unique), bool)
    np.logical_or.at(active, edge_ids, np.repeat(selected, 3))
    open_mask = (counts == 1) & active & (unique[:, 0] != unique[:, 1])
    open_ids = np.flatnonzero(open_mask)
    open_edges = unique[open_ids]
    lengths = np.linalg.norm(mesh.tri[:, [1,2,0]]-mesh.tri, axis=2)
    quality = 4*np.sqrt(3)*mesh.area/np.maximum(np.sum(lengths*lengths, axis=1), 1e-30)
    out = dict(weld_grid_m=args.weld, selected_faces=int(selected.sum()),
               open_edges=int(open_mask.sum()), nonmanifold_edges=int(((counts > 2) & active).sum()),
               degenerate_faces=int(((mesh.area <= 1e-12) & selected).sum()),
               sliver_faces=int(((quality < args.sliver_quality) & selected & (mesh.area > 1e-12)).sum()),
               sliver_quality_threshold=args.sliver_quality,
               open_edge_examples=[dict(start_m=points[unique[k, 0]].tolist(), end_m=points[unique[k, 1]].tolist(),
                                        mesh=mesh.names[mesh.owner[first[k]//3]]) for k in open_ids[:30]],
               t_junctions=0, t_junction_scan_complete=True, t_junction_examples=[])
    if not len(open_edges):
        return out
    a, b = points[open_edges[:, 0]], points[open_edges[:, 1]]
    edge_tree = BVH(lo=np.minimum(a,b), hi=np.maximum(a,b))
    point_tree = BVH(lo=points, hi=points)
    checked = 0
    for ei, vi in pairs(edge_tree, point_tree, epsilon=args.weld):
        checked += len(ei)
        if args.max_pairs and checked > args.max_pairs:
            out['t_junction_scan_complete'] = False
            out['t_junction_stop_reason'] = 'AABB pair budget exceeded; count is a lower bound'
            break
        ab = b[ei]-a[ei]
        length2 = np.sum(ab*ab, axis=1)
        u = np.sum((points[vi]-a[ei])*ab, axis=1)/np.maximum(length2, 1e-30)
        distance = np.linalg.norm(points[vi]-a[ei]-u[:, None]*ab, axis=1)
        end_slack = args.weld/np.maximum(np.sqrt(length2), 1e-30)
        keep = (u > end_slack) & (u < 1-end_slack) & (distance <= args.weld)
        out['t_junctions'] += int(keep.sum())
        for edge, vertex in zip(ei[keep], vi[keep]):
            if len(out['t_junction_examples']) < 30:
                out['t_junction_examples'].append(dict(vertex_m=points[vertex].tolist(),
                                                        edge_start_m=a[edge].tolist(), edge_end_m=b[edge].tolist()))
        progress(f'T-junctions: {checked} AABB pairs, {out["t_junctions"]} vertex/edge incidences')
    return out


def look_report(source, target, args):
    p, faces, bary, total = sample_faces(source, source.selected(args.box), args.max_samples)
    identical = source.names == target.names and np.array_equal(source.tri, target.tri)
    if identical:
        # Preserve corner discontinuities in an unchanged mesh; a spatial tie at a seam
        # must not choose the neighbouring face's AO or normal in a self-comparison.
        ds, hit, weights = np.zeros(len(p)), faces.copy(), bary.copy()
    else:
        ds, hit, weights = target.bvh.nearest(p)
    report = dict(possible_stencil_points=total, sampled_points=len(p), matched_points=0, by_mesh={})
    matched = (hit >= 0) & (ds <= args.look_match_tolerance)
    report['matched_points'] = int(matched.sum())
    for owner, name in enumerate(source.names):
        ids = np.flatnonzero((source.owner[faces] == owner) & matched)
        summary = dict(sample_count=int(np.sum(source.owner[faces] == owner)), matched_count=len(ids))
        for attr in ('corner_ao', 'corner_normal'):
            if attr not in source.attrs[owner]:
                summary[attr] = dict(status='missing reference attribute')
                continue
            values = []
            for dest in np.unique(target.owner[hit[ids]]):
                use = ids[target.owner[hit[ids]] == dest]
                if attr not in target.attrs[dest]:
                    continue
                src = source.attrs[owner][attr][faces[use]-source.ranges[owner][0]]
                dst = target.attrs[dest][attr][hit[use]-target.ranges[dest][0]]
                if attr == 'corner_ao':
                    x, y = np.sum(src*bary[use], axis=1), np.sum(dst*weights[use], axis=1)
                    values.extend(np.abs(x-y).tolist())
                else:
                    x = np.sum(src*bary[use, :, None], axis=1)
                    y = np.sum(dst*weights[use, :, None], axis=1)
                    denom = np.linalg.norm(x, axis=1)*np.linalg.norm(y, axis=1)
                    valid = denom > 1e-12
                    # atan2 is stable for identical normals and reports exactly zero for the self-check.
                    values.extend(np.rad2deg(np.arctan2(np.linalg.norm(np.cross(x[valid],y[valid]),axis=1),
                                                       np.sum(x[valid]*y[valid],axis=1))).tolist())
            summary[attr] = distribution(np.asarray(values))
        report['by_mesh'][name] = summary
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--box', nargs=4, type=float, metavar=('X0','Z0','X1','Z1'))
    parser.add_argument('--max-samples', type=int, default=30000, help='per direction/domain; 0 = complete seven-point stencil')
    parser.add_argument('--spacing', type=float, help='riding barycentric lattice spacing in metres before budget thinning')
    parser.add_argument('--max-pairs', type=int, default=5000000, help='per scan; 0 = unbounded; incomplete scans are explicit')
    parser.add_argument('--tolerance', type=float, default=.01)
    parser.add_argument('--plane-tolerance', type=float, default=.005)
    parser.add_argument('--angle-tolerance', type=float, default=.5, help='degrees')
    parser.add_argument('--weld', type=float, default=1e-5)
    parser.add_argument('--sliver-quality', type=float, default=.001)
    parser.add_argument('--look-match-tolerance', type=float, default=.02)
    parser.add_argument('--checks', nargs='+', choices=('distance','overlaps','topology','look'),
                        default=['distance','overlaps','topology'])
    args = parser.parse_args(argv)
    if min(args.weld, args.tolerance, args.plane_tolerance) <= 0 or min(args.max_samples, args.max_pairs) < 0:
        parser.error('tolerances must be positive and budgets nonnegative')
    if args.spacing is not None and (not np.isfinite(args.spacing) or args.spacing <= 0):
        parser.error('spacing must be finite and positive')
    if args.box and (args.box[0] >= args.box[2] or args.box[1] >= args.box[3]):
        parser.error('box must satisfy x0 < x1 and z0 < z1')
    started = time.monotonic()
    result = dict(schema=1, frame='native absolute metres; y up', box=args.box,
                  settings={k: v for k,v in vars(args).items() if k not in ('reference','candidate','out')},
                  reference=str(args.reference), candidate=str(args.candidate), domains={}, complete=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def save():
        result['elapsed_seconds'] = time.monotonic()-started
        temp = args.out.with_suffix(args.out.suffix+'.tmp')
        temp.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        temp.replace(args.out)

    for domain in ('collision','render'):
        progress(f'loading {domain}', True)
        reference, candidate = MeshSet(args.reference, domain), MeshSet(args.candidate, domain)
        if not len(reference.tri) or not len(candidate.tri):
            raise ValueError(f'both sets must contain {domain} meshes')
        data = result['domains'][domain] = dict(reference_hashes=reference.hashes, candidate_hashes=candidate.hashes,
                                              reference_counts={}, candidate_counts={})
        for label, mesh in (('reference',reference), ('candidate',candidate)):
            chosen = mesh.selected(args.box)
            data[label+'_counts'] = {name: dict(total_triangles=end-start,
                                                selected_triangles=int(chosen[start:end].sum()),
                                                manifest_triangles=mesh.metadata.get(name,{}).get('triangles'),
                                                manifest_minus_npz=(int(mesh.metadata[name]['triangles'])-(end-start)
                                                                    if 'triangles' in mesh.metadata.get(name,{}) else None),
                                                role=mesh.metadata.get(name,{}).get('role'))
                                     for name,(start,end) in zip(mesh.names, mesh.ranges)}
            data[label+'_extraction'] = dict(manifest_sha256=mesh.manifest_hash,
                                              manifest_meshes_missing_npz=sorted(set(mesh.metadata)-set(mesh.names)),
                                              note='Count differences are extraction discrepancies, not inferred duplicate counts. '
                                                   'Structural scans describe NPZ faces only; omitted faces are not tested.')
        save()
        if domain == 'collision' and 'distance' in args.checks:
            for label, a, b in (('reference_to_candidate', reference,candidate), ('candidate_to_reference',candidate,reference)):
                progress(label, True)
                data[label] = distance_report(a,b,args)
                save()
        for label, mesh in (('reference',reference), ('candidate',candidate)):
            for check in ('overlaps','topology'):
                if check in args.checks:
                    progress(f'{label} {domain} {check}', True)
                    # Identity shares only absolute structural results, never forces them to zero.
                    if label == 'candidate' and reference.hashes == candidate.hashes:
                        data[label+'_'+check] = data['reference_'+check]
                    else:
                        data[label+'_'+check] = (overlap_report if check=='overlaps' else topology_report)(mesh,args)
                    save()
        if domain == 'render' and 'look' in args.checks:
            progress('render AO/normal comparison', True)
            data['reference_to_candidate_look'] = look_report(reference,candidate,args)
            save()
        del reference, candidate
    result['complete'] = True  # CLI completed; inspect individual scan completeness and sampling limits.
    save()
    progress(f'finished; report {args.out}', True)


if __name__ == '__main__':
    main()
