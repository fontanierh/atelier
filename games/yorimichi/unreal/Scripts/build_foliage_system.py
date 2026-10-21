"""The normal-build owner of every vegetation representation and its runtime registry.

Discover sources by material semantics as well as mesh names, including foliage in
mixed regional meshes. Originals remain owned by their importers and are read-only.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori  # noqa: E402

import hashlib
import json
import os
import platform
import subprocess
import unreal as U
from atelier import mesh_geometry as G
from atelier.native_protocol import context as native_environment, native_context, runtime_files
import atmosphere
import foliage_system as F
import see_through
from foliage_material import supports_lod_blend, enable_bark_lod_blend
from foliage_variant_validation import matches as variant_matches, settings_reader
import foliage_unit_policy as unit_policy

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


def collision_geometry(mesh, registry):
    """Disambiguate name-only hulls through their actual hard physics owner.

    Collision usage does not certify exclusive usage. Do not stamp a rigid role:
    if someone draws this unannotated plant-named hull, the runtime audit must
    still reject its missing representation. Explicit foliage semantics win.
    """
    path=mesh.get_path_name()
    options=U.AssetRegistryDependencyOptions(include_hard_package_references=True,
        include_soft_package_references=False,include_searchable_names=False,
        include_hard_management_references=False,include_soft_management_references=False)
    for package in sorted(str(p) for p in registry.get_referencers(path.split('.')[0],options)):
        for asset in registry.get_assets_by_package_name(package):
            if str(asset.asset_class_path.asset_name)!='StaticMesh':continue
            owner=E.load_asset(str(asset.package_name))
            if not owner:raise ValueError('Cannot inspect collision owner: '+package)
            if owner.get_path_name()==path:continue
            hull=owner.get_editor_property('complex_collision_mesh')
            if hull and hull.get_path_name()==path:return True
    return False


def classify(mesh, registry):
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
    if collision_geometry(mesh,registry):
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
    assert M.connect_material_expressions(vertex,'',emission,'A')
    assert M.connect_material_expressions(vertex,'A',emission,'B')
    base, glow = atmosphere.apply(material, vertex, emission)
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


def bind_variant_materials(mesh, replacements):
    """@cc [owner:fontanierh,label:correctness;performance] foliage-material-batch
    Binding source materials MUST preserve slot order, names, UV metadata and the
    two appended canopy slots. It MUST publish the material array once per variant,
    rather than invoking an editor mesh update for each source slot, and refuse
    if the mesh does not expose the requested bindings afterward.
    """
    slots = [slot.copy() for slot in mesh.get_editor_property('static_materials')]
    if len(slots) != len(replacements) + 2:
        raise ValueError('Foliage variant material layout differs from its source')
    for slot, material in zip(slots, replacements):
        slot.set_editor_property('material_interface', material)
    mesh.set_editor_property('static_materials', slots)
    if any(mesh.get_material(index) != material for index, material in enumerate(replacements)):
        raise ValueError('Foliage variant material bindings did not apply')


def write_representations(product, path, uv_channels, needed=('optimized','shadow','patch')):
    """@cc [owner:fontanierh,label:correctness;performance] bounded-foliage-serialization
    Transport MUST preserve every prepared float32 corner, slot and LOD exactly,
    use mesh_geometry's single shared writer/digest encoder and current native
    snapshot verification, stream without a whole-document string/DOM, and omit unrelated LOD geometry
    from shadow/patch inputs. It MUST NOT certify a source or runtime registry.
    """
    levels = dict(optimized=product['levels'], shadow=[product['shadow']], patch=[product['patch']])
    paths = {role:path.with_suffix('.'+role+'.mesh') for role in needed}
    geometry = {role:G.write_geometry(levels[role], uv_channels, destination) for role,destination in paths.items()}
    return paths, geometry


def memory_checkpoint(stage, path):
    """Observe this owned process at large allocation boundaries, without changing its guard."""
    try:
        result = subprocess.run(['ps', '-o', 'rss=', '-p', str(os.getpid())],
                                capture_output=True, text=True, check=True, timeout=2)
        U.log(f'FOLIAGE MEMORY {stage}: rss_mib={int(result.stdout.strip()) / 1024:.1f} {path}')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        U.log(f'FOLIAGE MEMORY {stage}: observation unavailable ({type(error).__name__}) {path}')


def saved_variants(mesh, paths, replacements, canopies, row, geometry, key):
    """Every unit hint and old partial output receives current native readback."""
    editor = settings_reader(U)
    dirty = {p.get_name() for p in U.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
    reused = {}
    for role, path in paths.items():
        if path in dirty or not E.does_asset_exist(path):
            continue
        candidate = E.load_asset(path)
        counts = row['triangles'] if role == 'optimized' else [row[role+'_triangles']]
        screens = F.SCREENS if role == 'optimized' else [1.]
        material_pair = (canopies[2], canopies[2]) if role == 'patch' else canopies[:2]
        if variant_matches(candidate, mesh, replacements, material_pair, counts, screens, geometry[role],
                           OUT/(key+'.'+role+'.snapshot'), editor=editor,
                           snapshot=U.YorimichiFoliageBuilder.export_geometry_snapshot, digest=G.file_digest,
                           refusal=lambda reason: U.log(f'FOLIAGE SAVED MISS {role} {path}: {reason}')):
            reused[role] = candidate
    return reused


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
                 yori.GAME/'unreal/Source/YorimichiImport/FoliageBuilder.h',
                 yori.GAME/'unreal/Source/YorimichiImport/MeshGeometrySnapshot.cpp',
                 yori.GAME/'unreal/Source/Yorimichi/Dev/FoliageSourceWriter.cpp',
                 yori.GAME/'unreal/Source/Yorimichi/Dev/FoliageSourceWriter.h',
                 yori.GAME/'unreal/Source/Yorimichi/Dev/FoliageGeometryReader.cpp',
                 yori.GAME/'unreal/Source/Yorimichi/Dev/FoliageGeometryReader.h',
                 OUT.parent/'unreal-modules/Yorimichi.json',
                 Path(unit_policy.__file__), yori.GAME/'foliage_unit_policy_witness.json',
                 Path(G.__file__), Path(__file__).with_name('foliage_variant_validation.py'), *runtime_files()]:
        algorithm.update(file.read_bytes())
    algorithm.update(U.SystemLibrary.get_engine_version().encode())
    algorithm.update(json.dumps(native_environment(native_context(yori.GAME.name)),sort_keys=True).encode())
    algorithm.update(json.dumps(dict(platform=sys.platform,architecture=platform.machine(),
                                     python=list(sys.version_info[:3])),sort_keys=True).encode())
    algorithm = algorithm.hexdigest()
    legacy = unit_policy.legacy_policies(yori.GAME,engine_version=U.SystemLibrary.get_engine_version(),
        environment=native_environment(native_context(yori.GAME.name)),
        runtime=dict(platform=sys.platform,architecture=platform.machine(),python=list(sys.version_info[:3])))
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
    counters = dict(unit_hits=0, published_hits=0, recertified_sources=0, reused_variants=0, built_variants=0)
    content = yori.GAME/'unreal/Content'
    for n, path in enumerate(candidates):
        mesh = E.load_asset(path)
        policy = classify(mesh,registry)
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
            counters['published_hits']+=1;counters['reused_variants']+=3
            U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} current: {path}')
            mesh=None
            U.YorimichiFoliageBuilder.collect_unused()
            continue
        key = F.asset_id(mesh.get_path_name())
        source_path, product_path = OUT/(key+'.source.json'), OUT/(key+'.json')
        before = digest(path)
        kind = F.category(mesh.get_name())
        destinations = {role:F.ROOT+'/Meshes/'+key+suffix for role,suffix in
                        (('optimized',''),('shadow','_Shadow'),('patch','_Patch'))}
        replacements = [blend_material(mesh.get_material(slot))
                        for slot in range(len(mesh.get_editor_property('static_materials')))]
        unit_path = OUT/'units'/(key+'.json')
        unit = G.load_unit(unit_path, identity=identity, policy=algorithm, content_root=content,
                           assets=list(destinations.values()))
        for old_policy in legacy:
            if unit is not None:break
            unit = G.load_unit(unit_path, identity=identity, policy=old_policy, content_root=content,
                               assets=list(destinations.values()))
        if unit:
            row, geometry = unit['metadata'], unit['geometry']
            try:
                required={'source','source_sha256','identity','kind','source_triangles','leaf_materials',
                          'triangles','shadow_triangles','patch_triangles','rigid_triangles','coverage',
                          'canopy_bounds','aggregate','output_sha256',*destinations}
                reusable = (set(row)>=required and isinstance(row['leaf_materials'],list) and
                            row['source']==mesh.get_path_name() and row['source_sha256']==before and
                            row['identity']==identity and row['kind']==kind and
                            row['source_triangles']==mesh.get_num_triangles(0) and set(geometry)==set(destinations))
                loaded = saved_variants(mesh,destinations,replacements,(near,far,patch_material),row,geometry,key) if reusable else {}
            except (AttributeError,KeyError,TypeError,ValueError):
                loaded = {}
            if len(loaded)==3 and all(row.get(role)==asset.get_path_name() for role,asset in loaded.items()):
                row['output_sha256']={role:digest(asset.get_path_name()) for role,asset in loaded.items()}
                records.append(row);materials.update(row['leaf_materials'])
                counters['unit_hits']+=1;counters['reused_variants']+=3
                G.save_unit(unit_path,identity=identity,policy=algorithm,content_root=content,
                            assets=list(destinations.values()),geometry=geometry,metadata=row)
                U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} unit readback accepted: {path}')
                loaded.clear();mesh=None
                U.YorimichiFoliageBuilder.collect_unused()
                continue
        U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} exporting: {path}')
        assert U.YorimichiFoliageSourceWriter.export_source(mesh, slots, classification, kind, str(source_path)), path
        source = json.loads(source_path.read_text())
        large_source = source_path.stat().st_size >= 32 * 1024 * 1024
        if large_source: memory_checkpoint('source loaded', path)
        source['rigid_lods'] = []
        if F.vegetation(mesh.get_name()):
            for level in range(1, len(F.SCREENS)):
                lod_path = OUT/(key+f'.rigid{level}.json')
                lod_index = round(level*(mesh.get_num_lods()-1)/(len(F.SCREENS)-1))
                assert U.YorimichiFoliageSourceWriter.export_source(mesh, slots, classification, kind, str(lod_path),lod_index), path
                source['rigid_lods'].append(json.loads(lod_path.read_text()))
            if kind == 'tree' and len(source['rigid_lods'][-1]['faces']) <= 256:
                source['far_proxy'] = source['rigid_lods'][-1]
        product = F.build(source)
        if large_source: memory_checkpoint('representations built', path)
        counts = [len(level['faces']) for level in product['levels']]
        detail = dict(shadow_triangles=len(product['shadow']['faces']),
                      rigid_triangles=product['rigid_triangles'], coverage=product['coverage'],
                      canopy_bounds=product['canopy_bounds'], triangles=counts,
                      patch_triangles=len(product['patch']['faces']))
        leaf_materials = [material['path'] for material in source['materials'] if material['foliage']]
        uv_channels=max(1,source['uv_channels'])
        absent=[role for role,path in destinations.items() if not E.does_asset_exist(path)]
        documents,geometry=write_representations(product,product_path,uv_channels,absent)
        levels=dict(optimized=product['levels'],shadow=[product['shadow']],patch=[product['patch']])
        for role in destinations:
            if role not in geometry:geometry[role]=G.expected_digest(levels[role],uv_channels)
        # Old partial products have no unit evidence: reproduce the CURRENT source
        # and preparation, then compare every saved corner before accepting them.
        loaded=saved_variants(mesh,destinations,replacements,(near,far,patch_material),detail,geometry,key)
        missing=[role for role in destinations if role not in loaded]
        if not missing:counters['recertified_sources']+=1
        counters['reused_variants']+=len(loaded)
        counters['built_variants']+=len(missing)
        U.log(f'FOLIAGE SAVED {path}: verified={len(loaded)} rebuild={missing}')
        repaired,checks=write_representations(product,product_path,uv_channels,[role for role in missing if role not in documents])
        assert all(checks[role]==geometry[role] for role in checks),path
        documents.update(repaired)
        del levels
        if large_source:memory_checkpoint('representations written',path)
        del source,product
        if large_source:memory_checkpoint('geometry released',path)
        for role in missing:
            document=documents[role]
            first,second=(patch_material,patch_material) if role=='patch' else (near,far)
            screens=F.SCREENS if role=='optimized' else [1.]
            result=U.YorimichiFoliageGeometryReader.build_variant(mesh,str(document),screens,destinations[role],first,second)
            assert result,destinations[role]
            bind_variant_materials(result,replacements)
            assert E.save_loaded_asset(result),destinations[role]
            expected=counts if role=='optimized' else [detail[role+'_triangles']]
            assert result.get_num_lods()==len(expected),destinations[role]
            assert [result.get_num_triangles(i) for i in range(len(expected))]==expected,(destinations[role],expected)
            assert variant_matches(result,mesh,replacements,(first,second),expected,screens,geometry[role],
                OUT/(key+'.'+role+'.built.snapshot'),editor=settings_reader(U),
                snapshot=U.YorimichiFoliageBuilder.export_geometry_snapshot,digest=G.file_digest,
                refusal=lambda reason:U.log(f'FOLIAGE BUILT MISS {role} {destinations[role]}: {reason}')),destinations[role]
            loaded[role]=result
        variants={role:asset.get_path_name() for role,asset in loaded.items()}
        assert digest(path)==before,('Foliage owner modified its source',path)
        materials.update(leaf_materials)
        row=dict(source=mesh.get_path_name(),source_sha256=before,kind=kind,
                 identity=identity,leaf_materials=leaf_materials,
                 output_sha256={k:digest(v) for k,v in variants.items()},
                 source_triangles=mesh.get_num_triangles(0),
                 aggregate=bool(detail['coverage']) and classification!='authored' and kind=='tree' and F.vegetation(mesh.get_name())
                           and 'palm' not in mesh.get_name().lower(),
                 **detail,**variants)
        G.save_unit(unit_path,identity=identity,policy=algorithm,content_root=content,
                    assets=list(destinations.values()),geometry=geometry,metadata=row)
        records.append(row)
        loaded.clear()
        U.log(f'FOLIAGE SYSTEM {n+1}/{len(candidates)} {path}: {records[-1]["triangles"]}')
        mesh=None;result=None
        U.YorimichiFoliageBuilder.collect_unused()
    assert records, 'No foliage sources were discovered'
    U.log('FOLIAGE PREPARATION COUNTS: '+json.dumps(counters,sort_keys=True))
    (OUT/'preparation-counts.json').write_text(json.dumps(dict(algorithm=algorithm,sources=len(records),**counters),indent=2)+'\n')
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
