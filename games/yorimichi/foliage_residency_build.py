"""Normal-build ownership and verification for compact foliage residency packages."""
import json
import re
import hashlib
import math
from pathlib import Path

from atelier import mesh_geometry

GAME = Path(__file__).resolve().parent
ROOT = '/Game/FoliageResident'
TREE_WORDS = frozenset({'tree', 'palm', 'pine', 'maple', 'ginkgo'})


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


def authored_spec(source):
    """Bind the explicitly authored prop and its committed collision witness."""
    path = GAME / 'assets/belmonte/source.json'
    entries = json.loads(path.read_text())['meshes']
    name = source.rsplit('/', 1)[-1].split('.')[0]
    if source.split('.')[0] != '/Game/Belmonte/Meshes/' + name:
        raise ValueError('Authored prop has no declared source owner')
    entry = next((row for row in entries if row['name'] == name), None)
    if entry is None:
        raise ValueError('Missing authored source manifest')
    collision = entry.get('collision')
    if collision:
        file = path.parent / collision['path']
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != collision['sha256']:
            raise ValueError('Changed authored collision source')
    return entry


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
    packages = sorted({p for row in rows for p in assets(row)} |
                      {ROOT + '/Materials/M_CanopyNearInteraction'})
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
                        GAME / 'foliage_residency_build.py', GAME / 'assets/belmonte/source.json',
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
    witness_files = []
    for row in report['assets']:
        packages.update(row[key].split('.')[0] for key in ('source', 'optimized', 'shadow', 'patch'))
        if row['source'].startswith('/Game/Belmonte/Meshes/'):
            entry = next((e for e in json.loads((GAME / 'assets/belmonte/source.json').read_text())['meshes']
                          if e['name'] == row['source'].rsplit('/', 1)[-1].split('.')[0]), {})
            if row['rigid_triangles'] == 0 and entry.get('collision'):
                witness_files.append(GAME / 'assets/belmonte' / entry['collision']['path'])
                packages.add(row['source'].split('.')[0] + '_Collision')
        packages.update(path.split('.')[0] for path in row['leaf_materials'] if path.startswith('/Game/'))
    files = mesh_geometry.package_inventory(content, sorted(packages))
    return sorted([*(Path(content) / path for path in files), *witness_files])
