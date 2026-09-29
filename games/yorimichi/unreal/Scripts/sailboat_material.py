"""Local sail flutter and feathered animated foam, with runtime fill/speed parameters."""
import unreal as U
E=U.EditorAssetLibrary;M=U.MaterialEditingLibrary

def material(wake=False):
 name='M_SailboatWake' if wake else 'M_SailboatCloth';path='/Game/Japan/Materials/'+name
 mat=E.load_asset(path) if E.does_asset_exist(path) else U.AssetToolsHelpers.get_asset_tools().create_asset(name,'/Game/Japan/Materials',U.Material,U.MaterialFactoryNew())
 M.delete_all_material_expressions(mat)
 def node(cls,**props):
  n=M.create_material_expression(mat,cls,0,0)
  for k,v in props.items():n.set_editor_property(k,v)
  return n
 def link(a,ao,b,bi):assert M.connect_material_expressions(a,ao,b,bi)
 def custom(code,inputs,output=U.CustomMaterialOutputType.CMOT_FLOAT3):
  n=node(U.MaterialExpressionCustom,code=code,output_type=output);args=[]
  for key,(src,out) in inputs.items():
   arg=U.CustomInput();arg.set_editor_property('input_name',key);args.append(arg)
  n.set_editor_property('inputs',args)
  for key,(src,out) in inputs.items():link(src,out,n,key)
  return n
 def prop(n,p):assert M.connect_material_property(n,'',p)
 vc=node(U.MaterialExpressionVertexColor);t=node(U.MaterialExpressionTime);p=node(U.MaterialExpressionWorldPosition)
 col=custom('return lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C));',{'C':(vc,'')})
 prop(col,U.MaterialProperty.MP_BASE_COLOR)
 prop(node(U.MaterialExpressionConstant,r=.95),U.MaterialProperty.MP_ROUGHNESS)
 prop(node(U.MaterialExpressionConstant,r=.1),U.MaterialProperty.MP_SPECULAR)
 mat.set_editor_property('two_sided',True)
 if wake:
  mat.set_editor_property('blend_mode',U.BlendMode.BLEND_TRANSLUCENT)
  mat.set_editor_property('translucency_lighting_mode',U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
  amount=node(U.MaterialExpressionScalarParameter,parameter_name='WakeAmount',default_value=0.)
  op=custom('return A*S*(.70+.20*sin(T*3.4+P.x*.019+P.y*.023));',{'A':(vc,'A'),'S':(amount,''),'T':(t,''),'P':(p,'')},U.CustomMaterialOutputType.CMOT_FLOAT1)
  prop(op,U.MaterialProperty.MP_OPACITY)
  prop(custom('return float3(0,0,sin(T*1.8+P.x*.008+P.y*.006)*.7);',{'T':(t,''),'P':(p,'')}),U.MaterialProperty.MP_WORLD_POSITION_OFFSET)
 else:
  fill=node(U.MaterialExpressionScalarParameter,parameter_name='SailFill',default_value=1.)
  direction=node(U.MaterialExpressionVectorParameter,parameter_name='FlutterDirection',default_value=U.LinearColor(0,1,0,0))
  flutter=custom('float wave=sin(T*2.5+P.z*.023)+.28*sin(T*5.1+P.x*.018);return D*A*(1.0+S*2.0)*wave;',{'A':(vc,'A'),'S':(fill,''),'D':(direction,''),'T':(t,''),'P':(p,'')})
  prop(flutter,U.MaterialProperty.MP_WORLD_POSITION_OFFSET)
 M.recompile_material(mat);E.save_loaded_asset(mat);return mat
