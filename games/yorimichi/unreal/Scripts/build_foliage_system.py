"""The normal-build owner of every vegetation representation and its runtime registry.

Discover sources by material semantics as well as mesh names, including foliage in
mixed regional meshes. Originals remain owned by their importers and are read-only.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import hashlib
import json
import unreal as U
import atmosphere
import foliage_system as F
import see_through
from foliage_material import supports_lod_blend, enable_bark_lod_blend
import yori

OUT = yori.OUT / 'foliage_system'
E = U.EditorAssetLibrary
M = U.MaterialEditingLibrary


def digest(asset):
    package = asset.split('.')[0].removeprefix('/Game/')
    root = yori.GAME / 'unreal/Content' / package
    if not root.with_suffix('.uasset').is_file():
        raise ValueError('Unsaved foliage dependency: '+asset)
    files = [root.with_suffix(suffix) for suffix in ('.uasset', '.uexp', '.ubulk')]
    h = hashlib.sha256()
    for file in files:
        if file.exists():
            h.update(file.suffix.encode()); h.update(file.read_bytes())
    return h.hexdigest()


def source_identity(mesh, registry):
    """A texture, material parameter or parent graph edit also invalidates its canopy palette."""
    pending, found = [mesh.get_path_name().split('.')[0]], set()
    options = U.AssetRegistryDependencyOptions()
    while pending:
        path = pending.pop()
        if not path.startswith('/Game/') or path in found:
            continue
        found.add(path)
        pending.extend(str(p) for p in registry.get_dependencies(path, options))
    return hashlib.sha256(json.dumps([(p,digest(p)) for p in sorted(found)]).encode()).hexdigest()


def leaf_material(material):
    return F.material_vegetation(material.get_name(),
        masked=U.YorimichiFoliageBuilder.material_is_masked(material),
        foliage=U.YorimichiFoliageBuilder.material_uses_foliage_shading(material))


def classify(mesh):
    names=[str(slot.get_editor_property('material_slot_name')) for slot in mesh.get_editor_property('static_materials')]
    if names and all(name.startswith(F.roles.RIGID_PREFIX) for name in names):return None
    if any(str(slot.get_editor_property('material_slot_name')).startswith(F.roles.AUTHORED_PREFIX)
           for slot in mesh.get_editor_property('static_materials')):
        return [], 'authored'
    if any(str(slot.get_editor_property('material_slot_name')).startswith(F.roles.SLOT_PREFIX)
           for slot in mesh.get_editor_property('static_materials')):
        return [], 'roles'
    slots = [i for i in range(len(mesh.get_editor_property('static_materials')))
             if mesh.get_material(i) and leaf_material(mesh.get_material(i))]
    name = mesh.get_name()
    if slots:
        return slots, 'material'
    if not F.vegetation(name):
        return None
    if name.startswith(('HD_ArcadeTree', 'HD_PlazaTree')):
        return [], 'palette'
    # Single-material modeled crowns, such as the caldera conifers, retain their
    # complete lower trunk. Thin groundcover does not receive a closed canopy core.
    if F.category(name) == 'tree':
        return [], 'height'
    return list(range(len(mesh.get_editor_property('static_materials')))), 'material'


def canopy_material(near, patch=False):
    name = 'M_ForestPatch' if patch else 'M_CanopyNear' if near else 'M_CanopyFar'
    path = F.ROOT + '/Materials/' + name
    assets = U.AssetToolsHelpers.get_asset_tools()
    material = E.load_asset(path) if E.does_asset_exist(path) else assets.create_asset(
        name, F.ROOT+'/Materials', U.Material, U.MaterialFactoryNew())
    M.delete_all_material_expressions(material)
    vertex = M.create_material_expression(material, U.MaterialExpressionVertexColor)
    emission=M.create_material_expression(material,U.MaterialExpressionMultiply)
    assert M.connect_material_expressions(vertex,'RGB',emission,'A')
    assert M.connect_material_expressions(vertex,'A',emission,'B')
    base, glow = atmosphere.apply(material, vertex, emission, base_out='RGB')
    assert M.connect_material_property(base, '', U.MaterialProperty.MP_BASE_COLOR)
    assert M.connect_material_property(glow, '', U.MaterialProperty.MP_EMISSIVE_COLOR)
    for prop, value in ((U.MaterialProperty.MP_ROUGHNESS, 1.), (U.MaterialProperty.MP_SPECULAR, 0.)):
        node = M.create_material_expression(material, U.MaterialExpressionConstant)
        node.set_editor_property('r', value)
        assert M.connect_material_property(node, '', prop)
    material.set_editor_property('used_with_instanced_static_meshes', True)
    material.set_editor_property('dithered_lod_transition', True)
    if near:
        see_through.add_mask(material)
    else:
        # Near tree instances and their distant patch share one 200-250 m
        # temporal coverage transition. The interiors still fully occlude.
        code = ('float d=distance(P,Camera); return saturate((d-20000.0)/5000.0);' if patch
                else 'return Fade;')
        keep = M.create_material_expression(material, U.MaterialExpressionCustom)
        keep.set_editor_property('output_type', U.CustomMaterialOutputType.CMOT_FLOAT1)
        keep.set_editor_property('code', code)
        inputs = [('P', U.MaterialExpressionWorldPosition), ('Camera', U.MaterialExpressionCameraPositionWS)] if patch else [
            ('Fade', U.MaterialExpressionPerInstanceFadeAmount)]
        arguments = []
        for key, _ in inputs:
            a = U.CustomInput(); a.set_editor_property('input_name', key); arguments.append(a)
        keep.set_editor_property('inputs', arguments)
        for key, cls in inputs:
            node = M.create_material_expression(material, cls)
            assert M.connect_material_expressions(node, '', keep, key)
        dither = see_through.custom(material, 0, 0, see_through.DITHER, ['keep'])
        assert M.connect_material_expressions(keep, '', dither, 'keep')
        see_through.masked(material)
        see_through.into_mask(material, dither, 0, 0, alone=True)
    M.recompile_material(material)
    assert E.save_loaded_asset(material)
    return material


def blend_material(material):
    """Every HISM section must support blending, without modifying shared source graphs."""
    if supports_lod_blend(material):
        return material
    key = F.asset_id(material.get_path_name())
    path = F.ROOT+'/Materials/MI_'+key
    result = E.load_asset(path) if E.does_asset_exist(path) else U.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_'+key, F.ROOT+'/Materials', U.MaterialInstanceConstant, U.MaterialInstanceConstantFactoryNew())
    M.set_material_instance_parent(result, material)
    enable_bark_lod_blend(result)
    assert E.save_loaded_asset(result)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    U.load_module('YorimichiImport')
    registry = U.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    candidates = sorted(str(asset.package_name) for asset in registry.get_assets_by_path('/Game', recursive=True)
                        if str(asset.asset_class_path.asset_name) == 'StaticMesh'
                        and not str(asset.package_name).startswith(F.ROOT+'/')
                        and '/FoliageLODs/' not in str(asset.package_name)
                        and '/lods/' not in str(asset.package_name).lower())
    algorithm = hashlib.sha256()
    for file in [Path(__file__), Path(F.__file__), Path(F.roles.__file__), Path(atmosphere.__file__), Path(see_through.__file__),
                 Path(__file__).with_name('foliage_material.py'),
                 yori.GAME/'unreal/Source/YorimichiImport/FoliageBuilder.cpp',
                 yori.GAME/'unreal/Source/YorimichiImport/FoliageBuilder.h']:
        algorithm.update(file.read_bytes())
    algorithm.update(U.SystemLibrary.get_engine_version().encode())
    algorithm = algorithm.hexdigest()
    previous_path = OUT/'report.json'
    previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    registry_path=yori.GAME/'unreal/Content/Data/foliage_system/registry.json'
    published=json.loads(registry_path.read_text()) if registry_path.is_file() else {}
    # Check the previous closure BEFORE rewriting the three shared materials.
    # A missing wrapper must force source regeneration, never be certified away.
    cached=F.cache_records(previous,published,algorithm,F.package_inventory(yori.GAME/'unreal/Content'))
    near,far,patch_material=canopy_material(True),canopy_material(False),canopy_material(False,patch=True)
    records = []
    materials = set()
    for n, path in enumerate(candidates):
        mesh = E.load_asset(path)
        policy = classify(mesh)
        if policy is None:
            mesh=None
            U.YorimichiFoliageBuilder.collect_unused()
            continue
        slots, classification = policy
        identity = source_identity(mesh,registry)
        old = cached.get(mesh.get_path_name())
        if old and old.get('identity') == identity and all(
                E.does_asset_exist(old[k]) and digest(old[k]) == old.get('output_sha256',{}).get(k)
                for k in ('optimized','shadow','patch')):
            records.append(old)
            materials.update(old['leaf_materials'])
            U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} current: {path}')
            mesh=None
            U.YorimichiFoliageBuilder.collect_unused()
            continue
        key = F.asset_id(mesh.get_path_name())
        source_path, product_path = OUT/(key+'.source.json'), OUT/(key+'.json')
        before = digest(path)
        kind = F.category(mesh.get_name())
        U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} exporting: {path}')
        assert U.YorimichiFoliageBuilder.export_source(mesh, slots, classification, kind, str(source_path)), path
        source = json.loads(source_path.read_text())
        source['rigid_lods'] = []
        if F.vegetation(mesh.get_name()):
            for level in range(1, len(F.SCREENS)):
                lod_path = OUT/(key+f'.rigid{level}.json')
                lod_index = round(level*(mesh.get_num_lods()-1)/(len(F.SCREENS)-1))
                assert U.YorimichiFoliageBuilder.export_source(mesh, slots, classification, kind, str(lod_path),lod_index), path
                source['rigid_lods'].append(json.loads(lod_path.read_text()))
            if kind == 'tree' and len(source['rigid_lods'][-1]['faces']) <= 256:
                source['far_proxy'] = source['rigid_lods'][-1]
        product = F.build(source)
        U.log(f'FOLIAGE SYSTEM importing representations: {path}')
        product_path.write_text(json.dumps(product, separators=(',', ':'))+'\n')
        variants = {}
        for shadow in (False, True):
            dest = F.ROOT + '/Meshes/' + key + ('_Shadow' if shadow else '')
            result = U.YorimichiFoliageBuilder.build_variant(mesh, str(product_path), dest, near, far, shadow)
            assert result, dest
            for slot in range(len(mesh.get_editor_property('static_materials'))):
                result.set_material(slot, blend_material(mesh.get_material(slot)))
            assert E.save_loaded_asset(result), dest
            expected = [len(product['shadow']['faces'])] if shadow else [len(v['faces']) for v in product['levels']]
            assert result.get_num_lods() == len(expected), dest
            assert [result.get_num_triangles(i) for i in range(len(expected))] == expected, (dest, expected)
            variants['shadow' if shadow else 'optimized'] = result.get_path_name()
        patch_path = OUT/(key+'.patch.json')
        patch_path.write_text(json.dumps({**product, 'shadow': product['patch']}, separators=(',', ':'))+'\n')
        patch = U.YorimichiFoliageBuilder.build_variant(mesh, str(patch_path), F.ROOT+'/Meshes/'+key+'_Patch',
                                                       patch_material, patch_material, True)
        assert patch and E.save_loaded_asset(patch), path
        assert patch.get_num_lods() == 1 and patch.get_num_triangles(0) == len(product['patch']['faces']), path
        variants['patch'] = patch.get_path_name()
        assert digest(path) == before, ('Foliage owner modified its source', path)
        leaf_materials = [m['path'] for m in source['materials'] if m['foliage']]
        materials.update(leaf_materials)
        records.append(dict(source=mesh.get_path_name(), source_sha256=before, kind=kind,
                            identity=identity, leaf_materials=leaf_materials,
                            output_sha256={k:digest(v) for k,v in variants.items()},
                            source_triangles=mesh.get_num_triangles(0), shadow_triangles=len(product['shadow']['faces']), rigid_triangles=product['rigid_triangles'],
                            aggregate=classification!='authored' and kind=='tree' and F.vegetation(mesh.get_name())
                                      and 'palm' not in mesh.get_name().lower(),
                            canopy_bounds=product['canopy_bounds'],
                            triangles=[len(v['faces']) for v in product['levels']], **variants))
        U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} {path}: {records[-1]["triangles"]}')
        mesh=None;result=None;patch=None
        U.YorimichiFoliageBuilder.collect_unused()
    assert records, 'No foliage sources were discovered'
    report = dict(version=F.VERSION, algorithm=algorithm, words=list(F.WORDS), materials=sorted(materials), assets=records,
                  packages=F.package_inventory(yori.GAME/'unreal/Content'))
    # Publish after every mesh and source identity has been verified. A failure
    # leaves no current build stamp; the runtime registry is a normal cook root.
    destination = yori.GAME/'unreal/Content/Data/foliage_system/registry.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2)+'\n')
    (OUT/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    U.log(f'FOLIAGE SYSTEM COMPLETE: {len(records)} sources')


if __name__ == '__main__':
    main()
