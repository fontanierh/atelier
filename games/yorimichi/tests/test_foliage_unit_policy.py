"""Pinned transport equivalence can locate old hints without executing historical code."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


GAME = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('unit_transport_policy', GAME/'foliage_unit_policy.py')
POLICY = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(POLICY)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    game = tmp_path/'games/fixture'; game.mkdir(parents=True)
    old = ('TSharedPtr<FJsonValue> Number(double V) { return Number(V); }\n\n'
           'bool Read(dummy) {}\n'
           'bool UYorimichiFoliageBuilder::ExportSource(args)\n{\n    geometry();\n'
           '    FString Text;\n    old_writer();\n}\n')
    new = ('TSharedPtr<FJsonValue> Number(double V) { return Number(V); }\n\n}\n#endif\n'
           'bool UYorimichiFoliageSourceWriter::ExportSource(args)\n{\n#if WITH_EDITOR\n    geometry();\n'
           '    auto& Files=stream();\n}\n')
    files = {'games/yorimichi/unreal/Source/YorimichiImport/FoliageBuilder.cpp':old.encode(),
             'games/yorimichi/unreal/Source/Yorimichi/Dev/FoliageSourceWriter.cpp':new.encode(),
             'games/fixture/current.py':b'raise AssertionError("historical code must never execute")'}
    for name, raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    historical = [b'raise AssertionError("never executed")\n', b'old source support\n']
    blobs = {str(i)*40:raw for i,raw in enumerate(historical,1)}
    witness = dict(schema=2,current={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()},
        policies=[[dict(path='games/fixture/current.py',blob=blob,sha256=hashlib.sha256(raw).hexdigest())
                  for blob,raw in blobs.items()]])
    path=game/'foliage_unit_policy_witness.json'

    def pin():
        raw=json.dumps(witness,sort_keys=True).encode();path.write_bytes(raw)
        monkeypatch.setattr(POLICY,'WITNESS_SHA256',hashlib.sha256(raw).hexdigest())
    pin()
    calls=[]
    def git(argv,**kwargs):
        calls.append(argv)
        assert argv[:3]==['git','--no-optional-locks','-C']
        assert argv[4:6]==['cat-file','blob']
        return SimpleNamespace(returncode=0 if argv[-1] in blobs else 1,stdout=blobs.get(argv[-1],b''))
    monkeypatch.setattr(POLICY.subprocess,'run',git)
    context=dict(engine_version='engine-current',environment=dict(engine='installed',toolchain='current'),
                 runtime=dict(platform='darwin',architecture='arm64',python=[3,11,8]))
    def run():return POLICY.legacy_policy(game,**context)
    expected=hashlib.sha256(b''.join(historical)+context['engine_version'].encode()
        +json.dumps(context['environment'],sort_keys=True).encode()
        +json.dumps(context['runtime'],sort_keys=True).encode()).hexdigest()
    return SimpleNamespace(root=tmp_path,game=game,files=files,blobs=blobs,witness=witness,path=path,
                           context=context,pin=pin,run=run,expected=expected,calls=calls)


def test_exact_pair_reproduces_ordered_old_policy_without_executing_it(pair):
    before={name:(pair.root/name).stat().st_mtime_ns for name in pair.files}
    assert pair.run()==pair.expected
    assert len(pair.calls)==2
    assert before=={name:(pair.root/name).stat().st_mtime_ns for name in pair.files}


@pytest.mark.parametrize('change',['current','missing','linked','witness','old-missing','old-bytes'])
def test_absent_or_changed_evidence_is_a_miss(pair,change):
    path=pair.root/'games/fixture/current.py'
    if change=='current':path.write_bytes(b'changed current code')
    elif change=='missing':path.unlink()
    elif change=='linked':path.unlink();path.symlink_to(pair.path)
    elif change=='witness':pair.path.write_text('{}')
    elif change=='old-missing':pair.blobs.pop(next(iter(pair.blobs)))
    else:pair.blobs[next(iter(pair.blobs))]=b'different Git bytes'
    assert pair.run() is None


@pytest.mark.parametrize('change',['palette','geometry'])
def test_changed_semantics_refuse_even_if_source_pins_are_updated(pair,change):
    name='games/yorimichi/unreal/Source/Yorimichi/Dev/FoliageSourceWriter.cpp'
    raw=pair.files[name].replace(b'return Number(V)',b'return Number(V+1)') if change=='palette' else pair.files[name].replace(b'geometry();',b'changed_geometry();')
    (pair.root/name).write_bytes(raw)
    pair.witness['current'][name]=hashlib.sha256(raw).hexdigest();pair.pin()
    assert pair.run() is None


@pytest.mark.parametrize('change',['engine','toolchain','python'])
def test_current_context_changes_rekey_the_lookup(pair,change):
    if change=='engine':pair.context['engine_version']='changed engine'
    elif change=='toolchain':pair.context['environment']['toolchain']='changed SDK'
    else:pair.context['runtime']['python']=[3,11,9]
    assert pair.run() not in (None,pair.expected)


@pytest.mark.parametrize('change',['runtime','nonfinite','blob','escaping'])
def test_malformed_context_and_witness_are_misses(pair,change):
    if change=='runtime':pair.context['runtime']['python']=[True,11,8]
    elif change=='nonfinite':pair.context['environment']['bad']=float('nan')
    elif change=='blob':pair.witness['policies'][0][0]['blob']='--bad-option';pair.pin()
    else:pair.witness['policies'][0][0]['path']='../escape';pair.pin()
    assert pair.run() is None


def test_both_ordered_policies_include_exact_retained_module_record(pair):
    raw=json.dumps(dict(module='Yorimichi',digest='a'*64,files={}),indent=2)+'\n'
    pair.witness['policies'].append([*pair.witness['policies'][0],
        dict(module_record=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())])
    pair.pin()
    expected=hashlib.sha256(b''.join(pair.blobs.values())+raw.encode()+pair.context['engine_version'].encode()
        +json.dumps(pair.context['environment'],sort_keys=True).encode()
        +json.dumps(pair.context['runtime'],sort_keys=True).encode()).hexdigest()
    assert POLICY.legacy_policies(pair.game,**pair.context)==(pair.expected,expected)
    assert pair.run()==pair.expected
    pair.witness['policies'][1][-1]['module_record']=raw+' '
    pair.pin()
    assert POLICY.legacy_policies(pair.game,**pair.context)==(pair.expected,)


def test_policies_deduplicate_without_weakening_evidence(pair):
    pair.witness['policies'].append(pair.witness['policies'][0]);pair.pin()
    assert POLICY.legacy_policies(pair.game,**pair.context)==(pair.expected,)


def test_changed_current_pair_refuses_both_histories(pair):
    pair.witness['policies'].append(pair.witness['policies'][0]);pair.pin()
    (pair.root/'games/fixture/current.py').write_bytes(b'changed validator')
    assert POLICY.legacy_policies(pair.game,**pair.context)==()
