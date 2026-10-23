"""Publish fitted site commands from explicit final ground and kit query products.

No site mesh primitive and no sibling FBX/GLB exporter runs in this stage.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import math
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT),str(WORLD)]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, TRIANGLE_LIMIT  # noqa: E402
from commands import Recorder,data  # noqa: E402
from regions.gondola.kit_sources import recording  # noqa: E402
from regions.gondola.kit_actions import query_mesh  # noqa: E402
from regions.gondola.layout import mesh_names  # noqa: E402


def site_module():
    spec = importlib.util.spec_from_file_location('gondola_fitted_source',Path(__file__).with_name('site.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def cabin_data(S, queries):
    module = sys.modules['cabin']
    with recording(module):
        c = S.Cabin(dict(S.P.DEFAULTS),S.P.derived(S.P.DEFAULTS)); recorded,_ = c.build()
    return dict(cabin=c,meshes={key:query_mesh(queries,key) for key in recorded})


def project(G, layouts, cab):
    """@cc [owner:fontanierh,label:correctness;performance] fitted-gondola-source-direction
    Fitting MUST consume final owned ground, walking layouts and exact cabin source
    query geometry. It MUST NOT read sibling rendered site or kit files. Every selected
    command stream MUST publish independently; all LODs of a logical rope MUST use the
    same explicit component count. Original span contact gates determine near tolerance.
    """
    S = site_module(); p = dict(S.P.DEFAULTS); d = S.P.derived(p)
    values = {}; stations = {}; lines = []; frames = {}
    tower_module = sys.modules['tower']
    for line in S.LINES:
        first,last = line['stations']
        for key,other in ((first,last),(last,first)):
            row,frame = S.fit_station(key,other,G,layouts)
            with recording(S.solid):
                foundation,posts = S.station_foundation(key,layouts[row['kind']],G,frame)
                stair,access = S.access_stair(key,layouts[row['kind']],G,frame)
            for mesh in (foundation,stair):
                values[mesh.name] = dict(schema=1,asset=mesh.name,commands=mesh.commands)
            stations[key] = dict(data=row,frame=data(frame),posts=posts,access=access)
            frames[key] = frame
            print('GONDOLA SITE SOURCE station',key,flush=True)
        A,B = np.asarray(S.STATIONS[first]['mouth']),np.asarray(S.STATIONS[last]['mouth'])
        length = float(np.linalg.norm(B-A)); direction = (B-A)/length
        fitted = [S.tower_fit(f'{line["id"]}_{index}',s,height,A,direction,G,p,build=False)
                  for index,(s,height) in enumerate(line['towers'])]
        supports = [(.6,frames[first][3]+d['rope_height_above_platform'],False)]
        supports += [(s,entry[2][3]+height,True) for (s,height),entry in zip(line['towers'],fitted)]
        supports += [(length-.6,frames[last][3]+d['rope_height_above_platform'],False)]
        saddles = list(S.tower_saddles(supports)); towers = []
        for index,(s,height) in enumerate(line['towers']):
            with recording(tower_module):
                tower,mesh,frame,row = S.tower_fit(f'{line["id"]}_{index}',s,height,A,direction,G,p,saddle=saddles[index+1])
            values[mesh.name] = dict(schema=1,asset=mesh.name,commands=mesh.commands)
            towers.append(dict(data=row,frame=data(frame),seats=tower.seats,
                               sheaves_x={str(key):value for key,value in tower.sheaves_x.items()}))
        profile = S.centre_profile(supports)
        audit = S.audit_span(line['id'],profile,cab,p)
        tolerance = S.near_rope_tolerance(audit['groove_max_mm'])
        normal = np.array([-direction[1],direction[0]])
        ropes = []
        for lod,(allowed,sides) in enumerate(((tolerance,12),(.015,8),(.05,6))):
            mesh = Recorder(f'GD_{line["id"]}_Rope_LOD{lod}')
            axes = []
            for side in (-1,1):
                points = np.c_[A+profile[:,0,None]*direction+side*p['gauge']/2*normal,profile[:,1]]
                reduced = S.simplify(points,allowed); axes.append(reduced)
                mesh.tube(reduced,p['rope_radius'],S.solid.STEEL,n=sides)
            if lod == 0:
                triangles = sum((len(axis)-1)*sides*2+2*(sides-2) for axis in axes)
                count = math.ceil(triangles/TRIANGLE_LIMIT)
            values[mesh.name] = dict(schema=1,asset=mesh.name,commands=mesh.commands,
                                     rope_group=dict(line=line['id'],lod=lod,components=count))
            ropes.append(dict(name=mesh.name,axis_deviation_m=allowed,
                               minimum_view_distance_m=(0.,1000.,2000.)[lod],
                               ring_counts=[len(axis) for axis in axes],axes=data(axes)))
        lines.append(dict(id=line['id'],supports=supports,profile=data(profile),
                          span_audit=audit,towers=towers,ropes=ropes,components=count))
    if set(values) != set(mesh_names()): raise ValueError('Incomplete fitted Gondola source commands')
    return data(values),data(dict(schema=1,stations=stations,lines=lines))


def publish(output,G,layouts,cab):
    values,fit = project(G,layouts,cab)
    output = real_directory(output,create=True)
    expected = {key+'.json' for key in values} | {'fit.json'}
    for path in output.iterdir():
        if path.name not in expected or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign fitted Gondola source member')
    for key,value in values.items(): atomic_json(output / (key+'.json'),value)
    atomic_json(output / 'fit.json',fit)
    print('GONDOLA FITTED SOURCE COMMANDS COMPLETE',len(values),flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit-queries',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    S = site_module()
    layouts = {key:json.loads((yori.OUT / f'gondola/layout_{key}.json').read_text()) for key in ('valley','rim','crater')}
    publish(args.output,S.ground(yori.OUT),layouts,cabin_data(S,args.kit_queries))


if __name__ == '__main__': main()
