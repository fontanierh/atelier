"""Add explicit LODs to existing foliage, preserving LOD0, materials and collision."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import sys
import unreal as U

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from foliage_material import enable_distance_fade, enable_bark_lod_blend, supports_lod_blend
from import_village import import_mesh


def verify_lods(target,screen_sizes,meshes,impostor=None):
    name=target.get_name()
    count=target.get_num_lods()
    assert count==len(screen_sizes),(name,'missing LOD')
    actual=list(meshes.get_lod_screen_sizes(target))
    assert all(abs(a-b)<1e-5 for a,b in zip(actual,screen_sizes)),(name,'LOD distances')
    slots=[s.get_editor_property('material_interface') for s in target.get_editor_property('static_materials')]
    assert all(m and supports_lod_blend(m) for m in slots),(name,'a material disables HISM blending')
    palettes=[]
    for level in range(count):
        palettes.append(sorted({target.get_material(meshes.get_lod_material_slot(target,level,section)).get_path_name()
                                for section in range(target.get_num_sections(level))}))
    if impostor:
        assert all(p==palettes[0] for p in palettes[:-1]),(name,'leaf LOD changes palette',palettes)
        expected=sorted(['/Game/Japan/Materials/MI_Bark.MI_Bark',
                         '/Game/Japan/Materials/MI_'+impostor+'.MI_'+impostor])
        assert palettes[-1]==expected,(name,'impostor material contract',palettes[-1],expected)
    else:assert all(p==palettes[0] for p in palettes),(name,'LOD changes the source palette',palettes)
    return {'vertices':[meshes.get_number_verts(target,i) for i in range(count)],
            'screen_sizes':actual,'materials_by_lod':palettes,'all_slots_blend':True}


def main(names=None, output=None, manifest_file='manifest.json', shared_materials=True):
    output=output or yori.OUT/'foliage_lods'
    manifest=json.loads((output/manifest_file).read_text())
    if names is not None: manifest={name:manifest[name] for name in names}
    editor=U.EditorAssetLibrary
    U.load_module('StaticMeshEditor')
    meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    if meshes is None: raise RuntimeError('StaticMeshEditor subsystem is unavailable')
    report=json.loads((output/'import.json').read_text()) if names is not None and (output/'import.json').exists() else {}
    for name,data in manifest.items():
        target=editor.load_asset('/Game/Japan/Assets/'+name)
        if not target: raise RuntimeError('Missing detailed foliage: '+name)
        original_vertices=meshes.get_number_verts(target,0)
        bounds=target.get_bounding_box()
        original_size=sum((getattr(bounds.max,axis)-getattr(bounds.min,axis))**2 for axis in ('x','y','z'))**.5
        lod_count=len(data['screen_sizes'])
        for level in range(1,lod_count):
            lod_name=f'{name}_LOD{level}'
            source=import_mesh(output/(lod_name+'.fbx'),'/Game/Japan/FoliageLODs',lod_name,fresh_slots=True)
            bounds=source.get_bounding_box()
            size=sum((getattr(bounds.max,axis)-getattr(bounds.min,axis))**2 for axis in ('x','y','z'))**.5
            assert original_size>0 and .8<=size/original_size<=1.15,(lod_name,'LOD bounds differ from LOD0',size,original_size)
            for index,slot in enumerate(source.get_editor_property('static_materials')):
                key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
                material=editor.load_asset('/Game/Japan/Materials/MI_'+key)
                if not material: raise RuntimeError('LOD material missing: '+key)
                source.set_material(index,material)
            editor.save_loaded_asset(source)
            assert meshes.set_lod_from_static_mesh(target,level,source,0,True)==level
        assert meshes.set_lod_screen_sizes(target,data['screen_sizes'])
        assert meshes.get_number_verts(target,0)==original_vertices,'LOD0 changed'
        assert target.get_num_lods()==lod_count
        editor.save_loaded_asset(target)
    if shared_materials:
        foliage=editor.load_asset('/Game/Japan/Materials/M_Foliage')
        enable_distance_fade(foliage)
        U.MaterialEditingLibrary.recompile_material(foliage)
        editor.save_loaded_asset(foliage)
        bark=editor.load_asset('/Game/Japan/Materials/MI_Bark')
        if not bark: raise RuntimeError('Bark material is missing')
        enable_bark_lod_blend(bark)
        editor.save_loaded_asset(bark)
    for name,data in manifest.items():
        report[name]=verify_lods(editor.load_asset('/Game/Japan/Assets/'+name),data['screen_sizes'],meshes,data.get('impostor_slot'))
    (output/'import.json').write_text(json.dumps(report,indent=2)+'\n')
    U.log('FOLIAGE LOD IMPORT COMPLETE: '+json.dumps(report))


if __name__ == '__main__': main()
