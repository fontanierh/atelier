"""Compose independently exported coastal meshes, materials and instance data without joining geometry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from atelier.model_export import glb_info  # noqa: E402
from atelier.model_files import member  # noqa: E402


def read(path):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing coastal assembly input')
    return json.loads(path.read_text())


def texture_names(materials):
    result = set()
    for value in materials.values():
        if value['texture']: result.add(value['texture'])
        for field in ('layers', 'normals'):
            result.update(v for v in value.get(field, {}).values() if v)
    return result


def assemble(out, *, expected_parents, heroes):
    """@cc [owner:fontanierh,label:correctness] coastal-independent-export-assembly
    Consume the complete current atomic mesh, hero texture and placement inventories.
    Every bounded piece MUST remain its own native source asset, with the former parent
    placement, material mapping, collision, culling and shadow semantics. No geometry
    constructor, Blender import or exporter may run here. Preflight every source and
    destination before staging; retire only the previous complete owner's flat files
    after publishing the current complete report. Missing products MUST fail.
    """
    from brinecove import foliage_library, region, rocks  # rocks installs the established material palette
    from brinecove import assembly_files as files
    from brinecove.runtime_data import group, material_report, IDENTITY
    from brinecove.plan_hero import key as hero_key
    atomic, destination = out / 'atomic_regions/brinecove', out / 'brinecove'
    library = read(atomic / 'logical-pieces.json')
    exports = read(atomic / 'assets/manifest.json')
    data = read(out / 'brinecove-data/placements.json')
    if (library.get('schema') != 1 or set(library['parents']) != set(expected_parents)
            or set(library['ownership']) != set(expected_parents)
            or exports.get('schema') != 1 or exports.get('complete') is not True
            or data.get('schema') != 1 or set(data['heroes']) != set(heroes)):
        raise ValueError('Incomplete coastal assembly membership')
    expected = [child for children in library['parents'].values() for child in children]
    rows = exports['exports']
    if (not expected or len(set(expected)) != len(expected)
            or {r['asset'] for r in rows} != set(expected) or len(rows) != len(expected)):
        raise ValueError('Coastal atomic export membership differs')
    models, groups, sources, used = [], [], {}, set()
    by_name = {row['asset']: row for row in rows}
    for parent, children in library['parents'].items():
        ownership = library['ownership'][parent]
        if not children: raise ValueError('Empty coastal logical owner')
        slug = next((slug for slug in heroes if hero_key(slug) == parent), None)
        if slug is None and ownership.get('kind') != 'mesh_set':
            raise ValueError('Coastal finished component ownership is incomplete')
        for child in children:
            row = by_name[child]
            if row['primary'] != child + '.glb': raise ValueError('Noncanonical coastal source')
            path = atomic / 'assets' / row['primary']
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file() or sha(path) != row['sha256']:
                raise ValueError('Coastal atomic export changed')
            triangles, slots, bounds = glb_info(path)
            if (triangles != row['triangles'] or not 0 < triangles <= 32768
                    or not slots or any(not slot.startswith('BC_') for slot in slots)):
                raise ValueError('Coastal exported geometry/material identity differs')
            slots = [slot[3:] for slot in slots]; used.update(slots)
            policy = ownership['metadata'][child] if slug is None else dict(collision=True, shadow=True, cull_cm=60000)
            transforms = [IDENTITY] if slug is None else data['heroes'][slug]
            sources[path.name] = path
            models.append(dict(name=child, path='glb/' + path.name, sha256=row['sha256'],
                triangles=triangles, bounds_m=bounds, slots=slots, collision=policy['collision']))
            groups.append(group(child, slots, transforms, **{k: policy[k] for k in ('collision', 'shadow', 'cull_cm')}))
    materials, textures = material_report(used - {slot for slot in used if slot.startswith('hero_')})
    for slug in heroes:
        folder = out / 'brinecove-data/heroes' / slug
        metadata = read(folder / 'materials.json')
        if metadata.get('complete') is not True or metadata.get('slug') != slug:
            raise ValueError('Missing coastal hero material data')
        materials.update(metadata['materials'])
        for filename, digest in metadata['files'].items():
            if member(filename) != Path(filename).name: raise ValueError('Nonflat coastal hero texture')
            path = folder / filename
            if path.is_symlink() or not path.is_file() or sha(path) != digest:
                raise ValueError('Coastal hero texture differs')
            if filename in textures: raise ValueError('Duplicate coastal texture owner')
            textures[filename] = path
    protos = foliage_library.load(out / 'models/brinecove/plants')
    if (set(data['plants']) | set(data['scrub'])) - protos.keys():
        raise ValueError('Placements require undefined coastal foliage models')
    for proto, model in protos.items():
        if proto not in data['plants'] and proto not in data['scrub']: continue
        if not 0 < model['triangles'] <= 32768: raise ValueError('Coastal foliage export exceeds the atomic budget')
        filename = model['name'] + '.glb'
        if filename in sources: raise ValueError('Duplicate coastal model owner')
        source = out / 'models/brinecove/plants' / proto / 'model.glb'
        sources[filename] = source
        models.append({**model, 'path': 'glb/' + filename})
        extra, selected = material_report(set(model['slots']) - materials.keys())
        materials.update(extra); textures.update(selected)
        low = proto.startswith('cover_'); height = model['bounds_m'][1][2] - model['bounds_m'][0][2]
        if proto in data['plants']:
            groups.append(group(model['name'], model['slots'], data['plants'][proto], collision=False, shadow=not low,
                cull_cm=5000 if low else 24000 if height < 4 else 60000))
        if proto in data['scrub']:
            groups.append(group(model['name'], model['slots'], data['scrub'][proto], collision=False, shadow=False, cull_cm=9000))
    if used - materials.keys() or texture_names(materials) != set(textures):
        raise ValueError('Incomplete coastal material/texture bindings')
    real_directory(destination)
    previous = dict(meshes=[], materials={})
    for filename in ('runtime.json', 'build-report.json'):
        if (destination / filename).is_symlink(): raise ValueError('Linked coastal publication')
    if (destination / 'build-report.json').exists(): previous = read(destination / 'build-report.json')
    prior_models = set()
    for model in previous['meshes']:
        value = member(model['path'])
        if value != 'glb/' + model['name'] + '.glb': raise ValueError('Foreign previous coastal model ownership')
        prior_models.add(Path(value).name)
    model_root = files.preflight(destination / 'glb', sources, prior_models)
    texture_root = files.preflight(destination / 'textures', textures, texture_names(previous['materials']))
    model_hashes = {name: sha(path) for name, path in sources.items()}
    if any(model_hashes[Path(model['path']).name] != model['sha256'] for model in models):
        raise ValueError('Coastal model differs before staging')
    texture_hashes = {name: sha(path) for name, path in textures.items()}
    runtime = dict(version=1, origin_cm=[region.ORIGIN[0] * 100., -region.ORIGIN[1] * 100., region.ORIGIN[2] * 100.],
        bounds_m=list(region.OUTER_WORLD), clearance_m=list(region.OUTER_WORLD), clear_prefixes=['SW_Boulder'],
        groups=groups, signs=[], zones=[dict(key='brinecove_quay', name='Brinecove · quay', x=region.QUAY_STOP[0],
        y=region.QUAY_STOP[1], z=data['quay_z'], yaw=-90., hint='The pirate port in the western reach: market, galleons and the waterfall')])
    diagnostics = {parent.removeprefix('SM_BC_'): value['diagnostics']
        for parent, value in library['ownership'].items() if value.get('kind') == 'mesh_set'}
    report = dict(meshes=models, materials=materials, seam=diagnostics['Ground']['seam'],
        **{field + '_faces': {parent: value[field] for parent, value in diagnostics.items()}
           for field in ('outside', 'drowned', 'degenerate')},
        triangles=sum(m['triangles'] for m in models), instances=sum(len(g['transforms']) for g in groups))
    files.stage(model_root, sources, model_hashes); files.stage(texture_root, textures, texture_hashes)
    if (any(sha(path) != model_hashes[name] for name, path in sources.items())
            or any(sha(path) != texture_hashes[name] for name, path in textures.items())):
        raise ValueError('Coastal input changed before publication')
    atomic_json(destination / 'runtime.json', runtime); atomic_json(destination / 'build-report.json', report)
    files.retire(model_root, sources); files.retire(texture_root, textures)
    print('BRINECOVE GAME BUILD COMPLETE', len(models), 'independently exported meshes', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--parent', action='append', required=True)
    parser.add_argument('--hero', action='append', required=True)
    args = parser.parse_args(argv)
    assemble(args.out, expected_parents=args.parent, heroes=args.hero)


if __name__ == '__main__': main()
