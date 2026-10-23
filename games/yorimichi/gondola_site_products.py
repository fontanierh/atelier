"""Pre-export-query site audits and complete file-only fitted Gondola assembly."""
import copy
import json
from pathlib import Path
import sys

from atelier.atomic_files import atomic_json
from atelier import export_assembly,export_manifest

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
sys.path.insert(0,str(WORLD))
from regions.gondola.layout import mesh_names  # noqa: E402


def frames_equal(before,after):
    import numpy as np
    if len(before) != 4 or len(after) != 4 or any(not np.array_equal(a,b) for a,b in zip(before,after)):
        raise ValueError('Fitted Gondola frame changed after source publication')


class Prepared:
    def __init__(self,out):
        self.out = Path(out)
        self.folder = self.out / 'gondola/world'
        self.queries = self.folder / 'query-data'
        self.kit_queries = self.out / 'gondola/query-data'
        self.sources = self.folder / 'source-data'
        self.fit = json.loads((self.sources / 'fit.json').read_text())
        self.inventory = json.loads((self.out / 'atomic_regions/gondola_site/logical-pieces.json').read_text())
        if (self.fit.get('schema') != 1 or self.inventory.get('schema') != 1
                or set(self.inventory['parents']) != set(mesh_names())):
            raise ValueError('Incomplete fitted Gondola source/export inventory')
        self.rows = {}
        for parent in mesh_names():
            ownership = self.inventory['ownership'][parent]
            if self.inventory['parents'][parent] != [row['name'] for row in ownership['pieces']]:
                raise ValueError('Incomplete fitted Gondola bounded membership')
            if '_Rope_LOD' not in parent and len(ownership['pieces']) != 1:
                raise ValueError('Non-rope Gondola subdivision needs explicit native logical bounds migration')
            members = []
            for row in ownership['pieces']:
                key = row['name']; root = self.out / 'exports/world.gondola_site.export' / key
                receipt = export_manifest.validate(root,key=key)
                if receipt['triangles'] != row['triangles'] or receipt['metadata']['collision_hulls'] != 0:
                    raise ValueError('Fitted Gondola piece differs from its original source plan')
                members.append(dict(name=key,sha256=receipt['sha256'],triangles=receipt['triangles'],
                                    path=str(root / receipt['primary'])))
            self.rows[parent] = members
        files = [self.sources / 'fit.json',*(self.queries / (key+'.json') for key in mesh_names()),
                 *self.kit_queries.glob('GD_*.json')]
        if not files or len(files) != len(set(files)): raise ValueError('Incomplete query bindings')
        self.bindings = {str(path.relative_to(self.out)):export_manifest.sha(path) for path in files}

    def members(self,parent,triangles):
        values = self.rows[parent]
        if sum(row['triangles'] for row in values) != triangles:
            raise ValueError('Fitted Gondola original audit geometry differs from exported membership')
        return [{key:value for key,value in row.items() if key != 'path'} for row in values]

    def paths(self,parent):
        return [Path(row['path']) for row in self.rows[parent]]

    def mesh(self,key,kit=False):
        from regions.gondola.kit_actions import query_mesh
        return query_mesh(self.kit_queries if kit else self.queries,key)

    def cabin(self,p,d):
        from regions.gondola.site_sources import cabin_data,site_module
        return cabin_data(site_module(),self.kit_queries)

    def shells(self):
        return {kind:{f'GD_Station{kind.title()}_{part}':self.mesh(f'GD_Station{kind.title()}_{part}',kit=True)
                      for part in ('Platform','Machinery','Fittings','Building')}
                for kind in ('valley','rim','crater')}

    def station(self,key,frame):
        row = self.fit['stations'][key]; frames_equal(row['frame'],frame)
        return self.mesh(f'GD_{key}_Foundation'),copy.deepcopy(row['posts']),self.mesh(f'GD_{key}_Access'),copy.deepcopy(row['access'])

    def tower(self,key,tower,frame):
        rows = [row for line in self.fit['lines'] for row in line['towers'] if row['data']['id'] == key]
        if len(rows) != 1: raise ValueError('Unknown fitted Gondola tower metadata')
        row = rows[0]; frames_equal(row['frame'],frame)
        tower.seats = copy.deepcopy(row['seats'])
        tower.sheaves_x = {int(side):values for side,values in row['sheaves_x'].items()}
        return self.mesh(f'GD_{key}_Tower')

    def rope(self,line,lod):
        return self.mesh(f'GD_{line}_Rope_LOD{lod}')

    def finish(self,result):
        for name,expected in self.bindings.items():
            if export_manifest.sha(self.out / name) != expected: raise ValueError('Gondola query input changed during audit')
        result.update(atomic=True,query_inputs=self.bindings,logical_pieces=self.inventory,
            rope_groups={line['id']:[row['name'] for row in self.rows[f'GD_{line["id"]}_Rope_LOD0']]
                         for line in self.fit['lines']})
        atomic_json(self.folder / 'site-audit.json',result)


def assemble(out):
    """@cc [owner:fontanierh,label:correctness] complete-fitted-gondola-atomic-assembly
    Assembly MUST require current complete original site/rope-contact audits and every
    declared bounded child before copying files. No parent mesh may be regenerated or
    joined. Current runtime/native membership MUST consume exactly these children,
    preserving every logical three-LOD rope group and its original forced LOD policy.
    """
    out = Path(out); products = Prepared(out); folder = products.folder
    value = json.loads((folder / 'site-audit.json').read_text())
    from gondola.validation import site_inputs,validate_site
    if (value.get('atomic') is not True or value.get('failures') != []
            or value.get('query_inputs') != products.bindings or value.get('inputs') != site_inputs(out)):
        raise ValueError('Gondola current complete source-bound site audit is missing or stale')
    items = [export_assembly.Item(row['name'],Path(row['path']).parent)
             for parent in mesh_names() for row in products.rows[parent]]
    result = export_assembly.assemble(items,folder / 'atomic-assets')
    if {row['asset'] for row in result['exports']} != {row['name'] for rows in products.rows.values() for row in rows}:
        raise ValueError('Gondola file assembly omitted a bounded child')
    atomic_json(folder / 'site.json',value)
    validate_site(out)
    return value
