"""The shared Sword Camp/Hidamari haze, from the pinned V1 donor baseline 7eec0f98dd.

atmosphere.py sha256 b59478df43df83b8c7386e7ff7c097f32faf647716fdacb804f3cf0c99336ebf (lines 17-68),
sea_look.py sha256 ffae53cded2bb461534c88c100bc75d3f93ec3bf396eb303e5d4ec3ad4dbb4fa (38-45, 50, 67-69).
The constants, HLSL and graph operations are unchanged. Each consuming record pins a copy of this one implementation
beside its entry builder; it receives the editor API explicitly and has no import-time editor state.
"""


def num(value):
    return repr(float(value))


def f3(colour):
    return 'float3(%s)' % ','.join(num(value) for value in colour)


HORIZON = (0.126, 0.311, 0.720)
HAZE_CM = 900000.0
FAR = 0.74
FAR_COLOUR = tuple(round(value * FAR, 4) for value in HORIZON)
START_CM = 3000.0
COLOUR = FAR_COLOUR
SHARE = f'saturate(1-exp(-max(D-{num(START_CM)},0)/{num(HAZE_CM)}))'


def code_base(expr='B'):
    return f'return ({expr})*(1-{SHARE});'


def code_glow(expr='E'):
    return f'float h={SHARE}; return ({expr})*(1-h)+{f3(COLOUR)}*h;'


def custom_inputs(unreal, names):
    inputs = []
    for name in names:
        arg = unreal.CustomInput()
        arg.set_editor_property('input_name', name)
        inputs.append(arg)
    return inputs


def _custom(unreal, material, code, inputs, x, y):
    mel = unreal.MaterialEditingLibrary
    node = mel.create_material_expression(material, unreal.MaterialExpressionCustom, x, y)
    node.set_editor_property('code', code)
    node.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    node.set_editor_property('inputs', custom_inputs(unreal, [name for name, _, _ in inputs]))
    for name, source, output in inputs:
        assert mel.connect_material_expressions(source, output, node, name), name
    return node


def apply(unreal, material, base, glow=None, base_out='', glow_out='', x=400, y=0):
    """@cc [owner:fontanierh,label:correctness] shared-master-haze-donor
    The base attenuation and emissive haze use the pinned donor constants and graph order. Both regions pass their
    own material and editor API; this helper imports and saves no assets and retains no region state.
    """
    depth = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionPixelDepth, x - 200, y + 300)
    base = _custom(unreal, material, code_base(), [('B', base, base_out), ('D', depth, '')], x, y)
    if glow is None:
        glow = _custom(unreal, material, f'float h={SHARE}; return {f3(COLOUR)}*h;', [('D', depth, '')], x, y + 200)
    else:
        glow = _custom(unreal, material, code_glow(), [('E', glow, glow_out), ('D', depth, '')], x, y + 200)
    return base, glow


def glow(unreal, material, x=400, y=200):
    """Donor atmosphere.glow: emission for base-colour code that already takes out the haze share."""
    depth = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionPixelDepth, x - 200, y + 100)
    return _custom(unreal, material, f'float h={SHARE}; return {f3(COLOUR)}*h;', [('D', depth, '')], x, y)
