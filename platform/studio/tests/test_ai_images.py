import base64
import json

import httpx
import pytest
from PIL import Image

from atelier.ai import images

PNG = b'\x89PNG fake image bytes'


@pytest.fixture
def api(monkeypatch):
    """A stand-in for the OpenAI image endpoints that records each request."""
    seen = []
    reply = {'status': 200, 'body': {'data': [{'b64_json': base64.b64encode(PNG).decode()}], 'usage': {'total_tokens': 7}}}

    def handler(request):
        seen.append(request)
        return httpx.Response(reply['status'], json=reply['body'])
    real = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen, reply


def test_generations_send_the_key_as_a_header_and_return_the_image(api):
    seen, _ = api
    blobs, body, _ = images.sunburst('a lantern; warm light', '1024x1024', key='sk-test')
    assert blobs == [PNG] and body['usage'] == {'total_tokens': 7} and 'b64_json' not in body['data'][0]
    request, = seen
    assert request.url.path == '/v1/images/generations' and request.headers['authorization'] == 'Bearer sk-test'
    assert json.loads(request.content) == {'model': images.MODEL, 'prompt': 'a lantern; warm light',
                                           'size': '1024x1024', 'quality': 'high', 'n': 1}


def test_edits_upload_the_references_as_jpeg_and_the_prompt_whole(api, tmp_path):
    seen, _ = api
    ref = tmp_path / 'still.png'
    Image.new('RGB', (2000, 1000), (200, 100, 50)).save(ref)
    images.sunburst('style only; do not draw Cairo', '1536x1024', [ref], 2, key='sk-test')
    request, = seen
    content = request.content
    assert request.url.path == '/v1/images/edits'
    assert b'style only; do not draw Cairo' in content and b'name="n"\r\n\r\n2' in content
    assert b'filename="still.jpg"' in content and b'image/jpeg' in content


def test_a_provider_error_is_raised_without_the_response_text(api):
    _, reply = api
    reply.update(status=400, body={'error': {'message': 'bad size'}})
    with pytest.raises(RuntimeError, match='HTTP 400: bad size'):
        images.sunburst('x', '1x1', key='sk-test')


def test_paint_writes_the_record_before_the_call_and_never_repays(api, tmp_path, monkeypatch):
    seen, _ = api
    record = tmp_path / 'A.provenance.json'
    real = images.sunburst

    def checked(*args, **kwargs):
        assert json.loads(record.read_text())['status'] == 'submitted'
        return real(*args, **kwargs)
    monkeypatch.setattr(images, 'sunburst', checked)
    done = images.paint(tmp_path / 'A.png', 'p', '1024x1024', record=record, metadata={'candidate': 'A'},
                        key='sk-secret-test')
    assert (tmp_path / 'A.png').read_bytes() == PNG
    assert done['status'] == 'done' and done['candidate'] == 'A' and done['endpoint'] == '/v1/images/generations'
    assert 'sk-secret-test' not in record.read_text()
    with pytest.raises(FileExistsError):
        images.paint(tmp_path / 'A.png', 'p', '1024x1024', record=record, key='sk-secret-test')
    assert len(seen) == 1
