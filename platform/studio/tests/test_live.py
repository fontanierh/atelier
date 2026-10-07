import socket

from atelier import live


def test_free_port_is_a_loopback_port_a_game_can_bind():
    port = live.free_port()
    assert 1024 < port < 65536
    with socket.socket() as s:
        s.bind(('127.0.0.1', port))


def test_python_body_never_starts_with_a_script_path_and_runs_the_code_in_the_shared_namespace():
    code = '"""Run with: atelier live py - < games/mygame/scenarios/walk.py"""\nTAKE = "é" + str(1 + 1)\n'
    body = live.python_body(code)
    assert not body.split(None, 1)[0].endswith('.py')
    shared = {'__name__': '__main__'}
    exec(compile(body, 'body', 'exec'), shared)
    assert shared['TAKE'] == 'é2'
    exec(compile(live.python_body('TAKE += "!"'), 'body', 'exec'), shared)
    assert shared['TAKE'] == 'é2!'


def test_python_body_tracebacks_name_the_sent_code():
    import traceback
    try:
        exec(compile(live.python_body('x = 1\nraise ValueError("boom")\n'), 'body', 'exec'), {})
    except ValueError:
        assert 'File "<atelier live>", line 2' in traceback.format_exc()
    else:
        raise AssertionError('the code did not run')


def test_request_wraps_only_python_bodies(monkeypatch):
    sent = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'
    monkeypatch.setattr(live.urllib.request, 'urlopen', lambda req, timeout: sent.append(req.data) or Response())
    live.request('/python', 'print(1)')
    live.request('/state')
    assert sent[0] == live.python_body('print(1)').encode() and sent[1] is None
