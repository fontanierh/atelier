"""Aerial perspective shared by every lit land material, so land, trees, the town and the sea fade into one haze.

The sea already hazes this way (sea_look.py): with pixel depth D its colour goes toward FAR_COLOUR, a little darker
than the painted dome's horizon, by 1 - exp(-D / HAZE_CM) (.1 at 1 km, .36 at 4 km). The land used to lerp its
albedo toward a pale grey-white (.64, .68, .76) by up to a half from 70 m to 2.3 km. Lit by the sun, that albedo came out
nearly white, and the forests and the city seen from afar looked frosted. Now a lit material gives up the same share
of its base colour (and of its own glow) as the sea, and that share is replaced by the haze colour as emission. Under
the fixed exposure, the emission is seen as the colour itself, whatever the lighting. Distant land then meets the sea
and the sky in the same blue, and nothing near the camera changes (START_CM).

    import atmosphere
    base, glow = atmosphere.apply(m, base_node, glow_node)   # Custom nodes: connect them to base colour / emissive
"""
import unreal
import sea_look as S

HAZE_CM = S.HAZE_CM
COLOUR = S.FAR_COLOUR
START_CM = 3000.0      # the first 30 m are untouched

SHARE = f'saturate(1-exp(-max(D-{S.num(START_CM)},0)/{S.num(HAZE_CM)}))'
MEL = unreal.MaterialEditingLibrary


def code_base(expr='B'):
    """HLSL return statement: the base colour expr with the haze's share taken out (needs input D)."""
    return f'return ({expr})*(1-{SHARE});'


def code_glow(expr='E'):
    """HLSL return statement: the emissive expr hazed, plus the haze colour (needs input D)."""
    return f'float h={SHARE}; return ({expr})*(1-h)+{S.f3(COLOUR)}*h;'


def _custom(m, code, inputs, x, y):
    n = MEL.create_material_expression(m, unreal.MaterialExpressionCustom, x, y)
    n.set_editor_property('code', code)
    n.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    args = []
    for name, _, _ in inputs:
        a = unreal.CustomInput(); a.set_editor_property('input_name', name); args.append(a)
    n.set_editor_property('inputs', args)
    for name, src, out in inputs:
        assert MEL.connect_material_expressions(src, out, n, name), name
    return n


def apply(m, base, glow=None, base_out='', glow_out='', x=400, y=0):
    """Nodes for base colour and emissive with the haze applied; glow None: the material had no emission."""
    depth = MEL.create_material_expression(m, unreal.MaterialExpressionPixelDepth, x - 200, y + 300)
    b = _custom(m, code_base(), [('B', base, base_out), ('D', depth, '')], x, y)
    if glow is None:
        g = _custom(m, f'float h={SHARE}; return {S.f3(COLOUR)}*h;', [('D', depth, '')], x, y + 200)
    else:
        g = _custom(m, code_glow(), [('E', glow, glow_out), ('D', depth, '')], x, y + 200)
    return b, g


def glow(m, x=400, y=200):
    """The emissive node for a material whose base colour code already takes out the haze's share (SHARE)."""
    depth = MEL.create_material_expression(m, unreal.MaterialExpressionPixelDepth, x - 200, y + 100)
    return _custom(m, f'float h={SHARE}; return {S.f3(COLOUR)}*h;', [('D', depth, '')], x, y)
