"""Binary glTF (GLB) files without a 3D library: split one into its JSON and BIN chunks, pack them again, and make a
compact copy with smaller JPEG textures. Only the standard library is imported at load time (Pillow when compacting)."""
import io, json, struct


def glb_parts(data):
    """(JSON document, BIN chunk) of a binary glTF."""
    magic, version, length = struct.unpack('<4sII', data[:12])
    if magic != b'glTF' or version != 2 or length != len(data): raise ValueError('not a glTF 2 binary')
    size, kind = struct.unpack('<I4s', data[12:20])
    if kind != b'JSON': raise ValueError('first chunk is not JSON')
    doc = json.loads(data[20:20+size])
    at = 20+size; binary = b''
    if at < len(data):
        size, kind = struct.unpack('<I4s', data[at:at+8])
        if kind != b'BIN\0': raise ValueError('second chunk is not BIN')
        binary = data[at+8:at+8+size]
    return doc, binary


def glb_pack(doc, binary):
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' '*(-len(text) % 4); binary += b'\0'*(-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28+len(text)+len(binary)) + struct.pack('<I4s', len(text), b'JSON') + text
            + struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def compact_glb(data, size=1024, quality=90):
    """The same GLB with every embedded image re-encoded as a JPEG at most `size` pixels on a side. Geometry and
    every other buffer view keep their exact bytes; the views are laid out again, 4-byte aligned, in their order."""
    from PIL import Image
    doc, binary = glb_parts(data)
    views = doc['bufferViews']
    if len(doc.get('buffers', [])) != 1 or 'uri' in doc['buffers'][0] or any(v.get('buffer', 0) for v in views):
        raise ValueError('expected one embedded buffer')
    new = {}
    for image in doc.get('images', []):
        if 'bufferView' not in image: continue
        v = views[image['bufferView']]; start = v.get('byteOffset', 0)
        im = Image.open(io.BytesIO(binary[start:start+v['byteLength']])).convert('RGB')
        scale = size/max(im.size)
        if scale < 1: im = im.resize((round(im.width*scale), round(im.height*scale)), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=quality)
        new[image['bufferView']] = buf.getvalue(); image['mimeType'] = 'image/jpeg'
    order = sorted(range(len(views)), key=lambda i: views[i].get('byteOffset', 0))
    for a, b in zip(order, order[1:]):
        if views[a].get('byteOffset', 0)+views[a]['byteLength'] > views[b].get('byteOffset', 0):
            raise ValueError('overlapping buffer views')
    out = bytearray()
    for i in order:
        v = views[i]; start = v.get('byteOffset', 0)
        chunk = new.get(i, binary[start:start+v['byteLength']])
        out += b'\0'*(-len(out) % 4)
        v['byteOffset'] = len(out); v['byteLength'] = len(chunk); out += chunk
    doc['buffers'][0]['byteLength'] = len(out)
    return glb_pack(doc, bytes(out))
