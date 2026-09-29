"""Review renders and web export for the sword combat clip set (game-r13).

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_review.py -- sheets [--clips A,B] [--step N]
    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_review.py -- videos [--clips A,B]
    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_review.py -- export

`sheets` writes captures/<clip>-<view>.jpg contact sheets (front, side, three-quarter), `videos` writes
captures/<clip>.mp4 (front | side | three-quarter, 60 fps), `export` writes web/combat.glb with the sword
and the combat clips plus the locomotion clips needed for transition scenarios, and library.json for Studio.
Nothing here modifies the source blend.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, json, math, os, subprocess, sys
from pathlib import Path
import bpy, numpy as np
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
import cairo_mixamo_review as review
from cairo_outfit_correctives import set_clip
# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
SRC = ASSET / 'game-r13/WarmOriginal-Game-r13.blend'
OUT = ASSET / 'combat-r01'
VIEWS = {'front': (1, 0, .18), 'side': (0, -1, .18), 'quarter': (1, -1, .25)}
STUDIO_EXTRA = ['Idle · library', 'Walk · library', 'Sprint · dressed', 'Roll · library', 'DashGround · library', 'JumpStart · library', 'JumpRise · library', 'Fall · library', 'Land · library']


def load():
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    s = bpy.context.scene; arm = next(o for o in s.objects if o.type == 'ARMATURE')
    manifest = json.loads((SRC.parent / 'source-manifest.json').read_text())
    roles = [r for r in manifest['roles'] if r.get('sword')]
    return s, arm, manifest, roles


def setup_render(s):
    for o in s.objects:
        if o.name.startswith('Review floor'): o.hide_render = True
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.511)); floor = bpy.context.object
    mat = bpy.data.materials.new('Review floor · combat'); mat.diffuse_color = (.32, .32, .32, 1); floor.data.materials.append(mat)
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    s.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'; s.eevee.taa_render_samples = 8
    s.render.resolution_percentage = 100; s.view_settings.view_transform = 'Standard'; s.render.image_settings.file_format = 'PNG'
    cam = s.camera; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.7; cam.data.clip_start = .01; cam.data.clip_end = 50
    return cam


def aim(cam, arm, view):
    t = arm.matrix_world @ arm.pose.bones['Root'].head; t.z = .10
    d = Vector(VIEWS[view]).normalized(); cam.location = t + d * 4; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()


def frames_of(role):
    return list(range(1, role['frames'] + 1))


def load_png(p):
    im = bpy.data.images.load(str(p)); w, h = im.size; a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3]; bpy.data.images.remove(im); return a


def save_sheet(a, p):
    h, w, _ = a.shape; im = bpy.data.images.new('sheet', w, h); im.pixels = np.concatenate([a[::-1], np.ones((h, w, 1), np.float32)], 2).ravel().tolist()
    im.filepath_raw = str(p); im.file_format = 'JPEG'; bpy.context.scene.render.image_settings.quality = 84; im.save(); bpy.data.images.remove(im)


def render(kind, clips, step):
    s, arm, manifest, roles = load(); cam = setup_render(s)
    caps = OUT / 'captures'; caps.mkdir(parents=True, exist_ok=True); work = OUT / 'captures' / '.frames'; work.mkdir(exist_ok=True)
    s.render.resolution_x = s.render.resolution_y = 320 if kind == 'sheets' else 400
    for role in roles:
        if clips and role['role'] not in clips: continue
        set_clip(arm, bpy.data.actions[role['clip']])
        frames = frames_of(role)[::step] if kind == 'sheets' else frames_of(role)
        for view in VIEWS:
            for f in frames:
                s.frame_set(f); aim(cam, arm, view)
                s.render.filepath = str(work / f'{role["role"]}-{view}-{f:03d}.png'); bpy.ops.render.render(write_still=True)
        if kind == 'sheets':
            for view in VIEWS:
                tiles = [load_png(work / f'{role["role"]}-{view}-{f:03d}.png') for f in frames]
                cols = min(10, len(tiles)); rows = math.ceil(len(tiles) / cols); W = tiles[0].shape[0]
                sheet = np.full((rows * (W + 6), cols * (W + 6), 3), .16, np.float32)
                for i, t in enumerate(tiles):
                    y = (i // cols) * (W + 6); x = (i % cols) * (W + 6); sheet[y:y + W, x:x + W] = t
                save_sheet(sheet, caps / f'{role["role"]}-{view}.jpg')
            (caps / f'{role["role"]}-frames.json').write_text(json.dumps({'frames': frames, 'columns': min(10, len(frames)), 'fps': 60}) + '\n')
        else:
            inputs = []
            for view in VIEWS: inputs += ['-framerate', '60', '-i', str(work / f'{role["role"]}-{view}-%03d.png')]
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *inputs, '-filter_complex', '[0:v][1:v][2:v]hstack=inputs=3', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(caps / f'{role["role"]}.mp4')], check=True)
        print('RENDERED', role['role'], kind, flush=True)


def export():
    s, arm, manifest, roles = load()
    keep = {r['clip'] for r in roles} | set(STUDIO_EXTRA)
    for a in list(bpy.data.actions):
        if a.name not in keep: bpy.data.actions.remove(a)
    # 240 Hz remap keeps sub-frame keys of the dense sprint; the exporter samples the timeline.
    for action in bpy.data.actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for key in fc.keyframe_points:
                            for attr in ['co', 'handle_left', 'handle_right']:
                                point = getattr(key, attr); point.x = 1 + (point.x - 1) * 4
                        fc.update()
    s.render.fps = 240; s.frame_start = 1; s.frame_end = 4 * 212
    (OUT / 'web').mkdir(parents=True, exist_ok=True)
    review.OUT = OUT; review.export(stem='combat', load=False)
    rows = []
    for r in roles:
        rows.append({'id': r['role'], 'label': r['role'].replace('Sword', 'Sword · '), 'model': 'combat', 'action': r['clip'], 'rate': 1, 'loop': r['loop'], 'duration': r['duration_seconds'],
                     'travel': None, 'profile': None, 'notes': r['notes'], 'active': r.get('active_window_seconds'), 'link': r.get('link_window_seconds'), 'rootMotion': r['root_motion']})
    for r in manifest['roles']:
        if r['clip'] in STUDIO_EXTRA and not r.get('sword') and r['role'] != 'Run':
            rows.append({'id': r['role'], 'label': r['role'], 'model': 'combat', 'action': r['clip'], 'rate': 1.15 if r['role'] == 'Roll' else r.get('tested_play_rate', 1), 'loop': r['loop'],
                         'duration': r['duration_seconds'], 'travel': r.get('travel'), 'profile': r.get('travel_profile_units_per_second'), 'notes': 'library clip for transition review; sword stays in hand', 'rootMotion': False})
    (OUT / 'library.json').write_text(json.dumps({'models': {'combat': 'web/combat.glb'}, 'floor': -.512, 'clips': rows}, indent=2) + '\n')
    print('EXPORTED', OUT / 'web/combat.glb', (OUT / 'web/combat.glb').stat().st_size, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('task', choices=['sheets', 'videos', 'export']); p.add_argument('--clips'); p.add_argument('--step', type=int, default=3)
    p.add_argument('--revision', default='game-r13', help='game revision whose combat clips are reviewed'); p.add_argument('--out', default='combat-r01', help='output folder in the asset directory')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    SRC = ASSET / a.revision / f"WarmOriginal-Game-{a.revision.split('-')[-1]}.blend"; OUT = ASSET / a.out
    if a.task == 'export': export()
    else: render(a.task, a.clips.split(',') if a.clips else None, a.step)
