"""Author D2 child templates from the existing logical-export constructor declarations."""
from pathlib import Path


EXPORT_SCRIPT = 'games/yorimichi/world/stage_mesh_export_v2.py'
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
    Runtime piece names belong only to the engine's validated group expansion.
    This compiler MUST NOT run discovery, export, validators or assembly callbacks.
    """
    from atelier.source_imports import ImportScanner

    by_name = {row['id']: row for row in rows}
    scanner = ImportScanner()
    root = Path(checkout)
    code = [path.relative_to(root).as_posix()
            for path in scanner.local_imports(root / EXPORT_SCRIPT)]
    groups, templates, families = {}, [], []
    for row in rows:
        if not row['replan']:
            continue
        calls = [command['fn'] for command in row['commands'] if command['kind'] == 'call'
                 and command['fn']['source'] == 'games/yorimichi/region_exports.py'
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
                if producer in groups:
                    raise Unsupported(f'{producer}: planner belongs to multiple export families')
                group = {'id': 'geometry', 'root': 'geometry', 'root_param': 'geometry_root',
                    'manifest': 'plan.json', 'adapter_version': 'd2.mesh-plan/1',
                    'parent': parent, 'encoding': encoding, 'class': 'GeometryPayload',
                    'logical_namespace': f'/Internal/{region}/{parent}', **LIMITS}
                groups[producer] = {'contract': group, 'source': location['path']}
                # The per-piece material-graph GLB route needs its own typed serializer;
                # it must not be silently relabelled as a legacy FBX body.
                template = {'producer': producer, 'group': 'geometry',
                    'unit_prefix': f'world.{region}.export.{parent}',
                    'op': {'kind': 'blender_export_piece', 'version': '1'},
                    'script': EXPORT_SCRIPT, 'code': code,
                    'params': {'format': 'fbx', 'options': {'path_mode': 'RELATIVE'}},
                    'payload_slot': 'payload', 'staged_path': 'inputs/payload',
                    'output_class': 'StaticMeshSource', 'logical_namespace': f'/Sources/{region}',
                    'files': [{'path': '$piece.fbx'}, {'path': 'export.json'}]}
                if encoding != 'mesh_ir':
                    template['op'] = {'kind': 'encoded_export_piece', 'version': '1'}
                templates.append(template)
                parents.append({'producer': producer, 'group': 'geometry', 'product': product,
                                'source': location['path'], 'prefix': template['unit_prefix']})
            families.append({'discovery': row['id'], 'region': region, 'parents': parents})
    return {'groups': groups, 'templates': templates, 'families': families}
