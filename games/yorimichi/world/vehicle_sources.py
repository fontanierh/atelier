"""Publish selected original vehicle constructor code/data before bounded exports."""
import argparse
import ast
import json
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402

FAMILIES={
    'sailboat':dict(material='SailboatPalette',builders={
        'SB_Hull':'hull','SB_Sail':'sail','SB_Boom':'boom','SB_Rudder':'rudder','SB_Wake':'wake'}),
    'kei':dict(material='KeiPalette',builders={
        'SM_Kei_Pickup':'pickup','SM_Kei_Wagon':'wagon','SM_Kei_Retro':'retro','SM_Kei_Microvan':'microvan'}),
    'kart':dict(material='KartPalette',builders={
        'SM_Kart_Body':'kart','SM_Kart_Seat':'seat','SM_Kart_Wheel':'wheel','SM_Kart_SteeringWheel':'steering_wheel'}),
}
SOURCE=yori.ASSETS/'vehicles'


def cockpit_layout():
    path=SOURCE/'kart/cockpit.py'
    spec=importlib.util.spec_from_file_location('vehicle_original_cockpit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.load()


def projection(text,family,*,layout=None):
    """@cc [owner:fontanierh,label:correctness;performance] selected-vehicle-constructor-source
    Each logical vehicle source MUST contain its unchanged selected constructor, complete
    transitive primitive/constant dependencies and consumed construction data only.
    Compiling a source MUST NOT execute the monolithic entry or construct a sibling part.
    Unrelated part/constant edits MUST stop at unchanged selected products before export.
    """
    if family not in FAMILIES:raise ValueError('Unknown independently declared vehicle family')
    if family=='kart':layout=cockpit_layout() if layout is None else layout
    tree=ast.parse(text);nodes={};order=[]
    def bound(target):
        if isinstance(target,ast.Name):return {target.id}
        if isinstance(target,(ast.Tuple,ast.List)):return set().union(*(bound(value) for value in target.elts))
        return set()
    # The finite original LAYOUT tuple reads are independent immutable dictionary
    # lookups: keep only a selected binding, not its unused neighbour's input.
    statements=[]
    for node in tree.body:
        if (family=='kart' and isinstance(node,ast.Assign) and len(node.targets)==1
                and isinstance(node.targets[0],ast.Tuple) and isinstance(node.value,ast.Tuple)
                and len(node.targets[0].elts)==len(node.value.elts)
                and any(isinstance(value,ast.Name) and value.id=='LAYOUT' for value in ast.walk(node.value))):
            statements.extend(ast.Assign(targets=[target],value=value) for target,value in zip(node.targets[0].elts,node.value.elts))
        else:statements.append(node)
    for node in statements:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            nodes[node.name]=node;order.append(node)
        elif isinstance(node,ast.Assign):
            names=set().union(*(bound(target) for target in node.targets))
            for name in names:nodes[name]=node
            order.append(node)
    result={};roster=set(FAMILIES[family]['builders'].values())
    for key,builder in FAMILIES[family]['builders'].items():
        pending=[builder];selected=set()
        if family=='kart':
            pending.extend(('geometry_hash','winding_selftest'))
            if key=='SM_Kart_Body':pending.append('finish_paint')
            else:pending.append('signed_volume')
        while pending:
            name=pending.pop()
            if name in selected or name not in nodes:continue
            selected.add(name)
            if family=='kart' and name=='LAYOUT':continue
            pending.extend(n.id for n in ast.walk(nodes[name]) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load))
        if selected & roster!={builder}:raise ValueError('Vehicle constructor closure includes a sibling')
        chosen=[];seen=set()
        for node in order:
            if family=='kart' and isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='LAYOUT' for target in node.targets):continue
            if any(nodes[name] is node for name in selected) and id(node) not in seen:
                seen.add(id(node));chosen.append(node)
        if any(isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id in ('OUT','ROOT') for n in ast.walk(node)) for node in chosen):
            raise ValueError('Selected vehicle source has ambient output dependencies')
        prefix='import math\nfrom mathutils import Matrix, Vector\nfrom village import mesh as v\n'
        if family=='kart':prefix+='import hashlib, json\nLAYOUT=__vehicle_data["layout"]\n'
        program=prefix+'\n\n'.join(ast.unparse(ast.fix_missing_locations(node)) for node in chosen)+'\n'
        result[key]=dict(schema=1,family=family,asset=key,builder=builder,program=program,
                         material=FAMILIES[family]['material'])
        if family=='kart':
            keys={node.slice.value for statement in chosen for node in ast.walk(statement) if isinstance(node,ast.Subscript)
                  and isinstance(node.value,ast.Name) and node.value.id=='LAYOUT' and isinstance(node.slice,ast.Constant)
                  and isinstance(node.slice.value,str)}
            result[key]['data']=dict(layout={name:layout[name] for name in sorted(keys)})
    return result


def publish(family,output,*,layout_output=None):
    layout=cockpit_layout() if family=='kart' else None
    if family=='kart' and layout_output is None:raise ValueError('Kart requires its independently owned full cockpit product')
    values=projection((SOURCE/family/'build.py').read_text(),family,layout=layout)
    output=real_directory(output,create=True);expected={key+'.json' for key in values}
    if any(path.is_symlink() or not path.is_file() or path.name not in expected for path in output.iterdir()):
        raise ValueError('Foreign vehicle source-data member')
    for key,value in values.items():atomic_json(output/(key+'.json'),value)
    if family=='kart':atomic_json(layout_output,layout)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--family',choices=FAMILIES,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--layout-output',type=Path)
    args=parser.parse_args();publish(args.family,args.output,layout_output=args.layout_output)
