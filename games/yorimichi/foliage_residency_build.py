"""Normal-build ownership and verification for compact foliage residency packages."""
import json
import re
import math
from pathlib import Path

from atelier import mesh_geometry

GAME = Path(__file__).resolve().parent
ROOT = '/Game/FoliageResident'
TREE_WORDS = frozenset({'tree', 'palm', 'pine', 'maple', 'ginkgo'})


def authored_leaf_row(old, result):
    """@cc [owner:fontanierh,label:correctness] authored-leaf-lod-publication
    Fresh native results MUST bind every actual authored leaf level, screen threshold,
    original level index and exact classified count, including an empty distant leaf
    level only when its original contains no leaf faces. LOD0 MUST remain positive/exact.
    Only a single-level original MAY use four nonempty nonincreasing reduced levels with
    the actual reducer identity. Native geometry/material/settings proof remains required.
    Opaque coverage patches MUST stay disabled; inherited old counts MUST NOT certify output.
    """
    row = dict(old, **result)
    levels = result.get('triangles')
    screens = result.get('leaf_screens')
    sources = result.get('leaf_source_lods')
    originals = result.get('source_leaf_lod_triangles')
    expected = old['source_triangles'] - old['rigid_triangles']
    if (not isinstance(result.get('leaf_reducer'), str) or not result['leaf_reducer'].strip()
            or type(result.get('source_leaf_triangles')) is not int or result['source_leaf_triangles'] != expected
            or not isinstance(levels, list) or not 1 <= len(levels) <= 8
            or any(type(n) is not int or n < 0 for n in levels) or levels[0] != expected or expected < 1
            or not isinstance(screens, list) or len(screens) != len(levels)
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in screens)
            or screens[0] <= 0 or any(a < b for a, b in zip(screens, screens[1:]))
            or not isinstance(sources, list) or len(sources) != len(levels)
            or any(type(n) is not int or not 0 <= n < 8 for n in sources)
            or not isinstance(originals, list) or not originals
            or any(type(n) is not int or n < 0 for n in originals) or originals[0] != expected):
        raise ValueError('Invalid authored leaf LOD provenance/counts/screens')
    if result['leaf_reducer'] == 'authored-source-lods':
        if not (2 <= len(levels) <= 8 and sources == list(range(len(levels))) and originals == levels):
            raise ValueError('Authored source LOD chain differs')
    elif (len(levels) != 4 or sources != [0, 0, 0, 0] or originals != [expected]
            or any(n < 1 for n in levels) or any(a < b for a, b in zip(levels, levels[1:]))):
        raise ValueError('Invalid single-source reduced leaf chain')
    row['aggregate'] = False
    row['coverage'] = []
    return row


def trunk_bounds(values):
    """Authored radius/endpoints use Blender metres; Unreal flips Y and uses cm."""
    if values is None:
        return []
    if (not isinstance(values, list) or len(values) != 7 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in values) or values[0] <= 0):
        raise ValueError('Invalid authored trunk radius/endpoints')
    result = [float(v) * 100 for v in values]
    result[2] *= -1
    result[5] *= -1
    if math.dist(result[1:4], result[4:7]) < 1:
        raise ValueError('Degenerate authored trunk')
    return result


def source_lods(count, standalone):
    if type(count) is not int or count < 1:
        raise ValueError('Missing source LOD chain')
    return [round(i * (count - 1) / 3) if standalone else 0 for i in range(4)]



def caldera_trunk_bounds(path):
    """@cc [owner:fontanierh,label:correctness] caldera-authored-trunk-policy
    Only the four exact committed Caldera tree sources and their authored PropLOD
    package paths MAY use this positive simple-trunk approximation. The upright
    producer anchors their trunk axis at local XY zero and ground at Z zero.
    A 40cm-radius capsule from -15cm to 10% of declared fitted height MUST remain
    independent of the model's broad root/ground skirt and canopy. Other paths
    MUST return no witness. Current source bytes/materials MUST already match the
    certified preparation; existing native capsule physics checks MUST still run.
    """
    from regions.craterpark.v2 import trees
    # Exact authored scope, pinned to the producer's current declared fit heights.
    heights = {'Tree_Caldera_BlackPine_A': 8., 'Tree_Caldera_BlackPine_B': 8.,
               'Tree_Caldera_Cedar_A': 12., 'Tree_Caldera_Cedar_B': 12.}
    for name, height in heights.items():
        base = '/Game/Japan/Assets/' + name
        paths = {base + '.' + name}
        for level in range(1, 4):
            asset = name + '_LOD' + str(level)
            package = '/Game/Japan/Hidamari/PropLODs/' + name + '/' + asset
            paths.add(package + '.' + asset)
        if path in paths:
            if name not in trees.TREES or trees.TREES[name][2] != height:
                raise ValueError('Caldera authored trunk fit changed: ' + name)
            return trunk_bounds([.4, 0., 0., -.15, 0., 0., height*.1])
    return None


def passable_plant(name, words, tokens):
    """Only positive non-tree plant semantics may disable a plant carrier's collision.

    Container/structure words are recovered from the ORIGINAL name, since the
    shared plant tokenizer intentionally removes planter/treehouse containers.
    Unknown generic plant/leaf/foliage names remain conservative.
    """
    name = name.rsplit('/', 1)[-1]
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    original = set(re.findall('[a-z]+', name.lower())) | set(tokens)
    structural = {'town', 'district', 'street', 'road', 'building', 'wall', 'fence',
                  'bridge', 'house', 'treehouse', 'ground', 'terrain', 'planter', 'pot', 'barrel', 'pavilion', 'stand', 'bucket'}
    structural = {form for word in structural for form in (word, word+'s', word+'es')}
    positive = {'bush', 'shrub', 'hedge', 'grass', 'fern', 'flower', 'groundcover',
                'azalea', 'niwaki', 'bloom', 'reed', 'vine', 'litter', 'cover_leaf',
                'cover_grass', 'cover_fern', 'coverleaf', 'covergrass', 'coverfern'}
    return bool(set(words) & positive) and not set(words) & TREE_WORDS and not original & structural


def excluded_authored(names, triangles):
    """@cc [owner:fontanierh,label:correctness;performance] ordinary-authored-props
    Only the complete explicit FoliageAuthored_ slot table and positive whole-mesh
    triangle budget <=12288 MAY exclude an indivisible authored prop from foliage
    residency. Region/name guesses, partial tags and oversized objects MUST NOT
    exempt dense or embedded vegetation. The caller MUST first validate current
    source bytes/material identity and actual triangle count against its report.
    """
    return (type(triangles) is int and 0 < triangles <= 12288 and bool(names) and
            all(isinstance(name, str) and name.startswith('FoliageAuthored_') for name in names))


def assets(row):
    result = [row[key].split('.')[0] for key in ('optimized', 'shadow', 'patch')]
    if row['rigid']:
        result.append(row['rigid'].split('.')[0])
    if row.get('collision'):
        result.append(row['collision'].split('.')[0])
    if len(result) != len(set(result)) or any(not p.startswith('/Game/') for p in result):
        raise ValueError('Invalid compact package membership')
    return result


def inventory(content, rows):
    """@cc [owner:fontanierh,label:correctness] authored-leaf-package-inventory
    Inventory MUST cover every declared current row package and its regular sidecars.
    Authored leaves retain their certified source material wrappers; an unused legacy
    solid-volume interaction material MUST NOT become an output prerequisite.
    This inventory MUST NOT substitute for native geometry/material validation.
    """
    packages = sorted({p for row in rows for p in assets(row)})
    return mesh_geometry.package_inventory(content, packages)


def verify(content, report_path):
    try:
        report = json.loads(Path(report_path).read_text())
        registry = json.loads((Path(content) / 'Data/foliage_residency/registry.json').read_text())
        return (report == registry and report['version'] == 2 and bool(report['assets']) and
                report['packages'] == inventory(content, report['assets']))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def step(ctx):
    """@cc [owner:fontanierh,label:correctness;performance] foliage-residency-owner
    Residency MUST consume the successful current preparation and all authored
    trunk manifests, preserve corner/material identity and keep rigid geometry
    once. Only exact saved package groups MAY enter the receiving registry.
    A partial unit MUST NOT publish whole-task success. New packages MUST remain
    outside original discovery; runtime readiness MUST require this owner.
    """
    from atelier import build_inputs, unreal_modules
    from atelier.build import DeferredInputs, Step, UnrealScript
    scripts = GAME / 'unreal/Scripts'
    script = scripts / 'prepare_foliage_residency.py'
    command = UnrealScript(script, 'FOLIAGE RESIDENCY COMPLETE', modules=('Yorimichi', 'YorimichiImport'),
                           null_rhi=True, memory_gib=10,
                           args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))
    command.timeout = 7200
    command.progress = 25
    content = GAME / 'unreal/Content'
    return Step('unreal.foliage_residency', [command],
                inputs=[*build_inputs.local_imports(script, (GAME, GAME / 'world', scripts)),
                        GAME / 'foliage_residency_build.py',
                        GAME / 'unreal/Source/Yorimichi/Dev/FoliageResidencyBuilder.cpp',
                        GAME / 'unreal/Source/Yorimichi/Dev/FoliageResidencyBuilder.h',
                        ctx.out / 'foliage_system/report.json', content / 'FoliageSystem',
                        content / 'Data/foliage_system/registry.json',
                        *(ctx.out / 'foliage' / name / 'manifest.json' for name in species()),
                        GAME.parents[1] / 'platform/studio/atelier/mesh_geometry.py'],
                deferred_inputs=[DeferredInputs('residency-current-packages', dependency_inputs,
                    (content, ctx.out / 'foliage_system/report.json'), support=(GAME / 'foliage_residency_build.py',))],
                after=['unreal.foliage_system'], needs=unreal_modules.needs(('Yorimichi', 'YorimichiImport')),
                outputs=[content / 'FoliageResident', content / 'Data/foliage_residency/registry.json',
                         ctx.out / 'foliage_residency/report.json'],
                verify=lambda: verify(content, ctx.out / 'foliage_residency/report.json'), heavy=True,
                about='compact certified foliage: rigid once, leaf-only LODs, authored trunk collision')


def species():
    # The actual source manifest roster is committed; each selected manifest is declared.
    return sorted(p.stem for p in (GAME / 'assets/foliage').glob('*.json'))


def dependency_inputs(content, report_path):
    """Exact source/derivative packages plus the current native material dependency closure.

    The native preparation report identity binds transitive source dependencies;
    each direct package and the shared collection additionally binds all sidecars.
    """
    report_path = Path(report_path)
    if not report_path.exists():
        return [report_path]
    report = json.loads(report_path.read_text())
    packages = {'/Game/Japan/Materials/MPC_Wind'}
    for row in report['assets']:
        packages.update(row[key].split('.')[0] for key in ('source', 'optimized', 'shadow', 'patch'))
        packages.update(path.split('.')[0] for path in row['leaf_materials'] if path.startswith('/Game/'))
    files = mesh_geometry.package_inventory(content, sorted(packages))
    return sorted(Path(content) / path for path in files)
