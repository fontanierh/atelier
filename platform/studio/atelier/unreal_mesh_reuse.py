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
from .native_protocol import context, read_json, safe_destination, native_context, atomic_json, runtime_files


def observed_environment(ctx, current):
    """Bound unknown historical state to one receiving engine/SDK observation."""
    target = safe_destination(ctx.out, 'native-imports/environment.json')
    if target.exists():
        saved = read_json(target)
        return isinstance(saved, dict) and saved.get('schema') == 1 and saved.get('context') == current
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
    """Read UE's UObject::SourceFileTagName(), whose registry key is AssetImportData."""
    import unreal
    if not mesh:
        return False
    data = unreal.AssetRegistryHelpers.create_asset_data(mesh)
    tag = data.get_tag_value('AssetImportData')
    return mesh_reuse.recorded_source_matches(tag, source)


def packages_clean(packages):
    """On-disk receipts cannot justify returning an owner-mutated in-memory package."""
    import unreal
    try:
        dirty = {package.get_name() for package in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()}
        return not dirty.intersection(packages)
    except (AttributeError, TypeError, RuntimeError):
        return False


class MeshReuse:
    """@cc [owner:fontanierh,label:correctness] native-mesh-candidate-admission
    Candidate reuse MUST require matching source/geometry policy and engine context,
    verified independent package copies, and Unreal's recorded import source hash.
    Captured old producer provenance MUST remain compatibility-only. Current native
    role, material and collision validation MUST still run before recording a receipt.
    Dirty loaded packages MUST miss even when their on-disk receipt matches. Owner finishing
    MUST rerun from current data after reuse and validate current materials, roles and collision.
    Current validation code MAY differ from historical geometry code, but its declared closure
    MUST enter fresh receipt identity. It MUST NOT weaken historical raw-geometry equality.
    Missing evidence MUST use ordinary import, never manufacture a cache hit or task stamp.
    """
    def __init__(self, ctx, task, script, functions, *, report_member=None, owner_script=None, owner_roots=(),
                 validation_script=None, validation_functions=()):
        from . import native_candidates as checkpoint_candidates
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
        validation_policy = None
        self.requires_validator = bool(validation_functions or validation_script is not None)
        if self.requires_validator:
            try:
                validator = Path(validation_script or self.script).resolve()
                if not validator.is_relative_to(paths.REPO.resolve()):
                    raise ValueError('Validation policy must belong to the repository')
                validation_policy = mesh_reuse.native_policy(validator.read_text(), validation_functions, validator)
            except (OSError, ValueError, SyntaxError, TypeError):
                self.enabled = False
        self.owner_sources = {}
        if owner_script:
            from . import source_imports
            owner_script = Path(owner_script).resolve()
            # Game-side finishing is part of the saved asset's identity. The
            # shared FBX boundary has its separate geometry policy above.
            self.owner_sources = {file.relative_to(paths.REPO).as_posix(): ast_dump(file.read_text())
                for file in source_imports.local_imports(owner_script, owner_roots)
                if file != self.script and file not in runtime_files() and file.is_relative_to(paths.REPO)}
        receipt_policy = (mesh_reuse.identity(dict(geometry=self.policy, owner=self.owner_sources))
                          if owner_script else self.policy)
        if validation_policy is not None:
            receipt_policy = mesh_reuse.identity(dict(import_policy=receipt_policy, validation=validation_policy))
        current_context = context(ctx)
        self.receipts = mesh_reuse.Receipts(ctx.out, task, current_context, receipt_policy, self.content)
        self.bundles = checkpoint_candidates.load_all(ctx, task) if self.enabled else []
        self.bundle = self.bundles[0] if self.bundles else None
        self.histories = []
        self.donor = {}
        self.pending = {}
        self.counts = dict(reused_local=0, reused_candidate=0, imported=0)
        self.miss_reasons = {}
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
                for relative_owner, current in self.owner_sources.items():
                    owner = mesh_reuse.saved_source(paths.REPO, relative_owner, inputs.get('<repo>/' + relative_owner))
                    owner_matches &= owner is not None and ast_dump(owner) == current
            self.local_compatible = bool(not old.get('touched') and previous and owner_matches
                                         and mesh_reuse.native_policy(previous, functions, self.script, inputs=inputs) == self.policy
                                         and observed_environment(ctx, current_context))
            self.previous_fingerprint = old.get('fingerprint')
            self.previous_stamp = old
        except (OSError, ValueError, KeyError, TypeError, SyntaxError):
            pass
        for bundle in self.bundles:
            compatible, donor = False, {}
            try:
                # Captured HEAD identifies the capture only. The original producing
                # task's per-file identities identify the geometry/finishing policy.
                donor_inputs = bundle['donor_stamp']['input_state']['inputs']
                if not isinstance(donor_inputs, dict):
                    raise ValueError('Missing original donor input evidence')
                relative_script = self.script.relative_to(paths.REPO).as_posix()
                donor_source = mesh_reuse.saved_source(paths.REPO, relative_script,
                                                       donor_inputs.get('<repo>/' + relative_script))
                if donor_source:
                    compatible = mesh_reuse.native_policy(donor_source, functions, self.script,
                                                           inputs=donor_inputs) == self.policy
                if compatible and owner_script:
                    for owner_name, current in self.owner_sources.items():
                        owner_source = mesh_reuse.saved_source(paths.REPO, owner_name,
                                                              donor_inputs.get('<repo>/' + owner_name))
                        compatible &= owner_source is not None and ast_dump(owner_source) == current
                report = checkpoint_candidates.member_path(ctx, task, report_member, bundle=bundle) if report_member else None
                if report:
                    donor = json.loads(report.read_text())
                    if not isinstance(donor, dict):
                        raise ValueError('Malformed original donor report')
            except (OSError, ValueError, KeyError, TypeError, SyntaxError):
                compatible = False

            self.histories.append((bundle, donor, compatible))
        if self.histories:
            self.donor = self.histories[0][1]
            self.compatible = any(item[2] for item in self.histories)

    def acquire(self, name, package, *, geometry, donor_geometry, sources, validator=None):
        """sources contains (logical package, current source file, expected SHA256).

        donor_geometry may be a report projection, evaluated separately for each independent
        donor. A complete source/collision group is always selected from one donor, never spliced.
        """
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
            return self.miss('unsupported_policy')
        if self.requires_validator and validator is None:
            return self.miss('required_validator_missing')
        if not packages_clean(packages):
            return self.miss('dirty_loaded_package')
        local = self.receipts.matches(name, key, packages)
        historical = False
        if local:
            self.pending[name]['provenance'] = self.receipts.records[name].get('provenance', {'kind': 'compatibility-only'})
        if not local and not self.receipts.path.exists() and self.local_compatible and validator is not None:
            local = (all(unreal.EditorAssetLibrary.does_asset_exist(target) for target in packages)
                     and mesh_reuse.historical_packages_match(self.ctx, self.task, self.previous_stamp, packages))
            if local:
                self.pending[name]['provenance'] = dict(kind='compatibility-only', historical_task=self.previous_fingerprint)
                historical = True
        copied = False
        if not local:
            if not self.compatible:
                reason = ('saved_receipt_mismatch' if self.receipts.path.exists() else
                          'local_package_history_mismatch' if self.local_compatible else
                          'no_compatible_package_history')
                return self.miss(reason)
            bundle = None
            geometry_matches = False
            for candidate, report, compatible in self.histories:
                if not compatible:
                    continue
                try:
                    previous = donor_geometry(report) if callable(donor_geometry) else donor_geometry
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
                if previous is None or geometry != previous:
                    continue
                geometry_matches = True
                if all(mesh_reuse.package_members(target)[0] in candidate['files'] for target in packages):
                    bundle = candidate
                    break
            if bundle is None:
                return self.miss('candidate_package_missing' if geometry_matches else 'candidate_geometry_mismatch')
            if any(unreal.EditorAssetLibrary.does_asset_exist(target) for target in packages):
                # An unproven existing package belongs to the normal importer;
                # candidate staging never replaces another completed scope.
                return self.miss('unproved_existing_package')
            selected = []
            for target in packages:
                members = mesh_reuse.package_members(target)
                if any(os.path.lexists(safe_destination(self.content, member.removeprefix('content/')))
                       for member in members):
                    return self.miss('unproved_disk_sidecar')
                if members[0] not in bundle['files']:
                    return self.miss('candidate_package_missing')
                for member in members:
                    if member not in bundle['files']:
                        continue
                    source = self.candidates.member_path(self.ctx, self.task, member, bundle=bundle)
                    if source is None:
                        return self.miss('candidate_member_missing')
                    destination = safe_destination(self.content, member.removeprefix('content/'))
                    selected.append((source, destination, bundle['files'][member]))
            # Prepare all sidecars and collision packages before any mesh load.
            self.content.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.mesh-import-', dir=self.content) as temporary:
                prepared = []
                for index, (source, destination, expected) in enumerate(selected):
                    temporary_file = Path(temporary) / str(index)
                    shutil.copyfile(source, temporary_file)
                    if (temporary_file.stat().st_size != expected['size']
                            or mesh_reuse.digest(temporary_file) != expected['sha256']):
                        return self.miss('candidate_copy_mismatch')
                    prepared.append((temporary_file, destination))
                for temporary_file, destination in prepared:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temporary_file, destination)
            unreal.AssetRegistryHelpers.get_asset_registry().scan_files_synchronous(
                [str(destination) for _, destination, _ in selected if destination.suffix == '.uasset'], True)
            copied = True
            self.pending[name]['provenance'] = dict(kind='compatibility-only',
                checkpoint=bundle['checkpoint'], donor_task=bundle['donor_task'],
                donor_fingerprint=bundle['donor_fingerprint'], source_revision=bundle['source_revision'])
        loaded = {target: unreal.load_asset(target) for target in packages}
        if not packages_clean(packages):
            return self.miss('dirty_loaded_package')
        if any(not loaded[target] or not imported_source_matches(loaded[target], source)
               for target, source, _ in sources):
            return self.miss('recorded_source_mismatch')
        if validator is not None:
            try:
                if not validator(loaded[package]):
                    return self.miss('current_validator_rejected')
            except Exception:
                return self.miss('current_validator_exception')
        self.counts['reused_candidate' if copied else 'reused_local'] += 1
        if historical:
            print('NATIVE MESH HISTORICAL COMPATIBILITY ' + json.dumps(dict(task=self.task,
                packages=packages, stamp_time=self.previous_stamp['time'],
                provenance='compatibility-only'), sort_keys=True), flush=True)
        return loaded[package]

    def miss(self, reason):
        """@cc [owner:fontanierh,label:correctness] native-reuse-miss-observation
        Diagnostics MUST describe an observed refusal branch, without changing its decision,
        counting it as reuse, or exposing exception/source path text. Finalized diagnostics
        MUST follow the same invocation and successful host boundary as actual reuse counts.
        """
        self.miss_reasons[reason] = self.miss_reasons.get(reason, 0) + 1
        return None

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
        if nonce is None:
            return
        record = None
        if self.enabled and all(imported_source_matches(unreal.load_asset(target), source)
               for target, source, _ in value['sources']):
            record = dict(key=value['key'], packages=value['packages'], provenance=value['provenance'],
                native_source_validated=True, sources=[dict(package=target, member=mesh_reuse.source_member(self.ctx, source),
                    sha256=expected) for target, source, expected in value['sources']])
        mesh_reuse.queue_pending(self.ctx, self.task, nonce, self.receipts.header['policy'], self.receipts.header['context'],
                                name, record, self.counts, miss_reasons=self.miss_reasons)

    def finish(self):
        result = dict(schema=1, task=self.task, counts=self.counts, miss_reasons=self.miss_reasons,
                      donor_checkpoint=self.bundle.get('checkpoint') if self.bundle else None,
                      donor_provenance=self.bundle.get('provenance') if self.bundle else None,
                      candidate_checkpoints=[bundle['checkpoint'] for bundle in self.bundles])
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
        self.enabled = True
        try:
            code = mesh_reuse.native_policy(Path(script).read_text(), functions, script)
        except (ValueError, SyntaxError):
            self.enabled = False
            code = mesh_reuse.identity({'reuse': 'unsupported-policy'})
        import_policy = mesh_reuse.identity(dict(code=code, support=[mesh_reuse.digest(file) for file in support]))
        self.book = mesh_reuse.Receipts(ctx.out, task + '.assets', context(ctx), import_policy,
                                        ctx.uproject.parent / 'Content')
        self.key = mesh_reuse.identity(dict(parameters=parameters,
            sources=[mesh_reuse.digest(file) for file in sources]))
        self.ctx, self.task = ctx, task + '.assets'
        self.sources = [Path(script), *map(Path, sources), *map(Path, support)]

    def matches(self, packages):
        return self.enabled and packages_clean(packages) and self.book.matches('assets', self.key, packages)

    def validated(self, packages):
        import unreal
        for package in packages:
            asset = unreal.load_asset(package)
            if not asset or not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=True):
                raise RuntimeError('Native asset group could not save ' + package)
        nonce = os.environ.get('ATELIER_MESH_REUSE_NONCE')
        if nonce and self.enabled:
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


_COMMON_FBX = {}


def common_fbx_mesh(source, destination, name, *, seed, fresh_slots, script, validator, owner_roots=()):
    """Default shared FBX boundary; unknown owner/provenance simply imports normally."""
    task, game = os.environ.get('ATELIER_BUILD_TASK'), os.environ.get('ATELIER_BUILD_GAME')
    owner = os.environ.get('ATELIER_BUILD_SCRIPT') or os.environ.get('ATELIER_SCRIPT')
    nonce = os.environ.get('ATELIER_MESH_REUSE_NONCE')
    if not task or not game or not owner or not nonce or not Path(owner).is_absolute():
        return None, None
    key = (task, game, owner, nonce, str(script))
    if key not in _COMMON_FBX:
        _COMMON_FBX[key] = MeshReuse(native_context(game), task, script, ('_import_mesh',), owner_script=owner, owner_roots=owner_roots)
    reuse = _COMMON_FBX[key]
    package = destination + '/' + name
    inputs = dict(format='fbx', fresh_slots=bool(fresh_slots), seed_sha256=mesh_reuse.digest(seed))
    mesh = reuse.acquire(package, package, geometry=inputs, donor_geometry=inputs,
                         sources=[(package, Path(source), mesh_reuse.digest(source))], validator=validator)
    return mesh, reuse
