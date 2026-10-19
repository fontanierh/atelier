"""Suno generation is recorded before submission and an uncertain call is never repaid."""
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location("suno_client_ledger_test", TOOLS / "suno_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CACHE", tmp_path)
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger")
    monkeypatch.setattr(module, "SESSION", tmp_path / "session.json")
    monkeypatch.setattr(module, "turnstile_token", lambda: "captcha")
    return module


class Response:
    status_code = 200
    text = ""

    def json(self):
        return {"clips": [{"id": "clip-a"}, {"id": "clip-b"}]}


def test_generation_is_recorded_before_the_call_and_never_submitted_twice(monkeypatch, tmp_path):
    sc = load(monkeypatch, tmp_path)
    client, calls = sc.Suno(), []

    def api(method, path, **kwargs):
        record = json.loads(next((tmp_path / "ledger").glob("*.json")).read_text())
        assert record["status"] == "submitted" and record["prompt"] == "a prompt"
        calls.append((method, path))
        return Response()

    client.api = api
    data = client.generate("a prompt")
    assert [clip["id"] for clip in data["clips"]] == ["clip-a", "clip-b"]
    record = json.loads(next((tmp_path / "ledger").glob("*.json")).read_text())
    assert record["status"] == "done" and record["clip_ids"] == ["clip-a", "clip-b"]
    with pytest.raises(FileExistsError):
        client.generate("a prompt")
    assert len(calls) == 1


def test_a_failed_submission_stays_uncertain_and_is_not_retried(monkeypatch, tmp_path):
    sc = load(monkeypatch, tmp_path)
    client, calls = sc.Suno(), []

    def api(method, path, **kwargs):
        calls.append((method, path))
        raise TimeoutError("provider timed out")

    client.api = api
    with pytest.raises(TimeoutError):
        client.generate("another prompt")
    record = json.loads(next((tmp_path / "ledger").glob("*.json")).read_text())
    assert record["status"] == "submission_uncertain" and record["error_type"] == "TimeoutError"
    with pytest.raises(FileExistsError):
        client.generate("another prompt")
    assert len(calls) == 1


def test_a_captcha_failure_happens_before_the_paid_record(monkeypatch, tmp_path):
    sc = load(monkeypatch, tmp_path)
    client, calls = sc.Suno(), []

    def no_token():
        raise sc.TurnstileError("not yet")

    monkeypatch.setattr(sc, "turnstile_token", no_token)
    with pytest.raises(sc.TurnstileError):
        client.generate("third prompt")
    assert not list((tmp_path / "ledger").glob("*.json"))

    monkeypatch.setattr(sc, "turnstile_token", lambda: "captcha")
    client.api = lambda method, path, **kwargs: (calls.append((method, path)), Response())[1]
    client.generate("third prompt")
    assert len(calls) == 1
