"""Build leaf-only LODs from certified saved sources without re-exporting originals."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import unreal as U
from atelier import mesh_geometry as G
from atelier.atomic_files import atomic_json
import foliage_system as F
import foliage_residency_build as R
import build_foliage_system as owner

E = U.EditorAssetLibrary
CONTENT = yori.GAME / 'unreal/Content'
OUT = yori.OUT / 'foliage_residency'


def main():
    """@cc [owner:fontanierh,label:correctness;performance] compact-saved-foliage
    Every input MUST belong to the current successful published preparation with
    matching complete package bytes. Native compaction MUST prove original rigid
    corner membership, all output corners/materials/settings and cooked collision
    before save/inventory/publication. Failed partial outputs MUST remain hints;
    no parent success stamp or legacy/source mutation may be manufactured.
    Small whole-mesh authored props MUST remain ordinary single meshes, excluded
    only by their complete explicit native role tag and shared 12288-triangle
    budget after current source identity checks, before any compaction or save.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads((yori.OUT / 'foliage_system/report.json').read_text())
    published = json.loads((CONTENT / 'Data/foliage_system/registry.json').read_text())
    if (report != published or not report.get('assets') or report.get('version') != 1 or
            report['packages'] != F.package_inventory(CONTENT)):
        raise ValueError('Residency requires complete current certified foliage preparation')
    if not U.YorimichiFoliageResidencyBuilder.self_test():
        raise ValueError('Receiving native residency fixture failed')
    # Exact authored leaves already retain their source opacity/wind/player-push
    # wrappers. Do not rebuild or bind the former solid-volume material.
    near = None
    registry = U.AssetRegistryHelpers.get_asset_registry()
    records = []
    for index, old in enumerate(report['assets']):
        source = E.load_asset(old['source'])
        if not source or owner.digest(old['source']) != old['source_sha256']:
            raise ValueError('Missing or changed certified source: ' + old['source'])
        if owner.source_identity(source, registry) != old['identity']:
            raise ValueError('Certified material/source dependency changed: ' + old['source'])
        names = [str(slot.get_editor_property('material_slot_name')) for slot in source.get_editor_property('static_materials')]
        triangles = source.get_num_triangles(0)
        if R.excluded_authored(names, triangles):
            if triangles != old['source_triangles']:
                raise ValueError('Authored ordinary-prop triangle count changed: ' + old['source'])
            U.log('FOLIAGE RESIDENCY excluded ordinary authored prop: ' + old['source'])
            source = None
            U.YorimichiFoliagePreparation.collect_unused()
            continue
        policy = owner.classify(source, registry)
        if policy is None:
            raise ValueError('Certified source lost foliage semantics: ' + old['source'])
        leaf_slots, classification = policy
        if classification == 'authored':
            raise ValueError('Invalid authored ordinary-prop exclusion: ' + old['source'])
        prepared = E.load_asset(old['optimized'])
        shadow = E.load_asset(old['shadow'])
        if not prepared or not shadow:
            raise ValueError('Missing certified preparation: ' + old['source'])
        compound = R.compound_tree(old['source'])
        standalone = F.vegetation(source.get_name())
        simple = bool(set(F.roles.plant_words(source.get_name())) & R.TREE_WORDS) and classification != 'authored' and not compound
        passable = R.passable_plant(source.get_name(), F.roles.plant_words(source.get_name()),
                                     F.roles.semantic_tokens(source.get_name())) and classification != 'authored'
        authored = []
        if source.get_name() in R.species():
            manifest = json.loads((yori.OUT / 'foliage' / source.get_name() / 'manifest.json').read_text())
            authored = R.trunk_bounds(manifest['trunk_collision']) if simple else []
        if simple and not authored and old['rigid_triangles'] == 0:
            authored = R.caldera_trunk_bounds(old['source'])
            if authored is None:
                raise ValueError('No declared whole-textured trunk source: ' + old['source'])
        expected_rigid = old['rigid_triangles']
        before = owner.digest(old['source'])
        directory = R.ROOT + '/' + F.asset_id(old['source'])
        result = U.YorimichiFoliageResidencyBuilder.compact(source, prepared, shadow,
            classification, leaf_slots, expected_rigid, simple,
            R.source_lods(source.get_num_lods(), standalone), authored, directory, near, passable)
        if not result:
            raise ValueError('Native compaction refused: ' + old['source'])
        row = R.authored_leaf_row(old, json.loads(result))
        row['source_materials'] = [source.get_material(i).get_path_name()
                                   for i in range(len(source.get_editor_property('static_materials')))]
        for asset in R.assets(row):
            if asset in {old['patch'].split('.')[0], row.get('collision', '').split('.')[0]}:
                continue
            mesh = E.load_asset(asset)
            if not mesh or not E.save_loaded_asset(mesh, True):
                raise ValueError('Compact package save failed: ' + asset)
        # Saves must exist with every regular sidecar before a record can contribute.
        unit_packages = G.package_inventory(CONTENT, R.assets(row))
        row['output_sha256'] = {role: owner.digest(row[role]) for role in ('optimized', 'shadow', 'patch')}
        if row['rigid']:
            row['output_sha256']['rigid'] = owner.digest(row['rigid'])
        if before != owner.digest(old['source']):
            raise ValueError('Residency changed its original source')
        atomic_json(OUT / 'units' / (F.asset_id(old['source']) + '.json'),
                    dict(source=old['source'], packages=unit_packages, row=row))
        records.append(row)
        U.log(f'FOLIAGE RESIDENCY {index+1}/{len(report["assets"])}: {old["source"]} rigid={row["rigid_triangles"]} canopy={row["triangles"]}')
        source = prepared = shadow = mesh = None
        U.YorimichiFoliagePreparation.collect_unused()
    result = dict(version=2, assets=records, words=report['words'], materials=report['materials'],
                  packages=R.inventory(CONTENT, records))
    atomic_json(CONTENT / 'Data/foliage_residency/registry.json', result)
    atomic_json(OUT / 'report.json', result)
    U.log(f'FOLIAGE RESIDENCY COMPLETE: {len(records)} sources')


if __name__ == '__main__':
    main()
