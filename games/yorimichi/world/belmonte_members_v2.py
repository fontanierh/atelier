"""Select rendered packets from one fully validated original Belmonte planner."""
import json
from pathlib import Path
import shutil

from atelier.build_v2.recipe_job import unpack_root
from encoded_region_plan import validate


def run(context):
    """@cc [owner:fontanierh,label:correctness] belmonte-render-projection
    The complete declared planner MUST validate before publishing its render-only
    group. Copy exact packets; preserve parent and selected assembly metadata.
    Whole collision packets remain owned by the original export family.
    """
    if context.params.get('action') == 'select':
        source = Path(context.input('selected'))
        filename = context.params['piece'] + context.params['extension']
        if set(context.inputs) != {'selected'} or set(context.outputs) != {filename} or {p.name for p in source.iterdir()} != {filename}:
            raise ValueError('Belmonte selected member differs')
        path = source / filename
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError('Belmonte selected member is not regular')
        context.output(filename).write_bytes(path.read_bytes())
        return
    if set(context.inputs) != {'source'} or set(context.params) != {'parent', 'geometry_root'}:
        raise ValueError('Belmonte projection requires one complete planner')
    root = Path(context.input('source'))
    archive = root / 'products/0-0.tree.tar'
    if (root.resolve() != root or not root.is_dir() or any(p.is_symlink() for p in root.rglob('*'))
            or [p for p in root.rglob('*') if p.is_file()] != [archive]):
        raise ValueError('Belmonte projection requires the exact planner archive')
    scratch = context.output_dir / '.belmonte-plan'
    destination = context.output_dir / 'geometry'
    if scratch.exists() or destination.exists():
        raise ValueError('Belmonte projection outputs must be fresh')
    try:
        if unpack_root(archive, scratch)['kind'] != 'directory':
            raise ValueError('Belmonte planner must be a directory')
        plan = validate(scratch)
        if plan['parent'] != context.params['parent']:
            raise ValueError('Belmonte planner belongs to another parent')
        selected = [row for row in plan['pieces'] if row['role'] == 'render']
        projected = dict(plan, pieces=selected, source_triangles=plan['source_render_triangles'], source_collision_triangles=0)
        destination.mkdir()
        for row in selected:
            (destination / row['payload']).write_bytes((scratch / row['payload']).read_bytes())
        (destination / 'plan.json').write_text(json.dumps(projected, sort_keys=True, separators=(',', ':')) + '\n')
        validate(destination)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def project_materials(source=None, textures=None, output=None, kind=None):
    """@cc [owner:fontanierh,label:correctness] belmonte-native-material-members
    Actual generated material descriptors and every selected texture digest MUST
    validate before publishing per-material JSON or per-texture PNG membership.
    Native membership MUST NOT be inferred from ambient Content or prior results.
    """
    import hashlib
    import re
    value = json.loads(Path(source).read_bytes())
    if set(value) != {'schema', 'materials', 'files', 'bindings'} or value['schema'] != 1:
        raise ValueError('Belmonte material view differs')
    materials = value['materials']; files = value['files']
    wanted = {'textures/' + m['texture'] for m in materials.values() if m['texture']}
    if set(files) != wanted or not materials or kind not in ('materials', 'textures'):
        raise ValueError('Belmonte material texture membership differs')
    selected = {}; names = set()
    for source_name, spec in materials.items():
        key = spec['name']
        if not re.fullmatch(r'MI_BM_(?:[0-9a-f]{12}|Ground)', key) or key.casefold() in names:
            raise ValueError('Belmonte material names are aliased or foreign')
        names.add(key.casefold())
        if kind == 'materials':
            selected[key + '.json'] = json.dumps(dict(source=source_name, spec=spec), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    for relative in sorted(wanted):
        filename = relative.removeprefix('textures/')
        if not re.fullmatch(r'T_BM_[0-9a-f]{12}\.png', filename):
            raise ValueError('Foreign Belmonte texture member')
        path = Path(textures) / filename
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError('Belmonte texture is not a regular produced member')
        raw = path.read_bytes()
        if files[relative] != {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}:
            raise ValueError('Belmonte generated texture bytes changed')
        if kind == 'textures': selected[filename] = raw
    output = Path(output)
    if output.exists() or not selected:
        raise ValueError('Belmonte member output must be fresh and nonempty')
    output.mkdir(parents=True)
    for filename, raw in selected.items(): (output / filename).write_bytes(raw)


def complete(geometry=None, runtime=None, render=(), hulls=None, materials=None, textures=(), tv=None, output=None, mesh_items=(), material_view=None):
    """@cc [owner:fontanierh,label:correctness] belmonte-complete-native-report
    The report MUST consume every actual finished render, hull, material, texture
    and TV Item plus current source geometry/runtime/material views. Current native
    measurements MUST match source membership and validation before publication.
    Missing members MUST refuse; no source-only success or ambient scan is allowed.
    """
    source = json.loads(Path(geometry).read_bytes()); live = json.loads(Path(runtime).read_bytes())
    palette = json.loads(Path(material_view).read_bytes())
    expected = {row['name']: row for row in source['meshes']}
    if len(expected) != len(source['meshes']) or not live.get('groups'):
        raise ValueError('Belmonte summary requires complete geometry and runtime')
    runtime_names = {g['asset'].split('.')[-1] for g in live['groups'] if not g.get('plant', False)}
    if runtime_names != set(expected):
        raise ValueError('Belmonte runtime/native mesh membership differs')
    def native(root, relative):
        path = Path(root) / ('content/Game/' + relative + '.uasset')
        if path.resolve() != path or not path.is_file():
            raise ValueError('Missing current Belmonte finished native package: ' + relative)
    current = {name: child.products[0].paths[0] for child, name in mesh_items}
    if len(current) != len(mesh_items) or set(current) != set(expected):
        raise ValueError('Belmonte current finished render membership differs')
    reports = {}
    def read_report(root, name, hull):
        path = Path(root) / ('data/reports/' + name + '.json')
        if path.resolve() != path or not path.is_file(): raise ValueError('Missing Belmonte current native report')
        value = json.loads(path.read_bytes())
        if set(value) != {'name', 'hull', 'triangles', 'bounds_cm', 'bounds_error_cm'} or value['name'] != name or value['hull'] is not hull or name in reports:
            raise ValueError('Belmonte current native report identity differs')
        if not 0 <= value['bounds_error_cm'] < 1. or type(value['triangles']) is not int or value['triangles'] < 1:
            raise ValueError('Belmonte current native report validation failed')
        reports[name] = value
    for child, name in render:
        if name not in current: raise ValueError('Foreign Belmonte native report')
        native(current[name], 'Belmonte/Meshes/' + name)
        read_report(child.products[0].paths[0], name, False)
    wanted_hulls = {Path(row['collision']['path']).stem for row in expected.values() if row.get('collision')}
    if set(hulls) != wanted_hulls: raise ValueError('Belmonte current finished hull membership differs')
    for name, (asset, report) in hulls.items():
        native(asset, 'Belmonte/Meshes/' + name); read_report(report, name, True)
    if set(reports) != set(expected) | wanted_hulls:
        raise ValueError('Belmonte complete current mesh report membership differs')
    for name, row in expected.items():
        if reports[name]['triangles'] != row['triangles']:
            raise ValueError('Belmonte native summary triangles differ from current geometry')
    if set(materials) != {'M_Belmonte', 'M_BelmonteJoin', *(v['name'] for v in palette['materials'].values())}:
        raise ValueError('Belmonte current native material membership differs')
    for name, root in materials.items(): native(root, 'Belmonte/Materials/' + name)
    texture_roots = {name: child.products[0].paths[0] for child, name in textures}
    wanted_textures = {Path(row['texture']).stem for row in palette['materials'].values() if row['texture']}
    if len(texture_roots) != len(textures) or set(texture_roots) != wanted_textures:
        raise ValueError('Belmonte current native texture membership differs')
    for name, root in texture_roots.items(): native(root, 'Belmonte/Textures/' + name)
    native(tv, 'Racing/M_RacingTv')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    result = {name: {'triangles': reports[name]['triangles'], 'bounds_cm': reports[name]['bounds_cm'],
                     'collision_hulls': bool(row.get('collision'))} for name, row in expected.items()}
    (output / 'import-report.json').write_text(json.dumps(result, indent=1) + '\n')
