"""Portable pools cannot certify legacy output, share mutable files or restore corrupted entries."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from atelier import artifact_pool as pool
from atelier.build import Python, Step, fingerprint


@pytest.fixture
def sample(tmp_path, monkeypatch):
    out=tmp_path/'build';out.mkdir()
    ctx=SimpleNamespace(out=out, stamps=out/'stamps', game='sandbox')
    step=Step('world.textures', [Python(Path('textures.py'))], outputs=[out/'textures'/'record.json'],
              pool_roots=[out/'textures'])
    (out/'textures').mkdir();(out/'textures'/'record.json').write_text('record')
    (out/'textures'/'image.png').write_bytes(b'pixels')
    ctx.stamps.mkdir()
    monkeypatch.setattr(pool, 'key',lambda *args:'identity')
    monkeypatch.delenv('ATELIER_BUILD_ROOT',raising=False)
    monkeypatch.delenv('ATELIER_PYTHON',raising=False)
    return ctx,step,tmp_path/'pool'


def certify(ctx):
    (ctx.stamps/'world.textures.json').write_text(json.dumps(dict(fingerprint='source',pool_key='identity',seconds=1)))


def test_independent_complete_roundtrip(sample):
    ctx,step,cache=sample;certify(ctx)
    pool.transfer('publish',ctx,step,'source',cache)
    (ctx.out/'textures'/'image.png').write_bytes(b'mutated')
    (ctx.out/'textures'/'extra').write_text('stale')
    pool.transfer('restore',ctx,step,'source',cache)
    assert (ctx.out/'textures'/'image.png').read_bytes()==b'pixels'
    assert not (ctx.out/'textures'/'extra').exists()
    assert (cache/'identity'/'outputs'/'textures'/'image.png').stat().st_ino != (ctx.out/'textures'/'image.png').stat().st_ino
    assert json.loads((ctx.stamps/'world.textures.json').read_text())['pooled_from']=='identity'


@pytest.mark.parametrize('stamp',[dict(fingerprint='source'),dict(fingerprint='source',pool_key='identity',touched=True)])
def test_legacy_or_touched_stamps_refused(sample,stamp):
    ctx,step,cache=sample;(ctx.stamps/'world.textures.json').write_text(json.dumps(stamp))
    with pytest.raises(ValueError,match='fresh successful'):pool.transfer('publish',ctx,step,'source',cache)
    assert not cache.exists()


def test_corruption_refused_before_target_mutation(sample):
    ctx,step,cache=sample;certify(ctx);pool.transfer('publish',ctx,step,'source',cache)
    (cache/'identity'/'outputs'/'textures'/'image.png').write_bytes(b'corrupt')
    before=(ctx.stamps/'world.textures.json').read_text()
    with pytest.raises(ValueError,match='hashes differ'):pool.transfer('restore',ctx,step,'source',cache)
    assert (ctx.stamps/'world.textures.json').read_text()==before
    assert (ctx.out/'textures'/'image.png').read_bytes()==b'pixels'


def test_symlinks_refused(sample):
    ctx,step,cache=sample;certify(ctx);(ctx.out/'textures'/'link').symlink_to('image.png')
    with pytest.raises(ValueError,match='symlinks'):pool.transfer('publish',ctx,step,'source',cache)


def test_escaping_root_and_dependency_refused(sample):
    ctx,step,cache=sample
    step.pool_roots=[ctx.out.parent/'outside']
    with pytest.raises(ValueError):pool.roots(ctx,step)
    step.pool_roots=[ctx.out/'textures'];step.needs=['world.layout']
    with pytest.raises(ValueError,match='independent Python'):pool.roots(ctx,step)


def test_same_key_different_bytes_does_not_overwrite(sample):
    ctx,step,cache=sample;certify(ctx);pool.transfer('publish',ctx,step,'source',cache)
    (ctx.out/'textures'/'image.png').write_bytes(b'other')
    with pytest.raises(ValueError,match='different bytes'):pool.transfer('publish',ctx,step,'source',cache)
    assert (cache/'identity'/'outputs'/'textures'/'image.png').read_bytes()==b'pixels'


def test_key_changes_with_real_inputs_tools_and_ownership_but_not_git_head(tmp_path,monkeypatch):
    studio=tmp_path/'platform'/'studio';(studio/'atelier').mkdir(parents=True)
    support=studio/'atelier'/'support.py';support.write_text('version=1')
    (tmp_path/'uv.lock').write_text('locked packages')
    ctx=SimpleNamespace(out=tmp_path/'build',game='sandbox')
    step=Step('world.textures',[Python(Path('textures.py'))],outputs=[ctx.out/'textures'/'data'],pool_roots=[ctx.out/'textures'])
    monkeypatch.setattr(pool.paths,'STUDIO',studio);monkeypatch.setattr(pool.paths,'REPO',tmp_path)
    monkeypatch.delenv('ATELIER_BUILD_ROOT',raising=False);monkeypatch.delenv('ATELIER_PYTHON',raising=False)
    first=pool.key(ctx,step,'source')
    assert pool.key(ctx,step,'different source')!=first
    (tmp_path/'.git').mkdir();(tmp_path/'.git'/'HEAD').write_text('unrelated feature')
    assert pool.key(ctx,step,'source')==first
    support.write_text('version=2')
    assert pool.key(ctx,step,'source')!=first


def test_status_keys_a_step_on_the_result_its_cutoff_need_recorded(sample, monkeypatch, capsys):
    ctx,step,cache=sample
    digest=Step('digest',[Python(Path('digest.py'))],outputs=[ctx.out/'digest.json'],cutoff=True)
    (ctx.out/'digest.json').write_text('digest')
    textures=replace(step,needs=['digest']);seen=[]
    (ctx.stamps/'digest.json').write_text(json.dumps(dict(fingerprint=fingerprint(digest,{}),result='outputs:recorded')))
    monkeypatch.setattr(pool,'Context',lambda game:ctx)
    monkeypatch.setattr(pool,'load_recipe',lambda game:SimpleNamespace(steps=lambda c:[digest,textures]))
    monkeypatch.setattr(pool,'key',lambda ctx,step,current:seen.append(current) or 'identity')
    monkeypatch.setattr(pool.paths,'cache_dir',lambda *names:cache)
    assert pool.main('status','sandbox','world.textures')==0
    assert seen==[fingerprint(textures,{'digest':'outputs:recorded'})]
