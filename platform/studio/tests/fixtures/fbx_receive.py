"""Fresh-process receiving checks avoid stale dependency graphs across factory resets."""
import json
from pathlib import Path
import sys

import bpy

folder, kind = sys.argv[sys.argv.index('--')+1:]
folder = Path(folder)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(folder/(kind+'.fbx')))
if kind == 'static':
    loaded = bpy.data.objects['Probe']
    assert len(loaded.data.vertices) == 4 and len(loaded.data.polygons) == 2
    for vertex, expected in zip(loaded.data.vertices, [(0,0,0),(2,0,0),(2,1,1),(0,1,0)]):
        assert max(abs(a-b) for a,b in zip(vertex.co, expected)) < 1e-6
    assert len(loaded.data.uv_layers) == 6
    assert [slot.material.name for slot in loaded.material_slots] == ['Leaf', 'Metal']
    assert [p.material_index for p in loaded.data.polygons] == [0,1]
    assert len(loaded.data.color_attributes) == 1
    for loop, value in zip(loaded.data.loops, loaded.data.color_attributes[0].data):
        expected = (float(loop.vertex_index % 2),0.,1.,1.)
        assert max(abs(a-b) for a,b in zip(value.color, expected)) < 1e-5
    for channel, uv in enumerate(loaded.data.uv_layers):
        for loop in loaded.data.loops:
            expected = (channel+loop.vertex_index*.125,loop.index*.125)
            assert max(abs(a-b) for a,b in zip(uv.data[loop.index].uv, expected)) < 1e-6
    assert all(normal.vector.z > .9999 for normal in loaded.data.corner_normals)
    assert 'UCX_Probe_00' in bpy.data.objects
    assert any(Path(img.filepath_from_user()).is_file()
               and not Path(img.filepath_from_user()).resolve().is_relative_to(folder/'author-textures')
               for img in bpy.data.images if img.source == 'FILE')
else:
    loaded_arm = next(obj for obj in bpy.data.objects if obj.type == 'ARMATURE')
    assert set(loaded_arm.data.bones.keys()) == {'Root','Child'}
    if kind == 'skeletal':
        loaded_skin = bpy.data.objects['Skin']
        assert set(loaded_skin.vertex_groups.keys()) == {'Root','Child'}
        assert all(abs(sum(group.weight for group in vertex.groups)-1.) < 1e-6
                   for vertex in loaded_skin.data.vertices)
    else:
        assert kind == 'clip'
        action = loaded_arm.animation_data.action
        assert action is not None
        # Bind the received action after its channels have been populated by the importer.
        slot = loaded_arm.animation_data.action_slot
        loaded_arm.animation_data.action = None
        loaded_arm.animation_data.action = action
        loaded_arm.animation_data.action_slot = slot
        loaded_arm.update_tag()
        start_frame,end_frame = action.frame_range
        assert abs(end_frame-start_frame-19.) < 1e-6
        def position(frame):
            bpy.context.scene.frame_set(int(frame))
            bpy.context.view_layer.update()
            obj = loaded_arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
            return obj.pose.bones['Child'].matrix.translation.copy()
        start = position(start_frame)
        travel = (position(end_frame)-start).length
        assert abs(travel-.25) < 1e-4, travel
(folder/(kind+'.receive.json')).write_text(json.dumps(dict(kind=kind,received=True)))
print('FBX RECEIVE CANARY COMPLETE',kind,flush=True)
