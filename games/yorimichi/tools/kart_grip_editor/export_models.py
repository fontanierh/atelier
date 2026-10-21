"""Guarded Blender export of prepared driver skins and their exact seated/bind frames for the grip editor."""
import hashlib
import json
from pathlib import Path
import sys

import bpy
from source_identity import source_identity, playable_ids

GAME = Path(__file__).resolve().parents[2]
ROOT = GAME.parents[1]
KART = GAME / 'assets/vehicles/kart'
sys.path.insert(0, str(KART))
# The diagnostic module parses Blender's argv. Keep its generated output in build/.
sys.argv = [sys.argv[0], '--', 'all', str(ROOT / 'build/yorimichi/kart-grip-editor')]
import preview as p  # noqa: E402

OUT = ROOT / 'build/yorimichi/kart-grip-editor'


def matrix(m):
    return [float(m[r][c]) for c in range(4) for r in range(4)]


def rigid(m):
    result = m.to_quaternion().to_matrix().to_4x4()
    result.translation = m.translation
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name in playable_ids():
        print('GRIP EDITOR prepare', name, flush=True)
        p.CHARACTER = name
        character = p.rig.load(name)
        prepared = character.prepare()
        p.character_export.rest(prepared)
        hooks = p.character_export.hooks(character)
        if hooks:
            hooks.body(prepared, {})
        arm = prepared.arm
        for ob in prepared.meshes:
            if ob.parent is None:
                world = ob.matrix_world.copy(); ob.parent = arm; ob.matrix_world = world
        root = arm
        while root.parent:
            root = root.parent
        p.SCALE = p.cockpit.fit(p.leg_length(arm, root))
        bind_arm = arm.matrix_world.copy()
        bind = {b.name: matrix(rigid(bind_arm @ b.matrix_local)) for b in arm.data.bones}
        kart = p.import_kart()
        p.pose(arm)
        posed = {b.name: matrix(rigid(arm.matrix_world @ b.matrix)) for b in arm.pose.bones}
        initial = {}
        from mathutils import Matrix, Vector
        wheel = Matrix.Translation(Vector(p.LAYOUT['steering']) * p.SCALE) @ Matrix.Rotation(
            __import__('math').radians(p.LAYOUT['steering_tilt_degrees']), 4, 'Y') @ Matrix.Scale(p.SCALE, 4)
        for side in 'LR':
            names = [f'hand_{side}', *(n for chain in p.finger_chains(arm, side) for n in chain)]
            initial[side] = {n: matrix(wheel.inverted() @ rigid(arm.matrix_world @ arm.pose.bones[n].matrix)) for n in names}
        arm.matrix_world = bind_arm
        arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        for image in bpy.data.images:
            if max(image.size, default=0) > 1024:
                image.scale(1024, 1024)
        p.rig.select([arm, *prepared.meshes], arm, reveal=True)
        target = OUT / f'{name}.glb'
        bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', use_selection=True,
                                  export_yup=False, export_skins=True, export_animations=False,
                                  export_morph=False, export_image_format='JPEG', export_jpeg_quality=90)
        if name == 'cairo':
            context = [ob for ob in kart if not ob.name.startswith(('SM_Kart_SteeringWheel', 'PreviewColumn'))]
            for ob in context:
                ob.matrix_world = Matrix.Scale(1 / p.SCALE, 4) @ ob.matrix_world
            p.rig.select(context, context[0], reveal=True)
            bpy.ops.export_scene.gltf(filepath=str(OUT / 'kart.glb'), export_format='GLB', use_selection=True,
                                      export_yup=False, export_animations=False)
        entries[name] = {'id': name, 'label': name.title(), 'model': f'models/{name}.glb',
                         'model_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                         'source_sha256': source_identity(name),
                         'scale': p.SCALE, 'bind_world': bind, 'seated_world': posed,
                         'parents': {b.name: b.parent.name if b.parent else None for b in arm.data.bones},
                         'initial_hands': initial, 'layout': p.LAYOUT}
        (OUT / f'{name}.json').write_text(json.dumps(entries[name], separators=(',', ':')) + '\n')
        print('GRIP EDITOR exported', name, target.stat().st_size, flush=True)
    (OUT / 'manifest.json').write_text(json.dumps({'schema': 1, 'characters': list(entries)}, indent=2) + '\n')
    print('GRIP EDITOR EXPORT COMPLETE', flush=True)


if __name__ == '__main__':
    main()
