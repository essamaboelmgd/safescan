"""Model configuration and exploratory verdict boundaries; no real-data training."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.config import DEFAULT_MODEL_PATH, ROOT, Settings
from backend.app.main import create_app
from backend.app.model import Classifier, EXPLORATORY_SCOPE, PUBLISHER_LABELS
from backend.app.schemas import ProductRecord
from backend.app.service import UNKNOWN, decide
from backend.app.vision import FEATURE_DIM, FEATURE_VERSION, preprocess


def test_default_model_and_relative_paths_are_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv('SAFESCAN_MODEL_PATH', raising=False)
    monkeypatch.delenv('SAFESCAN_DATA_DIR', raising=False)
    monkeypatch.chdir(tmp_path)
    assert Settings().model_path == DEFAULT_MODEL_PATH
    assert Settings.from_env().model_path == ROOT / 'models' / 'shoes_exploratory_v1.npz'
    monkeypatch.setenv('SAFESCAN_MODEL_PATH', 'models/custom.npz')
    monkeypatch.setenv('SAFESCAN_DATA_DIR', 'runtime/custom')
    assert Settings.from_env().model_path == ROOT / 'models' / 'custom.npz'
    assert Settings.from_env().data_dir == ROOT / 'runtime' / 'custom'


def test_explicit_missing_override_does_not_fall_back(monkeypatch, tmp_path):
    missing = tmp_path / 'operator-selected-missing.npz'
    monkeypatch.setenv('SAFESCAN_MODEL_PATH', str(missing))
    assert Settings.from_env().model_path == missing
    assert not Classifier(Settings.from_env().model_path).available


@pytest.mark.parametrize('scope', [
    {'experiment_scope': EXPLORATORY_SCOPE},
    {'label_provenance': PUBLISHER_LABELS},
])
@pytest.mark.parametrize('label', ['authentic', 'counterfeit'])
def test_exploratory_labels_cannot_produce_authenticity_verdicts(scope, label):
    prediction = {'available': True, 'prediction': label, 'confidence': 0.999, **scope}
    nearest = {'label': label, 'similarity_score': 1.0}
    assert decide(prediction, nearest, [], True) == UNKNOWN


def test_exploratory_api_keeps_unknown_even_with_estimates_and_matching_reference(
        settings, image_bytes, product_record):
    # Deliberately extreme TEST-ONLY weights exercise the decision boundary.
    # This is not a trained product classifier and yields no research metrics.
    settings.model_path = settings.data_dir.parent / 'TEST-ONLY-exploratory.npz'
    settings.enable_estimates = True
    np.savez(settings.model_path, weights=np.zeros(FEATURE_DIM), bias=-12,
             metadata=json.dumps({
                 'feature_version': FEATURE_VERSION, 'labels': ['authentic', 'counterfeit'],
                 'dataset_sha256': 'TEST-ONLY', 'experiment_scope': EXPLORATORY_SCOPE,
                 'label_provenance': PUBLISHER_LABELS,
             }))
    with TestClient(create_app(settings)) as client:
        health = client.get('/health').json()
        assert health['model_available'] is True
        assert health['model_scope'] == EXPLORATORY_SCOPE
        assert health['model_label_provenance'] == PUBLISHER_LABELS
        assert health['estimate_labels_requested'] is True
        assert health['estimate_labels_enabled'] is False
        upload = client.post('/api/uploads', files={'file': ('test.png', image_bytes)}).json()
        request = {'upload_id': upload['upload_id']}
        prediction = client.post('/api/classify', json=request)
        assert prediction.status_code == 200
        assert prediction.json()['confidence'] > 0.99
        assert prediction.json()['experiment_scope'] == EXPLORATORY_SCOPE
        assert 'unverified publisher labels' in prediction.json()['confidence_note']
        current = client.app.state.service
        current.db.upsert_product(ProductRecord.model_validate(product_record).model_dump(mode='json'))
        image = preprocess(image_bytes)
        current.db.add_reference({
            'id': 'TEST-ONLY-reference', 'product_id': product_record['id'],
            'upload_id': upload['upload_id'], 'label': 'authentic',
            'source_url': product_record['source_url'], 'features': image.features.tolist(),
            'phash': image.phash, 'feature_version': FEATURE_VERSION,
        })
        response = client.post('/api/verify', json=request)
        assert response.status_code == 200
        result = response.json()
        assert result['nearest_reference']['similarity_score'] > 0.99
        assert result['status'] == UNKNOWN
        assert any('publisher-provided labels' in note for note in result['explanations'])
        assert result['safety_records'] == []
        assert client.get('/health').json()['reference_count'] == 1


def test_invalid_metadata_does_not_break_health(settings):
    settings.model_path = settings.data_dir.parent / 'TEST-ONLY-invalid.npz'
    np.savez(settings.model_path, weights=np.zeros(FEATURE_DIM), bias=0, metadata='[]')
    with TestClient(create_app(settings)) as client:
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['model_available'] is False
        assert response.json()['model_scope'] is None
