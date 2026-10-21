"""Shared native adapter for validated mesh candidates, inside an ordinary import.

The owning recipe stages immutable candidates. This adapter only admits matching
geometry; callers still apply and validate current materials, roles and physics.
No guard, task stamp, donor checkout access or engine launch is performed here.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import mesh_reuse, paths
from .checkpoint_store import context, read_json, safe_destination


def observed_environment(ctx, current):
    """Bound unknown historical state to one receiving engine/SDK observation."""
    from .build_cache import atomic_json
    target = safe_destination(ctx.out, 'native-imports/environment.json')
    if target.exists():
        return read_json(target).get('context') == current
    if target.is_symlink():
        raise ValueError('Linked native receiving environment')
    try:
        engine = json.loads((ctx.unreal_root / 'Engine/Binaries/Mac/UnrealEditor.modules').read_text())
        native = json.loads((ctx.uproject.parent / 'Binaries/Mac/UnrealEditor.modules').read_text())
        if not engine.get('BuildId') or engine['BuildId'] != native.get('BuildId'):
            return False
    except (OSError, ValueError, KeyError):
        return False
    atomic_json(target, dict(schema=1, context=current, provenance='receiving-observation'))
    return True


def imported_source_matches(mesh, source):
    import unreal
    if not mesh:
        return False
    data = unreal.AssetRegistryHelpers.create_asset_data(mesh)
    tag = data.get_tag_value('SourceFile')
    return mesh_reuse.recorded_source_matches(tag, source)


class MeshReuse:
    """@cc [owner:fontanierh,label:correctness] native-mesh-candidate-admission
    Candidate reuse MUST require matching source/geometry policy and engine context,
    verified independent package copies, and Unreal's recorded import source hash.
    Captured old producer provenance MUST remain compatibility-only. Current native
    role, material and collision validation MUST still run before recording a receipt.
    Missing evidence MUST use ordinary import, never manufacture a cache hit or task stamp.
    """
    def __init__(self, ctx, task, script, functions, *, report_member=None, owner_script=None):
        from . import checkpoint_candidates
        self.ctx, self.task = ctx, task
        self.candidates = checkpoint_candidates
        self.content = ctx.uproject.parent / 'Content'
        self.script = Path(script).resolve()
        self.enabled = True
        try:
            self.policy = mesh_reuse.native_policy(self.script.read_text(), functions, self.script)
        except ValueError:
            self.enabled = False
            self.policy = mesh_reuse.identity({'reuse': 'unsupported-policy'})
        current_context = context(ctx)
        self.receipts = mesh_reuse.Receipts(ctx.out, task, current_context, self.policy, self.content)
        self.bundle = checkpoint_candidates.load(ctx, task) if self.enabled else None
        self.donor = {}
        self.pending = {}
        self.counts = dict(reused_local=0, reused_candidate=0, imported=0)
        self.compatible = False
        self.local_compatible = False
        try:
            if not self.enabled:
                raise ValueError('Unsupported native import policy')
            old = mesh_reuse.prior_stamp(ctx, task, os.environ.get('ATELIER_MESH_REUSE_NONCE'),
                                         os.environ.get('ATELIER_BUILD_PRIOR_STAMP'))
            if old is None:
                raise ValueError('No invocation-bound prior stamp')
            inputs = old['input_state']['inputs']
            if not isinstance(inputs, dict):
                raise ValueError('Malformed prior native inputs')
            relative_script = self.script.relative_to(paths.REPO).as_posix()
            previous = mesh_reuse.saved_source(paths.REPO, relative_script, inputs.get('<repo>/' + relative_script))
            owner_matches = True
            if owner_script:
                owner_script = Path(owner_script).resolve()
                relative_owner = owner_script.relative_to(paths.REPO).as_posix()
                owner = mesh_reuse.saved_source(paths.REPO, relative_owner, inputs.get('<repo>/' + relative_owner))
                owner_matches = owner is not None and mesh_reuse.identity(ast_dump(owner)) == mesh_reuse.identity(ast_dump(owner_script.read_text()))
            self.local_compatible = bool(not old.get('touched') and previous and owner_matches
                                         and mesh_reuse.native_policy(previous, functions, self.script, inputs=inputs) == self.policy
                                         and observed_environment(ctx, current_context))
            self.previous_fingerprint = old.get('fingerprint')
            self.previous_stamp = old
        except (OSError, ValueError, KeyError, TypeError, SyntaxError):
            pass
        if self.bundle:
            donor_source = mesh_reuse.revision_source(paths.REPO, self.bundle.get('source_revision'),
                self.script.relative_to(paths.REPO).as_posix())
            if donor_source:
                try:
                    self.compatible = mesh_reuse.native_policy(donor_source, functions, self.script,
                                                               revision=self.bundle.get('source_revision')) == self.policy
                except (ValueError, SyntaxError):
                    pass
            if self.compatible and owner_script:
                owner_name = Path(owner_script).resolve().relative_to(paths.REPO).as_posix()
                owner_source = mesh_reuse.revision_source(paths.REPO, self.bundle.get('source_revision'), owner_name)
                self.compatible = owner_source is not None and ast_dump(owner_source) == ast_dump(Path(owner_script).read_text())
            report = checkpoint_candidates.member_path(ctx, task, report_member, bundle=self.bundle) if report_member else None
            if report:
                self.donor = json.loads(report.read_text())

    def acquire(self, name, package, *, geometry, donor_geometry, sources, validator=None):
        """sources contains (logical package, current source file, expected SHA256)."""
        import unreal
        packages = [item[0] for item in sources]
        if package not in packages or len(set(packages)) != len(packages):
            raise ValueError('Mesh reuse requires a unique complete source/package group')
        source_hashes = {}
        for target, source, expected in sources:
            actual = mesh_reuse.digest(source)
            if actual != expected:
                raise ValueError('Current mesh source differs from its generator report: ' + name)
            source_hashes[target] = actual
        key = mesh_reuse.identity(dict(geometry=geometry, sources=source_hashes))
        self.pending[name] = dict(key=key, packages=packages, sources=sources,
                                  provenance={'kind': 'current-native-import'})
        if not self.enabled:
            return None
        local = self.receipts.matches(name, key, packages)
        if local:
            self.pending[name]['provenance'] = self.receipts.records[name].get('provenance', {'kind': 'compatibility-only'})
        if not local and not self.receipts.path.exists() and self.local_compatible and validator is not None:
            local = (all(unreal.EditorAssetLibrary.does_asset_exist(target) for target in packages)
                     and mesh_reuse.historical_packages_match(self.ctx, self.task, self.previous_stamp, packages))
            if local:
                self.pending[name]['provenance'] = dict(kind='compatibility-only', historical_task=self.previous_fingerprint)
        copied = False
        if not local:
            if not self.compatible or donor_geometry is None or geometry != donor_geometry:
                return None
            if any(unreal.EditorAssetLibrary.does_asset_exist(target) for target in packages):
                # An unproven existing package belongs to the normal importer;
                # candidate staging never replaces another completed scope.
                return None
            selected = []
            for target in packages:
                members = mesh_reuse.package_members(target)
                if any(os.path.lexists(safe_destination(self.content, member.removeprefix('content/')))
                       for member in members):
                    return None  # refuse orphan sidecars as well as primary packages
                if members[0] not in self.bundle['files']:
                    return None
                for member in members:
                    if member not in self.bundle['files']:
                        continue
                    source = self.candidates.member_path(self.ctx, self.task, member, bundle=self.bundle)
                    if source is None:
                        return None
                    destination = safe_destination(self.content, member.removeprefix('content/'))
                    selected.append((source, destination, self.bundle['files'][member]))
            # Prepare all sidecars and collision packages before any mesh load.
            self.content.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.mesh-import-', dir=self.content) as temporary:
                prepared = []
                for index, (source, destination, expected) in enumerate(selected):
                    temporary_file = Path(temporary) / str(index)
                    shutil.copyfile(source, temporary_file)
                    if (temporary_file.stat().st_size != expected['size']
                            or mesh_reuse.digest(temporary_file) != expected['sha256']):
                        return None
                    prepared.append((temporary_file, destination))
                for temporary_file, destination in prepared:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temporary_file, destination)
            unreal.AssetRegistryHelpers.get_asset_registry().scan_files_synchronous(
                [str(destination) for _, destination, _ in selected if destination.suffix == '.uasset'], True)
            copied = True
            self.pending[name]['provenance'] = dict(kind='compatibility-only',
                checkpoint=self.bundle['checkpoint'], donor_task=self.bundle['donor_task'],
                donor_fingerprint=self.bundle['donor_fingerprint'], source_revision=self.bundle['source_revision'])
        loaded = {target: unreal.load_asset(target) for target in packages}
        if any(not loaded[target] or not imported_source_matches(loaded[target], source)
               for target, source, _ in sources):
            return None
        if validator is not None and not validator(loaded[package]):
            return None
        self.counts['reused_candidate' if copied else 'reused_local'] += 1
        return loaded[package]

    def validated(self, name):
        """Queue after current native checks; the successful host publishes receipts."""
        self.defer_validated(name)

    def imported(self, name=None):
        self.counts['imported'] += 1
        if name is not None:
            self.pending[name]['provenance'] = {'kind': 'current-native-import'}

    def defer_validated(self, name):
        """The common boundary defers final package inventory until its owner exits."""
        import unreal
        value = self.pending.pop(name)
        nonce = os.environ.get('ATELIER_MESH_REUSE_NONCE')
        if nonce is None or not self.enabled:
            return
        record = None
        if all(imported_source_matches(unreal.load_asset(target), source)
               for target, source, _ in value['sources']):
            record = dict(key=value['key'], packages=value['packages'], provenance=value['provenance'],
                native_source_validated=True, sources=[dict(package=target, member=mesh_reuse.source_member(self.ctx, source),
                    sha256=expected) for target, source, expected in value['sources']])
        mesh_reuse.queue_pending(self.ctx, self.task, nonce, self.policy, self.receipts.header['context'],
                                name, record, self.counts)

    def finish(self):
        from .build_cache import atomic_json
        result = dict(schema=1, task=self.task, counts=self.counts,
                      donor_checkpoint=self.bundle.get('checkpoint') if self.bundle else None,
                      donor_provenance=self.bundle.get('provenance') if self.bundle else None)
        atomic_json(self.ctx.out / 'native-imports' / self.task / 'summary.json', result)
        print('NATIVE MESH REUSE ' + json.dumps(result, sort_keys=True), flush=True)


def ast_dump(source):
    import ast
    return ast.dump(ast.parse(source), include_attributes=False)


class AssetGroup:
    """@cc [owner:fontanierh,label:correctness] unchanged-native-asset-group
    Skipping a material/texture builder MUST require a receipt for its current
    parameters, all source/support bytes, engine context and complete saved packages.
    Historical candidates MUST NOT bootstrap this receipt. A new receipt MUST follow
    successful native loads and saves of every owned asset in the group.
    """
    def __init__(self, ctx, task, script, functions, *, parameters, sources=(), support=()):
        import_policy = mesh_reuse.identity(dict(
            code=mesh_reuse.native_policy(Path(script).read_text(), functions, script),
            support=[mesh_reuse.digest(file) for file in support]))
        self.book = mesh_reuse.Receipts(ctx.out, task + '.assets', context(ctx), import_policy,
                                        ctx.uproject.parent / 'Content')
        self.key = mesh_reuse.identity(dict(parameters=parameters,
            sources=[mesh_reuse.digest(file) for file in sources]))
        self.ctx, self.task = ctx, task + '.assets'
        self.sources = [Path(script), *map(Path, sources), *map(Path, support)]

    def matches(self, packages):
        return self.book.matches('assets', self.key, packages)

    def validated(self, packages):
        import unreal
        for package in packages:
            asset = unreal.load_asset(package)
            if not asset or not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=True):
                raise RuntimeError('Native asset group could not save ' + package)
        nonce = os.environ.get('ATELIER_MESH_REUSE_NONCE')
        if nonce:
            record = dict(kind='asset-group', key=self.key, packages=packages, native_assets_validated=True,
                provenance={'kind': 'current-native-import'}, sources=[
                    dict(member=mesh_reuse.source_member(self.ctx, file), sha256=mesh_reuse.digest(file))
                    for file in self.sources])
            mesh_reuse.queue_pending(self.ctx, self.task, nonce, self.book.header['policy'],
                                    self.book.header['context'], 'assets', record, {'rebuilt': 1})


def set_if_changed(asset, name, value):
    """Avoid dirtying a package when a current native setting already matches."""
    if asset.get_editor_property(name) != value:
        asset.set_editor_property(name, value)
    if asset.get_editor_property(name) != value:
        raise RuntimeError('Native property did not persist: ' + name)


def lods_match(mesh, plan):
    """Validate saved reduction and screen settings before skipping regeneration."""
    import unreal
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None or editor.get_lod_count(mesh) != len(plan):
        return False
    screens = editor.get_lod_screen_sizes(mesh)
    return (len(screens) == len(plan)
            and all(abs(float(actual) - screen) < 1e-5 for actual, (_, screen) in zip(screens, plan))
            and all(abs(float(editor.get_lod_reduction_settings(mesh, index).get_editor_property('percent_triangles'))
                        - percent) < 1e-5 for index, (percent, _) in enumerate(plan)))


_LEGACY = {}


def common_fbx_mesh(source, destination, name, *, seed, fresh_slots, script, validator):
    """Default shared FBX boundary; unknown owner/provenance simply imports normally."""
    task, game = os.environ.get('ATELIER_BUILD_TASK'), os.environ.get('ATELIER_BUILD_GAME')
    owner = os.environ.get('ATELIER_BUILD_SCRIPT') or os.environ.get('ATELIER_SCRIPT')
    nonce = os.environ.get('ATELIER_MESH_REUSE_NONCE')
    if not task or not game or not owner or not nonce:
        return None, None
    key = (task, game, owner, nonce, str(script))
    if key not in _LEGACY:
        from .build import Context
        _LEGACY[key] = MeshReuse(Context(game), task, script, ('_import_mesh',), owner_script=owner)
    reuse = _LEGACY[key]
    package = destination + '/' + name
    inputs = dict(format='legacy-fbx', fresh_slots=bool(fresh_slots), seed_sha256=mesh_reuse.digest(seed))
    mesh = reuse.acquire(package, package, geometry=inputs, donor_geometry=inputs,
                         sources=[(package, Path(source), mesh_reuse.digest(source))], validator=validator)
    return mesh, reuse
