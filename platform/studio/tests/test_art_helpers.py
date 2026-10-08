"""The shared art helpers: compact JPEG copies, set-aside records, error redaction, contact sheets and compact GLBs."""
import io
import struct

import pytest
from PIL import Image

from atelier import gltf
from atelier.ai import images, ledger
from atelier.review import contact_sheet


def png(size, colour=(200, 80, 40)):
    buf = io.BytesIO(); Image.new('RGB', size, colour).save(buf, 'PNG')
    return buf.getvalue()


def test_compact_shrinks_wide_images_and_never_enlarges(tmp_path):
    record = images.compact(png((3200, 1600)), tmp_path / 'a' / 'wide.jpg', 1600, 88)
    assert record == dict(file='wide.jpg', size='1600x800', jpeg_quality=88, chroma='4:2:0')
    assert Image.open(tmp_path / 'a' / 'wide.jpg').size == (1600, 800)
    small = tmp_path / 'small.png'; small.write_bytes(png((300, 200)))
    assert images.compact(small, tmp_path / 'small.jpg', 1024, 92, '4:4:4')['size'] == '300x200'


def test_set_aside_keeps_every_earlier_record(tmp_path):
    record = tmp_path / 'street.provenance.json'
    for n in (1, 2):
        record.write_text(str(n))
        assert ledger.set_aside(record).name == f'street.provenance.rejected-{n}.json'
    assert not record.exists() and (tmp_path / 'street.provenance.rejected-2.json').read_text() == '2'


def test_redact_removes_signed_urls():
    assert ledger.redact(RuntimeError('HTTP 403 at https://x.example/a?sig=1 retry')) == 'HTTP 403 at <URL omitted> retry'


def test_contact_sheet_tiles_existing_images_with_captions(tmp_path):
    paths = []
    for i in range(3):
        paths.append(tmp_path / f'{i}.png'); paths[-1].write_bytes(png((64, 32)))
    dest = contact_sheet.sheet([(p, p.stem) for p in paths] + [(tmp_path / 'missing.png', 'x')],
                               tmp_path / 'out' / 'sheet.jpg', 100, 50, 2)
    assert dest == tmp_path / 'out' / 'sheet.jpg' and Image.open(dest).size == (200, 2 * (50 + 30))
    assert contact_sheet.sheet([(tmp_path / 'missing.png', 'x')], tmp_path / 'none.jpg', 100, 50, 2) is None


def glb(texture, geometry=b'\x01\x02\x03'):
    views = [dict(buffer=0, byteOffset=0, byteLength=len(geometry)),
             dict(buffer=0, byteOffset=4, byteLength=len(texture))]
    binary = geometry + b'\0' + texture
    doc = dict(asset={'version': '2.0'}, buffers=[{'byteLength': len(binary)}], bufferViews=views,
               images=[dict(bufferView=1, mimeType='image/png')])
    return gltf.glb_pack(doc, binary)


def test_glb_parts_reads_what_glb_pack_writes():
    data = glb(b'texture!')
    doc, binary = gltf.glb_parts(data)
    assert len(data) % 4 == 0 and struct.unpack('<4sII', data[:12]) == (b'glTF', 2, len(data))
    assert doc['images'][0]['mimeType'] == 'image/png' and binary[:3] == b'\x01\x02\x03' and binary[4:12] == b'texture!'
    with pytest.raises(ValueError, match='not a glTF 2 binary'):
        gltf.glb_parts(data[:-4])


def test_compact_glb_reencodes_textures_and_keeps_geometry_bytes():
    doc, binary = gltf.glb_parts(gltf.compact_glb(glb(png((2048, 1024))), size=512))
    geometry, texture = doc['bufferViews']
    assert binary[:geometry['byteLength']] == b'\x01\x02\x03' and texture['byteOffset'] % 4 == 0
    image = Image.open(io.BytesIO(binary[texture['byteOffset']:texture['byteOffset'] + texture['byteLength']]))
    assert image.format == 'JPEG' and image.size == (512, 256) and doc['images'][0]['mimeType'] == 'image/jpeg'
    assert doc['buffers'][0]['byteLength'] == texture['byteOffset'] + texture['byteLength']
