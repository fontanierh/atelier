"""The package header reader understands real Unreal Engine 5 editor packages and refuses what it cannot read.

CI has no engine, so a small synthetic header builder covers every version branch the reader takes. When the engine
templates are installed, the reader is also run over their real One File Per Actor packages.
"""
import base64
import json
import struct

import pytest

from atelier import unreal_package_summary as ups
from atelier.engine import unreal_root

ENGINE = unreal_root()
OFPA_ROOTS = [ENGINE / 'Templates' / name / 'Content' / '__ExternalActors__'
              for name in ('TP_ThirdPerson', 'TP_FirstPerson', 'TP_TopDown')]
OFPA_ROOTS.append(ENGINE / 'Engine/Plugins/Experimental/PCGBiomeSample/Content/__ExternalActors__')
KNOWN_ACTOR = OFPA_ROOTS[0] / 'Variant_Platforming/Lvl_Platforming/5/PQ/PI85JOOOY2R6IWIS0B5ZV5.uasset'
needs_engine = pytest.mark.skipif(not KNOWN_ACTOR.is_file(), reason='Unreal Engine 5.8 templates are not installed')


# -- a minimal header writer, the mirror of the reader --------------------------------------------------------------

def fstring(text: str) -> bytes:
    if text == '':
        return struct.pack('<i', 0)
    if all(ord(c) < 128 for c in text):
        raw = text.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    raw = text.encode('utf-16-le') + b'\0\0'
    return struct.pack('<i', -(len(raw) // 2)) + raw


def guid_bytes(text: str) -> bytes:
    return struct.pack('<IIII', *(int(text[i:i + 8], 16) for i in range(0, 32, 8)))


def engine_version(major=5, minor=8, patch=0, changelist=1, branch='++UE5+Release-5.8') -> bytes:
    return struct.pack('<HHHI', major, minor, patch, changelist) + fstring(branch)


CUSTOM = {ups.UE5_MAIN_STREAM: 121, ups.UE5_RELEASE_STREAM: 56, ups.FORTNITE_MAIN: 207, ups.FORTNITE_SEASON: 13}


def actor_metadata(*, guid='5511878F4A993B5BB7436D78F81A56A5', location=(1500.0, 5300.0, 450.0),
                   base=('None', 'None'), native=('/Script/Engine', 'StaticMeshActor'), versions=None) -> str:
    versions = CUSTOM if versions is None else versions
    blob = struct.pack('<i', len(versions))
    blob += b''.join(guid_bytes(k) + struct.pack('<i', v) for k, v in versions.items())
    blob += struct.pack('<I', 0) + fstring(base[0]) + fstring(base[1]) + fstring(native[0]) + fstring(native[1])
    blob += guid_bytes(guid) + struct.pack('<4d', 0, 0, 0, 1) + struct.pack('<3d', *location)
    blob += struct.pack('<3d', 1, 1, 1) + b'\0' * 24          # the rest of the descriptor is not read
    return base64.b64encode(blob).decode()


def build_package(*, package_name='/Game/Props/SM_Box', ue5=ups.UE5_NEWEST_KNOWN, legacy=-9, ue4=522, licensee=0,
                  tag=ups.PACKAGE_FILE_TAG, flags=0, compression=0, names=None, imports=(), assets=(),
                  custom=None, tail=b'', header_size=None) -> bytes:
    """Bytes of an uncooked package header in the layout of object version `ue5`.

    `imports` holds (class_package, class_name, outer, object_name, package_name) tuples of names; names are added
    to the name table as needed. `assets` holds (object_path, class_path, {tag: value}).
    """
    names = list(names or [])
    for entry in imports:
        for value in (entry[0], entry[1], entry[3], entry[4]):
            base = value.rsplit('_', 1)[0] if value.endswith('_7') else value
            if base not in names:
                names.append(base)
    custom = CUSTOM if custom is None else custom

    def name_ref(value):
        if value.endswith('_7'):
            return struct.pack('<ii', names.index(value[:-2]), 8)
        return struct.pack('<ii', names.index(value), 0)

    name_table = b''.join(fstring(n) + b'\0\0\0\0' for n in names)
    import_table = b''.join(name_ref(c) + name_ref(k) + struct.pack('<i', o) + name_ref(n) + name_ref(p)
                            + (struct.pack('<I', 0) if ue5 >= ups.UE5_OPTIONAL_RESOURCES else b'')
                            for c, k, o, n, p in imports)
    registry = struct.pack('<qi', 0, len(assets))
    for path, cls, tags in assets:
        registry += fstring(path) + fstring(cls) + struct.pack('<i', len(tags))
        registry += b''.join(fstring(k) + fstring(v) for k, v in tags.items())

    def summary(name_offset, import_offset, registry_offset, total):
        i = lambda *values: struct.pack('<' + 'i' * len(values), *values)   # noqa: E731
        out = struct.pack('<I', tag) + i(legacy, 864, ue4, ue5, licensee)
        if ue5 >= ups.UE5_PACKAGE_SAVED_HASH:
            out += b'\x11' * 20 + i(total)
        out += i(len(custom)) + b''.join(guid_bytes(k) + i(v) for k, v in custom.items())
        if ue5 < ups.UE5_PACKAGE_SAVED_HASH:
            out += i(total)
        out += fstring(package_name) + struct.pack('<I', flags) + i(len(names), name_offset)
        if ue5 >= ups.UE5_ADD_SOFTOBJECTPATH_LIST:
            out += i(0, import_offset)
        out += fstring('98A9ABFF2AC4311616CBFCE92C62DE50') + i(0, import_offset)
        out += i(0, registry_offset, len(imports), import_offset)
        if ue5 >= ups.UE5_VERSE_CELLS:
            out += i(0, registry_offset, 0, registry_offset)
        if ue5 >= ups.UE5_METADATA_SERIALIZATION_OFFSET:
            out += i(import_offset)
        out += i(registry_offset, 0, registry_offset, registry_offset, 0)
        if ue5 >= ups.UE5_IMPORT_TYPE_HIERARCHIES:
            out += i(0, registry_offset)
        if ue5 < ups.UE5_PACKAGE_SAVED_HASH:
            out += b'\x22' * 16
        out += b'\x33' * 16 + i(1, 0, len(names)) + engine_version() + engine_version()
        out += struct.pack('<I', compression) + i(0) + struct.pack('<I', 0) + i(0)
        out += i(registry_offset) + struct.pack('<q', total + len(tail)) + i(0) + i(0) + i(0, 0)
        if ue5 >= ups.UE5_NAMES_REFERENCED_FROM_EXPORT_DATA:
            out += i(len(names))
        if ue5 >= ups.UE5_PAYLOAD_TOC:
            out += struct.pack('<q', -1)
        if ue5 >= ups.UE5_DATA_RESOURCES:
            out += i(-1)
        return out

    size = len(summary(0, 0, 0, 0))
    name_offset = size
    import_offset = name_offset + len(name_table)
    registry_offset = import_offset + len(import_table)
    total = registry_offset + len(registry) if header_size is None else header_size
    return summary(name_offset, import_offset, registry_offset, total) + name_table + import_table + registry + tail


def actor_package(**kw):
    tags = {'ActorLabel': kw.pop('label', 'Bench'), 'ActorMetaDataClass': '/Script/Engine.StaticMeshActor',
            'ActorMetaData': actor_metadata(**kw.pop('metadata', {}))}
    tags.update(kw.pop('tags', {}))
    return build_package(
        package_name='/Game/__ExternalActors__/Maps/Island/5/PQ/PI85JOOOY2R6IWIS0B5ZV5',
        flags=ups.PKG_CONTAINS_MAP_DATA,
        assets=[('/Game/Maps/Island.Island:PersistentLevel.StaticMeshActor_1', '/Script/Engine.StaticMeshActor', tags)],
        **kw)


# -- synthetic headers: every branch -------------------------------------------------------------------------------

def test_reads_the_summary_names_imports_and_asset_registry():
    data = build_package(
        names=['None', 'StaticMesh'], flags=0,
        imports=[('/Script/CoreUObject', 'Package', 0, '/Game/Materials/M_Paint', 'None'),
                 ('/Script/Engine', 'Material', -1, 'M_Paint_7', 'None')],
        assets=[('SM_Box', '/Script/Engine.StaticMesh', {'Triangles': '12', 'Note': 'déjà vu ✓'})])
    package = ups.parse(data)
    s = package.summary
    assert (s.legacy_file_version, s.file_version_ue4, s.file_version_ue5) == (-9, 522, ups.UE5_NEWEST_KNOWN)
    assert s.package_name == package.package_name == '/Game/Props/SM_Box'
    assert s.custom_versions == CUSTOM and s.total_header_size == len(data)
    assert s.import_count == 2 and s.export_count == 0 and str(s.saved_by) == '5.8.0-1+++UE5+Release-5.8'
    assert s.saved_hash == '11' * 20 and s.persistent_guid == '33' * 16 and not s.is_map
    assert package.names[:2] == ['None', 'StaticMesh']
    assert package.imports[1].object_name == 'M_Paint_7' and package.imports[1].outer_index == -1
    assert package.imported_packages == ['/Game/Materials/M_Paint']
    assert package.assets[0].tags == {'Triangles': '12', 'Note': 'déjà vu ✓'}
    assert package.actor is None


@pytest.mark.parametrize('ue5', [1000, 1001, 1002, 1003, 1008, 1009, 1014, 1015, 1016, 1017, 1018])
def test_every_known_ue5_summary_layout(ue5):
    data = build_package(ue5=ue5, imports=[('/Script/CoreUObject', 'Package', 0, '/Game/A', 'None')],
                         assets=[('SM_Box', '/Script/Engine.StaticMesh', {'K': 'V'})])
    package = ups.parse(data)
    assert package.summary.file_version_ue5 == ue5
    assert package.summary.summary_size == package.summary.name_offset
    assert package.assets[0].class_path == '/Script/Engine.StaticMesh'
    assert package.imported_packages == ['/Game/A']
    assert len(package.summary.saved_hash) == (40 if ue5 >= ups.UE5_PACKAGE_SAVED_HASH else 32)


def test_legacy_minus_eight_is_read_like_minus_nine():
    assert ups.parse(build_package(legacy=-8)).summary.legacy_file_version == -8


def test_external_actor_descriptor_gives_map_label_class_guid_and_location():
    package = ups.parse(actor_package(label='Harbour bench', metadata={'location': (-1250.5, 300.0, 12.0)}))
    actor = package.actor
    assert actor.map == '/Game/Maps/Island' and actor.name == 'StaticMeshActor_1'
    assert actor.label == 'Harbour bench' and actor.class_path == '/Script/Engine.StaticMeshActor'
    assert actor.native_class == '/Script/Engine.StaticMeshActor' and actor.base_class is None
    assert actor.guid == '5511878F4A993B5BB7436D78F81A56A5'
    assert actor.location == (-1250.5, 300.0, 12.0) and actor.rotation == (0, 0, 0, 1) and actor.scale == (1, 1, 1)
    assert actor.descriptor == 'decoded'


def test_blueprint_actor_names_its_base_class_and_an_explicit_guid_tag_wins():
    package = ups.parse(actor_package(
        metadata={'base': ('/Game/BP/BP_Door', 'BP_Door_C'), 'native': ('/Script/Engine', 'Actor')},
        tags={'ActorGuid': 'AAAAAAAABBBBBBBBCCCCCCCCDDDDDDDD'}))
    assert package.actor.base_class == '/Game/BP/BP_Door.BP_Door_C'
    assert package.actor.guid == 'AAAAAAAABBBBBBBBCCCCCCCCDDDDDDDD'


def test_older_descriptor_layout_is_reported_not_guessed():
    old = dict(CUSTOM, **{ups.FORTNITE_MAIN: 120})
    actor = ups.parse(actor_package(metadata={'versions': old})).actor
    assert actor.descriptor.startswith('unsupported: descriptor custom versions')
    assert actor.location is None and actor.guid is None
    assert actor.label == 'Bench' and actor.map == '/Game/Maps/Island'     # the plain tags still read


def test_damaged_descriptor_is_reported():
    actor = ups.parse(actor_package(tags={'ActorMetaData': 'not base64!'})).actor
    assert actor.descriptor == 'unsupported: ActorMetaData is not base64' and actor.label == 'Bench'
    short = base64.b64encode(base64.b64decode(actor_metadata())[:120]).decode()
    actor = ups.parse(actor_package(tags={'ActorMetaData': short})).actor
    assert actor.descriptor.startswith('unsupported: descriptor truncated')


def test_external_object_without_metadata_still_names_its_map():
    data = build_package(package_name='/Game/__ExternalObjects__/Maps/Island/9/SK/PAE64UA62B4I6LK904O50Y',
                         assets=[('/Game/Maps/Island.Island:PersistentLevel.ActorFolder_1',
                                  '/Script/Engine.ActorFolder', {})])
    actor = ups.parse(data).actor
    assert (actor.map, actor.class_path, actor.descriptor, actor.guid) == \
        ('/Game/Maps/Island', '/Script/Engine.ActorFolder', 'absent', None)


@pytest.mark.parametrize('name,expected', [
    ('/Game/__ExternalActors__/Maps/Island/5/PQ/HASH', '/Game/Maps/Island'),
    ('/Game/__ExternalObjects__/Island/0/AB/HASH', '/Game/Island'),
    ('/PCGBiomeSample/__ExternalActors__/Maps/Biome/3/1C/HASH', '/PCGBiomeSample/Maps/Biome'),
    ('/Game/Props/SM_Bench', None),
    ('/Game/__ExternalActors__/0/AB/HASH', None),
])
def test_external_map_from_the_encoded_path(name, expected):
    assert ups.external_map(name) == expected


@pytest.mark.parametrize('kw,error,match', [
    ({'tag': 0x12345678}, ups.PackageError, 'not an Unreal package'),
    ({'tag': ups.PACKAGE_FILE_TAG_SWAPPED}, ups.UnsupportedPackage, 'byte-swapped'),
    ({'legacy': -7}, ups.UnsupportedPackage, 'legacy file version -7'),
    ({'legacy': -10}, ups.UnsupportedPackage, 'legacy file version -10'),
    ({'ue4': 0, 'ue5': 0}, ups.UnsupportedPackage, 'unversioned'),
    ({'ue4': 518}, ups.UnsupportedPackage, 'UE4 object version 518'),
    ({'ue5': ups.UE5_NEWEST_KNOWN + 1}, ups.UnsupportedPackage, 'outside the supported'),
    ({'licensee': 3}, ups.UnsupportedPackage, 'licensee'),
    ({'flags': ups.PKG_FILTER_EDITOR_ONLY}, ups.UnsupportedPackage, 'cooked'),
    ({'flags': ups.PKG_COOKED}, ups.UnsupportedPackage, 'cooked'),
    ({'compression': 1}, ups.UnsupportedPackage, 'compression'),
    ({'header_size': 40}, ups.CorruptPackage, 'smaller than'),
])
def test_unsupported_and_corrupt_headers_fail_clearly(kw, error, match):
    with pytest.raises(error, match=match):
        ups.parse(build_package(**kw))


def test_truncated_package_is_corrupt_not_a_crash():
    data = build_package(assets=[('SM_Box', '/Script/Engine.StaticMesh', {'K': 'V'})])
    for size in (8, 40, 120, len(data) - 3):
        with pytest.raises(ups.CorruptPackage):
            ups.parse(data[:size])


def test_unsupported_is_a_package_error_and_never_a_corrupt_one():
    assert issubclass(ups.UnsupportedPackage, ups.PackageError)
    assert not issubclass(ups.UnsupportedPackage, ups.CorruptPackage)


def test_read_stops_at_the_header(tmp_path):
    data = build_package(assets=[('SM_Box', '/Script/Engine.StaticMesh', {'K': 'V'})], tail=b'\xEE' * 300_000)
    path = tmp_path / 'SM_Box.uasset'
    path.write_bytes(data)
    assert ups.read(path).assets == ups.parse(data).assets


def test_command_line_prints_json_and_fails_on_a_bad_file(tmp_path, capsys):
    good, bad = tmp_path / 'a.uasset', tmp_path / 'b.uasset'
    good.write_bytes(actor_package())
    bad.write_bytes(b'not a package at all, but long enough to read a tag')
    assert ups.main([str(good)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['actor']['label'] == 'Bench'
    assert report['assets'][0]['tags']['ActorMetaData'].startswith('<')
    assert ups.main([str(bad)]) == 1


# -- real Unreal Engine 5.8 packages -------------------------------------------------------------------------------

def real_packages():
    return sorted(p for root in OFPA_ROOTS if root.is_dir() for p in root.rglob('*.uasset'))


@needs_engine
def test_a_known_template_actor():
    package = ups.read(KNOWN_ACTOR)
    actor = package.actor
    assert package.package_name == ('/Game/__ExternalActors__/Variant_Platforming/Lvl_Platforming/5/PQ/'
                                    'PI85JOOOY2R6IWIS0B5ZV5')
    assert package.summary.package_flags & ups.PKG_CONTAINS_MAP_DATA
    assert actor.map == '/Game/Variant_Platforming/Lvl_Platforming'
    assert actor.actor_path.endswith(':PersistentLevel.StaticMeshActor_1')
    assert actor.label == 'SM_QuarterCylinder17' and actor.class_path == '/Script/Engine.StaticMeshActor'
    assert actor.guid == '5511878F4A993B5BB7436D78F81A56A5'
    assert actor.location == pytest.approx((1500.0, 5300.0, 450.0)) and actor.scale == pytest.approx((2, 2, 0.1))
    assert '/Game/LevelPrototyping/Meshes/SM_QuarterCylinder' in package.imported_packages


@needs_engine
def test_every_template_actor_package_is_read():
    packages = real_packages()
    assert len(packages) > 500
    maps, decoded = set(), 0
    for path in packages:
        package = ups.read(path)
        actor = package.actor
        assert actor is not None, path
        assert ups.external_map(package.package_name) == actor.map, path
        assert ups.UE5_INITIAL <= package.summary.file_version_ue5 <= ups.UE5_NEWEST_KNOWN
        if actor.descriptor == 'decoded':
            decoded += 1
            assert actor.guid and len(actor.guid) == 32 and actor.location is not None, path
            assert actor.native_class and actor.class_path, path
        else:
            assert actor.descriptor == 'absent', (path, actor.descriptor)
        maps.add(actor.map)
    assert decoded > 0.9 * len(packages)
    assert any(m.startswith('/PCGBiomeSample/') for m in maps) and len(maps) >= 5


@needs_engine
def test_template_blueprint_actor_and_map_package():
    blueprint = next(ups.read(p).actor for p in real_packages() if ups.read(p).actor.base_class)
    assert blueprint.class_path.endswith('_C') and blueprint.native_class.startswith('/Script/')
    level = ENGINE / 'Templates/TP_ThirdPerson/Content/Variant_Platforming/Lvl_Platforming.umap'
    package = ups.read(level)
    assert package.summary.is_map and package.actor is None
    assert [(a.object_path, a.class_path) for a in package.assets] == [('Lvl_Platforming', '/Script/Engine.World')]
