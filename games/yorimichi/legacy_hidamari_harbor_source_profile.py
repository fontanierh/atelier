"""Closed observations of the original Harbor source-only batch declaration; no producer execution."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
import re
import math
from pathlib import Path
import stat

class UnsupportedHidamariHarborSource(ValueError):
    """The declaration is outside the frozen original Harbor source-only batch role."""

@dataclass(frozen=True)
class HidamariHarborSource:
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
 'games/yorimichi/world/mesh_pieces.py': '78293e306a8a1c7d1ff4efde45dd16e22ed371d2a4ec80ef826a1abcf946c608',
 'games/yorimichi/world/random_stream.py': 'c8416c00a0e4efe014de70817ec3ba0dcd9e0d406746ab7f4da120c0b650fd3d',
 'games/yorimichi/world/region_mesh_parts.py': 'd93f2c4deb9c2c08bd730b7a4f1476b0ccf7a3dc7de2f604363c2ce8d4cc4725',
 'games/yorimichi/world/region_plan_files.py': '7451f36a391a5bd6a4c7e12a489b3ec8da64df3a14843257b7626e3958b736c6',
 'games/yorimichi/world/region_query.py': 'fa96910b6715daa5ed9cde939b9a8ed7b9677ea869983c385849e2785e3dce15',
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
 'games/yorimichi/world/regions/hidamari/city_data.py': '48f11986b20579347ff7c9f553238b5b694f98802e694565db3b7e9f3a524ac7',
 'games/yorimichi/world/regions/hidamari/city_poles.py': 'fbaa3df64b865694c1c79dd0cc49c273d9e4dc8faa34fd2186e0337160d1438d',
 'games/yorimichi/world/regions/hidamari/environment.py': 'd4d564fabed489a0c17e261f7ae86da5c471d23e4314e4acd740a525266d70cf',
 'games/yorimichi/world/regions/hidamari/forest_backdrop.py': '7efc1de4832350d2c409b4303f823b351d5ddad32ec98af95fac39931f7d8d9f',
 'games/yorimichi/world/regions/hidamari/harbor.py': '22fa9e6507038d6fe9adf727dbfdb9b3fcbe9bdc76b44e04c9beca46d7c78593',
 'games/yorimichi/world/regions/hidamari/harbor_mesh.py': '77023224cc7ed4802776307b80a3d2dfaf9142e6bed302a4f263a99bfcd0f9d5',
 'games/yorimichi/world/regions/hidamari/house_gardens.py': '82e912101b69472f2c4601d5a4b345d5d84f54874eead8129274691018ef75de',
 'games/yorimichi/world/regions/hidamari/layout.py': '8d2f1052f48764710cc5461e4dd21bf54a48aac8b25093f23daac485480c4ea2',
 'games/yorimichi/world/regions/hidamari/lettering_mesh.py': '552296ae5b603383e2a3d9e355fff0dc6236e219ba490dc5ef4c6a7f99d51d20',
 'games/yorimichi/world/regions/hidamari/logical/HD_Harbor.py': 'cf396339703423f759ad75a36d6b23a7d9903b67355d5ea8b6b09b0a56eaf04c',
 'games/yorimichi/world/regions/hidamari/logical/__init__.py': '83ee1455d7a04dba4fa5dc3060d474f78964779c300d370063dcd5398e46d23d',
 'games/yorimichi/world/regions/hidamari/mountains.py': '894f1bc5df848a5d7a49a4cc911ca576d146a8cbece6c6c4b294c16168c41a42',
 'games/yorimichi/world/regions/hidamari/natural_terrain.py': 'c8748da490a5cf964155d75d98f18d6da6ae593362b584be542c8ae10829dc3e',
 'games/yorimichi/world/regions/hidamari/park_grounds_placement.py': 'c2e60649927e81bae99c2c43ed00a1f1d49714e6d86c064de5fd1aea4c445cf7',
 'games/yorimichi/world/regions/hidamari/plan_asset.py': 'c9445f4839e41a78a51d78d708d4fc06fe5b97a8e43b811bc6305729cb442dcc',
 'games/yorimichi/world/regions/hidamari/public_spaces.py': 'fc2268a646ad218c6c4dfec7e66231934f0db54043d7f93e12a3f2b0f40b9044',
 'games/yorimichi/world/regions/hidamari/source_context.py': '096ce32a42fc6d01892484143ee68975cef33b450425d9f8573073459899fdad',
 'games/yorimichi/world/regions/hidamari/station_yard_placement.py': 'ce4478163ee0f994482de6c00272c5a5b7955442c16b988c2d3c842c0ae14004',
 'games/yorimichi/world/regions/hidamari/street_props.py': '4488a4ee3f0952da054fbf5c190285b51c5042ba6939d0b947eacda520a9fc5e',
 'games/yorimichi/world/regions/hidamari/surfaces.py': '15d1f4903c882a161afe55c7610272d35e46e9fec76f44e7e6520a9e1047ef5b',
 'games/yorimichi/world/regions/hidamari/temple_precinct_placement.py': '4ef637e8be482ecba46ed21aa121937e6a7054e62748af0490f4911b5dd51fc0',
 'games/yorimichi/world/regions/hidamari/working_harbor.py': '8f6a15500a0041415ed7cea6902b35b9f368af78de4e941f205f5125f4e88b0b',
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
 'games/yorimichi/world/source_geometry.py': '55e2be80d5c20d3bd073c766e4916f7d33a697150320bd254e8dc7ea411d7291',
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
 'platform/studio/atelier/build_batch_source.py': '2a61a96a1929832346327d0465a4c18e419c2e4e686d4a8cc7e06c436608195c',
 'platform/studio/atelier/build_batch_worker.py': 'b8812145d851943019b0415a330b27a6996b8921ecd4a9a146dbe5c8d937d22d',
 'platform/studio/atelier/export_manifest.py': '44da92d248422d587ebcb08b57e3f4308e7760411b68cccca28784abd5b7f3a6',
 'platform/studio/atelier/gltf.py': 'f5d5bb2bcd2e4fd22c534c49231080057ca81c9fa2fd4855d6978bd0d8d0358d',
 'platform/studio/atelier/mesh_cells.py': 'db88ba7bf0803fcae6abccbbc20fbc6c4e10965d3d721e770317640298ea887f',
 'platform/studio/atelier/mesh_collision.py': 'c2d7813ef2194ce82d9d2f908bb0b1c9919462c1c046db527167d18838c82183',
 'platform/studio/atelier/mesh_ir.py': '1522b888aefd3b7b0a3e63135972a45e5d9b11c2b1cdf4489b7ffa073a2d1cad',
 'platform/studio/atelier/mesh_materials.py': 'f0c4f63670c7d51d0769eef9128e587fdb65ee7cf1aab7f6fbbdb3f0479623e9',
 'platform/studio/atelier/mesh_partition.py': 'd6ab94f80cf8f3f220d422a194e8bd4e7a171c31ad9da56de9ecb1853a8b9ea3',
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
 'local:crater_geometry': 'efd75c9af468f4af4a02ff49bfa45c72a5658baa1ac20b86795b88de5f9e2d3c',
 'call:mesh_steps': '382b7334b9032e889da0f01e8b85b793a7232548cce0a39d1a5a0d6b4063fac7'}

HELPER_DIGESTS = {'import:1': '866a97c0a29d398dc2bf8a74409548dccd9bb5221f4bf0f58ad1a37ef83e5260',
 'import:2': '59051b17634cdcb5a576ceb58fdc0a4e5652ed3b60d66667e92ddefd931abeca',
 'import:3': '8a07a36ac15a922fa51057c063deda3a4eee1b9757f3ebfe97c2eb487778498a',
 'import:4': '033a6e1054e29744f788e36342fd6cba5d20cc14627b2ad6ab7eb541b3fac570',
 'import:5': 'fecb1cd4375004910b418012e1939abfd23827cb7be4bcea05aea7b7fe27f793',
 'assignment:GAME': 'c1fd8717a5ba75944ea2ab756a826c928f37e4d09c8df0b4b5ecd50571f84dbb',
 'assignment:WORLD': '12574000f07cf0e48410791ecd814d26eb908d4d94356d7fadb766d1252711f9',
 'assignment:REGIONS': '681755203859b40ea7a6f69813dcd7b8374111a7b4952ca112164344049a062c',
 'assignment:REGION': '2837f748dcbe0a5e7c36625088f200210b0004542af407e3cc8ebd9daf392cd0',
 'assignment:DATA_ASSETS': 'f11ce575ed6423d21e542038247b812f61c271167d4c8eb499dfcfee21164e2d',
 'function:load': '7735669a27d26d2a51b6e6feec9499fed8b8f86d2be1f3eca23dac2c97567be0',
 'function:mesh_steps': '0db6b184595ec1419dd023a489762016c32c41b457e0583aaf8643fcdf0644c0'}

SCRIPT_ROLES = ('games/yorimichi/world/mesh_pieces.py',
 'games/yorimichi/world/random_stream.py',
 'games/yorimichi/world/region_mesh_parts.py',
 'games/yorimichi/world/region_plan_files.py',
 'games/yorimichi/world/region_query.py',
 'games/yorimichi/world/regions/hidamari/__init__.py',
 'games/yorimichi/world/regions/hidamari/city_data.py',
 'games/yorimichi/world/regions/hidamari/plan_asset.py',
 'games/yorimichi/world/regions/hidamari/source_context.py',
 'games/yorimichi/world/regions/hidamari/surfaces.py',
 'games/yorimichi/world/regions/village/__init__.py',
 'games/yorimichi/world/regions/village/layout.py',
 'games/yorimichi/world/regions/village/mesh.py',
 'games/yorimichi/world/source_geometry.py',
 'games/yorimichi/world/yori.py',
 'platform/studio/atelier/__init__.py',
 'platform/studio/atelier/atomic_files.py',
 'platform/studio/atelier/blender/__init__.py',
 'platform/studio/atelier/blender/fbx.py',
 'platform/studio/atelier/export_manifest.py',
 'platform/studio/atelier/mesh_cells.py',
 'platform/studio/atelier/mesh_collision.py',
 'platform/studio/atelier/mesh_ir.py',
 'platform/studio/atelier/mesh_materials.py',
 'platform/studio/atelier/mesh_partition.py',
 'platform/studio/atelier/model_files.py',
 'platform/studio/atelier/paths.py')

CONSTRUCTOR_ROLES = ('games/yorimichi/world/coast_water.py',
 'games/yorimichi/world/coastal_surface.py',
 'games/yorimichi/world/farhills_grid.py',
 'games/yorimichi/world/regions/belmonte/__init__.py',
 'games/yorimichi/world/regions/belmonte/ground_names.py',
 'games/yorimichi/world/regions/belmonte/layout.py',
 'games/yorimichi/world/regions/belmonte/query_surface.py',
 'games/yorimichi/world/regions/belmonte/source.py',
 'games/yorimichi/world/regions/belmonte/terrain.py',
 'games/yorimichi/world/regions/belmonte/terrain_bounds.py',
 'games/yorimichi/world/regions/belmonte/terrain_palette.py',
 'games/yorimichi/world/regions/craterpark/__init__.py',
 'games/yorimichi/world/regions/craterpark/placement.py',
 'games/yorimichi/world/regions/craterpark/v2/__init__.py',
 'games/yorimichi/world/regions/craterpark/v2/curves.py',
 'games/yorimichi/world/regions/craterpark/v2/dsl.py',
 'games/yorimichi/world/regions/craterpark/v2/profile.py',
 'games/yorimichi/world/regions/craterpark/v2/v4_config.py',
 'games/yorimichi/world/regions/craterpark/v2/v4_placement.py',
 'games/yorimichi/world/regions/forest/__init__.py',
 'games/yorimichi/world/regions/forest/ecotone.py',
 'games/yorimichi/world/regions/forest/specs.py',
 'games/yorimichi/world/regions/hidamari/__init__.py',
 'games/yorimichi/world/regions/hidamari/arrival_placement.py',
 'games/yorimichi/world/regions/hidamari/city_poles.py',
 'games/yorimichi/world/regions/hidamari/environment.py',
 'games/yorimichi/world/regions/hidamari/forest_backdrop.py',
 'games/yorimichi/world/regions/hidamari/harbor.py',
 'games/yorimichi/world/regions/hidamari/harbor_mesh.py',
 'games/yorimichi/world/regions/hidamari/house_gardens.py',
 'games/yorimichi/world/regions/hidamari/layout.py',
 'games/yorimichi/world/regions/hidamari/lettering_mesh.py',
 'games/yorimichi/world/regions/hidamari/logical/HD_Harbor.py',
 'games/yorimichi/world/regions/hidamari/mountains.py',
 'games/yorimichi/world/regions/hidamari/natural_terrain.py',
 'games/yorimichi/world/regions/hidamari/park_grounds_placement.py',
 'games/yorimichi/world/regions/hidamari/public_spaces.py',
 'games/yorimichi/world/regions/hidamari/station_yard_placement.py',
 'games/yorimichi/world/regions/hidamari/street_props.py',
 'games/yorimichi/world/regions/hidamari/temple_precinct_placement.py',
 'games/yorimichi/world/regions/hidamari/working_harbor.py',
 'games/yorimichi/world/regions/hidamari_stable/__init__.py',
 'games/yorimichi/world/regions/hidamari_stable/layout.py',
 'games/yorimichi/world/regions/hippodrome/__init__.py',
 'games/yorimichi/world/regions/hippodrome/build.py',
 'games/yorimichi/world/regions/hippodrome/layout.py',
 'games/yorimichi/world/regions/megapark/__init__.py',
 'games/yorimichi/world/regions/megapark/forest.py',
 'games/yorimichi/world/regions/megapark/gate.py',
 'games/yorimichi/world/regions/megapark/placement.py',
 'games/yorimichi/world/regions/megapark/plants.py',
 'games/yorimichi/world/regions/megapark/trail.py',
 'games/yorimichi/world/regions/treehouse/__init__.py',
 'games/yorimichi/world/regions/treehouse/layout.py',
 'games/yorimichi/world/regions/treehouse/screen.py',
 'games/yorimichi/world/regions/village/__init__.py',
 'games/yorimichi/world/regions/village/layout.py',
 'games/yorimichi/world/regions/village/mesh.py',
 'games/yorimichi/world/regions/zeppelin/__init__.py',
 'games/yorimichi/world/regions/zeppelin/layout.py',
 'games/yorimichi/world/shorelines.py',
 'games/yorimichi/world/terrain_product.py',
 'games/yorimichi/world/terrain_query.py',
 'games/yorimichi/world/train/__init__.py',
 'games/yorimichi/world/train/corridor.py',
 'games/yorimichi/world/train/earthworks.py',
 'games/yorimichi/world/train/station_site.py',
 'games/yorimichi/world/yori.py',
 'platform/studio/atelier/__init__.py',
 'platform/studio/atelier/atomic_files.py',
 'platform/studio/atelier/blender/__init__.py',
 'platform/studio/atelier/blender/fbx.py',
 'platform/studio/atelier/gltf.py',
 'platform/studio/atelier/paths.py')

TAIL_ROLES = ('build/yorimichi/farhills.npy',
 'build/yorimichi/heightmap.npy',
 'build/yorimichi/megapark/trail.json',
 'build/yorimichi/treehouse/trees/trees.json',
 'build/yorimichi/world.json',
 'games/yorimichi/assets/craterpark/geometry',
 'games/yorimichi/assets/craterpark/scene.json',
 'games/yorimichi/assets/hidamari/export-parameters/HD_Harbor.json',
 'games/yorimichi/assets/hidamari/export-parameters/palettes/HD_Harbor.json',
 'games/yorimichi/assets/megapark/collision',
 'games/yorimichi/assets/megapark/geometry',
 'games/yorimichi/assets/megapark/map.json',
 'games/yorimichi/assets/vehicles/belmonte-train/line.json',
 'games/yorimichi/tools/craterpark_editor/data/inner_dug.bin',
 'games/yorimichi/tools/craterpark_editor/data/inner_natural.bin',
 'games/yorimichi/tools/craterpark_editor/data/outer.bin',
 'games/yorimichi/tools/craterpark_editor/data/terrain.json',
 'games/yorimichi/tools/craterpark_editor/shipped.json',
 'games/yorimichi/world/coast_water.py',
 'games/yorimichi/world/coastal_surface.py',
 'games/yorimichi/world/farhills_grid.py',
 'games/yorimichi/world/regions/belmonte/__init__.py',
 'games/yorimichi/world/regions/belmonte/ground_names.py',
 'games/yorimichi/world/regions/belmonte/layout.py',
 'games/yorimichi/world/regions/belmonte/query_surface.py',
 'games/yorimichi/world/regions/belmonte/source.py',
 'games/yorimichi/world/regions/belmonte/terrain.py',
 'games/yorimichi/world/regions/belmonte/terrain_bounds.py',
 'games/yorimichi/world/regions/belmonte/terrain_palette.py',
 'games/yorimichi/world/regions/craterpark/__init__.py',
 'games/yorimichi/world/regions/craterpark/placement.py',
 'games/yorimichi/world/regions/craterpark/v2/__init__.py',
 'games/yorimichi/world/regions/craterpark/v2/curves.py',
 'games/yorimichi/world/regions/craterpark/v2/dsl.py',
 'games/yorimichi/world/regions/craterpark/v2/profile.py',
 'games/yorimichi/world/regions/craterpark/v2/v4_config.py',
 'games/yorimichi/world/regions/craterpark/v2/v4_placement.py',
 'games/yorimichi/world/regions/forest/__init__.py',
 'games/yorimichi/world/regions/forest/ecotone.py',
 'games/yorimichi/world/regions/forest/specs.py',
 'games/yorimichi/world/regions/hidamari/__init__.py',
 'games/yorimichi/world/regions/hidamari/arrival_placement.py',
 'games/yorimichi/world/regions/hidamari/city_poles.py',
 'games/yorimichi/world/regions/hidamari/environment.py',
 'games/yorimichi/world/regions/hidamari/fonts/NotoSansJP.ttf',
 'games/yorimichi/world/regions/hidamari/forest_backdrop.py',
 'games/yorimichi/world/regions/hidamari/harbor.py',
 'games/yorimichi/world/regions/hidamari/harbor_mesh.py',
 'games/yorimichi/world/regions/hidamari/house_gardens.py',
 'games/yorimichi/world/regions/hidamari/layout.py',
 'games/yorimichi/world/regions/hidamari/lettering_mesh.py',
 'games/yorimichi/world/regions/hidamari/location.json',
 'games/yorimichi/world/regions/hidamari/logical/HD_Harbor.py',
 'games/yorimichi/world/regions/hidamari/logical/__init__.py',
 'games/yorimichi/world/regions/hidamari/mountains.py',
 'games/yorimichi/world/regions/hidamari/natural_terrain.py',
 'games/yorimichi/world/regions/hidamari/park_grounds_placement.py',
 'games/yorimichi/world/regions/hidamari/public_spaces.py',
 'games/yorimichi/world/regions/hidamari/station_yard_placement.py',
 'games/yorimichi/world/regions/hidamari/street_props.py',
 'games/yorimichi/world/regions/hidamari/temple_precinct_placement.py',
 'games/yorimichi/world/regions/hidamari/working_harbor.py',
 'games/yorimichi/world/regions/hidamari_stable/__init__.py',
 'games/yorimichi/world/regions/hidamari_stable/layout.py',
 'games/yorimichi/world/regions/hippodrome/__init__.py',
 'games/yorimichi/world/regions/hippodrome/build.py',
 'games/yorimichi/world/regions/hippodrome/layout.py',
 'games/yorimichi/world/regions/megapark/__init__.py',
 'games/yorimichi/world/regions/megapark/forest.py',
 'games/yorimichi/world/regions/megapark/gate.py',
 'games/yorimichi/world/regions/megapark/placement.py',
 'games/yorimichi/world/regions/megapark/plants.py',
 'games/yorimichi/world/regions/megapark/trail.py',
 'games/yorimichi/world/regions/treehouse/__init__.py',
 'games/yorimichi/world/regions/treehouse/layout.py',
 'games/yorimichi/world/regions/treehouse/screen.py',
 'games/yorimichi/world/regions/village/__init__.py',
 'games/yorimichi/world/regions/village/layout.py',
 'games/yorimichi/world/regions/village/mesh.py',
 'games/yorimichi/world/regions/zeppelin/__init__.py',
 'games/yorimichi/world/regions/zeppelin/layout.py',
 'games/yorimichi/world/shorelines.py',
 'games/yorimichi/world/terrain_product.py',
 'games/yorimichi/world/terrain_query.py',
 'games/yorimichi/world/train/__init__.py',
 'games/yorimichi/world/train/corridor.py',
 'games/yorimichi/world/train/earthworks.py',
 'games/yorimichi/world/train/station_site.py',
 'games/yorimichi/world/yori.py',
 'platform/studio/atelier/__init__.py',
 'platform/studio/atelier/atomic_files.py',
 'platform/studio/atelier/blender/__init__.py',
 'platform/studio/atelier/blender/fbx.py',
 'platform/studio/atelier/gltf.py',
 'platform/studio/atelier/paths.py')


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
        raise UnsupportedHidamariHarborSource(f'linked, missing or invalid source/data file: {path}') from error

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
        raise UnsupportedHidamariHarborSource(f'linked, missing or invalid input role: {path}') from error

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
            raise UnsupportedHidamariHarborSource('invalid output ancestry') from error
        expected = stat.S_ISDIR if directory or current != path else stat.S_ISREG
        if not expected(info.st_mode):
            raise UnsupportedHidamariHarborSource('linked or invalid output role')
        if stat.S_ISDIR(info.st_mode):
            try:
                descriptor = _open_root(current)
                os.close(descriptor)
            except OSError as error:
                raise UnsupportedHidamariHarborSource('linked output ancestry') from error
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
        raise UnsupportedHidamariHarborSource('invalid raw JSON declaration') from error

def _ast(checkout, path):
    try:
        return ast.parse(_read(checkout, path), filename=str(path))
    except (SyntaxError, ValueError) as error:
        raise UnsupportedHidamariHarborSource('invalid captured source structure') from error

def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

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
    if len(world)!=1:raise UnsupportedHidamariHarborSource('original world constructor differs')
    nodes['call:mesh_steps']=[n for n in ast.walk(world[0]) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='mesh_steps'
        and 'hidamari_build.py' in ast.unparse(n.func.value)]
    nodes['local:crater_geometry']=[n for n in world[0].body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='crater_geometry' for t in n.targets)]
    for role,expected in RECIPE_DIGESTS.items():
        found=nodes.get(role,[])
        if len(found)!=1 or _digest(found[0])!=expected:raise UnsupportedHidamariHarborSource('original recipe source differs: '+role)
    helper=_ast(checkout,game/'hidamari_build.py');nodes={}
    for i,n in enumerate(helper.body):
        if isinstance(n,(ast.Import,ast.ImportFrom)):nodes['import:'+str(i)]=[n]
        if isinstance(n,ast.FunctionDef):nodes.setdefault('function:'+n.name,[]).append(n)
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name):nodes.setdefault('assignment:'+t.id,[]).append(n)
    for role,expected in HELPER_DIGESTS.items():
        found=nodes.get(role,[])
        if len(found)!=1 or _digest(found[0])!=expected:raise UnsupportedHidamariHarborSource('original city constructor source differs: '+role)
    for source,expected in zip(code,CODE_DIGESTS.values()):
        if _digest(_ast(checkout,source))!=expected:raise UnsupportedHidamariHarborSource('original source structure differs: '+source.name)


def _closures(checkout,world,studio,step,expected):
    from atelier import paths
    from atelier.build import _FastImportScanner
    allowed=set(expected)
    def read(p):
        if p not in allowed:raise UnsupportedHidamariHarborSource('unknown source import target')
        _read(checkout,p)
    def anchor(p):
        if p==paths.STUDIO:return studio
        if p==paths.STUDIO/'atelier':return studio/'atelier'
        return p
    class Checked(_FastImportScanner.__bases__[0]):
        def resolve(self,root,parts):
            found=super().resolve(anchor(root),parts)
            for p in found:read(p)
            return found
    scanner=Checked();observed=set()
    for relative,roles in (('regions/hidamari/plan_asset.py',SCRIPT_ROLES),('regions/hidamari/logical/HD_Harbor.py',CONSTRUCTOR_ROLES)):
        actual=tuple(scanner.local_imports(world/relative,(world,world/'regions',studio)))
        wanted=tuple(checkout/p for p in roles)
        for p in actual:read(p)
        if actual!=wanted:raise UnsupportedHidamariHarborSource('original sorted source closure differs')
        observed.update(actual)
    observed.update(p for p in step.inputs if p.suffix=='.py')
    if tuple(sorted(observed))!=expected:raise UnsupportedHidamariHarborSource('selected union source closure differs')


def _context(checkout,path):
    _role(checkout,path);doc=_json(checkout,path)
    if (type(doc) is not dict or set(doc)!={'schema','asset','seed','prefix_words','palette_file'}
        or type(doc['schema']) is not int or doc['schema']!=1 or doc['asset']!='HD_Harbor'
        or type(doc['seed']) is not int or type(doc['prefix_words']) is not int
        or not 0<=doc['prefix_words']<=1_000_000 or type(doc['palette_file']) is not str):
        raise UnsupportedHidamariHarborSource('invalid selected source context')
    value=doc['palette_file'];stem=Path(value).stem
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',stem,re.ASCII) or value!='palettes/'+stem+'.json':
        raise UnsupportedHidamariHarborSource('invalid selected palette membership')
    palette=path.parent/value;_role(checkout,palette);colours=_json(checkout,palette)
    if (type(colours) is not dict or not colours or any(type(k) is not str or not k or type(v) is not list or len(v)!=3
        or any(type(c) not in (int,float) or not math.isfinite(c) for c in v) for k,v in colours.items())):
        raise UnsupportedHidamariHarborSource('invalid selected source palette')
    return palette


def qualify_hidamari_harbor_source(step,*,checkout:Path,output_root:Path)->HidamariHarborSource:
    """@cc [owner:fontanierh,label:correctness;safety] closed-harbor-source-batch-observation
    Accept only the original HD_Harbor source-only command, Batch, controls, selected
    context/palette membership, ordered input roles, complete fixed constructor closure
    and two named products. Raw/full keep identical inputs and their original named
    Far/canopy reads. Generated payloads MUST NOT be opened. Qualification MUST NOT run
    producers/helpers, mutate metadata, confer execution/repair/receipt authority or
    grant any other dynamic constructor, future batch member, plan or FBX output.
    """
    from atelier import build,build_products
    try:checkout,output_root=Path(checkout),Path(output_root)
    except (TypeError,ValueError) as e:raise UnsupportedHidamariHarborSource('invalid anchors') from e
    if any(os.environ.get(n,'').strip() for n in ('ATELIER_CRATERPARK_V4_DESIGN','ATELIER_CRATERPARK_EDITOR_PARK','ATELIER_CRATERPARK_EDITOR_LINES')):
        raise UnsupportedHidamariHarborSource('not the default shipped editor context')
    if (type(step) is not build.Step or getattr(step,'name',None)!='world.hidamari.source.HD_Harbor'
        or not checkout.is_absolute() or not output_root.is_absolute() or '..' in checkout.parts or '..' in output_root.parts
        or checkout==Path(checkout.anchor) or output_root==Path(output_root.anchor)):
        raise UnsupportedHidamariHarborSource('not the original Harbor Step and absolute anchors')
    game=checkout/'games/yorimichi';world=game/'world';regions=world/'regions';studio=checkout/'platform/studio'
    script=regions/'hidamari/plan_asset.py';parameters=game/'assets/hidamari/export-parameters/HD_Harbor.json'
    source=output_root/'hidamari/source-data/HD_Harbor';query=output_root/'hidamari/query-data/HD_Harbor.raw.npz'
    arguments=('--asset','HD_Harbor','--context',str(parameters),'--source-only','--output',str(source),'--query-output',str(query))
    products=(('hidamari.source.HD_Harbor',(source,)),('hidamari.query.HD_Harbor.raw',(query,)))
    defaults=dict(deferred_inputs=[],needs=['world.layout','world.treehouse_trees','world.craterpark_layout','world.craterpark_geometry'],
        after=[],heavy=True,pool_roots=[],explicit=False,verify=None,cutoff=False,references=[],cache=True,audit=False,
        optional_inputs=[],queries=[],toolchain=True,cook_recovery=None,checkpoint_previous_needs=None,
        checkpoint_restore=None,checkpoint_outputs=(),candidate_scope=None,replan=False,controller=None,outputs=[],
        about='raw Harbor source/query data before ferry access cuts; no mesh export')
    if (set(vars(step))!=set(defaults)|{'name','commands','inputs','products','reads','batch'}
        or any(not _exact(vars(step)[k],v) for k,v in defaults.items())):raise UnsupportedHidamariHarborSource('original Step controls differ')
    b=step.batch
    if (type(b) is not build.Batch or set(vars(b))!={'group','runtime_env','max_seconds'}
        or not _exact(b.group,'hidamari logical geometry') or not _exact(b.runtime_env,())
        or type(b.max_seconds) is not float or b.max_seconds!=240.):raise UnsupportedHidamariHarborSource('original Batch differs')
    if type(step.commands) is not list or len(step.commands)!=1:raise UnsupportedHidamariHarborSource('expected one original Blender command')
    c=step.commands[0]
    if (type(c) is not build.Blender or set(vars(c))!={'script','args','threads','factory_startup','env'}
        or not _exact(c.script,script) or not _exact(c.args,arguments) or type(c.threads) is not int or c.threads!=3
        or c.factory_startup is not True or not _exact(c.env,(('PYTHONHASHSEED','0'),))):raise UnsupportedHidamariHarborSource('original Blender command differs')
    if type(step.products) is not list or len(step.products)!=2:raise UnsupportedHidamariHarborSource('original products differ')
    for p,(name,paths) in zip(step.products,products):
        if (type(p) is not build_products.Product or set(vars(p))!={'name','paths','collection','bounds','optional_paths'}
            or not _exact(p.name,name) or not _exact(p.paths,paths) or p.collection is not None or p.bounds is not None
            or not _exact(p.optional_paths,())):raise UnsupportedHidamariHarborSource('original products differ')
    raw_reads=['terrain.FarHills.final'];full_reads=[*raw_reads,'treehouse.canopy_dimensions']
    if not (_exact(step.reads,raw_reads) or _exact(step.reads,full_reads)):raise UnsupportedHidamariHarborSource('original named reads differ')
    for p in (checkout,checkout/'games',game,world,regions,regions/'hidamari',checkout/'platform',studio):_role(checkout,p,directory=True)
    code=tuple(checkout/p for p in CODE_DIGESTS)
    for p in (*code,game/'build.py',game/'hidamari_build.py'):_role(checkout,p)
    generated=tuple(output_root/p for p in ('farhills.npy','heightmap.npy','megapark/trail.json','treehouse/trees/trees.json','world.json'))
    produced=(*generated,output_root/'terrain/FarHills/final.npz')
    if step.reads==full_reads:produced+= (output_root/'treehouse-data/canopy/trees.json',)
    _output(output_root,directory=True);_output(source,directory=True)
    for p in (*produced,query):_output(p,directory=False)
    palette=_context(checkout,parameters)
    data=game/'tools/craterpark_editor/data';park=data.parent/'shipped.json'
    for p in (park,data/'terrain.json'):_role(checkout,p)
    document,terrain=_json(checkout,park),_json(checkout,data/'terrain.json')
    try:
        layers=terrain['inner']['layers'];files=[*layers.values(),terrain['outer']['file']]
        if document['schema']!='craterpark-editor/1' or set(layers)!={'natural','dug'}:raise ValueError('editor metadata')
        if (any(type(n) is not str or n in ('','.','..') or '/' in n or '\\' in n or '\x00' in n for n in files)
            or len({n.casefold() for n in files})!=len(files)):raise ValueError('terrain names')
    except (KeyError,TypeError,AttributeError,ValueError) as e:raise UnsupportedHidamariHarborSource('invalid raw editor membership') from e
    substitutions=dict(zip(('inner_natural.bin','inner_dug.bin','outer.bin'),files));tail=[]
    for role in TAIL_ROLES:
        p=output_root/role[len('build/yorimichi/'):] if role.startswith('build/yorimichi/') else checkout/role
        if p.parent==data and p.name in substitutions:p=data/substitutions[p.name]
        if role=='games/yorimichi/assets/hidamari/export-parameters/palettes/HD_Harbor.json':p=palette
        tail.append(p)
    inputs=[*(checkout/p for p in SCRIPT_ROLES),studio/'atelier/build_batch_source.py',studio/'atelier/build_batch_worker.py',*sorted(tail)]
    if not _exact(step.inputs,inputs):raise UnsupportedHidamariHarborSource('original ordered inputs differ')
    raw=[p for p in inputs if p not in generated]
    directories={game/'assets/craterpark/geometry',game/'assets/megapark/geometry',game/'assets/megapark/collision'}
    for p in raw:_role(checkout,p,directory=p in directories)
    _source_contract(checkout,game,code);_closures(checkout,world,studio,step,code)
    return HidamariHarborSource(step.name,script,arguments,tuple(raw),tuple(produced),code,products)
