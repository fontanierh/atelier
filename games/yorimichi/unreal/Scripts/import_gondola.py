"""Import only the complete current ropeway kit and fitted world products."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori
from gondola.service import validate_service
from gondola.validation import PARAMETERS
ROOT=yori.OUT/'gondola'
validate_service(json.loads((ROOT/'runtime.json').read_text()),yori.OUT)
# No Unreal package mutation occurs before all current source/audit checks above.
import unreal
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mesh_import import import_mesh
from mesh_materials import assign_materials
from material_assets import import_texture, node, link, save_material
import gondola_native

E=unreal.EditorAssetLibrary
M=unreal.MaterialEditingLibrary
TOOLS=unreal.AssetToolsHelpers.get_asset_tools()
unreal.load_module('StaticMeshEditor')
EDITOR=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
if EDITOR is None:raise RuntimeError('StaticMeshEditor subsystem is unavailable after loading its module')
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
manifest=json.loads((ROOT/'manifest.json').read_text())
site=json.loads((ROOT/'world/site.json').read_text())
state=gondola_native.configure(site)


def material(name,rgb,roughness,metallic,texture):
    path='/Game/Gondola/Materials/'+name
    mat=E.load_asset(path) if E.does_asset_exist(path) else TOOLS.create_asset(name,'/Game/Gondola/Materials',unreal.Material,unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(mat)
    def linear(v):
        v/=255.
        return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    if texture:
        color=import_texture(str(ROOT/f'textures/GD_{texture}_color.png'),'/Game/Gondola/Textures')
        rough=import_texture(str(ROOT/f'textures/GD_{texture}_rough.png'),'/Game/Gondola/Textures')
        if not color or not rough:raise ValueError('Missing ropeway timber texture')
        rough.set_editor_property('srgb',False);E.save_loaded_asset(rough)
        c=node(mat,unreal.MaterialExpressionTextureSample,-300,0,texture=color)
        r=node(mat,unreal.MaterialExpressionTextureSample,-300,160,texture=rough,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    else:
        c=node(mat,unreal.MaterialExpressionConstant3Vector,-300,0,constant=unreal.LinearColor(*(linear(v) for v in rgb),1.))
        r=node(mat,unreal.MaterialExpressionConstant,-300,160,r=roughness)
    M.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    M.connect_material_property(r,'R' if texture else '',unreal.MaterialProperty.MP_ROUGHNESS)
    metal=node(mat,unreal.MaterialExpressionConstant,-300,300,r=metallic)
    M.connect_material_property(metal,'',unreal.MaterialProperty.MP_METALLIC)
    if name=='GD_Glass':
        mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property('two_sided',True)
        opacity=node(mat,unreal.MaterialExpressionConstant,-300,450,r=.18)
        M.connect_material_property(opacity,'',unreal.MaterialProperty.MP_OPACITY)
    else:mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE)
    if name=='GD_LampGlow':M.connect_material_property(c,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    save_material(mat)
    return mat


mats={name:material(name,*values,manifest['textured_materials'].get(name)) for name,values in manifest['materials'].items()}
report={}
for folder,dest,names in ((ROOT,'/Game/Gondola/Kit',PARAMETERS.asset_names()),
                          (ROOT/'world','/Game/Gondola/World',state['current'])):
    for name in names:
        source=folder/('assets' if folder==ROOT else 'atomic-assets')
        mesh=import_mesh(source/f'{name}.fbx',dest,name,seed=ROOT/'assets/GD_Cabin.fbx',fresh_slots=True)
        mesh.set_editor_property('generate_mesh_distance_field',False)
        collision=name.endswith('_Collision')
        body=mesh.get_editor_property('body_setup')
        if collision:
            body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
            if EDITOR.get_convex_collision_count(mesh)<=0:raise ValueError(name+': missing authored convex collision')
        elif folder!=ROOT and '_Rope_' not in name:
            body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        slots=[]
        for slot in mesh.static_materials:
            key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            if key not in mats and not collision:raise ValueError(name+': unknown material '+key)
            slots.append(mats.get(key,mats['GD_DarkIron']))
        if slots:assign_materials(mesh,slots)
        if name in {key for family in site['rope_groups'].values() for key in family}:
            for level in (1,2):
                path=source/(name.replace('_LOD0',f'_LOD{level}')+'.fbx')
                if EDITOR.import_lod(mesh,level,str(path))!=level:raise ValueError(name+': failed rope LOD import')
            if mesh.get_num_lods()!=3:raise ValueError(name+': incomplete rope detail levels')
        if not E.save_loaded_asset(mesh):raise ValueError('Gondola mesh save failed: '+name)
        report[name]={'triangles':[mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
                      'convex_hulls':EDITOR.get_convex_collision_count(mesh)}
        unreal.log('GONDOLA IMPORT '+name+' '+str(report[name]))
gondola_native.finish_ropes(site,report)
gondola_native.retire(state)
(ROOT/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('GONDOLA IMPORT COMPLETE')
