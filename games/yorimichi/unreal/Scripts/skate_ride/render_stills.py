"""Stills of the Ride clips sampled in Unreal: build/yorimichi/skate-ride/clip-stills/<CLIP>.png.

verify_clips.py writes, for a few clips (an ollie, a kickflip, a push, a 50-50 grind), the component-space pose
Unreal samples from the compressed asset at every frame. This draws SK_SkateRider's box body and board skinned to
those poses (six frames per clip, side by side, a three-quarter view framed tight on the rider, the ground at the
clip's lowest board point with the rider's shadow), with the native pose's joints as dots on top (the native decode
converted to Unreal space and composed through the hierarchy): a dot off its joint would be a mismatch.
Runs under `uv run` (Pillow); not part of the editor.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import native as N  # noqa: E402
import rider_mesh as M  # noqa: E402
import yori  # noqa: E402

BUNDLE = yori.OUT / 'skate-native' / 'package'  # the skate.runtime build step assembles it
OUT = yori.OUT / 'skate-ride'
POSES = OUT / 'still-poses'
STILLS = OUT / 'clip-stills'
PANELS, W, H = 6, 360, 460
YAW, PITCH = math.radians(-125.0), math.radians(-12.0)    # camera looks from the rider's front-left, a little above
LIGHT = (0.35, -0.45, 0.82)
COLOURS = {'body': (205, 150, 118), 'board': (58, 64, 74)}


def rotate(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def to_unreal(v):
    """glTF metres (as the GLB is written) -> Unreal cm, the Interchange mapping."""
    return (v[0] * 100.0, v[2] * 100.0, v[1] * 100.0)


def camera(p, centre):
    x, y, z = p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]
    cy, sy, cp, sp = math.cos(YAW), math.sin(YAW), math.cos(PITCH), math.sin(PITCH)
    fx, fy = x * cy + y * sy, -x * sy + y * cy      # f: towards the viewer after yaw; s: screen right
    depth = fx * cp + z * sp
    up = -fx * sp + z * cp
    return fy, up, depth


def skinned(mesh, locals_ue, pose):
    out = []
    for p, j, v in zip(mesh.positions, mesh.joints, locals_ue):
        bone = pose[j]
        r = rotate(bone['q'], v)
        out.append((r[0] + bone['t'][0], r[1] + bone['t'][1], r[2] + bone['t'][2]))
    return out


def native_joints(clip, frame, rig, reference):
    """The native local poses (clip added onto RIG_TPOSE) converted to Unreal and composed through the hierarchy
    (TRAJECTORY included, as Unreal's component space with the root motion kept in the root)."""
    globals_ = []
    for b, bone in enumerate(rig.bones):
        m = N.unreal_matrix(*N.sample_to_unreal(N.local_pose(clip, frame, b, reference)))
        globals_.append(m if bone.parent < 0 else N.multiply(m, globals_[bone.parent]))
    return [(g[3][0], g[3][1], g[3][2]) for g in globals_]


def draw_panel(image, ox, mesh, triangles, world, joints, ground, label):
    d = ImageDraw.Draw(image, 'RGBA')
    names = list(world)
    centre_bone = world['HIPS']['t']
    heights = [bone['t'][2] for bone in world.values()] + [ground]
    centre = (centre_bone[0], centre_bone[1], (min(heights) + max(heights)) / 2 + 4.0)   # the frame's height span
    scale = H / 250.0
    project = lambda p: camera(p, centre)

    def screen(c):
        return ox + W / 2 + c[0] * scale, H / 2 - c[1] * scale

    pose = [world[n] for n in names]
    points = skinned(mesh, LOCALS, pose)
    # ground line and shadow
    g0, g1 = screen(project((centre[0] - 400, centre[1], ground))), screen(project((centre[0] + 400, centre[1], ground)))
    d.line([g0, g1], fill=(150, 150, 150, 255), width=1)
    shadow = [(p[0], p[1], ground) for p in points]
    for material, tris in triangles.items():
        for a, b, c in tris:
            d.polygon([screen(project(shadow[i])) for i in (a, b, c)], fill=(0, 0, 0, 28))
    faces = []
    for material, tris in triangles.items():
        for a, b, c in tris:
            pa, pb, pc = points[a], points[b], points[c]
            u = [pb[i] - pa[i] for i in range(3)]
            v = [pc[i] - pa[i] for i in range(3)]
            n = M.unit(M.cross(u, v))
            ca, cb, cc = project(pa), project(pb), project(pc)
            depth = (ca[2] + cb[2] + cc[2]) / 3
            shade = 0.45 + 0.55 * max(0.0, sum(n[i] * LIGHT[i] for i in range(3)) / math.sqrt(sum(l * l for l in LIGHT)))
            colour = tuple(int(ch * shade) for ch in COLOURS[material])
            faces.append((depth, [screen(ca), screen(cb), screen(cc)], colour))
    for _, polygon, colour in sorted(faces, key=lambda f: -f[0]):
        d.polygon(polygon, fill=colour + (255,))
    for j in joints:
        x, y = screen(project(j))
        d.ellipse([x - 2.2, y - 2.2, x + 2.2, y + 2.2], outline=(20, 120, 220, 255), width=1)
    d.text((ox + 8, 8), label, fill=(30, 30, 30, 255))


def main():
    global LOCALS
    rig = N.Bundle(BUNDLE).rig()
    pose = rig.named_pose(0, 'RIG_TPOSE')
    _, globals_, mesh = M.build(rig, pose, N.split_sample)
    inverse = [M.invert_rigid(g) for g in globals_]
    LOCALS = [to_unreal(M.apply(inverse[j], p)) for p, j in zip(mesh.positions, mesh.joints)]
    triangles = {m: [tuple(idx[i:i + 3]) for i in range(0, len(idx), 3)] for m, idx in mesh.indices.items()}
    STILLS.mkdir(parents=True, exist_ok=True)
    bundle = N.Bundle(BUNDLE)
    index = []
    for path in sorted(POSES.glob('*.json')):
        data = json.loads(path.read_text())
        name, frames = data['clip'], data['frames']
        clip = next(N.load_clip(p.read_bytes()) for p in bundle.clip_paths() if p.stem == name)
        picks = sorted({round(i * (len(frames) - 1) / (PANELS - 1)) for i in range(PANELS)})
        ground = min(f['bones'][b]['t'][2] for f in frames for b in ('LEFT_WHEELFRONT', 'RIGHT_WHEELBACK')) - 2.7
        image = Image.new('RGB', (W * len(picks), H), (246, 244, 239))
        worst = 0.0
        for k, f in enumerate(picks):
            world = {b: frames[f]['bones'][b] for b in (bone.name for bone in rig.bones)}
            joints = native_joints(clip, f, rig, pose)
            worst = max(worst, max(math.dist(j, world[b.name]['t']) for j, b in zip(joints, rig.bones)))
            panel = Image.new('RGB', (W, H), (246, 244, 239))      # one image per panel: the ground line is clipped
            draw_panel(panel, 0, mesh, triangles, world, joints, ground,
                       f'{name}  frame {f}/{len(frames) - 1}  {frames[f]["time"]:.2f} s')
            ImageDraw.Draw(panel).line([(W - 1, 0), (W - 1, H)], fill=(215, 212, 205), width=1)
            image.paste(panel, (k * W, 0))
        out = STILLS / f'{name}.png'
        image.save(out)
        index.append(dict(clip=name, image=out.name, frames=picks, native_joint_max_cm=worst))
        print(f'{out}: frames {picks}, native joints within {worst:.5f} cm')
    (STILLS / 'index.json').write_text(json.dumps(index, indent=1) + '\n')


LOCALS = []
if __name__ == '__main__':
    main()
