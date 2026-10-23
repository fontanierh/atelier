"""The normal ferry consumes the validated final cut data, never a whole FBX."""
import json

import pytest

from atelier.export_manifest import sha
from test_ferry_site_inputs import inputs,proof


def prepared(tmp_path):
    from regions.hidamari.ferry_source import validated_atomic_harbor
    repo,build,code,_,_,_=inputs(tmp_path)
    raw=build/'hidamari/source-data/HD_Harbor';raw.mkdir(parents=True)
    (raw/'source.json').write_bytes(b'raw source manifest')
    (raw/'part.npz').write_bytes(b'raw source geometry')
    plan=build/'planned_exports/hidamari/HD_Harbor/plan.json';plan.parent.mkdir(parents=True)
    payload=plan.with_name('HD_Harbor.npz');payload.write_bytes(b'final source geometry')
    plan.write_text(json.dumps(dict(complete=True,parent='HD_Harbor',source_triangles=2,
        pieces=[dict(payload=payload.name,sha256=sha(payload))])))
    query=build/'hidamari/query-data/HD_Harbor.npz';query.parent.mkdir(parents=True);query.write_bytes(b'final query')
    projection=build/'hidamari/final-source-data/harbor-cut-data.json';projection.parent.mkdir(parents=True)
    projection.write_text(json.dumps(proof.projection(build,repo)))
    report=projection.with_name('harbor-cut.json')
    report.write_text(json.dumps(dict(schema=1,complete=True,failures=[],cuts=[dict(cap_normals_pass=True)],
        cut_data_sha256=sha(projection),raw_source={p.name:sha(p) for p in raw.iterdir()},
        plan_sha256=sha(plan),query_sha256=sha(query),triangles=dict(after=2))))
    return validated_atomic_harbor,repo,build,dict(raw=raw/'part.npz',payload=payload,plan=plan,
        query=query,projection=projection,report=report,code=code)


def test_current_cut_requires_complete_source_and_query_proof_without_any_fbx(tmp_path):
    validate,repo,build,paths=prepared(tmp_path)
    records=validate(build,repo)
    assert paths['payload'].relative_to(build).as_posix() in records
    assert paths['raw'].relative_to(build).as_posix() in records
    assert not list(build.rglob('*.fbx'))


@pytest.mark.parametrize('changed',['raw','payload','plan','query','projection','report','code','foreign','link'])
def test_service_refuses_changed_or_foreign_cut_evidence(tmp_path,changed):
    validate,repo,build,paths=prepared(tmp_path)
    if changed=='foreign':paths['payload'].with_name('Foreign.npz').write_bytes(b'keep')
    elif changed=='link':
        original=paths['payload'];original.rename(original.with_suffix('.kept'));original.symlink_to(original.with_suffix('.kept'))
    else:paths[changed].write_bytes(b'changed')
    with pytest.raises((ValueError,KeyError)):validate(build,repo)
