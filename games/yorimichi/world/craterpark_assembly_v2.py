"""Assemble the actual selected CraterPark exports and original runtime metadata."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
from atelier import export_assembly, export_manifest, mesh_ir
from atelier.atomic_files import managed_temporary_parent
from atelier.build_v2.recipe_job import unpack_root

GAME = Path(__file__).parents[1]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions')]
from craterpark import placement  # noqa: E402
from craterpark.v2 import export  # noqa: E402


def assemble(source=None, selected=None, destination=None):
    """@cc [owner:fontanierh,label:correctness] selected-craterpark-library-assembly
    Assembly MUST consume the complete canonical source inventory and exactly its
    actual render/collision/seed exports. Every export, retained checked plan,
    selected payload and original logical metadata MUST agree before original
    course/runtime metadata and the complete FBX library publish. No host-generated
    inventory, inferred face list, fake completion or original cold refusal may run.
    """
    source, destination = Path(source), Path(destination)
    inventory = json.loads((source / 'inputs.json').read_bytes())
    if inventory.get('schema') != 1 or inventory.get('complete') is not True:
        raise ValueError('Incomplete canonical CraterPark source inventory')
    expected = {row['name']: row for row in inventory['assets']}
    if len(expected) != len(inventory['assets']) or set(selected) != {'render', 'collision', 'seed'}:
        raise ValueError('Invalid canonical CraterPark ownership')
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crater-assembly-', dir=managed_temporary_parent(destination)) as name:
        scratch = Path(name)
        groups, items, seen = {'render': [], 'collision': []}, [], set()
        for kind in ('render', 'collision', 'seed'):
            for child, piece in selected[kind]:
                if piece in seen or piece not in expected or expected[piece]['kind'] != kind:
                    raise ValueError('Foreign or duplicate selected CraterPark export')
                seen.add(piece)
                roots = {}
                for role in ('export', 'payload', 'metadata'):
                    root = scratch / piece / role
                    unpack_root(child.products[0].paths[0] / (role + '.tree.tar'), root)
                    roots[role] = root
                receipt = export_manifest.validate(roots['export'], key=piece)
                plan = json.loads((roots['metadata'] / 'plan.json').read_bytes())
                rows = plan.get('pieces')
                if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('name') != piece:
                    raise ValueError('Selected CraterPark checked plan changed')
                row = rows[0]
                packet = (roots['payload'] / (piece + '.npz')).read_bytes()
                if (hashlib.sha256(packet).hexdigest() != row['sha256']
                        or receipt['metadata']['geometry_sha256'] != row['sha256']
                        or receipt['triangles'] != row['triangles']):
                    raise ValueError('Selected CraterPark export/payload identities differ')
                info = json.loads((roots['metadata'] / (piece + '.json')).read_bytes())
                if info.get('schema') != 1 or info.get('entry', {}).get('name') != piece:
                    raise ValueError('Foreign selected CraterPark metadata')
                metadata, mesh = mesh_ir.decode(packet)
                if not np.array_equal(metadata['matrix'], np.eye(4)):
                    raise ValueError('Unexpected CraterPark local-frame transform')
                original = info['entry']
                vertices = mesh['positions'][:, [0, 2, 1]].astype('f8')
                vertices[:, 2] *= -1
                vertices += np.asarray(original['native_origin'])
                entry = dict(original, name=piece, logical_parent=piece, source_faces=row['source_faces'],
                    fbx='fbx/' + receipt['primary'], sha256=receipt['sha256'], vertices=len(vertices),
                    triangles=row['triangles'], bounds={'minimum': vertices.min(0).tolist(), 'maximum': vertices.max(0).tolist()})
                entry['materials'] = [slot for i, slot in enumerate(metadata['slots']) if i in set(mesh['materials'])]
                if kind != 'seed': groups[kind].append(entry)
                items.append(export_assembly.Item(piece, roots['export']))
        if seen != set(expected):
            raise ValueError('Incomplete selected CraterPark export membership')
        export_assembly.assemble(items, destination / 'fbx')
        metadata_out = scratch / 'runtime'; metadata_out.mkdir()
        with np.load(source / 'metadata.npz', allow_pickle=False) as geometry:
            index = json.loads(str(geometry['index']))
            provenance = export.validate_geometry(index)
            build = {'scene_sha256': export.sha(placement.SOURCE / 'scene.json'), **groups}
            if provenance: build['v4'] = provenance
            export.write_metadata(metadata_out, placement.SOURCE, geometry, placement, build, index, provenance)
        for filename in ('build.json', 'park.json'):
            os.replace(metadata_out / filename, destination / filename)
    print(f'CRATERPARK ASSEMBLY COMPLETE {len(groups["render"])} {len(groups["collision"])}', flush=True)
