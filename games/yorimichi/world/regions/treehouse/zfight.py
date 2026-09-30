"""Z-fighting check for the tree house (Blender, headless): faces that lie in the same plane, face the same way and
overlap. The depth test flips between two such faces from frame to frame, so they flicker in the game.

    blender -b --python-exit-code 1 --python games/yorimichi/world/regions/treehouse/zfight.py -- [BUILD_DIR] [REPORT]

Reads BUILD_DIR/Treehouse.blend (TH_Structure, TH_Frame, TH_Trunks, TH_Dressing; BUILD_DIR defaults to
build/yorimichi/treehouse) and every prop instance in BUILD_DIR/runtime.json, each TH_P_*.fbx placed as the game
places it ([x, y, z, yaw, scale], turned counter-clockwise by yaw). A pair is two triangles whose normals are within
ANGLE degrees, whose planes are within GAP metres, and whose overlap in that plane is over AREA square metres.
Faces seen from opposite sides (a cloth built twice, a crate on a deck) are not pairs: one of them is always culled.
Triangles of the same prop instance are not checked against each other. Writes REPORT (default
build/yorimichi/review/treehouse/zfight.json) and exits 1 when any pair is found.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, sys, time
from collections import defaultdict
from pathlib import Path
import bpy
import numpy as np

ANGLE, GAP, AREA = 2.0, .0015, 1e-4
KEYS = ('TH_Structure', 'TH_Frame', 'TH_Trunks', 'TH_Dressing')


def triangles(ob, matrix=None):
    """World-space triangles of a mesh object (fan-triangulated polygons) and each one's material slot name."""
    me = ob.data
    co = np.zeros(len(me.vertices)*3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    M = np.array(matrix if matrix is not None else ob.matrix_world)
    co = co@M[:3, :3].T+M[:3, 3]
    n = len(me.polygons)
    start = np.zeros(n, int); total = np.zeros(n, int); mat = np.zeros(n, int)
    me.polygons.foreach_get('loop_start', start); me.polygons.foreach_get('loop_total', total)
    me.polygons.foreach_get('material_index', mat)
    loops = np.zeros(len(me.loops), int); me.loops.foreach_get('vertex_index', loops)
    tri, slot = [], []
    for k in range(3, total.max()+1 if n else 3):
        sel = np.flatnonzero(total == k)
        for j in range(1, k-1):
            tri.append(np.stack([loops[start[sel]], loops[start[sel]+j], loops[start[sel]+j+1]], 1)); slot.append(mat[sel])
    if not tri:
        return np.zeros((0, 3, 3)), np.zeros(0, int), []
    tri = np.concatenate(tri); slot = np.concatenate(slot)
    names = [m.name if m else '' for m in me.materials]
    return co[tri], slot, names


def prop_mesh(path):
    """The prop's triangles in its own frame (front -y, standing on z = 0), as props.py wrote it."""
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.import_scene.fbx(filepath=str(path), axis_forward='-Y', axis_up='Z')
    obs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.startswith('UCX_')]
    out = [triangles(o)[0] for o in obs]
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def gather(folder):
    bpy.ops.wm.open_mainfile(filepath=str(folder/'Treehouse.blend'))
    tris, label, group = [], [], []
    names = []
    for key in KEYS:
        ob = bpy.data.objects.get(key)
        if ob is None:
            raise SystemExit(f'{key} is not in {folder/"Treehouse.blend"}')
        t, slot, mats = triangles(ob)
        base = len(names); names += [f'{key}:{m}' for m in mats]
        tris.append(t); label.append(slot+base); group.append(np.full(len(t), -1))
    runtime = json.loads((folder/'runtime.json').read_text())
    sizes = {}
    inst = 0
    for key, rows in sorted(runtime['instances'].items()):
        path = folder/'props'/f'{key}.fbx'
        if not path.exists() or not rows:
            continue
        local = prop_mesh(path); lo, hi = local.reshape(-1, 3).min(0), local.reshape(-1, 3).max(0)
        sizes[key] = (hi-lo).round(3).tolist()
        names.append(f'prop:{key}'); lab = len(names)-1
        for x, y, z, yaw, s in rows:
            a = math.radians(yaw); R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
            tris.append(local*s@R.T+[x, y, z]); label.append(np.full(len(local), lab)); group.append(np.full(len(local), inst))
            inst += 1
    return np.concatenate(tris), np.concatenate(label), np.concatenate(group), names, sizes


def candidates(nrm, dist, lo, hi):
    """Pairs (i, j) with near-equal normals and planes and touching boxes, from hashed bins shifted by half a cell in
    each dimension so a pair across a bin edge still meets in one of them."""
    cell_n = 2*math.sin(math.radians(ANGLE))*1.5; cell_d = GAP*2
    q = np.column_stack([nrm/cell_n, dist/cell_d])
    pairs = set()
    for shift in range(16):
        off = np.array([(shift >> b) & 1 for b in range(4)])*.5
        key = np.floor(q+off).astype(np.int64)
        order = np.lexsort(key.T[::-1]); ks = key[order]
        brk = np.flatnonzero(np.any(ks[1:] != ks[:-1], axis=1))+1
        for grp in np.split(order, brk):
            if len(grp) < 2:
                continue
            if len(grp) <= 400:
                i, j = np.triu_indices(len(grp), 1); a, b = grp[i], grp[j]
            else:     # a big plane (a deck, a wall): sweep along x to pair only boxes that overlap there
                g = grp[np.argsort(lo[grp, 0])]; a_, b_ = [], []
                for k in range(len(g)):
                    end = np.searchsorted(lo[g, 0], hi[g[k], 0]+GAP, 'right')
                    if end > k+1:
                        a_.append(np.full(end-k-1, g[k])); b_.append(g[k+1:end])
                if not a_:
                    continue
                a, b = np.concatenate(a_), np.concatenate(b_)
            ok = np.all((lo[a] <= hi[b]+GAP) & (lo[b] <= hi[a]+GAP), axis=1)
            for x, y in zip(np.minimum(a[ok], b[ok]), np.maximum(a[ok], b[ok])):
                pairs.add((int(x), int(y)))
    return pairs


def clip_area(A, B):
    """Area of the overlap of two triangles given in the same 2D plane."""
    def ccw(t):
        return t if (t[1][0]-t[0][0])*(t[2][1]-t[0][1])-(t[1][1]-t[0][1])*(t[2][0]-t[0][0]) > 0 else t[::-1]
    out = [np.asarray(p) for p in ccw(list(A))]; B = ccw(list(B))
    for i in range(3):
        a, e = np.asarray(B[i]), np.asarray(B[(i+1) % 3])-np.asarray(B[i])
        side = lambda p: e[0]*(p[1]-a[1])-e[1]*(p[0]-a[0])
        inp, out = out, []
        for k, p in enumerate(inp):
            n = inp[(k+1) % len(inp)]; sp, sn = side(p), side(n)
            if sp >= 0: out.append(p)
            if (sp >= 0) != (sn >= 0): out.append(p+(n-p)*sp/(sp-sn))
        if len(out) < 3:
            return 0.
    xs, ys = np.array([p[0] for p in out]), np.array([p[1] for p in out])
    return .5*abs(float(xs@np.roll(ys, -1)-ys@np.roll(xs, -1)))


def main():
    args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    folder = Path(args[0]) if args else yori.OUT/'treehouse'
    report = Path(args[1]) if len(args) > 1 else yori.REVIEW/'treehouse'/'zfight.json'
    t0 = time.time()
    T, label, group, names, sizes = gather(folder)
    e1, e2 = T[:, 1]-T[:, 0], T[:, 2]-T[:, 0]; cr = np.cross(e1, e2); dbl = np.linalg.norm(cr, axis=1)
    keep = dbl/2 > AREA          # a triangle smaller than the threshold cannot overlap another by more
    T, label, group, cr, dbl = T[keep], label[keep], group[keep], cr[keep], dbl[keep]
    nrm = cr/dbl[:, None]; dist = np.einsum('ij,ij->i', nrm, T[:, 0])
    lo, hi = T.min(1), T.max(1)
    print(f'{len(T)} triangles ({int((~keep).sum())} tiny skipped), {time.time()-t0:.0f} s', flush=True)
    pairs = candidates(nrm, dist, lo, hi)
    print(f'{len(pairs)} candidate pairs, {time.time()-t0:.0f} s', flush=True)
    cos = math.cos(math.radians(ANGLE)); found = []
    for i, j in pairs:
        if group[i] >= 0 and group[i] == group[j]:
            continue
        if nrm[i]@nrm[j] < cos:
            continue
        if np.abs((T[j]-T[i][0])@nrm[i]).max() > GAP or np.abs((T[i]-T[j][0])@nrm[j]).max() > GAP:
            continue
        n = nrm[i]; u = np.cross(n, [0, 0, 1.] if abs(n[2]) < .9 else [1., 0, 0]); u /= np.linalg.norm(u); v = np.cross(n, u)
        A = [(p@u, p@v) for p in T[i]]; B = [(p@u, p@v) for p in T[j]]
        area = clip_area(A, B)
        if area > AREA:
            found.append((i, j, area))
    by = defaultdict(lambda: dict(pairs=0, area=0., at=[]))
    for i, j, area in found:
        k = ' | '.join(sorted((names[label[i]], names[label[j]])))
        b = by[k]; b['pairs'] += 1; b['area'] += area
        if len(b['at']) < 6: b['at'].append([round(float(c), 3) for c in (T[i].mean(0)+T[j].mean(0))/2])
    groups = sorted(({'between': k, 'pairs': v['pairs'], 'area_cm2': round(v['area']*1e4, 1), 'at': v['at']} for k, v in by.items()),
                    key=lambda g: -g['area_cm2'])
    out = dict(build=str(folder), triangles=int(len(T)), angle_deg=ANGLE, gap_m=GAP, min_area_m2=AREA, pairs=len(found),
               area_m2=round(sum(a for _, _, a in found), 4), groups=groups, prop_sizes=sizes)
    report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(out, indent=1)+'\n')
    for g in groups[:40]:
        print(f"{g['pairs']:6d} pairs {g['area_cm2']:10.1f} cm2  {g['between']}  e.g. {g['at'][0]}")
    print(f'ZFIGHT {"PASS" if not found else "FAIL"}: {len(found)} coplanar overlapping pairs, report {report}, {time.time()-t0:.0f} s', flush=True)
    sys.exit(1 if found else 0)


if __name__ == '__main__':
    main()
