"""Finite original Bike constructor decomposition; no mesh export or sibling execution."""
import ast
import copy
import symtable

STEERING=('BK_Steer_Core','BK_Steer_BasketShell','BK_Steer_BasketRim','BK_Steer_BasketFoot')
BUILDERS={
    'BK_Frame':'frame', 'BK_Steer_Core':'steer_core',
    'BK_Steer_BasketShell':'steer_shell', 'BK_Steer_BasketRim':'steer_rim',
    'BK_Steer_BasketFoot':'steer_foot', 'BK_WheelFront':'wheel_front',
    'BK_WheelRear':'wheel_rear','BK_Crank':'crank','BK_Pedal':'pedal',
    'BK_Kickstand':'kickstand','BK_RackBoard':'rack_board'}


def _names(target):
    if isinstance(target,ast.Name):return {target.id}
    if isinstance(target,(ast.Tuple,ast.List)):return set().union(*(_names(item) for item in target.elts))
    return set()


def _globals(node):
    source=ast.unparse(ast.fix_missing_locations(node))
    table=symtable.symtable(source,'selected-bike','exec')
    def collect(scope):
        return {s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced()} | set().union(*(collect(child) for child in scope.get_children()))
    return collect(table)


def programs(text):
    """@cc [owner:fontanierh,label:correctness;performance] semantic-bike-steering-constructors
    The steering source MUST preserve the exact original core, basket shell, rim and
    foot statements and steering-frame transform, without constructing another child's
    geometry. Independent constructor projections MUST contain only transitive consumed
    code/constants, and the layout producer MUST remain separate from render exports.
    """
    tree=ast.parse(text);functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    steer=functions['steer'];basket=functions['basket']
    # Finite source boundaries are structural, not cumulative counts from a new mesh.
    def assignment(node,name):
        return isinstance(node,ast.Assign) and any(name in _names(t) for t in node.targets)
    shell=next(i for i,n in enumerate(basket.body) if assignment(n,'rings'))
    rim=next(i for i,n in enumerate(basket.body) if assignment(n,'rim'))
    foot=next(i for i,n in enumerate(basket.body) if assignment(n,'foot'))
    assert shell<rim<foot
    prefix=basket.body[1:shell]
    assert [n.name for n in prefix if isinstance(n,ast.FunctionDef)]==['footprint','over']
    suffix=steer.body[-3:]
    assert ast.unparse(suffix[-1])=='return m' and ast.unparse(suffix[-2])=='m.transform(to_local)'
    assert ast.unparse(suffix[0])=='to_local = (Matrix.Translation(HEAD_BOTTOM) @ F.to_4x4()).inverted()'
    synthetic=[]
    core=copy.deepcopy(steer);core.name='steer_core'
    core.body=[node for node in core.body if not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
        and isinstance(node.value.func,ast.Name) and node.value.func.id=='basket')]
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='basket' for n in ast.walk(core))
    synthetic.append(core)
    for name,body in [('steer_shell',basket.body[shell:rim]),('steer_rim',basket.body[rim:foot]),('steer_foot',basket.body[foot:])]:
        pre=copy.deepcopy(prefix)
        if name!='steer_shell':
            # These calls already specify all three arguments; their defaults/over()
            # and shell subdivision constants are not consumed by rim or foot.
            pre=[node for node in pre if not (isinstance(node,ast.FunctionDef) and node.name=='over')
                 and not assignment(node,'rows') and not assignment(node,'seg')]
            fp=next(node for node in pre if isinstance(node,ast.FunctionDef));fp.args.defaults=[]
            assert all(len(n.args)==3 and not n.keywords for statement in body for n in ast.walk(statement)
                       if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='footprint')
        fn=ast.FunctionDef(name=name,args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
            body=ast.parse("m = Mesh('BK_Steer')\nF = frame_along(AXIS)").body+pre+copy.deepcopy(body)+copy.deepcopy(suffix),decorator_list=[])
        synthetic.append(fn)
    for name,asset,half in [('wheel_front','BK_WheelFront',.048),('wheel_rear','BK_WheelRear',.050)]:
        synthetic.append(ast.parse(f'def {name}():\n    return wheel({asset!r}, {half!r})').body[0])
    statements=tree.body+synthetic;nodes={}
    for node in statements:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):nodes[node.name]=node
        elif isinstance(node,ast.Assign):
            for target in node.targets:
                for name in _names(target):nodes[name]=node
    roster=set(BUILDERS.values())
    result={}
    for asset,builder in [*BUILDERS.items(),('__layout__','layout')]:
        selected=set();pending=[builder]+(['material'] if builder!='layout' else [])
        while pending:
            name=pending.pop()
            if name in selected or name not in nodes:continue
            selected.add(name);pending.extend(_globals(nodes[name]))
        if selected&roster not in ({builder},set()):raise ValueError('Bike source contains sibling constructor')
        chosen=[];seen=set()
        for node in statements:
            if any(nodes[name] is node for name in selected) and id(node) not in seen:
                seen.add(id(node));chosen.append(node)
        if {'OUT','ROOT','parts','export','main','steer','basket'}&selected:raise ValueError('Bike source includes ambient or whole steering entry')
        result[asset]='import math\nimport bpy, bmesh\nfrom mathutils import Matrix, Vector\nfrom mathutils.geometry import tessellate_polygon\n'+'\n\n'.join(ast.unparse(ast.fix_missing_locations(n)) for n in chosen)+'\n'
    return result
