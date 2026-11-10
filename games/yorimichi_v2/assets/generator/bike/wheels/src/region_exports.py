"""Normal cached logical geometry, atomic exports and complete regional assembly."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.build_batch_source import support as batch_support
from atelier.build import Batch, Blender, Call, Product, Python, Step
from atelier import export_assembly, export_tasks, paths
from atelier.model_files import member

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
EXPORTER = WORLD / 'export_region_piece.py'
ENCODED_EXPORTER = WORLD / 'export_encoded_piece.py'


@dataclass(frozen=True)
class LogicalAsset:
    key: str
    script: Path
    args: tuple = ()
    inputs: tuple = ()
    reads: tuple = ()
    needs: tuple = ()
    suffix: str = '.fbx'
    products: tuple = ()
    encoding: str = 'mesh_ir'


def inventory(root, parent, *, encoding='mesh_ir'):
    """Read task identities only; the owning ordinary task verifies all geometry payloads."""
    if encoding not in ('mesh_ir','encoded_glb'):raise ValueError('Unknown logical mesh encoding')
    suffix='.mesh' if encoding=='encoded_glb' else '.npz'
    root = Path(root)
    path = root / 'plan.json'
    # Discovery describes cold tasks without creating or admitting their outputs.
    # Existing plans still require strict lexical-root validation before any read.
    if not os.path.lexists(path):
        return ()
    root = export_tasks.real_directory(root)
    if path.is_symlink() or not path.is_file(): raise ValueError('Invalid logical plan')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('parent') != parent or value.get('complete') is not True
            or value.get('triangle_limit') != export_tasks.TRIANGLE_LIMIT or not value.get('pieces')):
        raise ValueError('Incomplete or foreign logical geometry plan')
    if encoding=='encoded_glb' and value.get('kind')!='encoded_glb':raise ValueError('Wrong logical mesh data encoding')
    seen, rows = set(), []
    total = 0
    for row in value['pieces']:
        key = export_tasks.name(row['name'])
        if (key.casefold() in seen or member(row['payload']) != key + suffix
                or type(row['triangles']) is not int or not 0 < row['triangles'] <= export_tasks.TRIANGLE_LIMIT):
            raise ValueError('Invalid or duplicate atomic geometry member')
        seen.add(key.casefold()); total += row['triangles']
        rows.append((key, root / row['payload']))
    if total != value['source_triangles']:
        raise ValueError('Logical geometry inventory is incomplete')
    return tuple(rows)


def steps(ctx, *, region, assets, after=(), inputs=()):
    """@cc [owner:fontanierh,label:correctness;performance] logical-region-export-graph
    Each logical constructor MUST be a separate normally cached planner with complete consumed
    code/data/product inputs. Auxiliary query/terrain outputs written by that constructor
    MUST be declared under the same normal producer before other tasks consume them. Every planned bounded piece MUST then own an independent normal
    cached exporter, whose geometry input excludes sibling identities. Cold discovery MUST use
    the build controller's successful planner expansion. Assembly MUST require all planners and
    all current export products; it MUST NOT reconstruct missing geometry inline or export it.
    """
    export_tasks.name(region)
    assets = tuple(assets)
    if not assets or len({export_tasks.name(a.key).casefold() for a in assets}) != len(assets):
        raise ValueError('Region requires an explicit unique logical asset inventory')
    planners, exports, logical, children, products = [], [], [], [], []
    barrier = f'world.{region}.geometry'
    for asset in assets:
        if asset.suffix not in export_tasks.PRIMARY:
            raise ValueError('Unsupported atomic region format')
        if asset.encoding not in ('mesh_ir','encoded_glb') or (asset.encoding=='encoded_glb' and asset.suffix!='.glb'):
            raise ValueError('Unsupported logical source encoding/primary combination')
        encoded=asset.encoding=='encoded_glb'
        root = ctx.out / 'planned_exports' / region / asset.key
        task = f'world.{region}.geometry.{asset.key}'
        product = f'{region}.geometry.{asset.key}'
        def complete(root=root,encoded=encoded):
            import sys
            if str(WORLD) not in sys.path: sys.path.insert(0, str(WORLD))
            if encoded:
                from encoded_region_plan import present
            else:
                from region_mesh_parts import present
            return present(root)
        arguments=(*asset.args,'--output',str(root))
        command=(Python(asset.script,arguments) if encoded else Blender(asset.script,arguments,
                    threads=3,factory_startup=True,env=(('PYTHONHASHSEED','0'),)))
        planners.append(Step(task, [command],
            inputs=[*local_imports(asset.script, (WORLD, WORLD / 'regions', paths.STUDIO)), *(batch_support().values() if not encoded else ()), *asset.inputs], needs=list(asset.needs), reads=list(asset.reads),
            after=list(after), products=[Product(product, (root,)), *asset.products], cache=True, toolchain=not encoded,
            heavy=True, batch=None if encoded else Batch(region + ' logical geometry'), verify=complete,
            about='construct only logical mesh ' + asset.key))
        logical.append((asset.key, root, task, product,asset.encoding))
        rows = inventory(root, asset.key,encoding=asset.encoding)
        atomic = export_tasks.steps(ctx, prefix=f'world.{region}.export',
            assets=[export_tasks.Asset(key, payload, asset.suffix) for key, payload in rows],
            script=ENCODED_EXPORTER if encoded else EXPORTER,
            runtime='python' if encoded else 'blender',
            inputs=[*(() if encoded else (WORLD/'mesh_pieces.py',)),*inputs],after=[barrier])
        exports.extend(atomic)
        children.extend((step, key) for step, (key, _) in zip(atomic, rows))
        products.extend(step.products[0].name for step in atomic)
    discovery = ctx.out / 'planned_exports' / region / 'discovery.json'
    def discover(ctx, log):
        rows = {}
        for parent, root, _, _,encoding in logical:
            found = inventory(root, parent,encoding=encoding)
            if not found: raise ValueError('Missing logical geometry plan: ' + parent)
            rows[parent] = [key for key, _ in found]
        atomic_json(discovery, dict(schema=1, parents=rows))
        log.write(f'Discovered {sum(map(len, rows.values()))} atomic {region} mesh exports\n')
    result = [*planners, Step(barrier, [Call('discover ' + region, discover)],
              inputs=[Path(__file__), *export_assembly.runtime_inputs()], reads=[row[3] for row in logical],
              products=[Product(region + '.geometry_inventory', (discovery,))], replan=True,
              about='discover all completed logical mesh plans before any export'), *exports]
    destination = ctx.out / 'atomic_regions' / region
    def assemble(ctx, log):
        expected = []
        parents, ownership = {}, {}
        for parent, root, _, _,encoding in logical:
            rows = inventory(root, parent,encoding=encoding)
            if not rows: raise ValueError('Missing logical geometry plan: ' + parent)
            expected.extend(key for key, _ in rows)
            parents[parent] = [key for key, _ in rows]
        if expected != [key for _, key in children]:
            raise ValueError('Region export roster changed without completed recipe expansion')
        for parent, root, _, _,encoding in logical:
            plan = json.loads((root / 'plan.json').read_text())
            if encoding=='encoded_glb':
                ownership[parent]={key:plan[key] for key in ('kind','source_triangles',
                    'source_render_triangles','source_collision_triangles','pieces')}
                continue
            ownership[parent] = {key: plan[key] for key in (
                'source_triangles', 'source_polygons', 'source_collision_hulls', 'slots', 'matrix')}
            ownership[parent]['pieces'] = [{key: row[key] for key in (
                'name', 'triangles', 'polygons', 'collision_hulls', 'min', 'max')} |
                ({'slots': row['slots']} if plan.get('kind') == 'mesh_set' else {}) for row in plan['pieces']]
            if plan.get('kind') == 'mesh_set':
                ownership[parent].update(kind='mesh_set', metadata=plan['metadata'], diagnostics=plan['diagnostics'])
        exports = [export_assembly.Item(key, step.products[0].paths[0]) for step, key in children]
        value = export_assembly.assemble(exports, destination / 'assets')
        atomic_json(destination / 'logical-pieces.json', dict(schema=1, parents=parents, ownership=ownership,
                    exports=[row['asset'] for row in value['exports']]))
        log.write(f'Assembled {len(exports)} independently cached {region} exports\n')
    result.append(Step(f'world.{region}.assembled', [Call('assemble ' + region, assemble)],
        inputs=[Path(__file__), *export_assembly.runtime_inputs()], needs=[barrier], reads=[*products, *(row[3] for row in logical)],
        products=[Product(region + '.atomic', (destination,))],
        about='complete validated independent export inventory for ' + region))
    return result
