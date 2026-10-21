"""Compact certified saved foliage; never export sources or rebuild canopy geometry."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib
import json
import unreal as U
from atelier import mesh_geometry as G
from atelier.atomic_files import atomic_json
import foliage_system as F
import foliage_residency_build as R
import build_foliage_system as owner
import shared_materials

E = U.EditorAssetLibrary
M = U.MaterialEditingLibrary
CONTENT = yori.GAME / 'unreal/Content'
OUT = yori.OUT / 'foliage_residency'


def interaction_current(material, mpc):
    if not material or not M.get_material_property_input_node(material, U.MaterialProperty.MP_WORLD_POSITION_OFFSET):
        return False
    cut = M.get_material_default_vector_parameter_value(material, 'CutScale')
    if (cut.r, cut.g, cut.b, cut.a) != (1., 1., 2., 1.):
        return False
    parameters = {str(node.get_editor_property('parameter_name'))
                  for node in M.get_material_expressions(material)
                  if isinstance(node, U.MaterialExpressionCollectionParameter) and
                  node.get_editor_property('collection') == mpc}
    return {'Wind', 'PlayerPos'} <= parameters


def interaction_material():
    """@cc [owner:fontanierh,label:correctness] residency-bush-interaction
    The owned near-material copy MUST retain the prepared opacity graph and alpha,
    use the existing shared Wind/PlayerPos collection without writing it, preserve
    CutScale Z=2 and add the canonical wind/player-push graph. Original prepared
    materials and source packages MUST remain unchanged.
    """
    source = F.ROOT + '/Materials/M_CanopyNear'
    path = R.ROOT + '/Materials/M_CanopyNearInteraction'
    mpc_path = '/Game/Japan/Materials/MPC_Wind'
    signature = hashlib.sha256(json.dumps(G.package_inventory(CONTENT, [source, mpc_path]), sort_keys=True).encode())
    for file in sorted({Path(__file__), Path(R.__file__), Path(G.__file__),
                        Path(shared_materials.__file__), Path(shared_materials.node.__code__.co_filename),
                        Path(shared_materials.link.__code__.co_filename)}):
        signature.update(file.read_bytes())
    stamp = OUT / 'interaction.json'
    try:
        old = json.loads(stamp.read_text())
        if old == dict(inputs=signature.hexdigest(), output=G.package_inventory(CONTENT, [path])):
            material = E.load_asset(path)
            if interaction_current(material, E.load_asset(mpc_path)):
                return material
    except (OSError, ValueError):
        pass
    # Force deletion may clear references: refuse every owner outside this exact
    # complete receiving roster before touching the owned derivative.
    if E.does_asset_exist(path):
        report = json.loads((yori.OUT / 'foliage_system/report.json').read_text())
        allowed = {R.ROOT + '/' + F.asset_id(row['source']) + '/' +
                   row['source'].rsplit('/', 1)[-1].split('.')[0] + suffix
                   for row in report['assets'] for suffix in ('', '_Canopy', '_Shadow')}
        registry = U.AssetRegistryHelpers.get_asset_registry()
        refs = {str(p) for p in registry.get_referencers(path, U.AssetRegistryDependencyOptions())}
        if refs - allowed:
            raise ValueError('Interaction material has external owners: ' + ', '.join(sorted(refs - allowed)))
        if not E.delete_asset(path):
            raise RuntimeError('Cannot replace owned interaction material')
    before = G.package_inventory(CONTENT, [source, mpc_path])
    material = E.duplicate_asset(source, path)
    mpc = E.load_asset(mpc_path)
    if not material or not mpc:
        raise RuntimeError('Missing canopy material or shared interaction collection')
    scales = [node for node in M.get_material_expressions(material)
              if isinstance(node, U.MaterialExpressionVectorParameter) and
              str(node.get_editor_property('parameter_name')) == 'CutScale']
    if len(scales) != 1:
        raise ValueError('Prepared canopy has no unique CutScale')
    scales[0].set_editor_property('default_value', U.LinearColor(1., 1., 2., 1.))
    shared_materials.wind_graph(material, mpc)
    M.recompile_material(material)
    if not E.save_loaded_asset(material, True):
        raise RuntimeError('Interaction material save failed')
    if before != G.package_inventory(CONTENT, [source, mpc_path]):
        raise ValueError('Interaction preparation changed shared source assets')
    if not interaction_current(material, mpc):
        raise ValueError('Interaction graph did not retain mask/push parameters')
    atomic_json(stamp, dict(inputs=signature.hexdigest(), output=G.package_inventory(CONTENT, [path])))
    return material


def main():
    """@cc [owner:fontanierh,label:correctness;performance] compact-saved-foliage
    Every input MUST belong to the current successful published preparation with
    matching complete package bytes. Native compaction MUST prove original rigid
    corner membership, all output corners/materials/settings and cooked collision
    before save/inventory/publication. Failed partial outputs MUST remain hints;
    no parent success stamp or legacy/source mutation may be manufactured.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads((yori.OUT / 'foliage_system/report.json').read_text())
    published = json.loads((CONTENT / 'Data/foliage_system/registry.json').read_text())
    if (report != published or not report.get('assets') or report.get('version') != 1 or
            report['packages'] != F.package_inventory(CONTENT)):
        raise ValueError('Residency requires complete current certified foliage preparation')
    if not U.YorimichiFoliageResidencyBuilder.self_test():
        raise ValueError('Receiving native residency fixture failed')
    near = interaction_material()
    registry = U.AssetRegistryHelpers.get_asset_registry()
    records = []
    for index, old in enumerate(report['assets']):
        source = E.load_asset(old['source'])
        prepared = E.load_asset(old['optimized'])
        shadow = E.load_asset(old['shadow'])
        if not source or not prepared or not shadow or owner.digest(old['source']) != old['source_sha256']:
            raise ValueError('Missing or changed certified source: ' + old['source'])
        if owner.source_identity(source, registry) != old['identity']:
            raise ValueError('Certified material/source dependency changed: ' + old['source'])
        policy = owner.classify(source, registry)
        if policy is None:
            raise ValueError('Certified source lost foliage semantics: ' + old['source'])
        leaf_slots, classification = policy
        standalone = F.vegetation(source.get_name())
        simple = bool(set(F.roles.plant_words(source.get_name())) & {'tree', 'palm'}) and classification != 'authored'
        passable = R.passable_plant(source.get_name(), F.roles.plant_words(source.get_name()),
                                     F.roles.semantic_tokens(source.get_name())) and classification != 'authored'
        authored = []
        if source.get_name() in R.species():
            manifest = json.loads((yori.OUT / 'foliage' / source.get_name() / 'manifest.json').read_text())
            authored = R.trunk_bounds(manifest['trunk_collision']) if simple else []
        before = owner.digest(old['source'])
        directory = R.ROOT + '/' + F.asset_id(old['source'])
        result = U.YorimichiFoliageResidencyBuilder.compact(source, prepared, shadow,
            classification, leaf_slots, old['rigid_triangles'], simple,
            R.source_lods(source.get_num_lods(), standalone), authored, directory, near, passable)
        if not result:
            raise ValueError('Native compaction refused: ' + old['source'])
        row = dict(old, **json.loads(result))
        row['source_materials'] = [source.get_material(i).get_path_name()
                                   for i in range(len(source.get_editor_property('static_materials')))]
        for asset in R.assets(row):
            if asset == old['patch'].split('.')[0]:
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
        U.YorimichiFoliageBuilder.collect_unused()
    result = dict(version=2, assets=records, words=report['words'], materials=report['materials'],
                  packages=R.inventory(CONTENT, records))
    atomic_json(CONTENT / 'Data/foliage_residency/registry.json', result)
    atomic_json(OUT / 'report.json', result)
    U.log(f'FOLIAGE RESIDENCY COMPLETE: {len(records)} sources')


if __name__ == '__main__':
    main()
