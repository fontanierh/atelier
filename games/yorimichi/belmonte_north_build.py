"""Independent northern terrain construction and explicit valley query products."""
import importlib.util
import json
from pathlib import Path

from atelier.build import Product,Python,Step
from atelier.build_inputs import local_imports

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world'
REGION=WORLD/'regions/belmonte'
LIBRARY=GAME/'assets/belmonte'
OWNERS=('SM_BM_NorthApron','SM_BM_NorthCountry')


def code(script):
    return local_imports(script,(WORLD,WORLD/'regions'))


def query_steps(ctx):
    entries=[row for row in json.loads((LIBRARY/'source.json').read_text())['meshes']
             if row['name'].startswith('SM_BM_BT_Terrain_')]
    if len(entries)!=56 or len({row['name'] for row in entries})!=56:raise ValueError('Incomplete valley source inventory')
    palette_script=REGION/'valley_palette.py';query=REGION/'valley_query.py'
    palette=ctx.out/'belmonte-query-data/palette.json'
    result=[Step('world.belmonte.valley_palette',[Python(palette_script,(
        '--source',str(LIBRARY/'source.json'),'--output',str(palette)))],
        inputs=[*code(palette_script),LIBRARY/'source.json'],
        products=[Product('belmonte.valley_palette',(palette,))],cache=True,
        about='effective terrain colours without unrelated world metadata')]
    for mode in ('natural','colours','final'):
        owner='BelmonteValleyColours' if mode=='colours' else 'BelmonteValley'
        target=ctx.out/'belmonte-query-data'/(owner+('-final.npz' if mode=='final' else '-natural.npz'))
        args=['--mode',mode,'--library',str(LIBRARY),'--output',str(target)]
        reads=[];inputs=code(query)
        if mode=='colours':
            args.extend(('--palette',str(palette)));reads.append('belmonte.valley_palette')
            inputs.extend(LIBRARY/row['path'] for row in entries)
        else:
            for row in entries:
                key=row['name']
                if mode=='natural':
                    args.extend(('--definition',str(ctx.out/'belmonte-model-definitions'/(key+'.json'))))
                    reads.append('belmonte.model_definition.'+key);inputs.append(LIBRARY/row['path'])
                else:
                    args.extend(('--surface',str(ctx.out/'belmonte-source-data'/(key+'.surface'))))
                    reads.append('belmonte.final_surface.'+key)
        result.append(Step('world.belmonte.valley_'+mode,[Python(query,tuple(args))],
            inputs=inputs,reads=reads,products=[Product('belmonte.valley_'+mode,(target,))],
            cache=True,heavy=True,about='complete '+mode+' query data before any rendered mesh export'))
    return result


def steps(ctx):
    """@cc [owner:fontanierh,label:correctness;performance] independent-northern-terrain-stages
    Apron and country MUST construct independently, consume only their own
    construction data and explicit per-owner seam projections, and preserve
    the original natural-stitch/carve/final-stitch/colour sequence. Valley
    natural geometry and effective colour arrays MUST be separate inputs.
    Whole query products MUST remain data, while every rendered child has its
    own bounded cached export; no rendered sibling is a construction input.
    """
    pipeline=REGION/'north_pipeline.py';root=ctx.out/'belmonte-north-data'
    line=GAME/'assets/vehicles/belmonte-train/line.json'
    context_script=REGION/'north_context.py';context=root/'context.json'
    result=[Step('world.belmonte.north_context',[Python(context_script,(
        '--world',str(ctx.out/'world.json'),'--heightmap',str(ctx.out/'heightmap.npy'),
        '--farhills',str(ctx.out/'farhills.npy'),'--output',str(context)))],
        inputs=[*code(context_script),ctx.out/'world.json',ctx.out/'heightmap.npy',ctx.out/'farhills.npy'],
        needs=['world.layout'],products=[Product('belmonte.north_context',(context,))],cache=True,
        about='only the island arrays and approach-road anchor used by northern terrain')]
    for owner,script_name in zip(OWNERS,('north_apron.py','north_country.py')):
        script=REGION/script_name
        arguments=['--output',str(root/'raw'/(owner+'.npz')),'--context',str(context),
                   '--heightmap',str(ctx.out/'heightmap.npy'),'--farhills',str(ctx.out/'farhills.npy')]
        reads=['belmonte.north_context'];products=[Product('belmonte.north.raw.'+owner,(root/'raw'/(owner+'.npz'),))]
        if owner==OWNERS[0]:
            arguments.extend(('--valley',str(ctx.out/'belmonte-query-data/BelmonteValley-natural.npz'),
                              '--report',str(root/'seam-report.json')))
            reads.append('belmonte.valley_natural');products.append(Product('belmonte.north_seam_report',(root/'seam-report.json',)))
        result.append(Step('world.belmonte.north.raw.'+owner,[Python(script,tuple(arguments))],
            inputs=[*code(script),ctx.out/'heightmap.npy',ctx.out/'farhills.npy',line],
            reads=reads,products=products,cache=True,heavy=True,
            about='construct only '+owner+' before any mesh export'))
    for stage in ('natural','final'):
        incoming='raw' if stage=='natural' else 'carve'
        args=['--mode','boundary','--output',str(root/(stage+'-seams'))]
        for owner in OWNERS:args.extend(('--input',str(root/incoming/(owner+'.npz'))))
        result.append(Step('world.belmonte.north.'+stage+'_boundaries',[Python(pipeline,tuple(args))],
            inputs=[*code(pipeline),line],reads=['belmonte.north.'+incoming+'.'+owner for owner in OWNERS],
            products=[Product('belmonte.north.'+stage+'_seam.'+owner,(root/(stage+'-seams')/(owner+'.json'),)) for owner in OWNERS],
            cache=True,heavy=True,about='only boundary knots consumed by each independent terrain'))
        for owner in OWNERS:
            target=(root/'natural'/(owner+'.npz') if stage=='natural' else ctx.out/'belmonte-source-data'/(owner+'.surface'))
            args=['--mode',stage,'--owner',owner,'--input',str(root/incoming/(owner+'.npz')),
                  '--seam',str(root/(stage+'-seams')/(owner+'.json')),'--output',str(target)]
            reads=['belmonte.north.'+incoming+'.'+owner,'belmonte.north.'+stage+'_seam.'+owner]
            if stage=='natural':
                query=ctx.out/'belmonte-natural-source-data'/(owner+'.surface')
                args.extend(('--query',str(query)))
                products=[Product('belmonte.north.natural.'+owner,(target,)),Product('belmonte.natural_surface.'+owner,(query,))]
            else:
                args.extend(('--palette',str(ctx.out/'belmonte-query-data/BelmonteValleyColours-natural.npz')))
                reads.append('belmonte.valley_colours');products=[Product('belmonte.final_surface.'+owner,(target,))]
            result.append(Step('world.belmonte.north.'+stage+'.'+owner,[Python(pipeline,tuple(args))],
                inputs=[*code(pipeline),line],reads=reads,products=products,cache=True,heavy=True,
                about='independent '+stage+' source '+owner))
        if stage=='natural':
            for owner in OWNERS:
                result.append(Step('world.belmonte.north.carve.'+owner,[Python(pipeline,(
                    '--mode','carve','--owner',owner,'--input',str(root/'natural'/(owner+'.npz')),
                    '--output',str(root/'carve'/(owner+'.npz'))))],inputs=[*code(pipeline),line],
                    reads=['belmonte.north.natural.'+owner],products=[Product('belmonte.north.carve.'+owner,(root/'carve'/(owner+'.npz'),))],
                    cache=True,heavy=True,about='carve only '+owner+' from its own natural source'))
    spec=importlib.util.spec_from_file_location('belmonte_north_independent_export_graph',GAME/'region_exports.py')
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    result.extend(graph.steps(ctx,region='belmonte_north',assets=[graph.LogicalAsset(owner,REGION/'plan_ground.py',
        args=('--asset',owner,'--surface',str(ctx.out/'belmonte-source-data'/(owner+'.surface'))),
        reads=('belmonte.final_surface.'+owner,),suffix='.glb',encoding='encoded_glb') for owner in OWNERS]))
    return result
