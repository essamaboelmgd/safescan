import json
import sqlite3
import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.database import Database
from backend.app.model import Classifier
from backend.app.schemas import ProductRecord
from backend.app.service import decide, UNKNOWN
from backend.app.vision import FEATURE_DIM, FEATURE_VERSION
from tools.train import fit, metrics, probability


def test_database_persists_and_sql_inputs_are_literal(tmp_path, product_record):
    path = tmp_path / 'test.sqlite3'
    db = Database(path)
    db.upsert_product(product_record)
    record = db.save_scan({'status': UNKNOWN, 'warnings': []})
    reopened = Database(path)
    assert reopened.by_barcode(product_record['barcode']) == product_record
    assert reopened.history() == [record]
    assert reopened.products("' OR 1=1 --") == []
    assert reopened.products('%') == []
    assert reopened.product('missing') is None
    with pytest.raises(sqlite3.IntegrityError):
        reopened.upsert_product({**product_record, 'id': 'other'})


def test_claims_require_provenance(product_record):
    ProductRecord.model_validate(product_record)
    with pytest.raises(ValidationError):
        ProductRecord.model_validate({**product_record, 'evidence': [{'kind': 'recall', 'title': 'UNSOURCED TEST CLAIM'}]})
    with pytest.raises(ValidationError):
        ProductRecord.model_validate({**product_record, 'certified': True})


def test_missing_corrupt_and_incompatible_models(tmp_path):
    assert not Classifier(tmp_path / 'missing.npz').available
    corrupt = tmp_path / 'bad.npz'
    corrupt.write_bytes(b'not a model')
    assert not Classifier(corrupt).available
    np.savez(corrupt, weights=np.zeros(FEATURE_DIM), bias=0, metadata=json.dumps({'feature_version': 'old'}))
    assert not Classifier(corrupt).available


def test_model_contract_with_explicit_test_artifact(tmp_path):
    path = tmp_path / 'TEST-ONLY.npz'
    np.savez(path, weights=np.zeros(FEATURE_DIM), bias=0,
             metadata=json.dumps({'feature_version': FEATURE_VERSION, 'labels': ['authentic', 'counterfeit'], 'dataset_sha256': 'TEST-ONLY'}))
    model = Classifier(path)
    result = model.predict(np.ones(FEATURE_DIM))
    assert result['available']
    assert result['confidence'] == 0.5


def test_decision_is_conservative():
    prediction = {'available': True, 'prediction': 'authentic', 'confidence': 0.99}
    nearest = {'label': 'authentic', 'similarity_score': 0.99}
    assert decide(prediction, nearest, [], True) == 'Likely Authentic'
    assert decide({**prediction, 'prediction': 'counterfeit'}, {**nearest, 'label': 'counterfeit'}, [], True) == 'Suspicious'
    for predicted, reference, quality, enabled, conflict in [
        (prediction, nearest, [], False, False), (prediction, nearest, ['blur'], True, False),
        (prediction, None, [], True, False), ({'available': False}, nearest, [], True, False),
        (prediction, nearest, [], True, True), ({**prediction, 'confidence': 0.7}, nearest, [], True, False),
        (prediction, {**nearest, 'label': 'counterfeit'}, [], True, False),
    ]:
        assert decide(predicted, reference, quality, enabled, conflict) == UNKNOWN


def test_training_math_on_toy_vectors_only():
    # Algorithm test, not training on products and not a reported accuracy result.
    x = np.array([[-1., 0.], [-2., 0.], [1., 0.], [2., 0.]])
    y = np.array([0., 0., 1., 1.])
    weights, bias, _ = fit(x, y, x, y, epochs=30)
    assert probability(x, weights, bias)[0] < probability(x, weights, bias)[-1]
    report = metrics([0, 1, 1], [0.1, 0.9, 0.2])
    assert report['confusion_matrix'] == {'tn': 1, 'fp': 0, 'fn': 1, 'tp': 1}
