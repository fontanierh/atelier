"""Reusable proof calls use the actual production planner's authored partition policy."""
import ast
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[1]


def literal(path,key):
    tree=ast.parse(path.read_text())
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets))
    return ast.literal_eval(node.value)


def calls(path):
    tree=ast.parse(path.read_text())
    names={a.asname or a.name for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)
        and n.module=='region_mesh_parts' for a in n.names if a.name=='plan'}
    return [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in names]


def invoke(call,key):
    # Invoke the complete actual call expression, including its real conditional,
    # without importing bpy, constructing geometry or executing the proof body.
    call=copy.deepcopy(call);call.func=ast.Name(id='record',ctx=ast.Load())
    expression=ast.fix_missing_locations(ast.Expression(body=call))
    def record(obj,root,**kwargs):return obj,root,kwargs
    obj=SimpleNamespace(name=key)
    scope=dict(record=record,obj=obj,args=SimpleNamespace(asset=key,output=Path('production')),
        root=Path('proof'),logical=Path('logical'),destination=Path('terminal'),plan_root=Path('southwest'),output=Path('material'),
        key=key,asset=key,hulls=[],collisions=[],mesh=SimpleNamespace(colliders=[]),m=SimpleNamespace(colliders=[]),
        capture_colliders=lambda values:values,capture_collision=lambda value:value,OPTIONS={},specs=[],
        mesh_materials=SimpleNamespace(capture_slots=lambda value:[]))
    actual=eval(compile(expression,'<actual-proof-planner-call>','eval'),scope)
    assert actual[0] is obj
    return actual[2]


def test_village_and_southwest_proof_calls_match_complete_production_rosters():
    families=(
        (GAME/'world/regions/village/catalogue.py','ASSETS',GAME/'world/regions/village/plan_asset.py',
         GAME/'tests/fixtures/village_atomic_equivalence.py','Village_Planting'),
        (GAME/'world/regions/southwest/models.py','MODELS',GAME/'world/regions/southwest/plan_asset.py',
         GAME/'tests/fixtures/southwest_atomic_context.py','SW_Island'),
    )
    for roster_path,symbol,production,proof,spatial in families:
        roster=literal(roster_path,symbol)
        keys=[row[2] for row in roster.values()] if isinstance(roster,dict) else roster
        production_call,=calls(production);proof_call,=calls(proof)
        assert spatial in keys
        for key in keys:
            expected='spatial' if key==spatial else 'whole'
            assert invoke(proof_call,key)['partition']==invoke(production_call,key)['partition']==expected


def test_ferry_terminal_and_gondola_proofs_keep_actual_small_units_whole():
    # The finite real terminal constructors and Gondola canonical parameter roster
    # define coverage; the test does not invent a smaller representative subset.
    terminal=[]
    for family in ('hidamari','brinecove'):
        terminal.extend(literal(GAME/'world/regions'/family/'ferry_terminal.py','CONSTRUCTORS'))
    spec=importlib.util.spec_from_file_location('raw_policy_gondola_parameters',GAME/'assets/vehicles/gondola/params.py')
    parameters=importlib.util.module_from_spec(spec);spec.loader.exec_module(parameters)
    gondola=[key for key in parameters.asset_names() if not key.endswith('_Collision')]
    assert len(terminal)==11 and len(gondola)==23
    for keys,production,proof in (
        (terminal,GAME/'world/regions/ferry/plan_terminal.py',GAME/'tools/ferry_terminal_source_control.py'),
        (gondola,GAME/'world/regions/gondola/plan_kit.py',GAME/'assets/vehicles/gondola/prove_atomic.py'),
    ):
        actual_call,=calls(production);proof_call,=calls(proof)
        for key in keys:assert invoke(proof_call,key)['partition']==invoke(actual_call,key)['partition']=='whole'


def test_actual_export_and_material_canaries_declare_their_intended_units():
    spatial,=calls(GAME/'tests/fixtures/atomic_mesh_export.py')
    assert invoke(spatial,'AtomicProbe')['partition']=='spatial'
    material=calls(GAME/'tests/fixtures/vertex_material_glb_canary.py')
    assert len(material)==2
    assert all(invoke(call,'Control')['partition']=='whole' for call in material)
