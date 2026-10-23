"""Project one original prop constructor and its consumed palette before Blender work."""
import argparse
import ast
import copy
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from material_specs import MATERIALS  # noqa: E402

SOURCE=Path(__file__).with_name('build_assets.py')
BUILDERS=dict(Leaf=('leaf_mesh',()),Litter=('litter',()),
    Rock_A=('rock',(36,(1.8,1.4,1.0))),Rock_B=('rock',(37,(1.1,.9,.7))),Rock_C=('rock',(38,(2.6,2.0,1.3))),
    Pole=('pole',()),Pole_Lamp=('pole',(True,)),Guardrail=('guardrail',()),Lantern=('lantern',()),
    Torii=('torii',()),SkyDome=('sky_dome',()),BirdBody=('bird_body',()),BirdWingL=('bird_wing',(1,)),BirdWingR=('bird_wing',(-1,)))


def bird_function(tree,wing):
    """Preserve the finite original body/wing statements without constructing siblings."""
    original=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='bird_parts')
    nodes=copy.deepcopy(original.body)
    first=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='B' for t in n.targets))
    body=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='body' for t in n.targets))
    loop=next(n for n in nodes if isinstance(n,ast.For))
    if (not isinstance(nodes[-1],ast.Return) or ast.unparse(nodes[-1].value)!='[body] + wings'
            or ast.literal_eval(loop.iter)!=((1,'BirdWingL'),(-1,'BirdWingR'))
            or ast.unparse(loop.target)!='(s, nm)' or ast.unparse(loop.body[-1])!='wings.append(W.build())'
            or ast.unparse(nodes[body].value)!='B.build()'):
        raise ValueError('Original independent bird boundary changed; update its equivalence proof')
    if wing:
        args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='name'),ast.arg(arg='s')],kwonlyargs=[],kw_defaults=[],defaults=[])
        statements=[*nodes[:first],ast.Assign(targets=[ast.Name(id='nm',ctx=ast.Store())],value=ast.Name(id='name',ctx=ast.Load())),
                    *loop.body[:-1],ast.Return(value=loop.body[-1].value.args[0])]
        return ast.fix_missing_locations(ast.FunctionDef(name='bird_wing',args=args,body=statements,decorator_list=[]))
    args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='name')],kwonlyargs=[],kw_defaults=[],defaults=[])
    return ast.fix_missing_locations(ast.FunctionDef(name='bird_body',args=args,body=[*nodes[:body+1],ast.Return(value=ast.Name(id='body',ctx=ast.Load()))],decorator_list=[]))


def project(text):
    """@cc [owner:fontanierh,label:correctness;performance] selected-world-prop-source
    Each source packet MUST contain only its selected original constructor, complete primitive
    dependencies and consumed palette data. Bird body/wing extraction MUST preserve the exact
    original geometry statements and shoulder frame without constructing sibling objects.
    Unrelated constructor/palette edits MUST leave unchanged selected packets byte-identical.
    """
    tree=ast.parse(text);functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    values={}
    for name,(builder,args) in BUILDERS.items():
        function=bird_function(tree,builder=='bird_wing') if builder.startswith('bird_') else functions[builder]
        keys=sorted({n.slice.value for n in ast.walk(function) if isinstance(n,ast.Subscript)
                     and isinstance(n.value,ast.Name) and n.value.id=='MATS' and isinstance(n.slice,ast.Constant)})
        # These imports expose the same original primitive implementation, with no exporter execution.
        program='import math, random\nimport bpy, bmesh\nfrom mathutils import Vector\nfrom asset_mesh import Mesh, MATS\n'+ast.unparse(function)+'\n'
        values[name]=dict(schema=1,asset=name,builder=builder,args=args,program=program,
                          materials={key:MATERIALS[key] for key in keys})
    return values


def publish(root):
    values=project(SOURCE.read_text());root=real_directory(root,create=True)
    expected={key+'.json' for key in values}
    if any(path.is_symlink() or not path.is_file() or path.name not in expected for path in root.iterdir()):
        raise ValueError('Foreign selected world prop source member')
    for key,value in values.items():atomic_json(root/(key+'.json'),value)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    publish(parser.parse_args().output)
