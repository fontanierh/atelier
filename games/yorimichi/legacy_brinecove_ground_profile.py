"""Closed source observations of the original final coastal Ground planner."""
from dataclasses import dataclass
import ast
import hashlib
import os
from pathlib import Path
import types
from atelier.build_v2.legacy_qualification import CallableObservation

class UnsupportedBrinecoveGround(ValueError):
    """The original Ground declaration or source roles cannot be established."""

@dataclass(frozen=True)
class BrinecoveGround:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]
    verifier: CallableObservation

INPUT_ROLES = ('games/yorimichi/world/mesh_pieces.py',
 'games/yorimichi/world/region_mesh_parts.py',
 'games/yorimichi/world/region_mesh_set.py',
 'games/yorimichi/world/region_plan_files.py',
 'games/yorimichi/world/region_query.py',
 'games/yorimichi/world/regions/brinecove/__init__.py',
 'games/yorimichi/world/regions/brinecove/boundary.py',
 'games/yorimichi/world/regions/brinecove/foliage_atlas.py',
 'games/yorimichi/world/regions/brinecove/geom.py',
 'games/yorimichi/world/regions/brinecove/geometry_finish.py',
 'games/yorimichi/world/regions/brinecove/ground.py',
 'games/yorimichi/world/regions/brinecove/ground_sampling.py',
 'games/yorimichi/world/regions/brinecove/kit.py',
 'games/yorimichi/world/regions/brinecove/landmarks.py',
 'games/yorimichi/world/regions/brinecove/layout.py',
 'games/yorimichi/world/regions/brinecove/paving_data.py',
 'games/yorimichi/world/regions/brinecove/piece_inputs.py',
 'games/yorimichi/world/regions/brinecove/plan_ground.py',
 'games/yorimichi/world/regions/brinecove/procedural/__init__.py',
 'games/yorimichi/world/regions/brinecove/procedural/_falls_zone.py',
 'games/yorimichi/world/regions/brinecove/procedural/cell_material.py',
 'games/yorimichi/world/regions/brinecove/procedural/falls_cliff.py',
 'games/yorimichi/world/regions/brinecove/procedural/ground_face.py',
 'games/yorimichi/world/regions/brinecove/procedural/yard_material.py',
 'games/yorimichi/world/regions/brinecove/region.py',
 'games/yorimichi/world/regions/brinecove/rim_schema.py',
 'games/yorimichi/world/regions/brinecove/rocks.py',
 'games/yorimichi/world/regions/brinecove/surface_mapping.py',
 'games/yorimichi/world/terrain_product.py',
 'games/yorimichi/world/yori.py',
 'platform/studio/atelier/__init__.py',
 'platform/studio/atelier/atomic_files.py',
 'platform/studio/atelier/export_manifest.py',
 'platform/studio/atelier/gltf.py',
 'platform/studio/atelier/mesh_cells.py',
 'platform/studio/atelier/mesh_collision.py',
 'platform/studio/atelier/mesh_ir.py',
 'platform/studio/atelier/mesh_materials.py',
 'platform/studio/atelier/mesh_partition.py',
 'platform/studio/atelier/model_export.py',
 'platform/studio/atelier/model_files.py',
 'platform/studio/atelier/paths.py',
 'platform/studio/atelier/build_batch_source.py',
 'platform/studio/atelier/build_batch_worker.py')

CODE_DIGESTS = {'games/yorimichi/brinecove_atomic_build.py': '793a575d1282ce165e0d6bad516bf0d86f37d0d42a7d03302e785842a93cfd94',
 'games/yorimichi/region_exports.py': '3b30f0b35a559adacd08df7149c268213c5b481d7e284fbcf478db002e6ee3ed',
 'games/yorimichi/world/mesh_pieces.py': '78293e306a8a1c7d1ff4efde45dd16e22ed371d2a4ec80ef826a1abcf946c608',
 'games/yorimichi/world/region_mesh_parts.py': 'd93f2c4deb9c2c08bd730b7a4f1476b0ccf7a3dc7de2f604363c2ce8d4cc4725',
 'games/yorimichi/world/region_mesh_set.py': '667a3df446981acd5f97056d4cda4e503e4cd29370decb44ce9ad2d5156a042b',
 'games/yorimichi/world/region_plan_files.py': '7451f36a391a5bd6a4c7e12a489b3ec8da64df3a14843257b7626e3958b736c6',
 'games/yorimichi/world/region_query.py': 'fa96910b6715daa5ed9cde939b9a8ed7b9677ea869983c385849e2785e3dce15',
 'games/yorimichi/world/regions/brinecove/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
 'games/yorimichi/world/regions/brinecove/boundary.py': '899069fce56e5bf9909856482c1e3b163498dd430d876c8db1476db866827d20',
 'games/yorimichi/world/regions/brinecove/foliage_atlas.py': '3de6eff0d43ffe0e6fb667c6087118887b8f1f470084b71884a81dd8708be878',
 'games/yorimichi/world/regions/brinecove/geom.py': '7bf56676bb3008f23eae82f3f7283807ecb861bb03e1f6f1a845bc4395a58bd3',
 'games/yorimichi/world/regions/brinecove/geometry_finish.py': '1e2a7f63ee7fb77c521c424d5b3e85f3fac9fbc31e27a81e91f5b0c0b0d8f87f',
 'games/yorimichi/world/regions/brinecove/ground.py': 'a67d8bb8f75bd2be9e0ac9271f602f44c412a231102a85ce60202b5820799102',
 'games/yorimichi/world/regions/brinecove/ground_sampling.py': '1c037da5fa0622dc89e4b0e2366b0c397166940ed444f8bf39442f70871cc463',
 'games/yorimichi/world/regions/brinecove/kit.py': 'eca78952598f4cabfba7cfcb7f8d6e78bf0c579642f44a7120dc0562232c62fd',
 'games/yorimichi/world/regions/brinecove/landmarks.py': 'b2906fb60ac9ffcdd1071c2bf16e702fe8ae49b9c0de65645734c4210d1e69c4',
 'games/yorimichi/world/regions/brinecove/layout.py': '13dbad8c737a43479179271f727701400abd6a2c9e35dea8f51e3299f4158462',
 'games/yorimichi/world/regions/brinecove/logical_catalogue.py': '25d0cc3cdf6c8b3dcecdbe22e029eaae6c0dd3fc086f8dce3a5fc4411bd4853b',
 'games/yorimichi/world/regions/brinecove/paving_data.py': '29014e36212ee529e04604f5539b10951fbe9fea295aabb5b2aef5d74bf8df27',
 'games/yorimichi/world/regions/brinecove/piece_inputs.py': '38bc8b2aad9e256bcbfd522495a6ea3105fbb4bb619ac6a974c43763ba90bfdd',
 'games/yorimichi/world/regions/brinecove/plan_ground.py': 'ec0808daeb55cb10e32f6ed9127cacb3422a755c6a29a5d81f349a37b747fec8',
 'games/yorimichi/world/regions/brinecove/procedural/__init__.py': '0c21b3cbe718673b99b12dd6d1752e0a8a46441ca3e107bc7892eb5518b265a2',
 'games/yorimichi/world/regions/brinecove/procedural/_falls_zone.py': '3810df34b109c2239d077938d43d8f34b19d4ba0a4c9e09e03e9c5211c1c7acc',
 'games/yorimichi/world/regions/brinecove/procedural/cell_material.py': 'd9d474ed973b262877375021f1ce415e633c92d2589ae6794a597d6225df19ef',
 'games/yorimichi/world/regions/brinecove/procedural/falls_cliff.py': '109e8fe284a9998a9fa31dd231271c91a7555ea34a080a72378fe382013bdbc2',
 'games/yorimichi/world/regions/brinecove/procedural/ground_face.py': 'bbb657711b9fb277fa3caa6222b7e92fe288b324197c3cbfc7af571e6d83b2d1',
 'games/yorimichi/world/regions/brinecove/procedural/yard_material.py': '202d7b4eaf263a3c2387096ddc47509afe11e9478379f0521544349f2b89c3e8',
 'games/yorimichi/world/regions/brinecove/region.py': 'd30f19ee9aa548093535146367893cf12b7d33d1c158527812b8e1796f56146d',
 'games/yorimichi/world/regions/brinecove/rim_schema.py': '51a03751482c5bceaab1532fd6825f3697c091737d015d5123a2f975e5903f87',
 'games/yorimichi/world/regions/brinecove/rocks.py': '4d58b64dac8ea3e37abcedb10984947d94bf16d8e3b680d6dbc1055cb82db7ef',
 'games/yorimichi/world/regions/brinecove/surface_mapping.py': 'cc8e24bcb2454180ac4035394806acbe49b0cee7761abc3b1e5bea3101ede37f',
 'games/yorimichi/world/terrain_product.py': '9bf1a8e738ab7a2a1da44d3d6bee65f348ad2369c48590adf7ad0dcfc3544bd1',
 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc',
 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15',
 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78',
 'platform/studio/atelier/build_batch_source.py': '2a61a96a1929832346327d0465a4c18e419c2e4e686d4a8cc7e06c436608195c',
 'platform/studio/atelier/build_batch_worker.py': 'b8812145d851943019b0415a330b27a6996b8921ecd4a9a146dbe5c8d937d22d',
 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6',
 'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
 'platform/studio/atelier/mesh_cells.py': 'db88ba7bf0803fcae6abccbbc20fbc6c4e10965d3d721e770317640298ea887f',
 'platform/studio/atelier/mesh_collision.py': 'c2d7813ef2194ce82d9d2f908bb0b1c9919462c1c046db527167d18838c82183',
 'platform/studio/atelier/mesh_ir.py': '1522b888aefd3b7b0a3e63135972a45e5d9b11c2b1cdf4489b7ffa073a2d1cad',
 'platform/studio/atelier/mesh_materials.py': 'f0c4f63670c7d51d0769eef9128e587fdb65ee7cf1aab7f6fbbdb3f0479623e9',
 'platform/studio/atelier/mesh_partition.py': 'd6ab94f80cf8f3f220d422a194e8bd4e7a171c31ad9da56de9ecb1853a8b9ea3',
 'platform/studio/atelier/model_export.py': '0ba9b3d7a54d8653b4c2674cded755487951fe4d213098a046977983cf4768c2',
 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb',
 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}

def _read(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, path.relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedBrinecoveGround('linked, absent or foreign source') from error


def _role(checkout, path, *, directory=False):
    from legacy_brinecove_component_profile import _role as shared, UnsupportedBrinecoveComponent
    try:
        shared(checkout, path, directory=directory)
    except UnsupportedBrinecoveComponent as error:
        raise UnsupportedBrinecoveGround(str(error)) from error


def _output(path, *, directory):
    from legacy_brinecove_component_profile import _output as shared, UnsupportedBrinecoveComponent
    try:
        shared(path, directory=directory)
    except UnsupportedBrinecoveComponent as error:
        raise UnsupportedBrinecoveGround(str(error)) from error


def qualify_brinecove_ground(step, *, checkout: Path, output_root: Path) -> BrinecoveGround:
    """@cc [owner:fontanierh,label:correctness;safety] closed-coastal-ground-observation
    Bind ONLY the original Ground declaration, all ten ordered rim/paving reads,
    original source/input/Batch controls and three complete owned products. Capture
    the real verifier code/defaults/WORLD/builtin identity without calling it. Fixed
    source candidates MUST be anchored and bounded before inert scanning. Generated
    rim/paving/terrain/query/plan bytes MUST NOT be opened or created. This observation
    MUST NOT execute producer functions or the verifier, certify native products,
    grant future tasks or Finish.
    """
    from atelier import build, build_products, paths
    from atelier.build_v2.legacy_qualification import CapturedCode, IdentityBinding, UnsupportedOrigin, verify_callable
    from legacy_brinecove_component_profile import _exact
    checkout, output_root = Path(checkout), Path(output_root)
    if (type(step) is not build.Step or type(getattr(step, 'name', None)) is not str
            or step.name != 'world.brinecove.geometry.SM_BC_Ground'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedBrinecoveGround('not original Ground Step and absolute anchors')
    if any(os.environ.get(n, '').strip() for n in ('ATELIER_CRATERPARK_V4_DESIGN',
            'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedBrinecoveGround('not the default shipped context')
    game = checkout / 'games/yorimichi'; world = game / 'world'; studio = checkout / 'platform/studio'
    script = world / 'regions/brinecove/plan_ground.py'
    primary = output_root / 'planned_exports/brinecove/SM_BC_Ground'
    terrain = output_root / 'terrain/Brinecove/final.npz'
    surface = output_root / 'brinecove/query-data/SM_BC_Ground.npz'
    owners = ('Rocks', 'Harbor', 'TownLower', 'Market', 'TownUpper', 'Landmarks', 'Ships', 'Props', 'Understory')
    rim = output_root / 'brinecove-data/final-rim.json'
    paving = tuple(output_root / 'brinecove-data/paving' / (name + '.json') for name in owners)
    arguments = ('--rim', str(rim), '--query-output', str(terrain), '--surface-output', str(surface),
                 *(word for path in paving for word in ('--paving', str(path))), '--output', str(primary))
    products = (('brinecove.geometry.SM_BC_Ground', (primary,)),
                ('brinecove.query.SM_BC_Ground', (surface,)), ('terrain.Brinecove.final', (terrain,)))
    reads = ['brinecove.rim_data', *('brinecove.paving.' + name for name in owners)]
    defaults = dict(deferred_inputs=[], needs=[], after=[], heavy=True, pool_roots=[], explicit=False,
        cutoff=False, references=[], cache=True, audit=False, optional_inputs=[], queries=[], toolchain=True,
        cook_recovery=None, checkpoint_previous_needs=None, checkpoint_restore=None, checkpoint_outputs=(),
        candidate_scope=None, replan=False, controller=None, outputs=[], reads=reads,
        about='construct only logical mesh SM_BC_Ground')
    if (set(vars(step)) != set(defaults) | {'name', 'commands', 'inputs', 'products', 'batch', 'verify'}
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())):
        raise UnsupportedBrinecoveGround('original Step controls differ')
    b = step.batch
    if (type(b) is not build.Batch or set(vars(b)) != {'group', 'runtime_env', 'max_seconds'}
            or not _exact(b.group, 'brinecove logical geometry') or not _exact(b.runtime_env, ())
            or type(b.max_seconds) is not float or b.max_seconds != 240.):
        raise UnsupportedBrinecoveGround('original Batch differs')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedBrinecoveGround('expected one original Blender command')
    command = step.commands[0]
    if (type(command) is not build.Blender or set(vars(command)) != {'script', 'args', 'threads', 'factory_startup', 'env'}
            or not _exact(command.script, script) or not _exact(command.args, arguments)
            or type(command.threads) is not int or command.threads != 3 or command.factory_startup is not True
            or not _exact(command.env, (('PYTHONHASHSEED', '0'),))):
        raise UnsupportedBrinecoveGround('original Blender command differs')
    if type(step.products) is not list or len(step.products) != 3:
        raise UnsupportedBrinecoveGround('original products differ')
    for product, (name, roots) in zip(step.products, products):
        if (type(product) is not build_products.Product
                or set(vars(product)) != {'name', 'paths', 'collection', 'bounds', 'optional_paths'}
                or not _exact(product.name, name) or not _exact(product.paths, roots)
                or product.collection is not None or product.bounds is not None or not _exact(product.optional_paths, ())):
            raise UnsupportedBrinecoveGround('original complete product roots differ')
    inputs = tuple(checkout / role for role in INPUT_ROLES)
    if not _exact(step.inputs, list(inputs)):
        raise UnsupportedBrinecoveGround('original ordered source roles differ')
    for path in (checkout, checkout / 'games', game, world, world / 'regions', world / 'regions/brinecove',
                 checkout / 'platform', studio):
        _role(checkout, path, directory=True)
    for path in inputs:
        _role(checkout, path)
    for path, directory in ((output_root, True), (primary, True), (terrain, False), (surface, False),
                            *((path, False) for path in (rim, *paving))):
        _output(path, directory=directory)
    for role, expected in CODE_DIGESTS.items():
        source = checkout / role
        _role(checkout, source)
        try:
            tree = ast.parse(_read(checkout, source), filename=str(source))
        except (ValueError, SyntaxError) as error:
            raise UnsupportedBrinecoveGround('invalid source structure') from error
        if hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest() != expected:
            raise UnsupportedBrinecoveGround('original source structure differs: ' + role)
    allowed = set(inputs)
    class Scanner(build._FastImportScanner.__bases__[0]):
        def resolve(self, root, parts):
            if root == paths.STUDIO: root = studio
            elif root == paths.STUDIO / 'atelier': root = studio / 'atelier'
            found = super().resolve(root, parts)
            for path in found:
                if path not in allowed:
                    raise UnsupportedBrinecoveGround('unknown import candidate')
                _read(checkout, path)
            return found
    actual = tuple(Scanner().local_imports(script, (world, world / 'regions', studio)))
    if actual != inputs[:-2]:
        raise UnsupportedBrinecoveGround('original script closure differs')
    if type(step.verify) is not types.FunctionType or vars(step.verify):
        raise UnsupportedBrinecoveGround('not the original verifier')
    captured = CapturedCode(str(game / 'region_exports.py'), _read(checkout, game / 'region_exports.py'))
    try:
        verifier = verify_callable(step.verify, captured, qualname='steps.<locals>.complete',
            namespace=step.verify.__globals__, defaults=(primary, False), keyword_defaults=None, closures={},
            globals_={'WORLD': world}, builtins_={'str': IdentityBinding(str)})
    except UnsupportedOrigin as error:
        raise UnsupportedBrinecoveGround('original verifier bindings differ') from error
    # Verifier-owned region_exports.py is captured separately by its observation;
    # producer code roles remain exactly the original script closure and two workers.
    return BrinecoveGround(step.name, script, arguments, inputs, (rim, *paving), tuple(sorted(inputs)), products, verifier)
