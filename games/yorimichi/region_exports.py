"""Normal cached logical geometry, atomic exports and complete regional assembly."""
from dataclasses import dataclass
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.build_batch_source import support as batch_support
from atelier.build import Batch, Blender, Call, Product, Step
from atelier import export_assembly, export_tasks
from atelier.model_files import member

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
EXPORTER = WORLD / 'export_region_piece.py'


@dataclass(frozen=True)
class LogicalAsset:
    key: str
    script: Path
    args: tuple = ()
    inputs: tuple = ()
    reads: tuple = ()
    needs: tuple = ()
    suffix: str = '.fbx'


def inventory(root, parent):
    """Read task identities only; the owning ordinary task verifies all geometry payloads."""
    root = export_tasks.real_directory(root)
    path = root / 'plan.json'
    if not path.exists():
        if path.is_symlink(): raise ValueError('Linked logical plan')
        return ()
    if path.is_symlink() or not path.is_file(): raise ValueError('Invalid logical plan')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('parent') != parent or value.get('complete') is not True
            or value.get('triangle_limit') != export_tasks.TRIANGLE_LIMIT or not value.get('pieces')):
        raise ValueError('Incomplete or foreign logical geometry plan')
    seen, rows = set(), []
    total = 0
    for row in value['pieces']:
        key = export_tasks.name(row['name'])
        if (key.casefold() in seen or member(row['payload']) != key + '.npz'
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
    code/data/product inputs. Every planned bounded piece MUST then own an independent normal
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
        root = ctx.out / 'planned_exports' / region / asset.key
        task = f'world.{region}.geometry.{asset.key}'
        product = f'{region}.geometry.{asset.key}'
        def complete(root=root):
            import sys
            if str(WORLD) not in sys.path: sys.path.insert(0, str(WORLD))
            from region_mesh_parts import present
            return present(root)
        planners.append(Step(task, [Blender(asset.script, (*asset.args, '--output', str(root)),
                    threads=3, factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
            inputs=[*local_imports(asset.script, (WORLD, WORLD / 'regions')), *batch_support().values(), *asset.inputs], needs=list(asset.needs), reads=list(asset.reads),
            after=list(after), products=[Product(product, (root,))], cache=True, toolchain=True,
            heavy=True, batch=Batch(region + ' logical geometry'), verify=complete,
            about='construct only logical mesh ' + asset.key))
        logical.append((asset.key, root, task, product))
        rows = inventory(root, asset.key)
        atomic = export_tasks.steps(ctx, prefix=f'world.{region}.export',
            assets=[export_tasks.Asset(key, payload, asset.suffix) for key, payload in rows],
            script=EXPORTER, inputs=[WORLD / 'mesh_pieces.py', *inputs], after=[barrier])
        exports.extend(atomic)
        children.extend((step, key) for step, (key, _) in zip(atomic, rows))
        products.extend(step.products[0].name for step in atomic)
    discovery = ctx.out / 'planned_exports' / region / 'discovery.json'
    def discover(ctx, log):
        rows = {}
        for parent, root, _, _ in logical:
            found = inventory(root, parent)
            if not found: raise ValueError('Missing logical geometry plan: ' + parent)
            rows[parent] = [key for key, _ in found]
        atomic_json(discovery, dict(schema=1, parents=rows))
        log.write(f'Discovered {sum(map(len, rows.values()))} atomic {region} mesh exports\n')
    result = [*planners, Step(barrier, [Call('discover ' + region, discover)],
              inputs=local_imports(Path(__file__)), reads=[row[3] for row in logical],
              products=[Product(region + '.geometry_inventory', (discovery,))], replan=True,
              about='discover all completed logical mesh plans before any export'), *exports]
    destination = ctx.out / 'atomic_regions' / region
    def assemble(ctx, log):
        expected = []
        parents = {}
        for parent, root, _, _ in logical:
            rows = inventory(root, parent)
            if not rows: raise ValueError('Missing logical geometry plan: ' + parent)
            expected.extend(key for key, _ in rows)
            parents[parent] = [key for key, _ in rows]
        if expected != [key for _, key in children]:
            raise ValueError('Region export roster changed without completed recipe expansion')
        exports = [export_assembly.Item(key, step.products[0].paths[0]) for step, key in children]
        value = export_assembly.assemble(exports, destination / 'assets')
        atomic_json(destination / 'logical-pieces.json', dict(schema=1, parents=parents,
                    exports=[row['asset'] for row in value['exports']]))
        log.write(f'Assembled {len(exports)} independently cached {region} exports\n')
    result.append(Step(f'world.{region}.assembled', [Call('assemble ' + region, assemble)],
        inputs=local_imports(Path(__file__)), needs=[barrier], reads=products,
        products=[Product(region + '.atomic', (destination,))],
        about='complete validated independent export inventory for ' + region))
    return result
