from backend.app.schemas import ProductRecord
from backend.app.vision import preprocess, FEATURE_VERSION


def test_health_missing_model_is_explicit(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['model_available'] is False
    assert response.json()['reference_count'] == 0


def test_upload_classify_search_verify_history(client, upload_id):
    request = {'upload_id': upload_id}
    assert client.get(f'/api/uploads/{upload_id}/image').headers['content-type'] == 'image/png'
    assert client.post('/api/classify', json=request).status_code == 503
    search = client.post('/api/search', json=request).json()
    assert search['matches'] == []
    result = client.post('/api/verify', json=request)
    assert result.status_code == 200
    record = result.json()
    assert record['status'] == 'Unknown / Insufficient Evidence'
    assert record['prediction']['confidence'] is None
    assert record['safety_records'] == []
    assert 'not official authentication' in record['disclaimer']
    assert client.get('/api/history').json()['items'] == [record]
    assert client.get('/api/history/' + record['scan_id']).json() == record


def test_reference_and_barcode_fusion_does_not_authenticate(client, upload_id, image_bytes, product_record):
    service = client.app.state.service
    product = ProductRecord.model_validate(product_record).model_dump(mode='json')
    service.db.upsert_product(product)
    image = preprocess(image_bytes)
    service.db.add_reference({'id': 'test-reference', 'product_id': product['id'], 'upload_id': upload_id,
                             'label': 'authentic', 'source_url': product['source_url'],
                             'features': image.features.tolist(), 'phash': image.phash, 'feature_version': FEATURE_VERSION})
    search = client.post('/api/search', json={'upload_id': upload_id}).json()
    assert search['matches'][0]['product_id'] == product['id']
    assert search['matches'][0]['similarity_score'] > 0.99
    assert search['matches'][0]['phash_distance'] == 0
    approximate = client.post('/api/search?algorithm=lsh', json={'upload_id': upload_id}).json()
    assert approximate['approximate'] is True
    assert approximate['matches'][0]['reference_id'] == 'test-reference'
    lookup = client.get('/api/barcodes/4006381333931').json()
    assert lookup['product']['id'] == product['id']
    assert client.get('/api/products/test-only').json() == product
    assert len(client.get('/api/products?q=Fixture').json()['items']) == 1
    record = client.post('/api/verify', json={'upload_id': upload_id, 'barcode': '4006381333931'}).json()
    assert record['metadata']['id'] == product['id']
    assert record['status'] == 'Unknown / Insufficient Evidence'
    assert record['safety_records'] == []


def test_metadata_warnings_do_not_turn_into_recall_records(client, upload_id):
    result = client.post('/api/verify', json={'upload_id': upload_id, 'barcode': '4006381333931'}).json()
    assert result['metadata'] is None
    assert result['safety_records'] == []
    assert any('does not mean' in warning for warning in result['warnings'])


def test_openapi_is_available(client):
    schema = client.get('/openapi.json').json()
    assert '/api/verify' in schema['paths']
    assert 'VerifyRequest' in schema['components']['schemas']


def test_classify_endpoint_with_temporary_test_artifact(settings, image_bytes):
    import json
    import numpy as np
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.vision import FEATURE_DIM
    settings.model_path = settings.data_dir.parent / 'TEST-ONLY.npz'
    np.savez(settings.model_path, weights=np.zeros(FEATURE_DIM), bias=-2,
             metadata=json.dumps({'feature_version': FEATURE_VERSION, 'labels': ['authentic', 'counterfeit'], 'dataset_sha256': 'TEST-ONLY'}))
    with TestClient(create_app(settings)) as current:
        uploaded = current.post('/api/uploads', files={'file': ('test.png', image_bytes)}).json()
        response = current.post('/api/classify', json={'upload_id': uploaded['upload_id']})
        assert response.status_code == 200
        assert response.json()['prediction'] == 'authentic'
        assert 0.5 < response.json()['confidence'] < 1
        assert 'not official authentication' in response.json()['disclaimer']
