"""Reference-led building lab for Hidamari (see hidamari/kit/__init__.py).

    PY='uv run python'   # any Python 3.11+ with NumPy and Pillow
    $PY games/yorimichi/world/regions/hidamari/kit/lab.py ref SLUG [--n 2]                # gpt-image-2.5-sunburst concept from the brief + game stills
    $PY games/yorimichi/world/regions/hidamari/kit/lab.py build SLUG                      # Blender build -> Unreal import -> in-game renders
    $PY games/yorimichi/world/regions/hidamari/kit/lab.py capture SLUG                    # renders only
    $PY games/yorimichi/world/regions/hidamari/kit/lab.py reconcile SLUG --ref REF --render RENDER   # gpt-image-2.5-sunburst reconciled target

Every artefact lands in build/yorimichi/kit/SLUG/ (ref_N.jpg, render_vK_front.jpg / _street.jpg,
reconciled_N.jpg, provenance.json; full-size PNG frames stay in build/yorimichi/captures/kit-SLUG-vK/). Blender and Unreal steps take file locks so several buildings can be
worked on in parallel; the OpenAI key is read from $OPENAI_API_KEY or the file in $OPENAI_API_KEY_FILE.
"""
import argparse,fcntl,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]));import yori  # noqa: E402
ROOT=yori.REGIONS;sys.path.insert(0,str(yori.GAME/'tools'))
PROJECT=yori.GAME/'unreal';OUT=yori.OUT/'hidamari';DOCS=yori.OUT/'kit';LOCKS=yori.OUT/'locks'
BRIEFS=ROOT/'hidamari/kit/briefs.json'
ENGINE=Path(os.environ.get('UE_ROOT','/Users/Shared/Epic Games/UE_5.8'))
STYLE_STILLS=[p for p in (yori.OUT/'kit'/'style').glob('*.png')]  # put a few in-game stills here to steer the reference style
STYLE=("The attached images are screenshots of our low-poly Unreal game (painted flat-shaded polygons with vertex colours, "
 "chunky timber, cream plaster, slate-blue tiled roofs, warm paper-lantern glow, autumn palette, soft daylight, no outlines). "
 "Paint a concept in exactly that style, as if it were a screenshot of the same game: same camera feel (street level, "
 "three-quarter view, 16:9), same lighting, same level of geometric simplicity.")

class lock:
    def __init__(self,name):LOCKS.mkdir(parents=True,exist_ok=True);self.f=(LOCKS/f'{name}.lock').open('w')
    def __enter__(self):
        t=time.time();fcntl.flock(self.f,fcntl.LOCK_EX)
        if time.time()-t>2:print(f'  (waited {time.time()-t:.0f}s for the {Path(self.f.name).stem} lock)',flush=True)
    def __exit__(self,*a):fcntl.flock(self.f,fcntl.LOCK_UN);self.f.close()

def key():
    k=os.environ.get('OPENAI_API_KEY') or (Path(os.environ['OPENAI_API_KEY_FILE']).read_text().strip() if os.environ.get('OPENAI_API_KEY_FILE') else '')
    if not k:raise SystemExit('Set OPENAI_API_KEY or OPENAI_API_KEY_FILE')
    return k

def brief(slug):
    b=json.loads(BRIEFS.read_text());assert slug in b,f'{slug} not in {BRIEFS}: {list(b)}';return b[slug]

def gpt_edit(prompt,images,n=1,size='1536x1024',quality='high',model='gpt-image-2.5-sunburst'):
    from atelier.ai import images as client  # one Sunburst client: the key travels in a header, never in argv
    try:blobs,_,secs=client.sunburst(prompt,size,images,n,model=model,quality=quality,key=key())
    except RuntimeError as e:raise SystemExit(f'gpt-image error: {e}')
    return blobs,round(secs)

def record(slug,entry):
    d=DOCS/slug;d.mkdir(parents=True,exist_ok=True);p=d/'provenance.json'
    log=json.loads(p.read_text()) if p.exists() else [];log.append(entry);p.write_text(json.dumps(log,indent=2)+'\n')

def next_index(folder,prefix,suffix='.jpg'):
    i=1
    while (folder/f'{prefix}{i}{suffix}').exists() or (folder/f'{prefix}{i}.png').exists():i+=1
    return i

def save_jpg(blob_or_path,out,size=None,quality=90):
    from PIL import Image
    import io
    im=Image.open(io.BytesIO(blob_or_path) if isinstance(blob_or_path,bytes) else blob_or_path).convert('RGB')
    if size:im=im.resize(size)
    im.save(out,quality=quality);return out

def ref(slug,n):
    b=brief(slug);d=DOCS/slug;d.mkdir(parents=True,exist_ok=True)
    prompt=(STYLE+" Design ONE building for the same city: "+b['brief']+
     f" The lot is {b.get('width',22)} m wide and {b.get('depth',16)} m deep, {b.get('floors',2)} floors; the design must fill the full width of the lot "
     "(one wide building, or the building plus an attached narrower neighbour of the same family), standing in a row of similar lots "
     "along a broad paved street, its front on the street. Show the whole lot from the street at eye height, three-quarter view, "
     "neighbours only hinted at the edges. It must be buildable from simple flat-shaded polygon primitives (boxes, beams, wedges, lathes): "
     "bold silhouette, clear roof form, deep eaves, big readable parts, no fine ornament, no photoreal texture, no people. "
     "Authored Japanese sign text is fine if it is short; otherwise no writing.")
    stills=[s for s in STYLE_STILLS if s.exists()][:3]
    data,secs=gpt_edit(prompt,stills,n=n)
    outs=[]
    for blob in data:
        i=next_index(d,'ref_');p=d/f'ref_{i}.jpg';save_jpg(blob,p,quality=92);outs.append(p)
    record(slug,dict(step='ref',prompt=prompt,stills=[str(s.relative_to(yori.REPO)) for s in stills],outputs=[o.name for o in outs],seconds=secs,model='gpt-image-2.5-sunburst'))
    for o in outs:print('REF',o)

def reconcile(slug,ref_path,render_path,note=''):
    d=DOCS/slug;d.mkdir(parents=True,exist_ok=True)
    prompt=("Two images are attached. Image 1 is our concept art for a building. Image 2 is the current in-game render of our implementation "
     "of it, from a low-poly Unreal game with painted flat-shaded polygons and vertex colours. Paint a reconciled target: keep exactly the camera, "
     "framing, lighting and neighbours of the render (image 2) and the game's painterly low-poly look, but make the building look MUCH better "
     "than the render and much closer to the concept (image 1) in silhouette, proportions, roof, materials, colours, storefront, props and signage. "
     "At the same time keep it EASIER to build than the concept: only forms that decompose into boxes, beams, wedges and simple lathes, "
     "no fine ornament, no photoreal textures, no complex curves, a plausible target we can actually reach in this engine. No UI text, no people. "+note)
    data,secs=gpt_edit(prompt,[ref_path,render_path],n=1)
    i=next_index(d,'reconciled_');p=d/f'reconciled_{i}.jpg';save_jpg(data[0],p,quality=92)
    record(slug,dict(step='reconcile',prompt=prompt,ref=str(Path(ref_path).resolve().relative_to(yori.REPO)),render=str(Path(render_path).resolve().relative_to(yori.REPO)),output=p.name,seconds=secs,model='gpt-image-2.5-sunburst'))
    print('RECONCILED',p)

def blender_build(assets):
    with lock('blender'):
        env=dict(os.environ,HIDAMARI_ASSETS=','.join(assets))
        log=yori.OUT/'logs'/f'kit-build-{assets[0]}.log';log.parent.mkdir(parents=True,exist_ok=True)
        t=time.time()
        with log.open('w') as f:r=subprocess.run(['blender','-b','--threads','4','--python-exit-code','1','--python',str(ROOT/'hidamari/build.py')],stdout=f,stderr=subprocess.STDOUT,env=env)
        text=log.read_text()
        if r.returncode or 'HIDAMARI BUILD COMPLETE' not in text:
            tail='\n'.join(text.splitlines()[-40:]);raise SystemExit(f'Blender build failed (see {log}):\n{tail}')
        manifest=json.loads((OUT/'manifest.json').read_text())
        for a in assets:
            e=manifest[a];print(f'BUILT {a}: {e["triangles"]} triangles, {e["collision_boxes"]} collision boxes, bounds z {e["min"][2]:.2f}..{e["max"][2]:.2f} ({time.time()-t:.0f}s)',flush=True)
            if e['triangles']>60000:raise SystemExit(f'{a} exceeds the 60,000-triangle kit budget ({e["triangles"]}); simplify before importing')

def unreal_import(assets):
    with lock('unreal'):
        env=dict(os.environ,HIDAMARI_ASSETS=','.join(assets))
        log=yori.OUT/'logs'/f'kit-import-{assets[0]}.log';t=time.time()
        cmd=[str(ENGINE/'Engine/Binaries/Mac/UnrealEditor-Cmd'),str(PROJECT/'Yorimichi.uproject'),'-run=pythonscript','-script='+str(PROJECT/'Scripts/import_hidamari.py'),'-unattended','-nop4','-nosplash','-stdout']
        with log.open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
        text=log.read_text()
        report=json.loads((OUT/'import-report.json').read_text()) if (OUT/'import-report.json').exists() else {}
        if 'Python script executed successfully' not in text or not all(report.get(a,{}).get('imported') for a in assets) or (OUT/'import-report.json').stat().st_mtime<t:
            errs=[l for l in text.splitlines() if 'Error' in l or 'Traceback' in l or 'AssertionError' in l][-15:]
            raise SystemExit(f'Unreal import failed (see {log}):\n'+'\n'.join(errs))
        print(f'IMPORTED {assets} ({time.time()-t:.0f}s)',flush=True)

def placement(asset):
    """A lit (south-facing, yaw 0) placement of the asset, away from the city edge."""
    city=json.loads((OUT/'city.json').read_text())
    cands=[b for b in city['buildings'] if b['asset']==asset]
    cands=cands or [dict(asset=asset,position=i[:3],yaw=i[3]) for i in city['instances'].get(asset,[])]
    assert cands,f'{asset} is not placed in city.json'
    lit=[b for b in cands if b['yaw']==0] or cands
    return min(lit,key=lambda b:abs(b['position'][0]-830)+abs(b['position'][1]-60))

def capture_views(slug,assets):
    from capture import capture
    from hidamari.layout import height
    d=DOCS/slug;d.mkdir(parents=True,exist_ok=True)
    b=placement(assets[0]);x,y,z=b['position'];yaw=b['yaw'];s=1 if yaw==0 else -1
    g=lambda px,py,h:[px,py,float(height(px,py))+h]
    briefs=json.loads(BRIEFS.read_text());w=briefs.get(slug,{}).get('width',22);dd=briefs.get(slug,{}).get('depth',16)
    # Camera distance follows the lot width, capped so it never enters the building across the street.
    dx=min(22,max(6,.85*w));dy=min(34 if w>30 else 28,dd/2+1.1*w+3);look=min(5,2+.12*w)
    shots={'front':(g(x-dx,y-s*dy,2.0),g(x+1,y-s*4,look)),'street':(g(x-40,y-s*15,2.2),g(x+25,y-s*13,4.0))}
    with lock('unreal'):
        k=next_index(d,'render_v','_front.jpg')
        session=f'kit-{slug}-v{k}-{uuid.uuid4().hex[:8]}'
        for name,(pos,target) in shots.items():
            capture(session,name,dict(character='cape_boy',road_index=0,fov=65,kind='world',seconds=.05,camera_position=pos,camera_target=target,player_position=g(x-8,y-s*13,0),events=[]),False,allow_visual_overlap=True)
            src=yori.OUT/'captures'/session/name/'frame_00002.png';dst=d/f'render_v{k}_{name}.jpg';save_jpg(src,dst,(1280,720),88);print('RENDER',dst,flush=True)
    record(slug,dict(step='capture',version=k,asset=assets[0],placement=b['position'],yaw=yaw,session=session))

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command',choices=['ref','build','capture','reconcile','briefs']);p.add_argument('slug',nargs='?')
    p.add_argument('--n',type=int,default=2);p.add_argument('--variant',type=int,default=0,help='capture: which of the brief assets to render');p.add_argument('--ref');p.add_argument('--render');p.add_argument('--note',default='')
    a=p.parse_args()
    if a.command=='briefs':
        for k,v in json.loads(BRIEFS.read_text()).items():print(k,v['assets'],'-',v['title'])
        return
    b=brief(a.slug)
    if a.command=='ref':ref(a.slug,a.n)
    elif a.command=='build':blender_build(b['assets']);unreal_import(b['assets']);capture_views(a.slug,b['assets'])
    elif a.command=='capture':capture_views(a.slug,[b['assets'][a.variant]])
    elif a.command=='reconcile':reconcile(a.slug,a.ref,a.render,a.note)
if __name__=='__main__':main()
