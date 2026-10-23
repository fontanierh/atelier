"""Import the south-west detour props (village kit, coconut stand, temple, island) into /Game/Japan/Assets with the
village material, and re-import the revised terrain. Level lighting, characters and preferences are untouched."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys
from pathlib import Path
import unreal
ROOT = yori.OUT;OUT=ROOT/'southwest'
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(yori.GAME))
import import_village as V
import sea_look
EAL=unreal.EditorAssetLibrary

MEL=unreal.MaterialEditingLibrary
def _node(m,cls,x,y,**props):
    n=MEL.create_material_expression(m,cls,x,y)
    for k,v in props.items():n.set_editor_property(k,v)
    return n
def _link(a,ao,b,bi):MEL.connect_material_expressions(a,ao,b,bi)
def _create(name,cls,factory):
    # reuse an existing asset (deleting one that the terrain or sea still references fails); the caller resets it
    path='/Game/Japan/Materials/'+name
    if EAL.does_asset_exist(path):return EAL.load_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',cls,factory)
def sand_material():
    """MI_Sand: the painted master with the white texture and a warm pale-sand tint (linear values stay dark: exposure lifts them)."""
    parent=EAL.load_asset('/Game/Japan/Materials/M_Painted');white=EAL.load_asset('/Game/Japan/Textures/T_white')
    mi=_create('MI_Sand',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi,parent);MEL.set_material_instance_texture_parameter_value(mi,'Tex',white)
    MEL.set_material_instance_vector_parameter_value(mi,'Tint',unreal.LinearColor(0.24,0.185,0.10,1.0))
    MEL.update_material_instance(mi);EAL.save_loaded_asset(mi);return mi
def sea_material():
    """M_Sea: the open sea (sea_look.py). Its colour is emissive: a deep blue-teal body, lighter teal in the shallows,
    a Fresnel reflection of the painted dome on world-space wave normals, white surf where the water meets anything
    (the scene depth behind the surface) and a haze toward a colour a little darker than the dome's horizon. The
    engine lights it for sun glints only (black base colour, specular .02), so its grazing reflection of the sky
    light's capture no longer turns the whole sea the sky's colour."""
    U=unreal;m=_create('M_Sea',U.Material,U.MaterialFactoryNew());MEL.delete_all_material_expressions(m)
    F1=U.CustomMaterialOutputType.CMOT_FLOAT1;F3=U.CustomMaterialOutputType.CMOT_FLOAT3
    def link(a,b,key):assert MEL.connect_material_expressions(a,'',b,key),key
    def prop(n,p):assert MEL.connect_material_property(n,'',p),p
    def custom(code,inputs,x,y,kind=F3):
        n=_node(m,U.MaterialExpressionCustom,x,y,code=code,output_type=kind)
        args=[]
        for key,_ in inputs:
            a=U.CustomInput();a.set_editor_property('input_name',key);args.append(a)
        n.set_editor_property('inputs',args)
        for key,src in inputs:link(src,n,key)
        return n
    po=_node(m,U.MaterialExpressionWorldPosition,-900,0);ti=_node(m,U.MaterialExpressionTime,-900,150)
    cam=_node(m,U.MaterialExpressionCameraVectorWS,-900,300);pd=_node(m,U.MaterialExpressionPixelDepth,-900,450)
    # scene depth is only readable from translucent materials: translucent, fully opaque
    sd=_node(m,U.MaterialExpressionSceneDepth,-900,600)
    behind=_node(m,U.MaterialExpressionSubtract,-700,550);link(sd,behind,'A');link(pd,behind,'B')
    waves=custom(sea_look.WAVES,[('P',po),('T',ti)],-600,0)
    prop(custom(sea_look.NORMAL,[('W',waves)],-250,0),U.MaterialProperty.MP_NORMAL)
    m.set_editor_property('tangent_space_normal',False)
    look=custom(sea_look.LOOK,[('W',waves),('V',cam),('D',pd),('L',behind),('P',po),('T',ti)],-250,250)
    prop(look,U.MaterialProperty.MP_EMISSIVE_COLOR)
    prop(_node(m,U.MaterialExpressionConstant3Vector,-250,500,constant=U.LinearColor(*sea_look.BASE,1.0)),U.MaterialProperty.MP_BASE_COLOR)
    prop(_node(m,U.MaterialExpressionConstant,-250,600,r=sea_look.ROUGHNESS),U.MaterialProperty.MP_ROUGHNESS)
    prop(custom('return %s*(1-H);'%sea_look.num(sea_look.SPECULAR),[('H',custom(sea_look.HAZE,[('D',pd)],-600,700,F1))],-250,700,F1),
         U.MaterialProperty.MP_SPECULAR)
    prop(_node(m,U.MaterialExpressionConstant,-250,800,r=1.0),U.MaterialProperty.MP_OPACITY)
    m.set_editor_property('blend_mode',U.BlendMode.BLEND_TRANSLUCENT)
    # Low-tessellation sea planes must evaluate the same fog at every pixel.
    m.set_editor_property('compute_fog_per_pixel',True)
    # forward shaded: the sun's specular on the wave normals gives the glints
    m.set_editor_property('translucency_lighting_mode',U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    MEL.recompile_material(m);EAL.save_loaded_asset(m);return m
def main():
    unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    from southwest_atomic_products import exports, native_inventory, native_files, DESTINATION, PARENTS
    from atelier import native_membership, native_packages
    from import_city_surface_tiles import prepare_collision_import, finish_empty_collision
    runtime, current = exports(ROOT)
    content = yori.GAME / 'unreal/Content'
    native_files(content)
    for parent in PARENTS:
        primary = content / 'Japan/Assets' / (parent + '.uasset')
        assert not any(p.is_symlink() for p in (primary, *primary.parents)), ('linked old Southwest parent', parent)
    previous = native_inventory(EAL)
    mat = EAL.load_asset('/Game/Japan/Materials/M_Village')
    assert mat is not None, 'Build the Village material owner before Southwest receiving'
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None
    content = yori.GAME / 'unreal/Content'
    report = {parent: [] for parent in PARENTS}
    for index, (parent, row, receipt, path) in enumerate(current, 1):
        name = row['name']
        from mesh_import import import_mesh
        mesh = import_mesh(path, DESTINATION, name, fresh_slots=True,
            before_import=lambda: prepare_collision_import(DESTINATION, name, editor))
        assert len(mesh.static_materials) == 1, (name, 'Southwest source material count')
        assert str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) == 'Southwest_Palette', name
        if mesh.get_material(0) != mat: mesh.set_material(0, mat)
        if mesh.get_num_lods() > 1: mesh.set_num_source_models(1)
        settings = editor.get_lod_build_settings(mesh, 0)
        if settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs', False)
            editor.set_lod_build_settings(mesh, 0, settings)
        body = mesh.get_editor_property('body_setup')
        assert body is not None, (name, 'missing complex collision body')
        if body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        finish_empty_collision(mesh, row, editor)
        assert mesh.get_num_triangles(0) == row['triangles'], (name, 'render triangle count')
        assert mesh.get_num_lods() == 1, (name, 'unexpected LODs')
        assert editor.get_num_uv_channels(mesh, 0) == 1, (name, 'UV channel count')
        assert not editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'), name
        assert mesh.get_material(0) == mat, (name, 'current material')
        assert unreal.CitySurfaceValidation.validate_collision(mesh, row['triangles'], False), (name, 'current own cooked LOD0')
        box = mesh.get_bounding_box(); lower, upper = receipt['bounds']
        expected = ([lower[0]*100, -upper[1]*100, lower[2]*100],
                    [upper[0]*100, -lower[1]*100, upper[2]*100])
        for coordinates, actual in zip(expected, (box.min, box.max)):
            assert all(abs(getattr(actual, axis)-value) < .2 for axis, value in zip(('x','y','z'),coordinates)), (name, 'bounds')
        native_packages.save(mesh, EAL, content)
        report[parent].append(dict(name=name, triangles=row['triangles'], asset=mesh.get_path_name()))
        mesh = body = None
        if index % 16 == 0: unreal.SystemLibrary.collect_garbage()
        unreal.log('SOUTHWEST current ' + name + ' ' + str(index) + '/' + str(len(current)))
    # unreal.island exclusively owns the separate terrain/sea assets and final shaders.
    # One complete reference preflight covers old pieces AND every original parent.
    # Every current child has been validated and physically saved before retirement.
    current_packages = [r['asset'].split('.')[0] for rows in report.values() for r in rows]
    replacements = {'/Game/Japan/Assets/' + parent: [r['asset'].split('.')[0] for r in report[parent]] for parent in PARENTS}
    replacements.update({package: current_packages for package in previous - set(current_packages)})
    # Pin every obsolete primary/ancestor as real filesystem ownership before any deletion.
    for package in replacements:
        primary = content / (package[len('/Game/'):] + '.uasset')
        assert not any(p.is_symlink() for p in (primary, *primary.parents)), ('linked obsolete Southwest package', package)
    retired = native_membership.retire_replaced(EAL, replacements)
    for package in replacements:
        primary = content / (package[len('/Game/'):] + '.uasset')
        assert not any(primary.with_suffix(suffix).exists() or primary.with_suffix(suffix).is_symlink()
                       for suffix in ('.uasset', '.uexp', '.ubulk', '.uptnl')), ('Southwest physical retirement failed', package)
    assert native_inventory(EAL) == set(current_packages), 'Southwest current native roster differs'
    files = native_files(content)
    assert {p.stem for p in files if p.suffix == '.uasset'} == {r['name'] for _,r,_,_ in current}
    assert set(report) == set(runtime['parents'])
    (OUT/'import-report.json').write_text(json.dumps(dict(parents=report, retired=retired), indent=2) + '\n')
    unreal.log('SOUTHWEST IMPORT COMPLETE %d meshes' % len(current_packages))
if __name__=='__main__':main()
