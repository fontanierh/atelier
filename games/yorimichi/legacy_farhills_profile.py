"""Source observations of the original FarHills Blender declaration, without execution or authority."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

class UnsupportedFarHills(ValueError):
    """The declaration is outside the original selected FarHills producer."""

@dataclass(frozen=True)
class FarHills:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]

CODE_DIGESTS = {'games/yorimichi/world/coast_water.py': '69cd33cb542a1250b15de84bd7041001c593eada1a1583542bbb7eda93b16fbe',
 'games/yorimichi/world/coastal_surface.py': '494eb87aceb154c518f1bc5553eb930bdbe268cd62c090a49ec3cc11ef9f9d4b',
 'games/yorimichi/world/farhills_grid.py': 'b035038b70a4a1cbb2777769410df42b72950152580f0b47bbe9a08fb38e9900',
 'games/yorimichi/world/farhills_surface.py': '9a05942ec40711880a114719911c840084745b87a74a1763793c96bcb1111c7d',
 'games/yorimichi/world/regions/belmonte/__init__.py': '296904b68a50f536419d21b83547f9083406e242cd304d16104ccdc270561614',
 'games/yorimichi/world/regions/belmonte/ground_names.py': '2929a49d9149ae30a5d440e2804eea38dcb04fae545717c5ac2716c7f3634ca1',
 'games/yorimichi/world/regions/belmonte/layout.py': 'f04288a374d62e254990724334f8359474d7a9dc1d4f0ab1596061a797748117',
 'games/yorimichi/world/regions/belmonte/query_surface.py': 'e97397c77e7c3be6f1aed294bfb96d8580f9743b645b5aa44e70d84caf3c78b7',
 'games/yorimichi/world/regions/belmonte/source.py': '382a35911a85aa5049d9972124d7ea45ccaf440f1339866bbcfedf5c29287c2e',
 'games/yorimichi/world/regions/belmonte/terrain.py': '338ff00f84f3f253c48c17802cd5d255fe02edea8f24746425902db79b6e79d8',
 'games/yorimichi/world/regions/belmonte/terrain_bounds.py': '29e1b3542757299550bf6a78df28c7471158e87eb0944393d65b58a5c7d83956',
 'games/yorimichi/world/regions/belmonte/terrain_palette.py': '7ed98d89661842238dfc0a3ee2d56817fb401b051bc466c81fc9a4fbe4d933aa',
 'games/yorimichi/world/regions/brinecove/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
 'games/yorimichi/world/regions/brinecove/region.py': 'd30f19ee9aa548093535146367893cf12b7d33d1c158527812b8e1796f56146d',
 'games/yorimichi/world/regions/craterpark/__init__.py': 'ddc45019fb560a38712699d5e211dbdf75aa072973224e526f93ac007b7c68a6',
 'games/yorimichi/world/regions/craterpark/placement.py': '254ffc8edcd579ca6f1d618e71c1976372314969c936bc98d27c653067d1b580',
 'games/yorimichi/world/regions/craterpark/v2/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
 'games/yorimichi/world/regions/craterpark/v2/curves.py': '621c4382706726fb806a21602bf32d7dbeef4b9365dbeb62c84ddc9f8041307f',
 'games/yorimichi/world/regions/craterpark/v2/dsl.py': '6cfceb8d2be59877c3f0d5a881bbe1b74f4989de6bbd9e0ee032888f47f6efc9',
 'games/yorimichi/world/regions/craterpark/v2/profile.py': '1833c4953c490fae27feb3faf918790625654c367dcfd005c8cc351bd35030bb',
 'games/yorimichi/world/regions/craterpark/v2/v4_config.py': '0ac95ac889ce2c5d194381f5782540df420adb5b7609979257aa4a7391f795dd',
 'games/yorimichi/world/regions/craterpark/v2/v4_placement.py': '0378ba842506a3fae49ac683066e3eb591221a2438527cb7dc54369a29fcb090',
 'games/yorimichi/world/regions/forest/__init__.py': '87d670a72a93d02f30f8a3d660b7bab1471bc441a1e999ecb103504694ed7ad7',
 'games/yorimichi/world/regions/forest/ecotone.py': '7fda03167845c1b2d0946f307655da6909281755047d5c2a77f165c4ab54d7b3',
 'games/yorimichi/world/regions/forest/specs.py': '8d2d1b9e3ce3c886190543d9af2ea808471fee83b8e101d8d016a2e56249cc7e',
 'games/yorimichi/world/regions/hidamari/__init__.py': '9a88cdef03c891a6ea959e2a68504ceca507c41ba3371e1a66b7e127a49bba84',
 'games/yorimichi/world/regions/hidamari/arrival_placement.py': 'c5917f2cbfe4358a6c535cefe0f098434904bd98e045fc4ff62d5cad2cee5578',
 'games/yorimichi/world/regions/hidamari/city_poles.py': 'fbaa3df64b865694c1c79dd0cc49c273d9e4dc8faa34fd2186e0337160d1438d',
 'games/yorimichi/world/regions/hidamari/forest_backdrop.py': '7efc1de4832350d2c409b4303f823b351d5ddad32ec98af95fac39931f7d8d9f',
 'games/yorimichi/world/regions/hidamari/house_gardens.py': '82e912101b69472f2c4601d5a4b345d5d84f54874eead8129274691018ef75de',
 'games/yorimichi/world/regions/hidamari/layout.py': '8d2f1052f48764710cc5461e4dd21bf54a48aac8b25093f23daac485480c4ea2',
 'games/yorimichi/world/regions/hidamari/mountains.py': '894f1bc5df848a5d7a49a4cc911ca576d146a8cbece6c6c4b294c16168c41a42',
 'games/yorimichi/world/regions/hidamari/natural_terrain.py': 'c8748da490a5cf964155d75d98f18d6da6ae593362b584be542c8ae10829dc3e',
 'games/yorimichi/world/regions/hidamari/park_grounds_placement.py': 'c2e60649927e81bae99c2c43ed00a1f1d49714e6d86c064de5fd1aea4c445cf7',
 'games/yorimichi/world/regions/hidamari/public_spaces.py': 'fc2268a646ad218c6c4dfec7e66231934f0db54043d7f93e12a3f2b0f40b9044',
 'games/yorimichi/world/regions/hidamari/station_yard_placement.py': 'ce4478163ee0f994482de6c00272c5a5b7955442c16b988c2d3c842c0ae14004',
 'games/yorimichi/world/regions/hidamari/street_props.py': '4488a4ee3f0952da054fbf5c190285b51c5042ba6939d0b947eacda520a9fc5e',
 'games/yorimichi/world/regions/hidamari/temple_precinct_placement.py': '4ef637e8be482ecba46ed21aa121937e6a7054e62748af0490f4911b5dd51fc0',
 'games/yorimichi/world/regions/hidamari_stable/__init__.py': 'af6a826ac11fbd651006cf1545e26f29ddc53c83edd691889e15f79cc8ec325f',
 'games/yorimichi/world/regions/hidamari_stable/layout.py': '27b452297c1cd184f70a6398227437a99d109dc38da306ab0ed9af9fac0bb8ba',
 'games/yorimichi/world/regions/hippodrome/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
 'games/yorimichi/world/regions/hippodrome/build.py': 'c95d91cc05ba3668c55c573b82531687aedc2da84de9f2e365e2fc5eb07c0738',
 'games/yorimichi/world/regions/hippodrome/layout.py': '82342d2c577b5c78de5ff317593fbabc1dc56f514d05d426185e9b2b0c841ba7',
 'games/yorimichi/world/regions/megapark/__init__.py': '81204d73f4d36aa7823fd022ddd112568ff1adf7a21fe19ba4c863f3f6a4c7e0',
 'games/yorimichi/world/regions/megapark/forest.py': '391cd0951290f733beb8dcee255b6516da73215545f045ba1ab495346d6ca181',
 'games/yorimichi/world/regions/megapark/gate.py': 'bac3c117dfa5d28609e5c49e2f74119062c502dfa4edab3006da3712508a5f21',
 'games/yorimichi/world/regions/megapark/placement.py': 'f489a1630040348390e75c37bdd92c7ae8c217b3d581bca20e14c3499c00964d',
 'games/yorimichi/world/regions/megapark/plants.py': '8684ffc70fbbda03e23bfc7b5535951e1cedcc0c518fdab48c131b1bc1657a5c',
 'games/yorimichi/world/regions/megapark/trail.py': 'c0fb1cdc783654104202f1c34bbe3124e3dc636d667ed73ad385aa835304a1bb',
 'games/yorimichi/world/regions/treehouse/__init__.py': '987d73431284c2698e4c479fe7612dd4d0bc0f7f38a74929f5bb6a6962f9be90',
 'games/yorimichi/world/regions/treehouse/layout.py': '27cbc8b1b6b93fdf57a0e3a7dbd96aab5a0d070ab0a0156d736b69d2786d568f',
 'games/yorimichi/world/regions/treehouse/screen.py': '38ef8a3d57cf125271064739a14054b0262be564cfa8ec4915d746a782b0ada6',
 'games/yorimichi/world/regions/village/__init__.py': '163922a3f31cc2a4c6a25e5652a3eb03063dfe4c6822f26b4ff5e7605ff4f557',
 'games/yorimichi/world/regions/village/layout.py': '0bc95caebbd15f148a8e4d150eea9033139a9e94ca923bb56595f8db2367290d',
 'games/yorimichi/world/regions/village/mesh.py': '4112908b8e0b4d8ad030c792ee5ea2a9c5a0acd424328193283a5fa8ce184a93',
 'games/yorimichi/world/regions/zeppelin/__init__.py': 'f6890cfa31f1bd901f288010c182cd28280b8a041856313cbfa5ec9a90b3195b',
 'games/yorimichi/world/regions/zeppelin/layout.py': '09e8d15b3666303c1018bc17a33516c33d03a50a84d4eec61807b5ab7658654e',
 'games/yorimichi/world/shorelines.py': '43e2e207adbb8823f8c57ae8f10425109e1215799f834489b4fe39348f676442',
 'games/yorimichi/world/terrain_product.py': '9bf1a8e738ab7a2a1da44d3d6bee65f348ad2369c48590adf7ad0dcfc3544bd1',
 'games/yorimichi/world/terrain_query.py': 'd6b7caf2509b7cc3508b2404886c42c8c92c9d951061239d4b5616eb1f15617b',
 'games/yorimichi/world/train/__init__.py': 'd0d8ab671a796a435d289c597eafaf15b194a8a1ca25a555c74e8f47d8974dda',
 'games/yorimichi/world/train/corridor.py': '3e62959aa17150196bd1a195d7024f5cf6ce480bf046f5c691a3481789213e3b',
 'games/yorimichi/world/train/earthworks.py': '425336d1d4bae2ce2379e2fde7144559f57a37af53bbabb1be6eff78700622ae',
 'games/yorimichi/world/train/station_site.py': '55c0b4d8cefc0ffcaa9cecd8e2dc0e276de44530a85a69fd95bba93db33a5d61',
 'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc',
 'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15',
 'platform/studio/atelier/atomic_files.py': '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78',
 'platform/studio/atelier/blender/__init__.py': '74666efa63ab960f719f813134ef71d0d777e201148dccc4f75d1636f99b667d',
 'platform/studio/atelier/blender/fbx.py': '8ffea4b05356596ca8e2e32334920e189a1e108ee86a4d1fdc089c0c89b78520',
 'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}

RECIPE_DIGESTS = {'assignment:MEGAPARK_FOREST': '2812f68c0877cd14c139f4d3171dcc48a739f8ffd342d1163b89b3c8905676b1',
 'assignment:MEGAPARK_PLANTS': '6d27a017f4cecb09464095b50db09a96bacefa7bf20262a3934cd2a9b7e258c9',
 'assignment:FOREST_IMPORTERS': 'eb95f4e599cf9c0044131fa599d576e39bedcfb4611cecfb297c871b43635204',
 'assignment:PLANTS_IMPORTERS': '81f2450e05b541b13112c116c125df8de86e1cf75db1fe5c66f11570eb1d58ce',
 'function:local_imports': 'b16827b19c9ec0f80228f21d369b4412ba0b2626d2e7117570af0fe8ba3804aa',
 'function:belmonte_train_corridor': 'db565b451044762cfadd657ea1f2434348d5bb91699ecfbe4119e75aa98fd632',
 'assignment:GAME': 'c1fd8717a5ba75944ea2ab756a826c928f37e4d09c8df0b4b5ecd50571f84dbb',
 'assignment:WORLD': '12574000f07cf0e48410791ecd814d26eb908d4d94356d7fadb766d1252711f9',
 'assignment:REGIONS': '681755203859b40ea7a6f69813dcd7b8374111a7b4952ca112164344049a062c',
 'assignment:ASSETS': 'f29137f195640a575621d14eb759c33a9d38d5e86953722dfde442fd949f6e1a',
 'assignment:TREEHOUSE': '8aeb779c03c16eabb241911002370bb8e6ab63b1c977c487b0cf7bf0b53a0fd6',
 'assignment:YORI': 'd9d1d1ba3774bdc2eede43a4b6ac611891d9ed0570581ecbba94aa5614baeb7a',
 'assignment:CRATERPARK': 'e6f40f231c8629b10c8d7c80a49b9560ef551844195fcafd457f5f30c2369f6c',
 'enrichment': '8ddab7ffccde79c9135970b994ec7bf8fcf37ec934b0ec46f77e0e4d6bd71da4',
 'step:world.farhills': 'f115cd04d44b35c0ac97a6e5395f37f2beebc27c48818f57768a4ba239e8d7f8',
 'local:crater_geometry': 'efd75c9af468f4af4a02ff49bfa45c72a5658baa1ac20b86795b88de5f9e2d3c'}

RAW_PREFIX = ('games/yorimichi/world/farhills_surface.py',
 'games/yorimichi/world/farhills_grid.py',
 'games/yorimichi/world/terrain_product.py',
 'games/yorimichi/world/shorelines.py',
 'games/yorimichi/world/yori.py',
 'games/yorimichi/world/train/corridor.py',
 'games/yorimichi/world/train/earthworks.py',
 'games/yorimichi/world/train/station_site.py',
 'games/yorimichi/assets/vehicles/belmonte-train/line.json',
 'games/yorimichi/world/regions/brinecove/region.py',
 'games/yorimichi/world/regions/hidamari/layout.py',
 'games/yorimichi/world/regions/hidamari_stable/layout.py',
 'games/yorimichi/world/regions/hidamari/mountains.py',
 'games/yorimichi/world/regions/craterpark/placement.py',
 'games/yorimichi/assets/craterpark/scene.json',
 'games/yorimichi/assets/craterpark/geometry',
 'games/yorimichi/world/regions/craterpark/v2/v4_config.py',
 'games/yorimichi/world/regions/belmonte/terrain.py',
 'games/yorimichi/world/regions/belmonte/source.py',
 'games/yorimichi/world/regions/belmonte/layout.py')

def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (tuple, list):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _read(checkout, path):
    from atelier.build_v2.controller_client import MAX_SOURCE_FILE_BYTES, _read_at
    try:
        return _read_at(checkout, path.relative_to(checkout).as_posix(), MAX_SOURCE_FILE_BYTES)
    except (OSError, ValueError) as error:
        raise UnsupportedFarHills(f'linked, missing or invalid source/data file: {path}') from error


def _role(checkout, path, *, directory=False):
    """Inspect only the role and nofollow ancestors; large data contents stay unopened."""
    from atelier.build_v2.controller_client import _open_root
    try:
        path.relative_to(checkout)
        descriptor = _open_root(path if directory else path.parent)
        try:
            if not directory and not stat.S_ISREG(os.stat(path.name, dir_fd=descriptor, follow_symlinks=False).st_mode):
                raise ValueError('not a regular file')
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as error:
        raise UnsupportedFarHills(f'linked, missing or invalid input role: {path}') from error


def _output(path, *, directory):
    from atelier.build_v2.controller_client import _open_root
    current = path
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue
        except OSError as error:
            raise UnsupportedFarHills('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedFarHills('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedFarHills('linked output ancestry') from error
            return
        current = current.parent


def _json(checkout, path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(_read(checkout, path), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise UnsupportedFarHills('invalid raw JSON declaration') from error


def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedFarHills('invalid captured source structure') from error


def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _source_contract(checkout, game, code):
    tree = _ast(checkout, game / 'build.py')
    nodes = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            nodes.setdefault('function:' + node.name, []).append(node)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    nodes.setdefault('assignment:' + target.id, []).append(node)
    nodes['enrichment'] = [n for n in ast.walk(tree) if isinstance(n, ast.With)
        and len(n.items) == 1 and ast.unparse(n.items[0].context_expr) == "diagnostic_phase('recipe.enrich')"]
    world = nodes.get('function:world_steps', [])
    if len(world) != 1:
        raise UnsupportedFarHills('original world constructor missing')
    nodes['step:world.farhills'] = [n for n in ast.walk(world[0]) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == 'Step' and n.args
        and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'world.farhills']
    nodes['local:crater_geometry'] = [n for n in world[0].body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'crater_geometry' for t in n.targets)]
    for role, expected in RECIPE_DIGESTS.items():
        found = nodes.get(role, [])
        if len(found) != 1 or _digest(found[0]) != expected:
            raise UnsupportedFarHills('original recipe source structure differs: ' + role)
    for source, expected in zip(code, CODE_DIGESTS.values()):
        if _digest(_ast(checkout, source)) != expected:
            raise UnsupportedFarHills('original source structure differs: ' + source.name)


def _closure(checkout, script, world, studio, expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    # Use the existing standard scanner behind the recipe acceleration layer.
    # Its candidate hook always runs, including aliases hidden by a warm fast cache.
    scanner_type = _FastImportScanner.__bases__[0]
    allowed = set(expected)
    def check(source):
        if source not in allowed:
            raise UnsupportedFarHills('unknown source import target')
        _read(checkout, source)
    def anchored(root):
        if root == paths.STUDIO:
            return studio
        if root == paths.STUDIO / 'atelier':
            return studio / 'atelier'
        return root
    class CheckedScanner(scanner_type):
        def resolve(self, root, parts):
            found = super().resolve(anchored(root), parts)
            for source in found:
                check(source)
            return found
    actual = tuple(CheckedScanner().local_imports(script, (world, world / 'regions', studio)))
    for source in actual:
        check(source)  # Bind the entire returned closure, not just individual candidates.
    if actual != expected:
        raise UnsupportedFarHills('original sorted source closure differs')
    return actual


def _member(value):
    if (type(value) is not str or not value or '\\' in value or '\x00' in value
            or Path(value).is_absolute() or any(p in ('', '.', '..') for p in value.split('/'))
            or Path(value).as_posix() != value or Path(value).suffix != '.glb'):
        raise UnsupportedFarHills('unsafe or ambiguous raw terrain member')
    return value


def qualify_farhills(step, *, checkout: Path, output_root: Path) -> FarHills:
    """@cc [owner:fontanierh,label:correctness;safety] closed-farhills-native-observation
    Accept only the original raw or complete enriched default FarHills declaration.
    Bind exact command, controls, products, raw membership and complete anchored source
    closure. Generated inputs MUST be skipped before content reads, cold or warm.
    Qualification MUST NOT execute producers, selectors, verifiers, save/load or probes,
    change outputs, invent a product or grant native/cache/repair/completion authority.
    """
    from atelier import build, build_products
    try:
        checkout, output_root = Path(checkout), Path(output_root)
    except (TypeError, ValueError) as error:
        raise UnsupportedFarHills('invalid anchors') from error
    if any(os.environ.get(n, '').strip() for n in ('ATELIER_CRATERPARK_V4_DESIGN',
            'ATELIER_CRATERPARK_EDITOR_PARK', 'ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedFarHills('not the default shipped editor context')
    if (type(step) is not build.Step or getattr(step, 'name', None) != 'world.farhills'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedFarHills('not the original FarHills Step and absolute anchors')
    game=checkout/'games/yorimichi';world=game/'world';regions=world/'regions';studio=checkout/'platform/studio'
    script=world/'farhills_surface.py';park=game/'tools/craterpark_editor/shipped.json';data=park.parent/'data'
    belmonte=game/'assets/belmonte';manifest=belmonte/'source.json'
    produced=tuple(output_root/p for p in ('world.json','heightmap.npy','farhills.npy',
                                         'megapark/trail.json','craterpark/v2/geometry.npz'))
    products=tuple(('terrain.FarHills.'+name,(output_root/'terrain/FarHills'/file,))
        for name,file in (('natural','natural.npz'),('final','final.npz'),('provenance','manifest.json')))
    defaults=dict(deferred_inputs=[],needs=['world.layout','world.craterpark_layout','world.craterpark_geometry'],
        after=[],heavy=True,pool_roots=[],explicit=False,verify=None,cutoff=False,references=[],
        cache=True,audit=False,optional_inputs=[],queries=[],toolchain=False,batch=None,cook_recovery=None,
        checkpoint_previous_needs=None,checkpoint_restore=None,checkpoint_outputs=(),candidate_scope=None,
        replan=False,controller=None,outputs=[],
        about='authoritative FarHills natural and final ordered geometry before city scenery')
    if (set(vars(step)) != set(defaults)|{'name','commands','inputs','products','reads'}
            or any(not _exact(vars(step)[n],v) for n,v in defaults.items())):
        raise UnsupportedFarHills('original Step controls differ')
    if type(step.commands) is not list or len(step.commands)!=1:
        raise UnsupportedFarHills('expected one original Blender command')
    c=step.commands[0]
    if (type(c) is not build.Blender or set(vars(c))!={'script','args','threads','factory_startup','env'}
            or not _exact(c.script,script) or not _exact(c.args,())
            or type(c.threads) is not int or c.threads!=3 or c.factory_startup is not True or not _exact(c.env,())):
        raise UnsupportedFarHills('original Blender command differs')
    if type(step.products) is not list or len(step.products)!=3:
        raise UnsupportedFarHills('original products differ')
    for p,(name,paths) in zip(step.products,products):
        if (type(p) is not build_products.Product
                or set(vars(p))!={'name','paths','collection','bounds','optional_paths'}
                or not _exact(p.name,name) or not _exact(p.paths,paths)
                or p.collection is not None or p.bounds is not None or not _exact(p.optional_paths,())):
            raise UnsupportedFarHills('original products differ')
    for p in (checkout,checkout/'games',game,world,regions,checkout/'platform',studio,data,belmonte):
        _role(checkout,p,directory=True)
    code=tuple(checkout/p for p in CODE_DIGESTS)
    for p in (*code,game/'build.py',park,data/'terrain.json',manifest):_role(checkout,p)
    canopy=output_root/'treehouse-data/canopy/trees.json'
    if not (_exact(step.reads,[]) or _exact(step.reads,['treehouse.canopy_dimensions'])):
        raise UnsupportedFarHills('original named read differs')
    observed_produced=produced+((canopy,) if step.reads else ())
    for p in (*observed_produced,*(p for _,paths in products for p in paths)):_output(p,directory=False)
    doc=_json(checkout,manifest)
    try:
        meshes=doc['meshes']
        if type(meshes) is not list:raise ValueError('mesh list')
        selected=[];names=set();members=set()
        for m in meshes:
            if type(m) is not dict or type(m.get('name')) is not str:raise ValueError('mesh record')
            if not m['name'].startswith('SM_BM_BT_Terrain_'):continue
            member=_member(m['path']);name=m['name'].casefold()
            if name in names or member.casefold() in members:raise ValueError('ambiguous terrain membership')
            names.add(name);members.add(member.casefold());selected.append(belmonte/member)
        if not selected:raise ValueError('empty terrain membership')
    except (KeyError,TypeError,ValueError) as error:
        raise UnsupportedFarHills('invalid raw terrain membership') from error
    document,terrain=_json(checkout,park),_json(checkout,data/'terrain.json')
    try:
        layers=terrain['inner']['layers'];files=[*layers.values(),terrain['outer']['file']]
        if document['schema']!='craterpark-editor/1' or set(layers)!={'natural','dug'}:raise ValueError('editor metadata')
        if (any(type(n) is not str or n in ('','.','..') or '/' in n or '\\' in n or '\x00' in n for n in files)
                or len(set(n.casefold() for n in files))!=len(files)):raise ValueError('terrain names')
    except (KeyError,TypeError,AttributeError,ValueError) as error:
        raise UnsupportedFarHills('invalid raw editor membership') from error
    raw=[*(checkout/p for p in RAW_PREFIX),*selected,
         *(regions/'megapark'/p for p in ('placement.py','trail.py','gate.py')),
         park,data/'terrain.json',*(data/n for n in files),manifest,
         game/'assets/megapark/map.json',game/'assets/megapark/geometry',game/'assets/megapark/collision']
    directories={game/'assets/craterpark/geometry',game/'assets/megapark/geometry',game/'assets/megapark/collision'}
    for p in raw:_role(checkout,p,directory=p in directories)
    # The actual raw factory interleaves four World reads before its Crater data tail.
    factory=[*raw[:-9],*produced[:4],*raw[-9:-4],produced[4],*raw[-4:]]
    drop={regions/'megapark/forest.py',regions/'megapark/plants.py'}
    enriched=[*factory,*(p for p in code if p not in factory and p not in drop)]
    if not ((_exact(step.inputs,factory) and _exact(step.reads,[]))
            or (_exact(step.inputs,enriched) and _exact(step.reads,['treehouse.canopy_dimensions']))):
        raise UnsupportedFarHills('original raw or complete enriched input order differs')
    _source_contract(checkout,game,code)
    _closure(checkout,script,world,studio,code)
    return FarHills(step.name,script,(),tuple(raw),observed_produced,code,products)
