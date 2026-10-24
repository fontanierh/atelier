"""Closed observations of the original city-layout declaration; no producer execution."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

class UnsupportedHidamariLayout(ValueError):
    """The declaration is outside the frozen original city-layout role."""

@dataclass(frozen=True)
class HidamariLayout:
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
 'games/yorimichi/world/regions/hidamari/__init__.py': '9a88cdef03c891a6ea959e2a68504ceca507c41ba3371e1a66b7e127a49bba84',
 'games/yorimichi/world/regions/hidamari/arrival_placement.py': 'c5917f2cbfe4358a6c535cefe0f098434904bd98e045fc4ff62d5cad2cee5578',
 'games/yorimichi/world/regions/hidamari/city_poles.py': 'fbaa3df64b865694c1c79dd0cc49c273d9e4dc8faa34fd2186e0337160d1438d',
 'games/yorimichi/world/regions/hidamari/forest_backdrop.py': '7efc1de4832350d2c409b4303f823b351d5ddad32ec98af95fac39931f7d8d9f',
 'games/yorimichi/world/regions/hidamari/house_gardens.py': '82e912101b69472f2c4601d5a4b345d5d84f54874eead8129274691018ef75de',
 'games/yorimichi/world/regions/hidamari/layout.py': '8d2f1052f48764710cc5461e4dd21bf54a48aac8b25093f23daac485480c4ea2',
 'games/yorimichi/world/regions/hidamari/layout_data.py': '797ea6913c92d9222641d7a0ec6f8addd3947c85e3be8965de68844f7ebe4e83',
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
 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6',
 'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
 'platform/studio/atelier/model_files.py': '349c53215e39d939950b972e4353747d4dff560eaf7dda49325774398561ccbb',
 'platform/studio/atelier/paths.py': '2a4a04024f6efa85292d64978ce795c3c8a772eeb7a79f68a97aed1a5183165e'}

RECIPE_DIGESTS = {'function:_load_helper_module': 'ace29b516cd27f31ea526e434b73418ace482267661ce220a8401c86e119cf11',
 'assignment:GAME': 'c1fd8717a5ba75944ea2ab756a826c928f37e4d09c8df0b4b5ecd50571f84dbb',
 'assignment:WORLD': '12574000f07cf0e48410791ecd814d26eb908d4d94356d7fadb766d1252711f9',
 'assignment:REGIONS': '681755203859b40ea7a6f69813dcd7b8374111a7b4952ca112164344049a062c',
 'assignment:ASSETS': 'f29137f195640a575621d14eb759c33a9d38d5e86953722dfde442fd949f6e1a',
 'assignment:TREEHOUSE': '8aeb779c03c16eabb241911002370bb8e6ab63b1c977c487b0cf7bf0b53a0fd6',
 'assignment:YORI': 'd9d1d1ba3774bdc2eede43a4b6ac611891d9ed0570581ecbba94aa5614baeb7a',
 'assignment:CRATERPARK': 'e6f40f231c8629b10c8d7c80a49b9560ef551844195fcafd457f5f30c2369f6c',
 'assignment:MEGAPARK_FOREST': '2812f68c0877cd14c139f4d3171dcc48a739f8ffd342d1163b89b3c8905676b1',
 'assignment:MEGAPARK_PLANTS': '6d27a017f4cecb09464095b50db09a96bacefa7bf20262a3934cd2a9b7e258c9',
 'assignment:FOREST_IMPORTERS': 'eb95f4e599cf9c0044131fa599d576e39bedcfb4611cecfb297c871b43635204',
 'assignment:PLANTS_IMPORTERS': '81f2450e05b541b13112c116c125df8de86e1cf75db1fe5c66f11570eb1d58ce',
 'function:local_imports': 'b16827b19c9ec0f80228f21d369b4412ba0b2626d2e7117570af0fe8ba3804aa',
 'function:belmonte_train_corridor': 'db565b451044762cfadd657ea1f2434348d5bb91699ecfbe4119e75aa98fd632',
 'enrichment': '8ddab7ffccde79c9135970b994ec7bf8fcf37ec934b0ec46f77e0e4d6bd71da4',
 'call:layout_steps': '6c3b2e1dceee0ea97260e5fdcefeef479f909b5e01a43b67dfb686fc0eb2e39c',
 'local:crater_geometry': 'efd75c9af468f4af4a02ff49bfa45c72a5658baa1ac20b86795b88de5f9e2d3c'}

HELPER_DIGESTS = {'import:1': '866a97c0a29d398dc2bf8a74409548dccd9bb5221f4bf0f58ad1a37ef83e5260',
 'import:2': '59051b17634cdcb5a576ceb58fdc0a4e5652ed3b60d66667e92ddefd931abeca',
 'import:3': '8a07a36ac15a922fa51057c063deda3a4eee1b9757f3ebfe97c2eb487778498a',
 'import:4': '033a6e1054e29744f788e36342fd6cba5d20cc14627b2ad6ab7eb541b3fac570',
 'import:5': 'fecb1cd4375004910b418012e1939abfd23827cb7be4bcea05aea7b7fe27f793',
 'assignment:GAME': 'c1fd8717a5ba75944ea2ab756a826c928f37e4d09c8df0b4b5ecd50571f84dbb',
 'assignment:WORLD': '12574000f07cf0e48410791ecd814d26eb908d4d94356d7fadb766d1252711f9',
 'assignment:REGIONS': '681755203859b40ea7a6f69813dcd7b8374111a7b4952ca112164344049a062c',
 'assignment:REGION': '2837f748dcbe0a5e7c36625088f200210b0004542af407e3cc8ebd9daf392cd0',
 'function:layout_steps': '40ea78b91b0ab239920b08959a35c23c9eb2998491ef0b2832161e22f5e0dd82'}

RAW_ROLES = ('games/yorimichi/world/coast_water.py', 'games/yorimichi/world/coastal_surface.py', 'games/yorimichi/world/farhills_grid.py', 'games/yorimichi/world/regions/belmonte/__init__.py', 'games/yorimichi/world/regions/belmonte/ground_names.py', 'games/yorimichi/world/regions/belmonte/layout.py', 'games/yorimichi/world/regions/belmonte/query_surface.py', 'games/yorimichi/world/regions/belmonte/source.py', 'games/yorimichi/world/regions/belmonte/terrain.py', 'games/yorimichi/world/regions/belmonte/terrain_bounds.py', 'games/yorimichi/world/regions/belmonte/terrain_palette.py', 'games/yorimichi/world/regions/craterpark/__init__.py', 'games/yorimichi/world/regions/craterpark/placement.py', 'games/yorimichi/world/regions/craterpark/v2/__init__.py', 'games/yorimichi/world/regions/craterpark/v2/curves.py', 'games/yorimichi/world/regions/craterpark/v2/dsl.py', 'games/yorimichi/world/regions/craterpark/v2/profile.py', 'games/yorimichi/world/regions/craterpark/v2/v4_config.py', 'games/yorimichi/world/regions/craterpark/v2/v4_placement.py', 'games/yorimichi/world/regions/forest/__init__.py', 'games/yorimichi/world/regions/forest/ecotone.py', 'games/yorimichi/world/regions/forest/specs.py', 'games/yorimichi/world/regions/hidamari/__init__.py', 'games/yorimichi/world/regions/hidamari/arrival_placement.py', 'games/yorimichi/world/regions/hidamari/city_poles.py', 'games/yorimichi/world/regions/hidamari/forest_backdrop.py', 'games/yorimichi/world/regions/hidamari/house_gardens.py', 'games/yorimichi/world/regions/hidamari/layout.py', 'games/yorimichi/world/regions/hidamari/layout_data.py', 'games/yorimichi/world/regions/hidamari/mountains.py', 'games/yorimichi/world/regions/hidamari/natural_terrain.py', 'games/yorimichi/world/regions/hidamari/park_grounds_placement.py', 'games/yorimichi/world/regions/hidamari/public_spaces.py', 'games/yorimichi/world/regions/hidamari/station_yard_placement.py', 'games/yorimichi/world/regions/hidamari/street_props.py', 'games/yorimichi/world/regions/hidamari/temple_precinct_placement.py', 'games/yorimichi/world/regions/hidamari_stable/__init__.py', 'games/yorimichi/world/regions/hidamari_stable/layout.py', 'games/yorimichi/world/regions/hippodrome/__init__.py', 'games/yorimichi/world/regions/hippodrome/build.py', 'games/yorimichi/world/regions/hippodrome/layout.py', 'games/yorimichi/world/regions/megapark/__init__.py', 'games/yorimichi/world/regions/megapark/forest.py', 'games/yorimichi/world/regions/megapark/gate.py', 'games/yorimichi/world/regions/megapark/placement.py', 'games/yorimichi/world/regions/megapark/plants.py', 'games/yorimichi/world/regions/megapark/trail.py', 'games/yorimichi/world/regions/treehouse/__init__.py', 'games/yorimichi/world/regions/treehouse/layout.py', 'games/yorimichi/world/regions/treehouse/screen.py', 'games/yorimichi/world/regions/village/__init__.py', 'games/yorimichi/world/regions/village/layout.py', 'games/yorimichi/world/regions/village/mesh.py', 'games/yorimichi/world/regions/zeppelin/__init__.py', 'games/yorimichi/world/regions/zeppelin/layout.py', 'games/yorimichi/world/shorelines.py', 'games/yorimichi/world/terrain_product.py', 'games/yorimichi/world/terrain_query.py', 'games/yorimichi/world/train/__init__.py', 'games/yorimichi/world/train/corridor.py', 'games/yorimichi/world/train/earthworks.py', 'games/yorimichi/world/train/station_site.py', 'games/yorimichi/world/yori.py', 'platform/studio/atelier/__init__.py', 'platform/studio/atelier/atomic_files.py', 'platform/studio/atelier/blender/__init__.py', 'platform/studio/atelier/blender/fbx.py', 'platform/studio/atelier/export_manifest.py', 'platform/studio/atelier/gltf.py', 'platform/studio/atelier/model_files.py', 'platform/studio/atelier/paths.py', 'games/yorimichi/world/regions/craterpark/placement.py', 'games/yorimichi/assets/craterpark/scene.json', 'games/yorimichi/assets/craterpark/geometry', 'games/yorimichi/world/regions/craterpark/v2/v4_config.py', 'games/yorimichi/tools/craterpark_editor/shipped.json', 'games/yorimichi/tools/craterpark_editor/data/terrain.json', 'games/yorimichi/tools/craterpark_editor/data/inner_natural.bin', 'games/yorimichi/tools/craterpark_editor/data/inner_dug.bin', 'games/yorimichi/tools/craterpark_editor/data/outer.bin', 'games/yorimichi/world/train/corridor.py', 'games/yorimichi/world/train/earthworks.py', 'games/yorimichi/world/train/station_site.py', 'games/yorimichi/assets/vehicles/belmonte-train/line.json', 'games/yorimichi/world/regions/hidamari/location.json', 'games/yorimichi/assets/hidamari/props', 'games/yorimichi/assets/megapark/map.json', 'games/yorimichi/assets/megapark/geometry', 'games/yorimichi/assets/megapark/collision')


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
        raise UnsupportedHidamariLayout(f'linked, missing or invalid source/data file: {path}') from error

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
        raise UnsupportedHidamariLayout(f'linked, missing or invalid input role: {path}') from error

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
            raise UnsupportedHidamariLayout('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedHidamariLayout('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedHidamariLayout('linked output ancestry') from error
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
        raise UnsupportedHidamariLayout('invalid raw JSON declaration') from error

def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedHidamariLayout('invalid captured source structure') from error

def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

def _closure(checkout, script, world, studio, expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    # Use the existing standard scanner behind the recipe acceleration layer.
    # Its candidate hook always runs, including aliases hidden by a warm fast cache.
    scanner_type = _FastImportScanner.__bases__[0]
    allowed = set(expected)
    def check(source):
        if source not in allowed:
            raise UnsupportedHidamariLayout('unknown source import target')
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
        raise UnsupportedHidamariLayout('original sorted source closure differs')
    return actual


def _source_contract(checkout,game,code):
    tree=_ast(checkout,game/'build.py');nodes={}
    for n in tree.body:
        if isinstance(n,ast.FunctionDef):nodes.setdefault('function:'+n.name,[]).append(n)
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name):nodes.setdefault('assignment:'+t.id,[]).append(n)
    nodes['enrichment']=[n for n in ast.walk(tree) if isinstance(n,ast.With) and len(n.items)==1
        and ast.unparse(n.items[0].context_expr)=="diagnostic_phase('recipe.enrich')"]
    world=nodes.get('function:world_steps',[])
    if len(world)!=1:raise UnsupportedHidamariLayout('original world constructor differs')
    nodes['call:layout_steps']=[n for n in ast.walk(world[0]) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='layout_steps'
        and '_load_helper_module' in ast.unparse(n.func.value)]
    nodes['local:crater_geometry']=[n for n in world[0].body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='crater_geometry' for t in n.targets)]
    for role,expected in RECIPE_DIGESTS.items():
        found=nodes.get(role,[])
        if len(found)!=1 or _digest(found[0])!=expected:raise UnsupportedHidamariLayout('original recipe source differs: '+role)
    helper=_ast(checkout,game/'hidamari_build.py');nodes={}
    for i,n in enumerate(helper.body):
        if isinstance(n,(ast.Import,ast.ImportFrom)):nodes['import:'+str(i)]=[n]
        if isinstance(n,ast.FunctionDef):nodes.setdefault('function:'+n.name,[]).append(n)
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name):nodes.setdefault('assignment:'+t.id,[]).append(n)
    for role,expected in HELPER_DIGESTS.items():
        found=nodes.get(role,[])
        if len(found)!=1 or _digest(found[0])!=expected:raise UnsupportedHidamariLayout('original city constructor source differs: '+role)
    for source,expected in zip(code,CODE_DIGESTS.values()):
        if _digest(_ast(checkout,source))!=expected:raise UnsupportedHidamariLayout('original source structure differs: '+source.name)


def qualify_hidamari_layout(step,*,checkout:Path,output_root:Path)->HidamariLayout:
    """@cc [owner:fontanierh,label:correctness;safety] closed-city-layout-observation
    Accept only the original default city-layout command, controls, ordered code/raw
    roles and exact named product reads. Both raw and full declarations keep the SAME
    input list; only the original full named canopy read adds a generated role.
    Generated payloads MUST be excluded before content reads, cold or warm. Qualifying
    MUST NOT run producers/selectors/helpers, mutate output or metadata, or confer
    execution, cache, repair or completion authority.
    """
    from atelier import build,build_products
    try:checkout,output_root=Path(checkout),Path(output_root)
    except (TypeError,ValueError) as e:raise UnsupportedHidamariLayout('invalid anchors') from e
    if any(os.environ.get(n,'').strip() for n in ('ATELIER_CRATERPARK_V4_DESIGN','ATELIER_CRATERPARK_EDITOR_PARK','ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedHidamariLayout('not the default shipped editor context')
    if (type(step) is not build.Step or getattr(step,'name',None)!='world.hidamari.layout_data'
        or not checkout.is_absolute() or not output_root.is_absolute() or '..' in checkout.parts or '..' in output_root.parts
        or checkout==Path(checkout.anchor) or output_root==Path(output_root.anchor)):
        raise UnsupportedHidamariLayout('not the original city Step and absolute anchors')
    game=checkout/'games/yorimichi';world=game/'world';regions=world/'regions';studio=checkout/'platform/studio'
    script=regions/'hidamari/layout_data.py';output=output_root/'hidamari/layout-data.json'
    arguments=('--output',str(output));products=(('hidamari.city_data',(output,)),)
    defaults=dict(deferred_inputs=[],needs=['world.layout','world.treehouse_trees','world.craterpark_layout','world.craterpark_geometry'],
        after=[],heavy=True,pool_roots=[],explicit=False,verify=None,cutoff=False,references=[],cache=True,audit=False,
        optional_inputs=[],queries=[],toolchain=True,batch=None,cook_recovery=None,checkpoint_previous_needs=None,
        checkpoint_restore=None,checkpoint_outputs=(),candidate_scope=None,replan=False,controller=None,outputs=[],
        about='city placement and final-surface queries without constructing meshes')
    if (set(vars(step))!=set(defaults)|{'name','commands','inputs','products','reads'}
        or any(not _exact(vars(step)[k],v) for k,v in defaults.items())):
        raise UnsupportedHidamariLayout('original Step controls differ')
    if type(step.commands) is not list or len(step.commands)!=1:raise UnsupportedHidamariLayout('expected one original Blender command')
    c=step.commands[0]
    if (type(c) is not build.Blender or set(vars(c))!={'script','args','threads','factory_startup','env'}
        or not _exact(c.script,script) or not _exact(c.args,arguments) or type(c.threads) is not int or c.threads!=3
        or c.factory_startup is not True or not _exact(c.env,(('PYTHONHASHSEED','0'),))):
        raise UnsupportedHidamariLayout('original Blender command differs')
    if type(step.products) is not list or len(step.products)!=1:raise UnsupportedHidamariLayout('original product differs')
    p=step.products[0]
    if (type(p) is not build_products.Product or set(vars(p))!={'name','paths','collection','bounds','optional_paths'}
        or not _exact(p.name,products[0][0]) or not _exact(p.paths,(output,)) or p.collection is not None
        or p.bounds is not None or not _exact(p.optional_paths,())):raise UnsupportedHidamariLayout('original product differs')
    raw_reads=['terrain.FarHills.final'];full_reads=[*raw_reads,'treehouse.canopy_dimensions']
    if not (_exact(step.reads,raw_reads) or _exact(step.reads,full_reads)):raise UnsupportedHidamariLayout('original named reads differ')
    for p in (checkout,checkout/'games',game,world,regions,regions/'hidamari',checkout/'platform',studio):_role(checkout,p,directory=True)
    code=tuple(checkout/p for p in CODE_DIGESTS)
    for p in (*code,game/'build.py',game/'hidamari_build.py'):_role(checkout,p)
    generated=tuple(output_root/p for p in ('world.json','heightmap.npy','farhills.npy','megapark/trail.json','treehouse/trees/trees.json'))
    produced=(*generated,output_root/'terrain/FarHills/final.npz')
    if step.reads==full_reads:produced+= (output_root/'treehouse-data/canopy/trees.json',)
    _output(output_root,directory=True)
    for p in (*produced,output):_output(p,directory=False)
    data=game/'tools/craterpark_editor/data';park=data.parent/'shipped.json'
    for p in (park,data/'terrain.json'):_role(checkout,p)
    document,terrain=_json(checkout,park),_json(checkout,data/'terrain.json')
    try:
        layers=terrain['inner']['layers'];files=[*layers.values(),terrain['outer']['file']]
        if document['schema']!='craterpark-editor/1' or set(layers)!={'natural','dug'}:raise ValueError('editor metadata')
        if (any(type(n) is not str or n in ('','.','..') or '/' in n or '\\' in n or '\x00' in n for n in files)
            or len({n.casefold() for n in files})!=len(files)):raise ValueError('terrain names')
    except (KeyError,TypeError,AttributeError,ValueError) as e:raise UnsupportedHidamariLayout('invalid raw editor membership') from e
    substitutions=dict(zip(('inner_natural.bin','inner_dug.bin','outer.bin'),files))
    raw=[]
    for role in RAW_ROLES:
        p=checkout/role
        if p.parent==data and p.name in substitutions:p=data/substitutions[p.name]
        raw.append(p)
    directories={game/'assets/craterpark/geometry',game/'assets/hidamari/props',game/'assets/megapark/geometry',game/'assets/megapark/collision'}
    for p in raw:_role(checkout,p,directory=p in directories)
    if not _exact(step.inputs,[*raw,*generated]):raise UnsupportedHidamariLayout('original ordered inputs differ')
    _source_contract(checkout,game,code);_closure(checkout,script,world,studio,code)
    return HidamariLayout(step.name,script,arguments,tuple(raw),tuple(produced),code,products)
