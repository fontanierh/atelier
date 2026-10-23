"""Paired real foliage owner fixture. No native work runs on import.

Source-only preparation freezes the production bodies/inputs; parent owns native admission.
The only source adaptation is a finite reversible literal package namespace map.
"""
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import types

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'tools'), str(Path(__file__).parent)]
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atomic_equivalence_io import artifact, canonical, require  # noqa: E402
from track_native_equivalence import (actor_scope, assets, bound_inputs as common_inputs, check_input, fixture_files,  # noqa: E402
    native_raw_set, receiving_startup, release_actor, retire_owned, sha, whole_bounds, FIELDS)

OWNER_COUNT, AUTHORED_LODS, SOURCE_LODS, NATIVE_PACKAGES, NATIVE_PAGES = 18, 84, 66, 84, 150
# Exact current unchanged production sources; no computed/new importer declaration is admitted.
MAPPED = {
    'asset_catalog': ('world/asset_catalog.py', 'c56a3afcea30d1cb71dccf8784ad29a64396e6303229d45a048e49cde07ad677'),
    'material_assets': ('unreal/Scripts/material_assets.py', '4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f'),
    'see_through': ('unreal/Scripts/see_through.py', '9d7da40163a6e4023d91e8fc2aaacdd2578bf07ef02f05b4e10dcc1c4c8fd105'),
    'shared_materials': ('unreal/Scripts/shared_materials.py', '8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720'),
    'import_foliage_lods': ('unreal/Scripts/import_foliage_lods.py', '0a9650d53181c670fee40733ace3649f2ca1092c0a674920f2d88294135ebc6b'),
    'foliage_package_repair': ('unreal/Scripts/foliage_package_repair.py', '90a923ef949e7e4ba5139ebf0c3c6b60ffc52ff5084ead34bdc6543912ed427b'),
    'import_foliage': ('unreal/Scripts/import_foliage.py', 'cbf3a5e2466195c52e21cb87cabd199ef10398c5553b2a03fc21d784ac17bee9'),
}


def bound_inputs(spec):
    common_inputs(spec)
    require(isinstance(spec.get('absent_inputs'),list),'Missing optional engine-data absence inventory')
    for path in spec['absent_inputs']:
        real_directory(Path(path).parent)
        require(not os.path.lexists(path),'Previously absent engine material companion appeared')


def mapped_tree(name, source, package):
    """@cc [owner:fontanierh,label:correctness] exact-foliage-fixture-namespace
    Only SHA-pinned original bodies MAY run, with exhaustive reversible literal
    Japan/SeeThrough/header-path translation and exact final dispatch removal.
    Geometry, shader, material, collision, LOD and save bodies MUST remain unchanged.
    """
    require(name in MAPPED and re.fullmatch(r'/Game/AtelierValidation/Foliage_[0-9a-f]{12}', package),
            'Unknown source or nonexclusive foliage namespace')
    relative, digest = MAPPED[name]; path = Path(source) / relative
    require(sha(path) == digest, 'Changed production foliage source: ' + name)
    tree = ast.parse(path.read_bytes()); original = ast.dump(tree); changed = []
    # Only the two real script dispatches are removed, never an arbitrary final statement.
    dispatch = None
    if name in ('shared_materials', 'import_foliage'):
        dispatch = tree.body.pop()
        require(isinstance(dispatch, ast.If) and ast.dump(dispatch) == ast.dump(ast.parse(
            "if __name__ == '__main__':\n    main()\n").body[0]), 'Changed production final dispatch')
    prefixes = {'/Game/Japan': package + '/Japan', '/Game/SeeThrough': package + '/SeeThrough'}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str): continue
        before = node.value
        for prefix, target in prefixes.items():
            if before == prefix or before.startswith(prefix + '/'):
                node.value = target + before.removeprefix(prefix); changed.append((node, before)); break
        else:
            if name == 'foliage_package_repair' and before == 'Japan/Assets':
                node.value = package.removeprefix('/Game/') + '/Japan/Assets'; changed.append((node, before))
        # Runtime project paths have only the two proven literal families.
        if before.startswith('/Game/'):
            require(any(before == p or before.startswith(p + '/') for p in prefixes), 'Unmapped production project path')
    require(changed, 'Expected exact namespace literals are absent')
    mapped = ast.dump(tree)
    for node, value in changed: node.value = value
    if dispatch is not None: tree.body.append(dispatch)
    require(ast.dump(tree) == original, 'Namespace transform changed other production AST')
    # Return a fresh mapped tree; the checked original AST stays independent.
    restored = ast.parse(path.read_bytes())
    if dispatch is not None: restored.body.pop()
    for node in ast.walk(restored):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str): continue
        for prefix, target in prefixes.items():
            if node.value == prefix or node.value.startswith(prefix + '/'):
                node.value = target + node.value.removeprefix(prefix); break
        else:
            if name == 'foliage_package_repair' and node.value == 'Japan/Assets':
                node.value = package.removeprefix('/Game/') + '/Japan/Assets'
    require(ast.dump(restored) == mapped, 'Nondeterministic namespace transform')
    return ast.fix_missing_locations(restored)


def catalog_literal(name):
    path = GAME / MAPPED['asset_catalog'][0]
    require(sha(path) == MAPPED['asset_catalog'][1], 'Changed actual owner catalogue')
    tree = ast.parse(path.read_bytes())
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


def owner_names():
    return catalog_literal('FOLIAGE')


def inventory(manifests):
    require(isinstance(manifests, dict) and len(manifests) == OWNER_COUNT and set(manifests) == set(owner_names()), 'Incomplete eighteen-owner manifest census')
    rows = {}
    for name, data in manifests.items():
        require(re.fullmatch(r'(Tree|Bush|Grass)_[A-Za-z0-9_]+', name), 'Foreign foliage owner')
        require(isinstance(data,dict) and {'screen_sizes','triangles','collision','import_trunk_collision','materials'} <= set(data),
                'Missing actual foliage manifest fields')
        levels = len(data['screen_sizes'])
        require(levels in (3, 6) and len(data['triangles']) == levels and all(type(n) is int and n > 0 for n in data['triangles'])
                and data['collision'] in ('complex', 'default') and data['import_trunk_collision'] is False
                and data['materials'] and isinstance(data['materials'], list), 'Invalid actual foliage manifest')
        require((name.startswith('Tree_') and levels == 6) or (not name.startswith('Tree_') and levels == 3),
                'Unexpected authored foliage chain')
        canonical(data); rows[name] = dict(owner=name, lods=levels, placed=True, query_only=name.startswith('Tree_'), collision=data['collision'])
        for level in range(1, levels):
            rows[f'{name}_LOD{level}'] = dict(owner=name, lods=1, placed=False, query_only=False, collision=data['collision'])
    require(sum(len(d['screen_sizes']) for d in manifests.values()) == AUTHORED_LODS
            and len(rows) == NATIVE_PACKAGES and sum(row['lods'] for row in rows.values()) == NATIVE_PAGES,
            'Missing assembled or source-LOD native pages')
    return rows


def query_plan(name, item):
    rows=[]
    for mode in ('complex','simple'):
        positive=item['query_only'] and (mode=='complex' or item['collision']=='complex')
        for kind in (('positive','negative') if positive else ('negative',)):
            for shape in ('ray','capsule'):
                rows.append(dict(id=name+'.'+mode+'.'+shape+'.'+kind, kind=shape+'_'+kind,
                                 mode=mode))
    return rows


def validate_controls(controls, manifests):
    expected = inventory(manifests)
    require(set(controls) == set(expected), 'Missing primary/source-LOD query census')
    for name, item in expected.items():
        plan=query_plan(name,item);values=controls[name]
        require(len(values)==len(plan) and [v['id'] for v in values]==[v['id'] for v in plan]
                and [v['kind'] for v in values]==[v['kind'] for v in plan], 'Incomplete foliage query controls')
        canonical(values)
        for value,planned in zip(values,plan):
            require(set(value) == {'id', 'kind', 'input'} and value['input']['channel'] == 'Pawn'
                    and value['input']['trace_complex'] is (planned['mode']=='complex')
                    and value['input']['start'] != value['input']['end'], 'Malformed source-derived query control')
            query = value['input']; capsule = value['kind'].startswith('capsule')
            fields = {'start','end','channel','trace_complex'} | ({'radius_cm','half_height_cm','orientation'} if capsule else set())
            require(set(query) == fields and all(isinstance(query[k], list) and len(query[k]) == 3
                    and all(type(x) in (int, float) for x in query[k]) for k in ('start','end')), 'Malformed foliage query input')
            if capsule:
                require(type(query['radius_cm']) in (int,float) and type(query['half_height_cm']) in (int,float)
                    and 0 < query['radius_cm'] <= query['half_height_cm'] and query['orientation'] == [0.,0.,0.,1.]
                    and all(type(x) in (int,float) for x in query['orientation']), 'Malformed actual capsule parameters')


@contextmanager
def production_modules(spec):
    source = Path(spec['source']) / 'games/yorimichi'; package = spec['package']
    order = ('asset_catalog', 'material_assets', 'see_through', 'shared_materials',
             'import_foliage_lods', 'foliage_package_repair', 'import_foliage')
    trees = {name: mapped_tree(name, source, package) for name in order}  # All proofs precede execution.
    saved = {name: sys.modules.get(name) for name in order}
    original_yori = {key: getattr(yori, key) for key in ('OUT','TEXTURES','GAME')}
    sys.path[:0] = [str(source / 'unreal/Scripts'), str(source / 'world')]
    try:
        yori.OUT = Path(spec[spec['phase'] + '_data']); yori.TEXTURES = Path(spec['textures'])
        yori.GAME = Path(spec['receiving']) / 'games/yorimichi'
        for name in order:
            module = types.ModuleType(name); module.__file__ = str(source / MAPPED[name][0]); sys.modules[name] = module
            exec(compile(trees[name], module.__file__, 'exec'), module.__dict__)
        yield {name: sys.modules[name] for name in order}
    finally:
        for name, value in saved.items():
            if value is None: sys.modules.pop(name, None)
            else: sys.modules[name] = value
        for key, value in original_yori.items(): setattr(yori, key, value)


def validate_component_policy(policy,item):
    require(policy.get('collision_enabled') == int(item['query_only']) and policy.get('object_channel') == 0,
            'Actual fixture collision flag/object channel differs')
    responses=policy.get('responses')
    require(isinstance(responses,list) and len(responses)>4 and responses[2]==2
            and responses[4]==(0 if item['placed'] else 2), 'Actual Pawn/Camera collision responses differ')


def component_collision(record,item):
    require(len(record['component_policies'])==1,'One real component policy required per native package')
    validate_component_policy(json.loads(artifact(record['component_policies'][0])),item)


def compare(records, manifests):
    expected = inventory(manifests)
    require(set(records) == {'original','current'} and all(set(v) == set(expected) for v in records.values()),
            'Incomplete paired actual foliage native census')
    result = {}
    for name, item in expected.items():
        old, new = records['original'][name], records['current'][name]
        require(old['policy_scope'] == new['policy_scope'] == 'fixture' and whole_bounds(old) == whole_bounds(new),
                name + ' actual whole bounds/scope differs')
        component_collision(old,item);component_collision(new,item)
        a, b = native_raw_set(old, name), native_raw_set(new, name)
        require(not a['hulls'] and not b['hulls'],name + ' current disabled-trunk policy retained hulls')
        require(set(a['render_lods']) == set(b['render_lods']) == set(range(item['lods'])), name + ' missing actual LODs')
        for observed in (a,b):
            require(set(observed['source_lods']) == set(range(item['lods']))
                and set(observed['source_presence']) == set(range(item['lods']))
                and all(observed['source_presence'][level] == {True} and observed['source_lods'][level]
                        for level in range(item['lods'])), name + ' missing authored saved MeshDescription')
        for key in FIELDS: require(a[key] == b[key], name + ' native ' + key + ' differs')
        require(a['probes'] == b['probes'], name + ' native query policy/results differ')
        rows = a['probes']['controls']; plan=query_plan(name,item)
        require(len(rows)==len(plan) and [r['id']for r in rows]==[r['id']for r in plan]
                and [r['kind']for r in rows]==[r['kind']for r in plan]
                and all(row['kind'].endswith('_negative') == (row['hit'] is None) for row in rows),
                name + ' actual simple/complex query positive/negative controls failed')
        result[name] = dict(lods=item['lods'], owner=item['owner'], placed_fixture=item['placed'], exact=True)
    return dict(schema=1, native_geometry_complete=True, owners=OWNER_COUNT, authored_lods=AUTHORED_LODS,
        source_lod_packages=SOURCE_LODS, native_packages=NATIVE_PACKAGES, native_pages=NATIVE_PAGES,
        complete=False, native_complete=False, production_runtime_complete=False, normal_native_reuse=False,
        assets=result, scope='Real foliage owner/materials in mapped fixture namespace; no placement/HISM/game/cook/task-reuse claim')


def require_fixture_context(environment):
    require(not environment.get('ATELIER_BUILD_TASK') and not environment.get('ATELIER_MESH_REUSE_NONCE'),
            'Fixture cannot inherit a normal task/receipt publication context')


def camera_ignore(U):
    """ECollisionResponse exports as CollisionResponseType, not the response struct."""
    response=getattr(getattr(U,'CollisionResponseType',None),'ECR_IGNORE',None)
    require(response is not None,'Installed Unreal CollisionResponseType.ECR_IGNORE is unavailable')
    return response


def run_native(spec_path, digest):
    import unreal as U
    require_fixture_context(os.environ)
    ignored_camera=camera_ignore(U)  # Refuse unsupported reflection before any asset mutation.
    spec_path = Path(spec_path).absolute(); spec = json.loads(artifact(dict(path=str(spec_path),sha256=digest)))
    bound_inputs(spec); startup = receiving_startup(spec,U); output = real_directory(spec['output'])
    atomic_json(output / 'startup-ddc.json', startup)
    package = spec['package']; require(re.fullmatch(r'/Game/AtelierValidation/Foliage_[0-9a-f]{12}',package), 'Foreign fixture')
    content = Path(spec['content']); require(Path(U.Paths.project_content_dir()).resolve() == content.resolve(), 'Wrong project Content')
    folder = real_directory(content / package.removeprefix('/Game/'))
    E = U.EditorAssetLibrary; require(not os.path.lexists(folder) and not assets(E,package), 'Fresh exclusive fixture required')
    manifests = spec['manifests']; expected = inventory(manifests); validate_controls(spec['controls'], manifests)
    for key, value in spec['textures_input'].items(): check_input(key,value)
    api=getattr(U,'NativeAtomicEquivalence',None)
    require(api is not None and all(callable(getattr(api,name,None))for name in('snapshot','component_policy','probe')),
            'Actual compiled native readback API missing before fixture mutation')
    actors = []; actor_editor = U.get_editor_subsystem(U.EditorActorSubsystem)
    require(actor_editor is not None, 'Missing editor actors')
    require(U.EditorLoadingAndSavingUtils.new_blank_map(False) is not None, 'Missing query physics world')
    U.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    U.SystemLibrary.execute_console_command(None, 'MessageLog.DisablePopup 1')
    require(U.SystemLibrary.get_console_variable_int_value('MessageLog.DisablePopup') == 1, 'Missing modal-only suppression')
    partial = lambda: dict(package=package,observed_packages=sorted(assets(E,package)))
    with actor_scope(actors,actor_editor,U.StaticMeshComponent,output,partial), production_modules(spec) as modules:
        import atomic_equivalence_capture as capture
        modules['shared_materials'].main()  # Entire genuine shader/interface owner; no replacement graphs.
        shared = set(modules['asset_catalog'].shared_packages())
        require(assets(E,package) == shared, 'Actual material owner emitted incomplete/foreign package membership')
        for index, name in enumerate(sorted(manifests)):
            os.environ['ATELIER_FOLIAGE'] = name
            modules['import_foliage'].main()  # Unchanged actual main + complete apply_lods/material/save checks.
            report = json.loads((yori.OUT / 'imports/foliage' / (name+'.json')).read_bytes())
            require(report['triangles'] == manifests[name]['triangles'], 'Actual owner report changed authored chain')
            print('FOLIAGE ACTUAL OWNER '+name+' '+str(index+1)+'/18',flush=True)
        paths = {name:package+'/Japan/Assets/'+name if item['placed'] else
                 package+'/Japan/FoliageLODs/'+item['owner']+'/'+name for name,item in expected.items()}
        crowns = {package+'/Japan/FoliageLODs/'+name+'/MI_'+data['crown']['slot']
                  for name,data in manifests.items() if data.get('crown')}
        allowed = shared | set(paths.values()) | crowns
        require(assets(E,package) == allowed, 'Missing or unowned foliage package before receiving proof')
        loaded = [E.load_asset(path) for path in paths.values()]; require(all(loaded), 'Missing native source/base packages')
        require(E.save_loaded_assets(loaded,only_if_is_dirty=True), 'Saved native packages failed')
        packages = [mesh.get_outermost() for mesh in loaded]; loaded.clear()
        changed,error = U.EditorLoadingAndSavingUtils.reload_packages(packages,U.ReloadPackagesInteractionMode.ASSUME_POSITIVE)
        require(changed and not str(error), 'Saved actual package reload failed');packages.clear();U.SystemLibrary.collect_garbage()
        records = {}
        for index,(name,item) in enumerate(sorted(expected.items())):
            mesh = E.load_asset(paths[name]);require(mesh is not None and mesh.get_num_lods()==item['lods'], 'Incomplete saved chain')
            actor = actor_editor.spawn_actor_from_class(U.StaticMeshActor,U.Vector(0,0,0));require(actor is not None,'No fixture actor')
            actors.append(actor); component = actor.get_component_by_class(U.StaticMeshComponent)
            component.set_mobility(U.ComponentMobility.MOVABLE);require(component.set_static_mesh(mesh),'Mesh assignment failed')
            component.set_collision_profile_name('BlockAll');component.set_collision_enabled(
                U.CollisionEnabled.QUERY_ONLY if item['query_only'] else U.CollisionEnabled.NO_COLLISION)
            component.set_editor_property('can_ever_affect_navigation',False)
            require(component.get_editor_property('can_ever_affect_navigation') is False,'Navigation fixture flag differs')
            if item['placed']: component.set_collision_response_to_channel(U.CollisionChannel.ECC_CAMERA,ignored_camera)
            controls=[dict(row,target=component.get_path_name()) for row in spec['controls'][name]]
            descriptor=capture.capture([component],name,output/'captures'/name,controls=controls,inputs=[spec_path],policy_scope='fixture')
            component_collision(descriptor,item)
            archived=[]
            for row in descriptor['saved_packages']:
                source=Path(row['path']);target=output/'saved-packages'/(hashlib.sha256(str(source).encode()).hexdigest()+source.suffix)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                require(sha(source)==sha(target)==row['sha256'],'Saved native archive bytes differ')
                archived.append(dict(path=str(target),sha256=row['sha256']))
            descriptor['saved_packages']=archived;records[name]=descriptor
            release_actor(actor,actor_editor,U.StaticMeshComponent,actors);mesh=None;component=None
            print('FOLIAGE ACTUAL SAVED CAPTURE '+name+' '+str(index+1)+'/84',flush=True)
        bound_inputs(spec)
        atomic_json(output/'native.json',{spec['phase']:records})
        retire_owned(U,allowed,allowed)
        atomic_json(output/'cleanup.json',dict(root=str(folder),allowed_packages=sorted(allowed),
            remaining=fixture_files(folder,allowed,package)))
    print('FOLIAGE ACTUAL18/84/150 NATIVE FIXTURE COMPLETE '+spec['phase']+' '+digest,flush=True)


if __name__ == '__main__':
    run_native(os.environ['ATELIER_FOLIAGE_NATIVE_SPEC'],os.environ['ATELIER_FOLIAGE_NATIVE_SHA256'])
