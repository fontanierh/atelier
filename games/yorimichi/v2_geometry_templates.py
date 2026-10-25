"""Author D2 child templates from the existing logical-export constructor declarations."""
from pathlib import Path


EXPORT_SCRIPT = 'games/yorimichi/world/stage_mesh_export_v2.py'
ENCODED_SCRIPT = 'games/yorimichi/world/stage_encoded_export_v2.py'
REGION_EXPORTS = 'games/yorimichi/region_exports.py'
DERIVED_ROOT = 'build/v2-derived'
LIMITS = {'max_pieces': 65536, 'max_manifest_bytes': 64 * 1024 * 1024,
          'max_member_bytes': 128 * 1024 * 1024, 'max_total_bytes': 64 * 1024 * 1024 * 1024}


class Unsupported(ValueError):
    """A logical declaration does not provide enough information to author its children."""


def _logical(value):
    return (isinstance(value, list) and value and all(
        isinstance(member, list) and len(member) == 5
        and isinstance(member[0], str) and isinstance(member[1], dict)
        and set(member[1]) == {'path'} and all(isinstance(member[i], str) for i in (2, 3, 4))
        for member in value))


def geometry_templates(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] authored-geometry-child-templates
    Logical parents MUST come from original constructor declarations, never existing
    generated plan files. Each parent MUST match its exact producer/product/root.
    Export formats MUST come from the planner declaration and MUST remain unchanged.
    Runtime piece names belong only to the engine's validated group expansion.
    This compiler MUST NOT run discovery, export, validators or assembly callbacks.
    """
    from atelier.source_imports import ImportScanner

    by_name = {row['id']: row for row in rows}
    scanner = ImportScanner()
    root = Path(checkout)
    def closure(script):
        return [path.relative_to(root).as_posix() for path in scanner.local_imports(
            root / script, (root / 'games/yorimichi/world', root / 'platform/studio'))]
    code = closure(EXPORT_SCRIPT)
    encoded_code = closure(ENCODED_SCRIPT)
    groups, templates, families = {}, [], []
    for row in rows:
        if not row['replan']:
            continue
        calls = [command['fn'] for command in row['commands'] if command['kind'] == 'call'
                 and command['fn']['source'] == REGION_EXPORTS
                 and command['fn']['qualname'].endswith('.discover')]
        for call in calls:
            candidates = [value for value in call['closure'] if _logical(value)]
            if len(candidates) != 1 or not row['id'].endswith('.geometry'):
                raise Unsupported(f'{row["id"]}: ambiguous logical-export declaration')
            region = row['id'].removeprefix('world.').removesuffix('.geometry')
            parents = []
            for parent, location, producer, product, encoding in candidates[0]:
                declared = by_name.get(producer)
                owned = [p for p in declared['products'] if p['id'] == product] if declared else []
                if len(owned) != 1 or owned[0]['paths'] != [location['path']]:
                    raise Unsupported(f'{producer}: logical parent differs from its declared product')
                if encoding not in ('mesh_ir', 'encoded_glb'):
                    raise Unsupported(f'{producer}: unsupported geometry payload encoding {encoding}')
                export_format = declared.get('export_format')
                if export_format not in ('fbx', 'glb') or (encoding == 'encoded_glb' and export_format != 'glb'):
                    raise Unsupported(f'{producer}: missing or incompatible declared export format')
                if producer in groups:
                    raise Unsupported(f'{producer}: planner belongs to multiple export families')
                group = {'id': 'geometry', 'root': 'geometry', 'root_param': 'geometry_root',
                    'manifest': 'plan.json', 'adapter_version': 'd2.mesh-plan/1',
                    'parent': parent, 'encoding': encoding, 'class': 'GeometryPayload',
                    'logical_namespace': f'/Internal/{region}/{parent}', **LIMITS}
                groups[producer] = {'contract': group, 'source': location['path'], 'format': export_format}
                template = {'producer': producer, 'group': 'geometry',
                    'unit_prefix': f'world.{region}.export.{parent}',
                    'op': {'kind': 'blender_export_piece', 'version': '1'},
                    'script': EXPORT_SCRIPT, 'code': code,
                    'params': {'format': export_format,
                               'options': {'path_mode': 'RELATIVE'} if export_format == 'fbx' else {}},
                    'payload_slot': 'payload', 'staged_path': 'inputs/payload',
                    'output_class': 'StaticMeshSource', 'logical_namespace': f'/Sources/{region}',
                    'files': [{'path': '$piece.' + export_format}, {'path': 'export.json'}]}
                if encoding == 'encoded_glb':
                    # The lossless encoded body: unchanged GLB bytes plus the original receipt.
                    # Selected payload fields (member, encoding, role) are injected by the core.
                    template.update(op={'kind': 'encoded_export_piece', 'version': '1'},
                                    script=ENCODED_SCRIPT, code=encoded_code, params={},
                                    files=[{'path': '$piece.glb'}, {'path': 'export.json'}])
                templates.append(template)
                parents.append({'producer': producer, 'group': 'geometry', 'product': product, 'parent': parent,
                                'source': location['path'], 'prefix': template['unit_prefix']})
            families.append({'discovery': row['id'], 'region': region, 'parents': parents})
    return {'groups': groups, 'templates': templates, 'families': families,
            'derived': derived_tokens(rows, families)}


def derived_tokens(rows, families):
    """@cc [owner:fontanierh,label:correctness] assembly-children-before-key
    Each region assembly Call captures (children, destination, logical, region). Its children capture
    MUST become one before-key derived_items token naming the family's export templates in
    logical parent order, so the controller binds every expanded child's asset item before
    keying. Destination and logical captures stay unchanged. Ambiguity refuses.
    """
    by_region = {family['region']: family for family in families}
    tokens = []
    for row in rows:
        if not (row['id'].startswith('world.') and row['id'].endswith('.assembled')):
            continue
        region = row['id'].removeprefix('world.').removesuffix('.assembled')
        for index, command in enumerate(row['commands']):
            fn = command.get('fn') if command['kind'] == 'call' else None
            if not fn or fn['source'] != REGION_EXPORTS or not fn['qualname'].endswith('.assemble'):
                continue
            family = by_region.get(region)
            if family is None:
                raise Unsupported(f'{row["id"]}: assembly has no discovered export family')
            logical = [i for i, value in enumerate(fn['closure']) if _logical(value)]
            destination = [i for i, value in enumerate(fn['closure'])
                           if isinstance(value, dict) and set(value) == {'path'}]
            children = [i for i, value in enumerate(fn['closure'])
                        if isinstance(value, list) and i not in logical]
            names = [i for i, value in enumerate(fn['closure']) if isinstance(value, str)]
            if (len(fn['closure']) != 4 or len(logical) != 1 or len(destination) != 1 or len(children) != 1
                    or len(names) != 1 or fn['closure'][names[0]] != region):
                raise Unsupported(f'{row["id"]}: assembly captures differ from (children, destination, logical, region)')
            parents = [member[0] for member in fn['closure'][logical[0]]]
            if parents != [parent['parent'] for parent in family['parents']]:
                raise Unsupported(f'{row["id"]}: assembly logical parents differ from its export family')
            tokens.append({'unit': row['id'], 'command': index, 'capture': children[0],
                           'value': {'derived_items': {'root': f'{DERIVED_ROOT}/{region}', 'templates': [
                               {'producer': parent['producer'], 'group': parent['group'],
                                'unit_prefix': parent['prefix']} for parent in family['parents']]}}})
    return tokens


def apply_derived(rows, tokens):
    """Return rows with each assembly children capture replaced by its derived_items token."""
    from copy import deepcopy
    rows = deepcopy(list(rows))
    by_name = {row['id']: row for row in rows}
    for token in tokens:
        fn = by_name[token['unit']]['commands'][token['command']]['fn']
        fn['closure'][token['capture']] = deepcopy(token['value'])
    return rows
