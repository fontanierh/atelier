"""Exact fitted Gondola receiving membership and native three-LOD logical bounds."""
import json
from pathlib import Path
import re

import unreal
from atelier import native_membership
from atelier.export_manifest import real_directory

DESTINATION = '/Game/Gondola/World'


def configure(site):
    if site.get('atomic') is not True: raise ValueError('Native Gondola requires bounded source membership')
    current = [piece['name'] for row in site['exports'] for piece in row['pieces']
               if not any(token in piece['name'] for token in ('_Rope_LOD1','_Rope_LOD2'))]
    if not current or len(current) != len(set(current)): raise ValueError('Incomplete native Gondola membership')
    previous = native_membership.inventory(unreal.EditorAssetLibrary,DESTINATION,'GD_')
    logical = {row['name'] for row in site['exports'] if not any(token in row['name'] for token in ('_Rope_LOD1','_Rope_LOD2'))}
    for package in previous:
        key = package.rsplit('/',1)[-1]
        if key not in logical and key not in current and not re.fullmatch(r'GD_L[123]_Rope_LOD0_Piece0[0-7]',key):
            raise ValueError('Foreign Gondola world member prevents retirement: '+key)
    return dict(previous=previous,current=current)


def finish_ropes(site,report):
    """Retain original source-LOD finishing; measure only actual final native buffers."""
    bounds = {}
    for line in site['lines']:
        names = site['rope_groups'][line['id']]
        parts = [unreal.EditorAssetLibrary.load_asset(DESTINATION+'/'+name) for name in names]
        if not parts or any(part is None or part.get_num_lods() != 3 for part in parts):
            raise ValueError('Incomplete native Gondola three-LOD rope family')
        result = unreal.GondolaRopeMeshComponent.finish_logical_rope('GD_'+line['id']+'_Rope',parts)
        if not result: raise ValueError('Actual native logical Gondola rope bounds are unavailable')
        value = json.loads(result)
        if set(value) != {'origin','extent','sphere_radius'}: raise ValueError('Incomplete native Gondola logical sphere')
        for name,mesh in zip(names,parts):
            if not unreal.EditorAssetLibrary.save_loaded_asset(mesh): raise ValueError('Gondola rope package save failed: '+name)
            report[name]['logical_bounds'] = value
        bounds[line['id']] = value
    return bounds


def retire(state):
    removed = native_membership.retire(unreal.EditorAssetLibrary,state['previous'],state['current'],DESTINATION,'GD_')
    folder = Path(unreal.Paths.project_content_dir()) / 'Gondola/World'
    real_directory(folder)
    obsolete = state['previous'] - {DESTINATION+'/'+key for key in state['current']}
    if any(list(folder.glob(package.rsplit('/',1)[-1]+'.*')) for package in obsolete):
        raise ValueError('Retired Gondola native package remains on disk')
    return removed
