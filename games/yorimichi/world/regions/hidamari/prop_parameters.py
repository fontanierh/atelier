"""Validate one selected fitted prop or conifer LOD without loading sibling parameters."""
import json
import math
from pathlib import Path
import re


def load(path):
    path=Path(path);value=json.loads(path.read_text())
    fields={'schema','name','parent','slug','size','turn','target','solid','upright','crown','lod','settings'}
    if not isinstance(value,dict) or set(value)!=fields or value['schema']!=1 or value['name']!=path.stem:
        raise ValueError('Invalid selected Hidamari prop parameters')
    if (not isinstance(value['slug'],str) or not re.fullmatch('[a-z][a-z0-9_]+',value['slug'])
            or any(type(value[k]) is not bool for k in ('solid','upright'))
            or any(type(value[k]) not in (int,float) or not math.isfinite(value[k]) for k in ('size','turn','target'))
            or not 0<value['size']<=100 or not 0<value['target']<=1 or type(value['lod']) is not int):
        raise ValueError('Invalid fitted prop geometry parameters')
    if value['upright']:
        parent=value['parent'];lod=value['lod'];settings=value['settings']
        if (not isinstance(parent,str) or not re.fullmatch('Tree_Caldera_(BlackPine|Cedar)_[AB]',parent)
                or not 0<=lod<=3 or value['name']!=(parent if lod==0 else parent+'_LOD'+str(lod))
                or value['solid'] or type(value['crown']) not in (int,float)
                or not math.isfinite(value['crown']) or value['crown']<=0
                or not isinstance(settings,dict) or set(settings)!={'LODS','SHELL','BASE','FLOAT'}):
            raise ValueError('Invalid selected conifer parameters')
        levels=settings['LODS']
        if (not isinstance(levels,list) or len(levels)!=4 or levels[0]!=[1.,1.,None]
                or any(not isinstance(row,list) or len(row)!=3 for row in levels)
                or [row[2] for row in levels]!=[None,'weld','shell','shell']):
            raise ValueError('Invalid conifer LOD policy')
        numbers=[number for row in levels for number in row[:2]]
        for key in ('SHELL','BASE'):
            row=settings[key]
            if not isinstance(row,list) or len(row)!=2:raise ValueError('Invalid conifer shell policy')
            numbers.extend(row)
        numbers.append(settings['FLOAT'])
        if (any(type(number) not in (int,float) or not math.isfinite(number) or not 0<number<=1 for number in numbers)
                or any(levels[i][j]>=levels[i-1][j] for i in range(1,4) for j in (0,1))):
            raise ValueError('Invalid conifer reduction policy')
    elif (value['name']!='HD_P_'+value['slug'] or value['parent']!=value['name']
            or value['lod']!=0 or value['settings'] is not None or value['crown'] is not None):
        raise ValueError('Invalid selected street prop')
    return value
