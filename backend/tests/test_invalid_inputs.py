import pytest


@pytest.mark.parametrize('data', [b'', b'not an image', b'\x89PNG\r\n\x1a\ntruncated'])
def test_invalid_image(client, data):
    response = client.post('/api/uploads', files={'file': ('fake.jpg', data, 'image/jpeg')})
    assert response.status_code == 422


def test_oversized_image(client, settings):
    settings.max_upload_bytes = 16
    assert client.post('/api/uploads', files={'file': ('x.png', b'x' * 17)}).status_code == 413


@pytest.mark.parametrize('body', [{}, {'upload_id': '../secret'}, {'upload_id': 'z' * 32},
                                      {'upload_id': 'a' * 32, 'barcode': 'garbage'},
                                      {'upload_id': 'a' * 32, 'unexpected': True},
                                      {'upload_id': 'a' * 32, 'algorithm': 'fake'}])
def test_bad_verification_body(client, body):
    assert client.post('/api/verify', json=body).status_code == 422


@pytest.mark.parametrize('barcode', ['123', '4006381333932', '４００６３８１３３３９３１', 'abc12345'])
def test_bad_barcode(client, barcode):
    assert client.get('/api/barcodes/' + barcode).status_code == 422


def test_pagination_and_search_bounds(client, upload_id):
    for path in ['/api/history?limit=0', '/api/history?offset=-1', '/api/products?limit=101']:
        assert client.get(path).status_code == 422
    assert client.post('/api/search?k=21', json={'upload_id': upload_id}).status_code == 422
    assert client.post('/api/search?algorithm=made-up', json={'upload_id': upload_id}).status_code == 422


def test_missing_records(client):
    for path in ['/api/products/missing', '/api/history/missing', '/api/uploads/' + 'a' * 32 + '/image']:
        assert client.get(path).status_code == 404
    for endpoint in ['classify', 'verify', 'search']:
        assert client.post('/api/' + endpoint, json={'upload_id': 'a' * 32}).status_code == 404
    assert client.get('/api/uploads/not-an-id/image').status_code == 422
