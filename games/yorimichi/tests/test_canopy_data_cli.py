"""The shared entry point works as plain Python data assembly and Blender recolouring."""
import json
from pathlib import Path
import subprocess
import sys

GAME=Path(__file__).resolve().parents[1]


def test_plain_python_canopy_data_uses_real_command_line_without_blender_separator(tmp_path):
    inputs=[];expected={}
    for index,kind in enumerate(('Maple','Crimson','Amber','Ginkgo')):
        name='Tree_Canopy_'+kind;dimensions=[index+1.,2.,3.]
        path=tmp_path/(name+'.json');path.write_text(json.dumps(dict(name=name,dimensions=dimensions)))
        inputs.extend(('--record',str(path)));expected[name]=dimensions
    output=tmp_path/'data/trees.json'
    script=GAME/'world/regions/treehouse/canopy_data.py'
    result=subprocess.run([sys.executable,str(script),*inputs,'--output',str(output)],
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert 'TREEHOUSE CANOPY DATA COMPLETE' in result.stdout
    assert json.loads(output.read_text())==expected
