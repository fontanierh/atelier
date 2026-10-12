"""Lit crown atlases: baked albedo and normal, alpha-coverage mips and HISM fade."""
import unreal as U
import atmosphere


def parent(default_normal):
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools()
    path='/Game/Japan/Materials/M_ForestImpostor'
    m=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('M_ForestImpostor','/Game/Japan/Materials',U.Material,U.MaterialFactoryNew())
    M.delete_all_material_expressions(m)
    def node(cls,**props):
        n=M.create_material_expression(m,cls)
        for k,v in props.items():n.set_editor_property(k,v)
        return n
    colour=node(U.MaterialExpressionTextureSampleParameter2D,parameter_name='Tex',
                texture=E.load_asset('/Engine/EngineResources/WhiteSquareTexture'))
    normal=node(U.MaterialExpressionTextureObjectParameter,parameter_name='NormalTex',
                texture=default_normal,sampler_type=U.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    uv=node(U.MaterialExpressionTextureCoordinate)
    tangent=node(U.MaterialExpressionVertexTangentWS);vertex=node(U.MaterialExpressionVertexNormalWS)
    mapped=node(U.MaterialExpressionCustom,output_type=U.CustomMaterialOutputType.CMOT_FLOAT3,
                code='float3 n=Texture2DSample(Tex,TexSampler,UV).rgb*2-1; return normalize(T*n.x+cross(N,T)*n.y+N*n.z);')
    values=[('Tex',normal,''),('UV',uv,''),('T',tangent,''),('N',vertex,'')]
    args=[]
    for name,expression,output in values:
        a=U.CustomInput();a.set_editor_property('input_name',name);args.append(a)
    mapped.set_editor_property('inputs',args)
    # Connect again after publishing the named inputs.
    for name,expression,output in values:assert M.connect_material_expressions(expression,output,mapped,name)
    assert M.connect_material_property(mapped,'',U.MaterialProperty.MP_NORMAL)
    fill=node(U.MaterialExpressionMultiply,const_b=.015);M.connect_material_expressions(colour,'RGB',fill,'A')
    base,emit=atmosphere.apply(m,colour,fill)
    M.connect_material_property(base,'',U.MaterialProperty.MP_BASE_COLOR);M.connect_material_property(emit,'',U.MaterialProperty.MP_EMISSIVE_COLOR)
    subsurface=node(U.MaterialExpressionMultiply,const_b=.22)
    M.connect_material_expressions(colour,'RGB',subsurface,'A')
    M.connect_material_property(subsurface,'',U.MaterialProperty.MP_SUBSURFACE_COLOR)
    fade=node(U.MaterialExpressionPerInstanceFadeAmount);mask=node(U.MaterialExpressionMultiply)
    M.connect_material_expressions(colour,'A',mask,'A');M.connect_material_expressions(fade,'',mask,'B')
    M.connect_material_property(mask,'',U.MaterialProperty.MP_OPACITY_MASK)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=1.),'',U.MaterialProperty.MP_ROUGHNESS)
    M.connect_material_property(node(U.MaterialExpressionConstant,r=0.),'',U.MaterialProperty.MP_SPECULAR)
    m.set_editor_property('blend_mode',U.BlendMode.BLEND_MASKED);m.set_editor_property('two_sided',True)
    m.set_editor_property('opacity_mask_clip_value',.4)
    m.set_editor_property('shading_model',U.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    m.set_editor_property('tangent_space_normal',False);m.set_editor_property('dithered_lod_transition',True)
    m.set_editor_property('used_with_instanced_static_meshes',True)
    M.recompile_material(m);E.save_loaded_asset(m)
    return m


def instance(name,record,output,master):
    E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary;AT=U.AssetToolsHelpers.get_asset_tools();textures={}
    for kind,file in record['atlases'].items():
        task=U.AssetImportTask();task.filename=str(output/file);task.destination_path='/Game/Japan/Textures'
        task.destination_name='T_'+name+'_'+kind;task.automated=True;task.replace_existing=True;task.save=True
        AT.import_asset_tasks([task]);texture=E.load_asset('/Game/Japan/Textures/'+task.destination_name);assert texture
        texture.set_editor_property('srgb',kind=='colour');texture.set_editor_property('max_texture_size',512)
        if kind=='normal':texture.set_editor_property('compression_settings',U.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        else:
            texture.set_editor_property('do_scale_mips_for_alpha_coverage',True)
            texture.set_editor_property('alpha_coverage_thresholds',U.Vector4(0,0,0,.4))
        E.save_loaded_asset(texture);textures[kind]=texture
    key=name+'_Impostor';path='/Game/Japan/Materials/MI_'+key
    mi=E.load_asset(path) if E.does_asset_exist(path) else AT.create_asset('MI_'+key,'/Game/Japan/Materials',U.MaterialInstanceConstant,U.MaterialInstanceConstantFactoryNew())
    M.set_material_instance_parent(mi,master)
    M.set_material_instance_texture_parameter_value(mi,'Tex',textures['colour'])
    M.set_material_instance_texture_parameter_value(mi,'NormalTex',textures['normal'])
    M.update_material_instance(mi);E.save_loaded_asset(mi)
    return mi
