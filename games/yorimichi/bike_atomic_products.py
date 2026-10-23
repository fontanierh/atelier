"""Complete independent Bike source/native roster; no combined steering fallback."""
import json
import math
from pathlib import Path

from atelier.export_manifest import real_directory,sha,TRIANGLE_LIMIT
from atelier.model_files import regular_files

STEERING=('BK_Steer_BasketFoot','BK_Steer_BasketRim','BK_Steer_BasketShell','BK_Steer_Core')
OTHER=('BK_Frame','BK_WheelFront','BK_WheelRear','BK_Crank','BK_Pedal','BK_Kickstand','BK_RackBoard')
PARTS=(*OTHER,*STEERING)
DESTINATION='/Game/Japan/Assets'


def read(out):
    root=real_directory(Path(out)/'bike');assets=real_directory(root/'assets')
    for path in (root/'manifest.json',assets/'manifest.json'):
        if path.is_symlink() or not path.is_file():raise ValueError('Regular complete Bike manifest required')
    value=json.loads((root/'manifest.json').read_text());receipt=json.loads((assets/'manifest.json').read_text())
    if set(value.get('parts',{}))!=set(PARTS) or value.get('steering_parts')!=list(STEERING):raise ValueError('Incomplete Bike physical/group membership')
    if receipt.get('complete') is not True or not isinstance(receipt.get('exports'),list):raise ValueError('Incomplete Bike primary inventory')
    rows={row['asset']:row for row in receipt['exports']}
    if len(rows)!=len(receipt['exports']) or set(rows)!=set(PARTS):raise ValueError('Foreign or duplicate Bike source primary')
    for key in PARTS:
        report=value['parts'][key];row=rows[key]
        if (set(report)!={'triangles','vertices','min','max'} or type(report['triangles']) is not int
                or not 0<report['triangles']<=TRIANGLE_LIMIT or type(report['vertices']) is not int or report['vertices']<=0
                or row.get('triangles')!=report['triangles'] or row.get('primary')!=key+'.fbx'
                or row.get('metadata',{}).get('slots')!=['BikePalette'] or row['metadata'].get('collision_hulls')!=0
                or row['metadata'].get('uv_channels')!=['UVMap']):raise ValueError('Bike source attributes/ownership differ')
        for low,high in zip(report['min'],report['max']):
            if not math.isfinite(low) or not math.isfinite(high) or low>high:raise ValueError('Invalid Bike source bounds')
        if len(report['min'])!=3 or len(report['max'])!=3:raise ValueError('Incomplete Bike source frame')
        path=assets/(key+'.fbx')
        if path.is_symlink() or not path.is_file() or sha(path)!=row.get('sha256'):raise ValueError('Bike source bytes changed')
    if regular_files(assets)!={'manifest.json',*(key+'.fbx' for key in PARTS)}:raise ValueError('Foreign Bike primary file')
    return value
