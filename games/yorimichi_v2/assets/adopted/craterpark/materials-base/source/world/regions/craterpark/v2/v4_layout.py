"""Compile resolved v4 JSON into the existing Park export/validation interface.

This module contains no course coordinates, template geometry, or fallback layout.
"""
from dataclasses import asdict, is_dataclass
import json
import time
from pathlib import Path

import numpy as np

from . import bowls, dsl, primitives as P, solids
from . import v4_geometry as geometry


def compile_design(design, *, terrain=None, include_ground=True):
    """@cc [owner:fontanierh,label:correctness] v4-json-structural-ownership
    Every resolved structural module MUST be compiled once from its JSON data.
    Unsupported geometry MUST fail before returning a Park; acceptance diagnostics
    MUST remain visible and MUST NOT suppress primitive structural validators.
    """
    terrain = terrain or design.ground_at
    document = design.document
    built = {}; rollins = []; ports = []; began=time.monotonic()
    for name in design.order:
        segment, geo = design.segments[name], design.geo[name]
        print(f'V4 geometry: module {len(built)+1}/{len(design.order)} {name}; elapsed {time.monotonic()-began:.1f}s',flush=True)
        built[name] = geometry.build_module(segment, geo, terrain)
        print(f'V4 geometry: completed {name}; {len(built[name].mesh.F)} faces; elapsed {time.monotonic()-began:.1f}s',flush=True)
        if geo['kind'] == 'rollin' and segment.get('support') == 'tower':
            rollins.append((built[name], geo))
        if geo['kind'] == 'bowl_entry':
            row = geometry.module_ports(built[name],geo)['end']
            pose = geo['end']; heading = np.array([np.cos(np.radians(pose['h'])),np.sin(np.radians(pose['h']))])
            if np.ptp(row[:,1]) > 1e-6:
                raise geometry.GeometryError(f'{name}: bowl-entry shoulders must fade to a level owned row')
            ports.append(bowls.Port(name,segment.get('entry','floor'),np.array([pose['x'],pose['z']]),heading,
                                    pose['y'],pose['a'],float(np.linalg.norm(row[-1]-row[0])),
                                    float(segment.get('entry_speed',0)),row))
    parts = list(built.values())
    if document.get('tower'):
        if not rollins:
            raise geometry.GeometryError('declared tower has no resolved owned roll-in modules')
        print(f'V4 geometry: tower concrete core; elapsed {time.monotonic()-began:.1f}s',flush=True)
        parts.append(geometry.tower_deck(document['tower'],rollins,terrain))
    if document.get('bowl'):
        print(f'V4 geometry: Prado bowl; elapsed {time.monotonic()-began:.1f}s',flush=True)
        parts.append(geometry.build_bowl(document['bowl'],ports))
    combined = P.Built.concat(parts)
    # Validate the assembled seams before asking ground to own their complement.
    # This deliberately propagates nonmanifold seams, rather than previewing them away.
    combined.foot = solids.check_open(combined.mesh,name='v4.modules')
    if include_ground:
        print(f'V4 geometry: site ground and exact foot loops; elapsed {time.monotonic()-began:.1f}s',flush=True)
        ground_spec = ground_specification(design, terrain)
        land = geometry.build_ground(ground_spec,combined,terrain)
        combined.mesh = dsl.Mesh.concat([combined.mesh,land])
    ride_lines = []
    for line in design.lines:
        names = [s['id'] if isinstance(s,dict) else s for s in line['segments']]
        if not names:
            raise geometry.GeometryError(f"{line['id']}: empty designed riding line")
        positions = []
        for name in names:
            g=design.geo[name]; p=np.c_[g['x'],g['y'],g['z']]
            positions.extend(p if not positions else p[1:])
        first, last = design.geo[names[0]]['start'], design.geo[names[-1]]['end']
        spawn=(tuple([first['x'],first['y'],first['z']]),float(first['h']))
        airs=[(name+'.launch',name+'.landing') for name in names if design.geo[name]['kind']=='gap']
        ride_lines.append(dsl.RideLine(line['id'],names,np.asarray(positions),spawn,
                                       np.array([last['x'],last['y'],last['z']]),airs=airs))
    checks = combined.checks + [dict(kind='v4_design',source=str(getattr(design,'source','')),
                                    diagnostics=[asdict(d) if is_dataclass(d) else d for d in design.diagnostics],
                                    grounded_modules=list(built),include_ground=include_ground)]
    return dsl.Park(combined.mesh,combined.rails,ride_lines,checks)


def ground_specification(design, terrain):
    """Use an explicit outline or the selected site's declared buildable polygon."""
    spec = dict(design.document['ground'])
    if 'outline' in spec:
        polygon = np.asarray(spec['outline'],'f8')[:,[0,2]]
        if 'guide' not in spec:
            spec['guide'] = np.asarray(spec['outline'],'f8').tolist()
        return spec
    site = dict(design.document.get('site', {}))
    if 'file' in site:
        base = Path(design.source).parent if design.source else Path.cwd()
        selected = base / Path(site['file']).expanduser()
        for candidate in site.get('prefer', []):
            path = base / Path(candidate).expanduser()
            if path.is_file():
                selected = path
                break
        external = json.loads(selected.read_text())
        site = {**external, **site}
    polygon = site.get('buildable')
    if polygon is None and 'buildable_polygon' in site:
        polygon = site['buildable_polygon']['coordinates'][0]
    if polygon is None:
        raise geometry.GeometryError('ground needs ground.outline or an explicit site buildable polygon')
    polygon = np.asarray(polygon,'f8')[:, :2]
    if len(polygon)>1 and np.linalg.norm(polygon[0]-polygon[-1])<1e-8:
        polygon = polygon[:-1]
    if len(polygon)<3 or not np.isfinite(polygon).all():
        raise geometry.GeometryError('site buildable polygon needs at least three finite points')
    y = terrain(polygon[:,0],polygon[:,1])
    spec['outline'] = np.c_[polygon[:,0],y,polygon[:,1]].tolist()
    if 'guide' not in spec:
        # A broad sampled survey guide retains the selected DEPTH terrain;
        # ground.py blends its exact owned feature-foot loops into this field.
        spacing = geometry.finite(spec.get('guide_spacing_m',32.),'ground.guide_spacing_m',positive=True)
        x = np.arange(polygon[:,0].min(),polygon[:,0].max()+spacing/2,spacing)
        z = np.arange(polygon[:,1].min(),polygon[:,1].max()+spacing/2,spacing)
        xx,zz = np.meshgrid(x,z); points = np.c_[xx.ravel(),zz.ravel()]
        points = points[solids._inside(points,polygon)]
        if len(points)>2500:
            raise geometry.GeometryError('ground guide exceeds 2500 samples; explicitly increase guide_spacing_m')
        spec['guide'] = np.c_[points[:,0],terrain(points[:,0],points[:,1]),points[:,1]].tolist()
    return spec


def park(path=None, *, terrain=None, include_ground=True):
    """Resolve the selected JSON anew on every call; no mutable design cache."""
    from .v4_design import load_design
    design = load_design(path,terrain=terrain)
    return compile_design(design,terrain=terrain,include_ground=include_ground)
