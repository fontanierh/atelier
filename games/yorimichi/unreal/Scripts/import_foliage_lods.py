"""Apply an authored LOD chain without writing shared materials or its source product."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import json
import unreal as U
import yori
from foliage_material import supports_lod_blend
from mesh_import import import_mesh


def verify_lods(target,screen_sizes,meshes,impostor=None,bark='Bark',interface=None):
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
        return interface[path]['lod_blend']
    assert all(blends(m) for m in slots),(name,'a material disables HISM blending')
    palettes=[]
    for level in range(count):
        palettes.append(sorted({target.get_material(meshes.get_lod_material_slot(target,level,section)).get_path_name()
                                for section in range(target.get_num_sections(level))}))
    if impostor:
        assert all(p==palettes[0] for p in palettes[:-1]),(name,'leaf LOD changes palette',palettes)
        expected=sorted(['/Game/Japan/Materials/MI_'+bark+'.MI_'+bark,
                         '/Game/Japan/Materials/MI_'+impostor+'.MI_'+impostor])
        assert palettes[-1]==expected,(name,'impostor material contract',palettes[-1],expected)
    else:assert all(p==palettes[0] for p in palettes),(name,'LOD changes the source palette',palettes)
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
    return verify_lods(target, data['screen_sizes'], meshes, data.get('impostor_slot'), data.get('impostor_bark', 'Bark'), interface=interface)


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
