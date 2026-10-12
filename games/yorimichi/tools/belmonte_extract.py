"""One-time environmental source extraction from the pinned, current Belmonte level.

Run inside Unreal on an isolated Haras reference checkout. This tool never saves
the source level and exports static geometry only. BELMONTE_EXPORT_DIR names an
ignored output directory; the normal build consumes the resulting committed GLBs,
not this project or its classes.
"""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import unreal

LEVEL = '/Game/Maps/HarasValley'
OUT = Path(os.environ['BELMONTE_EXPORT_DIR'])
FOLIAGE_PREFIXES = ('SM_BV_', 'SM_BVV_FarVeg', 'SM_BVV_VineStrip', 'SM_BVV_Hedge',
                    'SM_BHip_InfieldHedge', 'SM_BHip_UrnTopiary', 'SM_BC_GorgeGreen')


def vector(value):
    return [float(value.x), float(value.y), float(value.z)]


def transform(value):
    q = value.rotation
    return {'translation_cm': vector(value.translation), 'scale': vector(value.scale3d),
            'rotation_xyzw': [float(q.x), float(q.y), float(q.z), float(q.w)]}


def export(asset, path, exporter, options=None):
    task = unreal.AssetExportTask()
    task.object = asset
    task.filename = str(path)
    task.exporter = exporter
    task.automated = True
    task.prompt = False
    task.replace_identical = True
    if options is not None:
        task.options = options
    assert unreal.Exporter.run_asset_export_task(task), (asset.get_path_name(), 'export failed')
    assert path.is_file() and path.stat().st_size > 0, path
    return hashlib.sha256(path.read_bytes()).hexdigest()


def material_data(material):
    """Snapshot the resolved material data, including per-estate dynamic colour."""
    library = unreal.MaterialEditingLibrary
    result = {'source_asset': material.get_path_name(), 'scalars': {}, 'vectors': {}, 'textures': {}}
    getters = {'scalar': library.get_material_instance_scalar_parameter_value,
               'vector': library.get_material_instance_vector_parameter_value,
               'texture': library.get_material_instance_texture_parameter_value}
    for kind, names in [('scalar', library.get_scalar_parameter_names(material)),
                        ('vector', library.get_vector_parameter_names(material)),
                        ('texture', library.get_texture_parameter_names(material))]:
        for name in names:
            if isinstance(material, unreal.MaterialInstanceDynamic):
                value = getattr(material, f'get_{kind}_parameter_value')(name)
            elif isinstance(material, unreal.MaterialInstanceConstant):
                value = getters[kind](material, name)
            else:
                value = getattr(library, f'get_material_default_{kind}_parameter_value')(material, name)
            if kind == 'vector':
                value = [float(value.r), float(value.g), float(value.b), float(value.a)]
            elif kind == 'texture':
                value = value.get_path_name() if value else None
            else:
                value = float(value)
            result[kind + 's'][str(name)] = value
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fbx').mkdir(exist_ok=True)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assert unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(LEVEL), LEVEL
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    # The member IsPartitionedWorld has no UFUNCTION in 5.8; its visible
    # WorldSettings property provides the actual partition object instead.
    assert world.get_world_settings().get_editor_property('world_partition') is None, 'Load partition cells before export'
    streaming, hidden_levels = [], set()
    for level in unreal.ObjectIterator(unreal.LevelStreaming):
        if level.get_outer() != world:
            continue
        loaded = level.get_loaded_level()
        record = {'level': level.get_path_name(), 'loaded': loaded.get_path_name() if loaded else None,
                  'visible_in_editor': bool(level.get_editor_property('should_be_visible_in_editor')),
                  'visible_in_game': bool(level.get_editor_property('should_be_visible'))}
        streaming.append(record)
        assert loaded is not None, ('Unloaded streaming level', record)
        if not record['visible_in_editor'] or not record['visible_in_game']:
            hidden_levels.add(loaded.get_path_name())
    all_actors = actors.get_all_level_actors()
    census = dict(Counter(a.get_outer().get_path_name() for a in all_actors))
    unreal.log('BELMONTE LEVEL CENSUS ' + json.dumps({'actors': census, 'streaming': streaming}))
    meshes, placements, vegetation, excluded, foliage_assets, signs, materials_data = {}, [], [], [], [], [], {}
    for actor in all_actors:
        if actor.get_outer().get_path_name() in hidden_levels:
            excluded.append({'actor': actor.get_actor_label(), 'reason': 'hidden streaming level'})
            continue
        if actor.get_editor_property('hidden') or actor.get_editor_property('is_editor_only_actor'):
            excluded.append({'actor': actor.get_actor_label(), 'class': actor.get_class().get_name(),
                             'reason': 'hidden in game or editor-only actor'})
            continue
        components = actor.get_components_by_class(unreal.PrimitiveComponent)
        for component in components:
            if isinstance(component, unreal.TextRenderComponent) and component.is_visible():
                colour = component.get_editor_property('text_render_color')
                signs.append({'text': str(component.get_editor_property('text')),
                              'transform': transform(component.get_world_transform()),
                              'size_cm': float(component.get_editor_property('world_size')),
                              'colour_srgb': [int(colour.r), int(colour.g), int(colour.b)]})
                continue
            if not isinstance(component, unreal.StaticMeshComponent):
                excluded.append({'actor': actor.get_actor_label(), 'class': component.get_class().get_name(),
                                 'reason': 'non-static component: coverage review required'})
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if mesh is None:
                continue
            path, name = mesh.get_path_name(), mesh.get_name()
            if (not component.is_visible() or component.get_editor_property('hidden_in_game')
                    or component.get_editor_property('is_editor_only')):
                excluded.append({'asset': path, 'reason': 'component not visible'})
                continue
            if isinstance(component, unreal.InstancedStaticMeshComponent):
                transforms = []
                for i in range(component.get_instance_count()):
                    t = component.get_instance_transform(i, world_space=True)
                    assert t is not None, (path, 'Missing instance transform', i)
                    transforms.append(t)
            else:
                transforms = [component.get_world_transform()]
            if not transforms:
                continue
            box = mesh.get_bounding_box()
            if isinstance(component, unreal.SplineMeshComponent):
                raise ValueError((path, 'Spline deformation must be exported explicitly'))
            by_class = isinstance(component, unreal.FoliageInstancedStaticMeshComponent) or isinstance(actor, unreal.InstancedFoliageActor)
            if by_class:
                foliage_assets.append({'name': name, 'path': path, 'count': len(transforms)})
            known_plant = name.startswith(FOLIAGE_PREFIXES) or any(k in path.lower() for k in ('/vegetation/', '/trees/', '/plants/'))
            if known_plant:
                vegetation.append({'name': name, 'source_asset': path, 'count': len(transforms),
                                   'bounds_cm': [vector(box.min), vector(box.max)],
                                   'transforms': [transform(t) for t in transforms]})
                excluded.append({'asset': path, 'reason': 'planting retained as data; meshes replaced by Yorimichi flora'})
                continue
            environment = path.startswith('/Game/Haras/Belmonte/') or path.startswith('/HarasVillage/Meshes/SM_HV_Emblem_')
            if not environment:
                excluded.append({'asset': path, 'reason': 'outside current Belmonte environment'})
                continue
            if 'Crowd' in name:
                excluded.append({'asset': path, 'reason': 'character scenery'})
                continue
            if name.startswith('SM_BT_Backdrop_'):
                excluded.append({'asset': path, 'reason': 'distant backdrop replaced by Yorimichi terrain'})
                continue
            meshes.setdefault(path, {'name': name, 'source_asset': path,
                                     'bounds_cm': [vector(box.min), vector(box.max)],
                                     'fallback_triangles': mesh.get_num_triangles(0),
                                     'slots': [str(s.get_editor_property('imported_material_slot_name'))
                                               for s in mesh.get_editor_property('static_materials')]})
            materials = [component.get_material(i) for i in range(component.get_num_materials())]
            material_paths = [m.get_path_name() if m else None for m in materials]
            for material in materials:
                if material and material.get_path_name() not in materials_data:
                    materials_data[material.get_path_name()] = material_data(material)
            for t in transforms:
                placements.append({'asset': path, 'transform': transform(t), 'materials': material_paths,
                                   'actor': actor.get_actor_label()})
    options = unreal.FbxExportOption()
    options.set_editor_property('collision', True)
    options.set_editor_property('level_of_detail', False)
    assert meshes and placements, 'No visible environmental meshes extracted'
    dry = os.environ.get('BELMONTE_EXTRACT_DRY') == '1'
    unreal.log('BELMONTE FOLIAGE CENSUS ' + json.dumps(foliage_assets))
    for index, (path, entry) in enumerate(sorted(meshes.items())):
        asset = unreal.load_asset(path)
        name = entry['name'] + '-' + hashlib.sha256(path.encode()).hexdigest()[:10]
        destination = OUT / 'fbx' / (name + '.fbx')
        entry['fbx'] = destination.relative_to(OUT).as_posix()
        if not dry:
            entry['sha256'] = export(asset, destination, unreal.StaticMeshExporterFBX(), options)
        unreal.log(f'BELMONTE EXTRACT {index + 1}/{len(meshes)} {entry["name"]}')
    textures = {}
    for data in materials_data.values():
        for path in data['textures'].values():
            if not path or path in textures:
                continue
            asset = unreal.load_asset(path)
            name = asset.get_name() + '-' + hashlib.sha256(path.encode()).hexdigest()[:10]
            destination = OUT / 'textures' / (name + '.png')
            destination.parent.mkdir(exist_ok=True)
            textures[path] = {'file': destination.relative_to(OUT).as_posix()}
            if not dry:
                textures[path]['sha256'] = export(asset, destination, unreal.TextureExporterPNG())
            unreal.log('BELMONTE TEXTURE ' + name)
    result = {'version': 1, 'level': LEVEL, 'units': 'Unreal centimetres, native quaternion xyzw',
              'dry_run': dry, 'actor_census': census, 'streaming': streaming, 'foliage_census': foliage_assets,
              'meshes': list(meshes.values()),
              'materials': materials_data, 'textures': textures, 'signs': signs,
              'placements': placements, 'vegetation': vegetation, 'excluded': excluded,
              'embedded_foliage_policy': 'Conversion removes foliage material primitives, including bundled plants.'}
    (OUT / ('census.json' if dry else 'scene.json')).write_text(json.dumps(result, separators=(',', ':')) + '\n')
    unreal.log(f'BELMONTE EXTRACT COMPLETE: {len(meshes)} meshes, {len(placements)} placements')


main()
