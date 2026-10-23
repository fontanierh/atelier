"""Immutable original Treehouse geometry/props/canopies versus complete atomic exports.

Normal guarded Blender only. Native cook/query/five-UV receiving remains separate.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME),str(GAME/'world'),str(GAME/'world/regions'),str(Path(__file__).resolve().parent)]
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from forest_lake_equivalence import load,snapshot,compare,pixels  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
import export_region_piece  # noqa: E402


def forget(names):
    import treehouse
    for name in names:
        sys.modules.pop('treehouse.'+name,None)
        if hasattr(treehouse,name):delattr(treehouse,name)


def export_all(out,region,parents):
    for parent in parents:
        folder=out/'planned_exports'/region/parent
        value=validate(folder)
        for row in value['pieces']:
            export_region_piece.main(['--input',str(folder/row['payload']),
                '--output',str(out/('exports/world.'+region+'.export')/row['name'])])


def graph_assembly(recipe,kind,out):
    steps=getattr(recipe,kind+'_steps')(SimpleNamespace(out=out))
    region='treehouse_'+('surfaces' if kind=='surface' else 'trees' if kind=='canopy' else 'props')
    next(step for step in steps if step.name=='world.'+region+'.assembled').commands[0].fn(SimpleNamespace(out=out),sys.stdout)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor',type=Path,required=True);parser.add_argument('--donor-head',required=True)
    parser.add_argument('--baseline',default='283329c07');parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--attestation',type=Path,required=True);parser.add_argument('--attestation-sha256',required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    repo=GAME.parents[1]
    if sha(args.attestation)!=args.attestation_sha256:raise ValueError('Host attestation bytes changed')
    attestation=json.loads(args.attestation.read_text())
    if (attestation.get('schema')!=1 or attestation.get('repo')!=str(repo) or attestation.get('donor')!=str(args.donor)
            or attestation.get('donor_head')!=args.donor_head or attestation.get('baseline_revision')!=args.baseline):
        raise ValueError('Foreign host authority manifest')
    head=attestation['source_head'];source_before=attestation['current_source'];donor_before=attestation['donor_inputs']
    archive_before=attestation['archive_files'];archive=Path(attestation['archive']);baseline=attestation['baseline_files']
    closure=[Path(path) for path in source_before];inputs=[Path(path) for path in donor_before]
    if snapshot(closure)!=source_before or snapshot(inputs)!=donor_before or snapshot([Path(path) for path in archive_before])!=archive_before:
        raise ValueError('Prepared proof inputs changed before guarded execution')
    if os.path.lexists(args.output):raise ValueError('Treehouse proof requires a fresh output')
    real_directory(args.output.parent);args.output.mkdir()
    from treehouse_atomic_build import TREES,PROPS,SURFACES
    donor=args.donor/'build/yorimichi'
    old=args.output/'old';new=args.output/'new'
    for root in (old,new):
        root.mkdir()
        for path in inputs:
            target=root/path.relative_to(donor);target.parent.mkdir(parents=True,exist_ok=True);copy_file(path,target)
    import asset_mesh as A
    import treehouse
    yori.OUT=old;yori.TEXTURES=old/'textures';A.TEX=str(yori.TEXTURES);A.MATS.clear();A.LEAF_CROPS.clear()
    forget(('trees','layout','tmesh','build','props'))
    # The immutable trees script calls main() itself, exactly once on load.
    load('immutable_treehouse_trees',archive/'trees.py')
    props=load('immutable_treehouse_props',archive/'props.py');props.OUT=old/'treehouse/props';props.main()
    load('treehouse.layout',archive/'layout.py');load('treehouse.tmesh',archive/'tmesh.py')
    build=load('immutable_treehouse_build',archive/'build.py');build.main()
    # Original production already partitions Dressing. Retain an additional
    # whole authoring-object control to compare its complete five UV values.
    obj=bpy.data.objects.get('TH_Dressing')
    if obj is None:raise ValueError('Immutable whole Dressing diagnostic missing')
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    from atelier.blender.fbx import export_fbx
    control=old/'treehouse/assets/TH_Dressing_whole-control.fbx'
    export_fbx(filepath=str(control),use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Y',axis_up='Z',object_types={'MESH'},mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)
    forget(('trees','layout','tmesh','build','props'))
    yori.OUT=new;yori.TEXTURES=new/'textures';A.TEX=str(yori.TEXTURES)
    from treehouse import plan_tree,plan_prop,canopy_data,plan_surface,assemble_atomic
    import treehouse_atomic_build as recipe
    parameters=GAME/'assets/treehouse/export-parameters'
    results={};images=[]
    records=[]
    for name in TREES:
        record=new/'treehouse-data/canopy/records'/(name+'.json');records.append(record)
        plan_tree.main(['--parameters',str(parameters/(name+'.json')),'--record',str(record),
                       '--output',str(new/'planned_exports/treehouse_trees'/name)])
    canopy_data.dimensions(records,new/'treehouse-data/canopy/trees.json')
    canopy_data.main(['--recolour',str(new/'treehouse-data/canopy/recoloured')])
    export_all(new,'treehouse_trees',TREES);graph_assembly(recipe,'canopy',new)
    assemble_atomic.library(new,'trees',TREES)
    for name in PROPS:
        source=GAME/'assets/treehouse/props'/name.removeprefix('TH_P_')/(name.removeprefix('TH_P_')+'.glb')
        plan_prop.main(['--parameters',str(parameters/(name+'.json')),'--source',str(source),
            '--data',str(new/'treehouse-data/props'/name),'--output',str(new/'planned_exports/treehouse_props'/name)])
    export_all(new,'treehouse_props',PROPS);graph_assembly(recipe,'prop',new)
    assemble_atomic.library(new,'props',PROPS)
    forget(('layout','build','tmesh'))
    from treehouse import geometry_data
    geometry_data.main(['--out',str(new/'treehouse-data/surfaces')])
    for name in SURFACES:
        plan_surface.main(['--source',str(new/'treehouse-data/surfaces'/name),
            '--output',str(new/'planned_exports/treehouse_surfaces'/name)])
    export_all(new,'treehouse_surfaces',SURFACES);graph_assembly(recipe,'surface',new)
    assemble_atomic.surfaces(new)
    for name in TREES+PROPS:
        folder='trees' if name in TREES else 'props'
        current=new/'treehouse'/folder/(name+'.fbx')
        results[name]=compare(old/'treehouse'/folder/(name+'.fbx'),[current])
    manifest=json.loads((new/'treehouse/surfaces.json').read_text())
    for parent in SURFACES:
        children=[new/'treehouse'/manifest['assets'][name]['fbx'] for name in manifest['parents'][parent]]
        source=control if parent=='TH_Dressing' else old/'treehouse/assets'/(parent+'.fbx')
        results[parent]=compare(source,children)
    for name in PROPS:
        filename=name+'.png';left=old/'treehouse/props'/filename;right=new/'treehouse/props'/filename
        ls,lp=pixels(left);rs,rp=pixels(right)
        if ls!=rs or not np.array_equal(lp,rp):raise ValueError('Fitted prop texture pixels differ: '+name)
        images.append(dict(name=filename,control=sha(left),current=sha(right),equal=True))
    for colour in ('crimson','amber'):
        filename='T_leaf_'+colour+'.png';left=old/'treehouse/trees'/filename;right=new/'treehouse/trees'/filename
        ls,lp=pixels(left);rs,rp=pixels(right)
        if ls!=rs or not np.array_equal(lp,rp):raise ValueError('Canopy recolour pixels differ')
        images.append(dict(name=filename,control=sha(left),current=sha(right),equal=True))
    if json.loads((old/'treehouse/trees/trees.json').read_text())!=json.loads((new/'treehouse/trees/trees.json').read_text()):
        raise ValueError('Canopy dimensions differ')
    old_props=json.loads((old/'treehouse/props/props.json').read_text());new_props=json.loads((new/'treehouse/props/props.json').read_text())
    for row in new_props.values():row.pop('authored_hulls')
    if old_props!=new_props:raise ValueError('Complete prop placement/material metadata differs')
    if json.loads((old/'treehouse/runtime.json').read_text())!=json.loads((new/'treehouse/runtime.json').read_text()):
        raise ValueError('Treehouse placements/rooms/lights differ')
    # A real selected source-parameter change reconstructs and exports one prop;
    # untouched canonical exports must retain exact bytes and stat identities.
    unchanged=[path for path in (new/'exports').rglob('*.fbx')]
    before=snapshot(unchanged);edited=args.output/'one-edit';edited.mkdir()
    name='TH_P_planter';value=json.loads((parameters/(name+'.json')).read_text());value['turn']+=1
    parameter=edited/(name+'.json');atomic_json(parameter,value)
    plan_prop.main(['--parameters',str(parameter),'--source',str(GAME/'assets/treehouse/props/planter/planter.glb'),
        '--data',str(edited/'data'),'--output',str(edited/'plan')])
    row=validate(edited/'plan')['pieces'][0]
    export_region_piece.main(['--input',str(edited/'plan'/row['payload']),'--output',str(edited/'export')])
    if sha(edited/'export'/(name+'.fbx'))==sha(new/'exports/world.treehouse_props.export'/name/(name+'.fbx')):
        raise ValueError('Actual selected prop edit did not alter its export')
    if snapshot(unchanged)!=before:raise ValueError('A selected prop edit changed unrelated export bytes/stat identities')
    if snapshot(inputs)!=donor_before:raise ValueError('Donor input bytes/stat identities changed')
    if snapshot(closure)!=source_before or snapshot([Path(path) for path in archive_before])!=archive_before:
        raise ValueError('Source/archive bytes/stat identities changed')
    if sha(args.attestation)!=args.attestation_sha256:raise ValueError('Host authority changed during native work')
    atomic_json(args.output/'result.json',dict(schema=1,complete=True,source_head=head,baseline_revision=args.baseline,
        baseline_files=baseline,donor_head=args.donor_head,donor_inputs=donor_before,current_source=source_before,
        host_attestation_sha256=args.attestation_sha256,host_attestation=str(args.attestation),exports=results,images=images,runtime_equal=True,prop_metadata_equal=True,canopy_dimensions_equal=True,
        selected_prop_edit=dict(name=name,unrelated_exports=len(unchanged)-1,unchanged_canonical_exports=len(unchanged),unchanged=True),
        scope='complete exported corner/channel/frame/hull conservation and runtime data; native receiving separate'))
    print('TREEHOUSE FULL ATOMIC EQUIVALENCE COMPLETE',len(results),len(images),flush=True)


if __name__=='__main__':main()
