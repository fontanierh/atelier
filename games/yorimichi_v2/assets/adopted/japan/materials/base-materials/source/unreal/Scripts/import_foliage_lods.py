"""Apply an authored LOD chain without writing shared materials or its source product."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import json
import unreal as U
import yori
from foliage_material import supports_lod_blend
from mesh_import import import_mesh


# A far crown (world/far_crown.py) is the one slot of a tree's last LOD: an instance of the opaque, already
# compiled M_Painted with the crown's colour and the dithered LOD blending HISM needs (as on MI_Bark), so no shared
# material and no new shader permutation. It lives in the tree's own LOD folder, so the product that owns that
# folder (a tree's import step, or the forest's) retains, restores and inventories it with the LODs.
def crown_path(crown, folder):
    return folder + '/MI_' + crown['slot']


def crown_material(crown, folder):
    from foliage_material import enable_bark_lod_blend
    editor = U.EditorAssetLibrary
    name = 'MI_' + crown['slot']
    path = crown_path(crown, folder)
    if editor.does_asset_exist(path):
        material = editor.load_asset(path)
    else:
        material = U.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, U.MaterialInstanceConstant, U.MaterialInstanceConstantFactoryNew())
    parent = editor.load_asset('/Game/Japan/Materials/M_Painted')
    white = editor.load_asset('/Game/Japan/Textures/T_white')
    if not (material and parent and white):
        raise RuntimeError('Crown material inputs missing: ' + crown['slot'])
    colour = U.LinearColor(*crown['colour'], 1.)
    edit = U.MaterialEditingLibrary
    changed = material.get_editor_property('parent') != parent
    if changed:
        edit.set_material_instance_parent(material, parent)
    if edit.get_material_instance_vector_parameter_value(material, 'Tint') != colour:
        edit.set_material_instance_vector_parameter_value(material, 'Tint', colour); changed = True
    if edit.get_material_instance_texture_parameter_value(material, 'Tex') != white:
        edit.set_material_instance_texture_parameter_value(material, 'Tex', white); changed = True
    if not supports_lod_blend(material):
        enable_bark_lod_blend(material); changed = True
    if changed:
        edit.update_material_instance(material)
    # Unchanged crowns keep a clean package, as unchanged LOD sources do.
    if not editor.save_loaded_asset(material, only_if_is_dirty=True):
        raise RuntimeError('Could not save crown material: ' + path)
    return material


def verify_lods(target,screen_sizes,meshes,impostor=None,bark='Bark',interface=None,crown=None,folder=None):
    name=target.get_name()
    count=target.get_num_lods()
    assert count==len(screen_sizes),(name,'missing LOD')
    actual=list(meshes.get_lod_screen_sizes(target))
    assert all(abs(a-b)<1e-5 for a,b in zip(actual,screen_sizes)),(name,'LOD distances')
    slots=[s.get_editor_property('material_interface') for s in target.get_editor_property('static_materials')]
    def blends(material):
        if not material:
            return False
        if interface is None:  # legacy forest imports read the shared native material product
            return supports_lod_blend(material)
        path = material.get_path_name().split('.')[0]
        if crown is not None and path == crown_path(crown, folder):
            return supports_lod_blend(material)   # owned here, not a shared-material product
        return interface[path]['lod_blend']
    assert all(blends(m) for m in slots),(name,'a material disables HISM blending')
    palettes=[]
    for level in range(count):
        palettes.append(sorted({target.get_material(meshes.get_lod_material_slot(target,level,section)).get_path_name()
                                for section in range(target.get_num_sections(level))}))
    # A far crown is one extra level after the authored chain (and after the impostor, when there is one).
    authored=palettes[:-1] if crown else palettes
    if crown:
        expected=[crown_path(crown,folder)+'.MI_'+crown['slot']]
        assert palettes[-1]==expected,(name,'crown material contract',palettes[-1],expected)
    if impostor:
        assert all(p==authored[0] for p in authored[:-1]),(name,'leaf LOD changes palette',palettes)
        expected=sorted(['/Game/Japan/Materials/MI_'+bark+'.MI_'+bark,
                         '/Game/Japan/Materials/MI_'+impostor+'.MI_'+impostor])
        assert authored[-1]==expected,(name,'impostor material contract',authored[-1],expected)
    else:assert all(p==authored[0] for p in authored),(name,'LOD changes the source palette',palettes)
    return {'vertices':[meshes.get_number_verts(target,i) for i in range(count)],
            'screen_sizes':actual,'materials_by_lod':palettes,'all_slots_blend':True}

def apply_lods(target, data, output, meshes, *, seed, folder, interface=None, reuse_validator=None):
    """@cc [owner:fontanierh,label:performance] preserve-unchanged-lod-source-packages
    Current material bindings MUST still be applied and validated. An unchanged binding
    MUST NOT dirty its source LOD package, and clean source packages MUST NOT be forced
    through a save. Target LOD assembly and its current validation MUST still run.
    A task-supplied reuse predicate MUST accompany every source import so the base
    and LODs share one receipt policy and pending evidence packet.
    """
    editor = U.EditorAssetLibrary
    name = target.get_name()
    original_vertices = meshes.get_number_verts(target, 0)
    bounds = target.get_bounding_box()
    original_size = sum((getattr(bounds.max, a) - getattr(bounds.min, a)) ** 2 for a in ('x', 'y', 'z')) ** .5
    for level in range(1, len(data['screen_sizes'])):
        lod_name = f'{name}_LOD{level}'
        source = import_mesh(output / (lod_name + '.fbx'), folder, lod_name, seed=seed, fresh_slots=True,
                             reuse_validator=reuse_validator)
        bounds = source.get_bounding_box()
        size = sum((getattr(bounds.max, a) - getattr(bounds.min, a)) ** 2 for a in ('x', 'y', 'z')) ** .5
        assert original_size > 0 and .8 <= size / original_size <= 1.15, (lod_name, 'LOD bounds differ', size, original_size)
        for index, slot in enumerate(source.get_editor_property('static_materials')):
            key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            crown = data.get('crown')
            if crown and key == crown['slot']:
                material = crown_material(crown, folder)
            else:
                material = editor.load_asset('/Game/Japan/Materials/MI_' + key)
            if not material:
                raise RuntimeError('LOD material missing: ' + key)
            if source.get_material(index) != material:
                source.set_material(index, material)
            if source.get_material(index) != material:
                raise RuntimeError('LOD material binding did not persist: ' + key)
        if not editor.save_loaded_asset(source, only_if_is_dirty=True):
            raise RuntimeError('Could not save owned LOD package: ' + source.get_path_name())
        assert meshes.set_lod_from_static_mesh(target, level, source, 0, True) == level
    assert meshes.set_lod_screen_sizes(target, data['screen_sizes'])
    assert meshes.get_number_verts(target, 0) == original_vertices, 'LOD0 changed'
    if not editor.save_loaded_asset(target):
        raise RuntimeError('Could not save foliage LOD chain: ' + target.get_path_name())
    return verify_lods(target, data['screen_sizes'], meshes, data.get('impostor_slot'), data.get('impostor_bark', 'Bark'),
                       interface=interface, crown=data.get('crown'), folder=folder)


def main(output, manifest_file='trees.json'):
    """Legacy forest owner; its existing village seed dependency is declared by unreal.world."""
    manifest = json.loads((output / manifest_file).read_text())
    U.load_module('StaticMeshEditor')
    meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    if meshes is None:
        raise RuntimeError('StaticMeshEditor subsystem is unavailable')
    report = {}
    for name, data in manifest.items():
        target = U.EditorAssetLibrary.load_asset('/Game/Japan/Assets/' + name)
        if not target:
            raise RuntimeError('Missing detailed foliage: ' + name)
        report[name] = apply_lods(target, data, output, meshes, seed=yori.OUT / 'village/assets/Village_Sign.fbx',
                                  folder='/Game/Japan/FoliageLODs')
    (output / 'import.json').write_text(json.dumps(report, indent=2) + '\n')
    U.log('FOLIAGE LOD IMPORT COMPLETE: ' + json.dumps(report))
