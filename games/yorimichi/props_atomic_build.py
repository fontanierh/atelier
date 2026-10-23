"""Independent small prop constructors and exports; assembly only gathers verified files."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build import Call,Product,Python,Step
from atelier.build_inputs import local_imports
from atelier import export_assembly

GAME=Path(__file__).resolve().parent;WORLD=GAME/'world'


def load(key,path):
    spec=importlib.util.spec_from_file_location(key,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def steps(ctx):
    sources=load('world_selected_prop_sources',WORLD/'prop_sources.py')
    graph=load('world_prop_export_graph',GAME/'region_exports.py')
    source=ctx.out/'prop-source-data'
    result=[Step('world.props.sources',[Python(WORLD/'prop_sources.py',('--output',str(source)))],
        inputs=[*local_imports(WORLD/'prop_sources.py',(WORLD,)),WORLD/'build_assets.py'],
        products=[Product('props.source.'+key,(source/(key+'.json'),)) for key in sources.BUILDERS],cache=True)]
    assets=[]
    for key,value in sources.project(sources.SOURCE.read_text()).items():
        textures=[ctx.out/'textures'/spec['texture'] for spec in value['materials'].values() if spec.get('texture')]
        assets.append(graph.LogicalAsset(key,WORLD/'plan_world_prop.py',args=('--source',str(source/(key+'.json'))),
            reads=('props.source.'+key,),inputs=tuple(textures),needs=('world.textures',) if textures else ()))
    result.extend(graph.steps(ctx,region='props',assets=assets))
    def assemble(ctx,log):
        root=ctx.out/'atomic_regions/props'
        logical=json.loads((root/'logical-pieces.json').read_text())
        if set(logical['parents'])!=set(sources.BUILDERS) or any(rows!=[key] for key,rows in logical['parents'].items()):
            raise ValueError('Props require the complete original rigid ownership/pivot roster')
        items=[export_assembly.Item(key,ctx.out/'exports/world.props.export'/key) for key in sources.BUILDERS]
        value=export_assembly.assemble(items,ctx.out/'props/assets')
        atomic_json(ctx.out/'props/manifest.json',dict(schema=1,complete=True,exports=value['exports']))
        log.write('Assembled fourteen independently cached props without joining geometry\n')
    result.append(Step('world.props',[Call('assemble world props',assemble)],
        inputs=[Path(__file__),*export_assembly.runtime_inputs()],reads=['props.atomic'],
        products=[Product('props.library',(ctx.out/'props',))]))
    return result
