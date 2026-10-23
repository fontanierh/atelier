"""Strict selected Treehouse source parameters; membership is owned by the recipe."""
import json
import math
from pathlib import Path
import re


def load(path):
    path=Path(path)
    value=json.loads(path.read_text())
    name=value.get('name')
    if value.get('schema')!=1 or not isinstance(name,str) or name!=path.stem:
        raise ValueError('Foreign selected Treehouse source parameters')
    if name.startswith('Tree_Canopy_'):
        args=value.get('args')
        if (set(value)!={'schema','name','args'} or not re.fullmatch('Tree_Canopy_[A-Za-z0-9_]+',name)
                or not isinstance(args,list) or len(args)!=6 or type(args[0]) is not int
                or args[1] not in ('LeafMaple','LeafCrimson','LeafAmber','LeafGinkgo')
                or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in args[2:])
                or any(type(args[i]) is not int for i in (4,5))):
            raise ValueError('Invalid selected canopy parameters')
    elif name.startswith('TH_P_'):
        if (set(value)!={'schema','name','slug','size','turn','target','solid'}
                or not re.fullmatch('TH_P_[a-z0-9_]+',name) or name!='TH_P_'+value['slug']
                or type(value['solid']) is not bool or any(type(value[k]) not in (int,float)
                    or not math.isfinite(value[k]) for k in ('size','turn','target'))
                or not 0<value['size']<=100 or not 0<value['target']<=1):
            raise ValueError('Invalid selected prop parameters')
    else:raise ValueError('Unknown selected Treehouse source family')
    return value
