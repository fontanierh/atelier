"""Sealed observations of the original world layout declaration.

This package grants no task, cache, repair or completion authority. It never opens
produced geometry or executes a producer, selector, provenance helper or tool.
"""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat


class UnsupportedWorldLayout(ValueError):
    """The declaration is outside the original default shipped editor layout role."""


@dataclass(frozen=True)
class WorldLayout:
    step: str
    script: Path
    arguments: tuple[str, ...]
    raw_inputs: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    output_paths: tuple[Path, ...]
    products: tuple[tuple[str, tuple[Path, ...]], ...]


CODE_DIGESTS = {
    'games/yorimichi/world/coast_water.py': '69cd33cb542a1250b15de84bd7041001c593eada1a1583542bbb7eda93b16fbe',
    'games/yorimichi/world/coastal_dressing.py': '3567f2801399b643cf4ecedac9c48e59544f7487ee5ad0e986e1b65892aef78f',
    'games/yorimichi/world/coastal_surface.py': '494eb87aceb154c518f1bc5553eb930bdbe268cd62c090a49ec3cc11ef9f9d4b',
    'games/yorimichi/world/farhills_grid.py': 'b035038b70a4a1cbb2777769410df42b72950152580f0b47bbe9a08fb38e9900',
    'games/yorimichi/world/gen_world.py': '66421faae3da265da1c529c6a7455bd7a0fddaf89c1673881d8e38290c57ec4d',
    'games/yorimichi/world/regions/belmonte/__init__.py': '296904b68a50f536419d21b83547f9083406e242cd304d16104ccdc270561614',
    'games/yorimichi/world/regions/belmonte/ground_names.py': '2929a49d9149ae30a5d440e2804eea38dcb04fae545717c5ac2716c7f3634ca1',
    'games/yorimichi/world/regions/belmonte/layout.py': 'f04288a374d62e254990724334f8359474d7a9dc1d4f0ab1596061a797748117',
    'games/yorimichi/world/regions/belmonte/query_surface.py': 'e97397c77e7c3be6f1aed294bfb96d8580f9743b645b5aa44e70d84caf3c78b7',
    'games/yorimichi/world/regions/belmonte/source.py': '382a35911a85aa5049d9972124d7ea45ccaf440f1339866bbcfedf5c29287c2e',
    'games/yorimichi/world/regions/belmonte/terrain.py': '338ff00f84f3f253c48c17802cd5d255fe02edea8f24746425902db79b6e79d8',
    'games/yorimichi/world/regions/belmonte/terrain_bounds.py': '29e1b3542757299550bf6a78df28c7471158e87eb0944393d65b58a5c7d83956',
    'games/yorimichi/world/regions/belmonte/terrain_palette.py': '7ed98d89661842238dfc0a3ee2d56817fb401b051bc466c81fc9a4fbe4d933aa',
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
    'games/yorimichi/world/regions/forest_lake/__init__.py': 'd82253ded29073a81236931a2220ad71220fe9febe42e89da18903f691aed8d3',
    'games/yorimichi/world/regions/forest_lake/layout.py': 'cbf9f98c9cde50fe54e83ee7fed0c1816e8a6280184e3872376a53be6bb61984',
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
    'games/yorimichi/world/regions/houses/__init__.py': '2f6623acb53e89a909fc3b04849b622bf9002c138800ec63bef5a5ceb52c8453',
    'games/yorimichi/world/regions/houses/layout.py': '9e312ea3326ee766d86d8b523a8aa3f3cc0c3825cc50fd28af6510577db722fd',
    'games/yorimichi/world/regions/mega/__init__.py': 'b79fec867562f6c7260103bb71de9f2e195f5fa09e1e30790e18096b70fcdfad',
    'games/yorimichi/world/regions/mega/layout.py': '3d333e44cc391965c6152fc96209e954b102ff35ad195b7155830c2fd3818b26',
    'games/yorimichi/world/regions/megapark/__init__.py': '81204d73f4d36aa7823fd022ddd112568ff1adf7a21fe19ba4c863f3f6a4c7e0',
    'games/yorimichi/world/regions/megapark/forest.py': '391cd0951290f733beb8dcee255b6516da73215545f045ba1ab495346d6ca181',
    'games/yorimichi/world/regions/megapark/gate.py': 'bac3c117dfa5d28609e5c49e2f74119062c502dfa4edab3006da3712508a5f21',
    'games/yorimichi/world/regions/megapark/placement.py': 'f489a1630040348390e75c37bdd92c7ae8c217b3d581bca20e14c3499c00964d',
    'games/yorimichi/world/regions/megapark/plants.py': '8684ffc70fbbda03e23bfc7b5535951e1cedcc0c518fdab48c131b1bc1657a5c',
    'games/yorimichi/world/regions/megapark/trail.py': 'c0fb1cdc783654104202f1c34bbe3124e3dc636d667ed73ad385aa835304a1bb',
    'games/yorimichi/world/regions/skatepark/__init__.py': 'f771e58ea742465e2d3855b559d9729a081c3d9976a0d953687c9dd90b288edd',
    'games/yorimichi/world/regions/skatepark/pier_site.py': 'aa6c3aae7edfab4f76ad2becc8da00886bc31dfbcb22956a4c88494af77a391d',
    'games/yorimichi/world/regions/southwest/__init__.py': '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
    'games/yorimichi/world/regions/southwest/island.py': '9bcf0940118d42991e0bf33c958464fe561099c3a8cea3892ae197d22509d77d',
    'games/yorimichi/world/regions/southwest/layout.py': '8c3b6c3b3313cd6d04cfd3789d549ca14aae8083cdeddf7cfc4fe874c475b0b9',
    'games/yorimichi/world/regions/southwest/mesh.py': '80057edf50a022c24369aa906444da385a84bebab864a416bf9afe2dd058d116',
    'games/yorimichi/world/regions/treehouse/__init__.py': '987d73431284c2698e4c479fe7612dd4d0bc0f7f38a74929f5bb6a6962f9be90',
    'games/yorimichi/world/regions/treehouse/layout.py': '27cbc8b1b6b93fdf57a0e3a7dbd96aab5a0d070ab0a0156d736b69d2786d568f',
    'games/yorimichi/world/regions/treehouse/screen.py': '38ef8a3d57cf125271064739a14054b0262be564cfa8ec4915d746a782b0ada6',
    'games/yorimichi/world/regions/village/__init__.py': '163922a3f31cc2a4c6a25e5652a3eb03063dfe4c6822f26b4ff5e7605ff4f557',
    'games/yorimichi/world/regions/village/layout.py': '0bc95caebbd15f148a8e4d150eea9033139a9e94ca923bb56595f8db2367290d',
    'games/yorimichi/world/regions/village/mesh.py': '4112908b8e0b4d8ad030c792ee5ea2a9c5a0acd424328193283a5fa8ce184a93',
    'games/yorimichi/world/regions/zeppelin/__init__.py': 'f6890cfa31f1bd901f288010c182cd28280b8a041856313cbfa5ec9a90b3195b',
    'games/yorimichi/world/regions/zeppelin/layout.py': '09e8d15b3666303c1018bc17a33516c33d03a50a84d4eec61807b5ab7658654e',
    'games/yorimichi/world/shorelines.py': '43e2e207adbb8823f8c57ae8f10425109e1215799f834489b4fe39348f676442',
    'games/yorimichi/world/terrain_product.py': 'ec8f9b8fd562da64704e1a0353d9136cf4ce1bb8aea5cb06c0a8d5e75c5cb1c9',
    'games/yorimichi/world/terrain_query.py': 'd6b7caf2509b7cc3508b2404886c42c8c92c9d951061239d4b5616eb1f15617b',
    'games/yorimichi/world/torii_clearance.py': '1f8429da0d226415842b3616a474ce1796eb19cf7cdc954e07d6db2de4d96455',
    'games/yorimichi/world/train/__init__.py': 'd0d8ab671a796a435d289c597eafaf15b194a8a1ca25a555c74e8f47d8974dda',
    'games/yorimichi/world/train/corridor.py': '3e62959aa17150196bd1a195d7024f5cf6ce480bf046f5c691a3481789213e3b',
    'games/yorimichi/world/train/earthworks.py': '425336d1d4bae2ce2379e2fde7144559f57a37af53bbabb1be6eff78700622ae',
    'games/yorimichi/world/train/station_site.py': '55c0b4d8cefc0ffcaa9cecd8e2dc0e276de44530a85a69fd95bba93db33a5d61',
    'games/yorimichi/world/yori.py': 'f3b3fe2e2b0600e2dae704a2c2ae8a25fd28e6160f6d2baeb5c3bd12c817fbbc',
    'platform/studio/atelier/__init__.py': '3695a32f8b7db8b12e9a6983751c82c9c5f109ac726a6e0b0f0dcda9b7511a15',
    'platform/studio/atelier/blender/__init__.py': '74666efa63ab960f719f813134ef71d0d777e201148dccc4f75d1636f99b667d',
    'platform/studio/atelier/blender/fbx.py': '8ffea4b05356596ca8e2e32334920e189a1e108ee86a4d1fdc089c0c89b78520',
    'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
    'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e',
}


RECIPE_DIGESTS = {
    'assignment:MEGAPARK_FOREST': '2812f68c0877cd14c139f4d3171dcc48a739f8ffd342d1163b89b3c8905676b1',
    'assignment:MEGAPARK_PLANTS': '6d27a017f4cecb09464095b50db09a96bacefa7bf20262a3934cd2a9b7e258c9',
    'assignment:FOREST_IMPORTERS': 'eb95f4e599cf9c0044131fa599d576e39bedcfb4611cecfb297c871b43635204',
    'assignment:PLANTS_IMPORTERS': '81f2450e05b541b13112c116c125df8de86e1cf75db1fe5c66f11570eb1d58ce',

    'function:local_imports': 'b16827b19c9ec0f80228f21d369b4412ba0b2626d2e7117570af0fe8ba3804aa',
    'function:belmonte_train_corridor': 'db565b451044762cfadd657ea1f2434348d5bb91699ecfbe4119e75aa98fd632',
    'function:world_steps': 'e0c66580d89bc6bb2b019e9dcd39bbbdb1d597a6fa2f06c3739159f7556af3e9',
    'assignment:GAME': 'c1fd8717a5ba75944ea2ab756a826c928f37e4d09c8df0b4b5ecd50571f84dbb',
    'assignment:WORLD': '12574000f07cf0e48410791ecd814d26eb908d4d94356d7fadb766d1252711f9',
    'assignment:REGIONS': '681755203859b40ea7a6f69813dcd7b8374111a7b4952ca112164344049a062c',
    'assignment:ASSETS': 'f29137f195640a575621d14eb759c33a9d38d5e86953722dfde442fd949f6e1a',
    'assignment:TREEHOUSE': '8aeb779c03c16eabb241911002370bb8e6ab63b1c977c487b0cf7bf0b53a0fd6',
    'assignment:YORI': 'd9d1d1ba3774bdc2eede43a4b6ac611891d9ed0570581ecbba94aa5614baeb7a',
    'assignment:CRATERPARK': 'e6f40f231c8629b10c8d7c80a49b9560ef551844195fcafd457f5f30c2369f6c',
    'enrichment': '8ddab7ffccde79c9135970b994ec7bf8fcf37ec934b0ec46f77e0e4d6bd71da4',
}


# Original ordered factory roles, including deliberate duplicate declarations.
RAW_PREFIX = (
    'games/yorimichi/world/gen_world.py',
    'games/yorimichi/world/regions/forest/ecotone.py',
    'games/yorimichi/world/regions/forest/specs.py',
    'games/yorimichi/world/regions/houses/layout.py',
    'games/yorimichi/world/torii_clearance.py',
    'games/yorimichi/world/yori.py',
    'games/yorimichi/world/regions/village/layout.py',
    'games/yorimichi/world/regions/mega/layout.py',
    'games/yorimichi/world/regions/skatepark/__init__.py',
    'games/yorimichi/world/regions/skatepark/pier_site.py',
    'games/yorimichi/world/regions/southwest/__init__.py',
    'games/yorimichi/world/regions/southwest/island.py',
    'games/yorimichi/world/regions/southwest/layout.py',
    'games/yorimichi/world/regions/southwest/mesh.py',
    'games/yorimichi/world/regions/village/__init__.py',
    'games/yorimichi/world/regions/village/layout.py',
    'games/yorimichi/world/yori.py',
    'platform/studio/atelier/__init__.py',
    'platform/studio/atelier/paths.py',
    'games/yorimichi/world/regions/skatepark/pier_site.py',
    'games/yorimichi/world/regions/forest_lake/layout.py',
    'games/yorimichi/world/regions/zeppelin/layout.py',
    'games/yorimichi/world/regions/treehouse/layout.py',
    'games/yorimichi/world/regions/treehouse/screen.py',
    'games/yorimichi/world/regions/megapark/placement.py',
    'games/yorimichi/world/regions/megapark/forest.py',
    'games/yorimichi/world/regions/megapark/trail.py',
    'games/yorimichi/world/regions/megapark/gate.py',
    'games/yorimichi/world/regions/hidamari/mountains.py',
    'games/yorimichi/world/regions/craterpark/placement.py',
    'games/yorimichi/assets/craterpark/scene.json',
    'games/yorimichi/assets/craterpark/geometry',
    'games/yorimichi/world/regions/craterpark/v2/v4_config.py',
    'games/yorimichi/world/regions/hidamari/layout.py',
    'games/yorimichi/world/regions/hidamari_stable/layout.py',
    'games/yorimichi/world/regions/hidamari/forest_backdrop.py',
    'games/yorimichi/world/farhills_grid.py',
    'games/yorimichi/assets/megapark/map.json',
    'games/yorimichi/assets/megapark/geometry',
    'games/yorimichi/assets/megapark/collision',
    'games/yorimichi/world/train/corridor.py',
    'games/yorimichi/world/train/earthworks.py',
    'games/yorimichi/world/train/station_site.py',
    'games/yorimichi/assets/vehicles/belmonte-train/line.json',
)


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
        raise UnsupportedWorldLayout(f'linked, missing or invalid source/data file: {path}') from error


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
        raise UnsupportedWorldLayout(f'linked, missing or invalid input role: {path}') from error


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
            raise UnsupportedWorldLayout('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedWorldLayout('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedWorldLayout('linked output ancestry') from error
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
        raise UnsupportedWorldLayout('invalid raw JSON declaration') from error


def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedWorldLayout('invalid captured source structure') from error


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
    for role, expected in RECIPE_DIGESTS.items():
        found = nodes.get(role, [])
        if len(found) != 1 or _digest(found[0]) != expected:
            raise UnsupportedWorldLayout('original recipe source structure differs: ' + role)
    for source, expected in zip(code, CODE_DIGESTS.values()):
        if _digest(_ast(checkout, source)) != expected:
            raise UnsupportedWorldLayout('original source structure differs: ' + source.name)


def _closure(checkout, script, world, studio, expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    # Use the existing standard scanner behind the recipe acceleration layer.
    # Its candidate hook always runs, including aliases hidden by a warm fast cache.
    scanner_type = _FastImportScanner.__bases__[0]
    allowed = set(expected)
    def check(source):
        if source not in allowed:
            raise UnsupportedWorldLayout('unknown source import target')
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
        raise UnsupportedWorldLayout('original sorted source closure differs')
    return actual


def qualify_world_layout(step, *, checkout: Path, output_root: Path) -> WorldLayout:
    """@cc [owner:fontanierh,label:correctness;safety] closed-world-layout-observation
    Qualification MUST accept only the original raw factory or complete enriched layout
    Step in the default shipped editor context. Fixed code roles MUST be checked before
    inert scanning and bound to their original structure and complete import closure.
    Produced geometry and canopy JSON MUST be excluded before any content read, including warm inputs.
    No producer, selector, provenance, process probe or task authority is granted.
    """
    from atelier import build
    try:
        checkout, output_root = Path(checkout), Path(output_root)
    except (TypeError, ValueError) as error:
        raise UnsupportedWorldLayout('invalid anchors') from error
    if any(os.environ.get(name, '').strip() for name in (
            'ATELIER_CRATERPARK_V4_DESIGN', 'ATELIER_CRATERPARK_EDITOR_PARK',
            'ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedWorldLayout('not the default shipped editor context')
    if (type(step) is not build.Step or type(getattr(step, 'name', None)) is not str or step.name != 'world.layout'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout == Path(checkout.anchor) or output_root == Path(output_root.anchor)):
        raise UnsupportedWorldLayout('not the original layout Step and absolute anchors')
    game = checkout / 'games/yorimichi'
    world = game / 'world'
    regions = world / 'regions'
    v2 = regions / 'craterpark/v2'
    studio = checkout / 'platform/studio'
    script = world / 'gen_world.py'
    park = game / 'tools/craterpark_editor/shipped.json'
    data = park.parent / 'data'
    outputs = tuple(output_root / name for name in (
        'world.json', 'heightmap.npy', 'heightmap.bin', 'farhills.npy',
        'treehouse/layout.json', 'megapark/trail.json', 'map_preview.png'))
    produced = (output_root / 'craterpark/v2/geometry.npz',
                output_root / 'treehouse-data/canopy/trees.json')
    defaults = dict(deferred_inputs=[], needs=['world.treehouse_trees.data', 'world.craterpark_layout', 'world.craterpark_geometry'],
        after=[], heavy=False,
        pool_roots=[], explicit=False, verify=None, cutoff=True, products=[], reads=['treehouse.canopy_dimensions'], references=[],
        cache=False, audit=False, optional_inputs=[], queries=[], toolchain=False, batch=None,
        cook_recovery=None, checkpoint_previous_needs=None, checkpoint_restore=None,
        checkpoint_outputs=(), candidate_scope=None, replan=False, controller=None,
        about='terrain heightfield, road, scatter and every region layout -> world.json (dependents see these files)')
    if (set(vars(step)) != set(defaults) | {'name', 'commands', 'inputs', 'outputs'}
            or any(not _exact(vars(step)[name], value) for name, value in defaults.items())
            or not _exact(step.outputs, list(outputs))):
        raise UnsupportedWorldLayout('original Step controls or output roles differ')
    if type(step.commands) is not list or len(step.commands) != 1:
        raise UnsupportedWorldLayout('expected one original Python command')
    command = step.commands[0]
    if (type(command) is not build.Python or set(vars(command)) != {'script', 'args'}
            or not _exact(command.script, script) or not _exact(command.args, ())):
        raise UnsupportedWorldLayout('original layout command differs')
    # Precheck all fixed roles and their ancestors before the first source read.
    for path in (checkout, checkout / 'games', game, world, regions, v2,
                 checkout / 'platform', studio, data):
        _role(checkout, path, directory=True)
    code = tuple(checkout / relative for relative in CODE_DIGESTS)
    for source in (*code, game / 'build.py', park, data / 'terrain.json'):
        _role(checkout, source)
    for output in (*outputs, *produced):
        _output(output, directory=False)
    raw = [*(checkout / role for role in RAW_PREFIX), park, data / 'terrain.json']
    document, terrain = _json(checkout, park), _json(checkout, data / 'terrain.json')
    try:
        layers = terrain['inner']['layers']
        names = [*layers.values(), terrain['outer']['file']]
        if document['schema'] != 'craterpark-editor/1' or set(layers) != {'natural', 'dug'}:
            raise ValueError('unsupported default editor metadata')
        if (any(type(name) is not str or name in ('', '.', '..') or '/' in name or '\\' in name
                or '\x00' in name for name in names)
                or len(set(name.casefold() for name in names)) != len(names)):
            raise ValueError('terrain references are not unique basenames')
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise UnsupportedWorldLayout('unsupported raw editor/terrain membership') from error
    raw.extend(data / name for name in names)
    for path in raw:
        _role(checkout, path, directory=path in (game / 'assets/craterpark/geometry',
                game / 'assets/megapark/geometry', game / 'assets/megapark/collision'))
    # Never treat the generated NPZ or canopy JSON as a source or raw-data content candidate.
    factory = [*raw, produced[0]]
    # The original recipe wrapper excludes plants for gen_world, while the
    # separately bound complete scanner closure still includes that source.
    dropped = regions / 'megapark/plants.py'
    enriched = [*factory, *(source for source in code if source not in factory and source != dropped)]
    if not (_exact(step.inputs, factory) or _exact(step.inputs, enriched)):
        raise UnsupportedWorldLayout('original raw or complete enriched input order differs')
    _source_contract(checkout, game, code)
    _closure(checkout, script, world, studio, code)
    return WorldLayout(step.name, script, (), tuple(raw), produced, code, outputs, ())
