"""Opt-in guarded native receiving proof, independent of any game's compiled modules."""
import io
import json
import os
from pathlib import Path
import struct


from atelier import engine
from atelier.gltf import glb_pack
from atelier.harness.safety import guarded



def source_glb():
    from PIL import Image
    binary, views, accessors = bytearray(), [], []
    def data(values, kind, width, component=5126):
        binary.extend(b'\0' * (-len(binary) % 4))
        payload = struct.pack('<' + ('f' if component == 5126 else 'H') * len(values), *values)
        views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(payload)))
        binary.extend(payload)
        accessors.append(dict(bufferView=len(views)-1, componentType=component, count=len(values)//width, type=kind))
        return len(accessors)-1
    positions = [(0.,0.,0.),(2.,0.,0.),(2.,1.,1.),(0.,0.,0.),(2.,1.,1.),(0.,1.,0.)]
    position = data([v for p in positions for v in p], 'VEC3', 3)
    accessors[position].update(min=[0,0,0], max=[2,1,1])
    normal = data([0.,0.,1.]*6, 'VEC3', 3)
    colour = data([1.,0.,0.,1., 0.,1.,0.,1., 0.,0.,1.,1.]*2, 'VEC4', 4)
    attributes = dict(POSITION=position, NORMAL=normal, COLOR_0=colour)
    for channel in range(6):
        attributes['TEXCOORD_'+str(channel)] = data([v for i in range(6)
            for v in ((1. if i<3 else 2., 0.) if channel==5 else (channel+i*.125, i*.125))], 'VEC2', 2)
    primitives = [dict(attributes=attributes, indices=data(list(range(i,i+3)), 'SCALAR', 1, 5123), material=i//3)
                  for i in (0,3)]
    image = io.BytesIO(); Image.new('RGBA', (1,1), (255,0,0,255)).save(image, 'PNG')
    binary.extend(b'\0'*(-len(binary)%4))
    views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(image.getvalue())))
    binary.extend(image.getvalue())
    return glb_pack(dict(asset={'version':'2.0'}, buffers=[dict(byteLength=len(binary))], bufferViews=views,
        accessors=accessors, meshes=[dict(name='Probe',primitives=primitives)], nodes=[dict(mesh=0)],
        scenes=[dict(nodes=[0])], scene=0, images=[dict(bufferView=len(views)-1,mimeType='image/png')],
        textures=[dict(source=0)], materials=[dict(name='Leaf',pbrMetallicRoughness=dict(baseColorTexture=dict(index=0))),
                                             dict(name='Metal')]), bytes(binary))


def run(tmp_path):
    (tmp_path/'Probe.glb').write_bytes(source_glb())
    project = tmp_path/'Project/MeshCanary.uproject'
    project.parent.mkdir()
    project.write_text(json.dumps(dict(FileVersion=3, Plugins=[dict(Name=name, Enabled=True) for name in
        ('PythonScriptPlugin','EditorScriptingUtilities','Interchange','InterchangeEditor','InterchangeAssets')])))
    fixtures = Path(__file__).resolve().parents[1] / 'fixtures'
    command = [str(engine.unreal_cmd()), str(project), '-run=pythonscript', '-script='+str(fixtures/'interchange_import.py'),
               '-nullrhi', '-unattended', '-nosplash', '-nosound', '-stdout', '-FullStdOutLogOutput']
    code = guarded.run(command, tmp_path/'unreal.guard', timeout=900, kind='job',
        purpose='geometry-only mesh receiving parity canary', env=dict(os.environ, ATELIER_MESH_CANARY_DIR=str(tmp_path)))
    assert code == 0
    assert json.loads((tmp_path/'import-result.json').read_text())['new_packages'] == 1
    assert 'INTERCHANGE MESH CANARY COMPLETE' in (tmp_path/'unreal.guard/stdout.log').read_text()
    command = [engine.blender(), '-b', '--factory-startup', '--threads','3', '--python-exit-code','1',
               '--python',str(fixtures/'fbx_geometry.py'),'--',str(tmp_path)]
    code = guarded.run(command, tmp_path/'compare.guard', timeout=900, kind='job',
                       purpose='native imported geometry corner parity')
    assert code == 0
    assert json.loads((tmp_path/'geometry-result.json').read_text())['exact'] is True
    assert 'INTERCHANGE GEOMETRY EXACT' in (tmp_path/'compare.guard/stdout.log').read_text()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run(args.output.resolve())
    print('NATIVE INTERCHANGE CANARY PASS', flush=True)
