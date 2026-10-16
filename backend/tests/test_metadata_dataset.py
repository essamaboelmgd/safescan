import csv
from io import BytesIO
from pathlib import Path
import httpx
import numpy as np
from PIL import Image
import pytest

from backend.app.metadata import fetch_food_metadata
from tools.dataset import FIELDS, assign_splits, load_manifest


def test_network_errors_and_invalid_responses(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError('TEST ONLY')
    monkeypatch.setattr(httpx, 'get', fail)
    record, warning = fetch_food_metadata('4006381333931')
    assert record is None and 'unavailable' in warning
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, json=[], request=httpx.Request('GET', 'https://example.invalid')))
    assert fetch_food_metadata('4006381333931')[0] is None


def test_external_catalogue_cannot_create_safety_claims(monkeypatch):
    body = {'status': 1, 'product': {'product_name': 'TEST-ONLY', 'labels': 'certified', 'recalls': ['untrusted']}}
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, json=body, request=httpx.Request('GET', 'https://example.invalid')))
    record, warning = fetch_food_metadata('4006381333931')
    assert record['evidence'] == []
    assert warning is None
    assert 'certified' not in record.values()


def write_manifest(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_empty_manifest_fails_without_inventing_data(tmp_path):
    path = tmp_path / 'manifest.csv'
    write_manifest(path, [])
    with pytest.raises(ValueError, match='empty'):
        load_manifest(path)


def test_duplicate_and_group_leakage_rejected(tmp_path, image_bytes):
    (tmp_path / 'a.png').write_bytes(image_bytes)
    (tmp_path / 'b.png').write_bytes(image_bytes)
    base = {'image_path': 'a.png', 'product_id': 'TEST', 'label': 'authentic', 'group_id': 'one',
            'split': 'train', 'source_url': 'https://example.invalid/test'}
    path = tmp_path / 'manifest.csv'
    write_manifest(path, [base, {**base, 'image_path': 'b.png', 'split': 'test'}])
    with pytest.raises(ValueError, match='duplicate'):
        load_manifest(path)
    array = np.random.default_rng(31).integers(0, 256, (60, 60, 3), dtype=np.uint8)
    Image.fromarray(array).save(tmp_path / 'b.png')
    with pytest.raises(ValueError, match='group leaks'):
        load_manifest(path)


def test_manifest_paths_cannot_escape(tmp_path):
    path = tmp_path / 'manifest.csv'
    write_manifest(path, [{'image_path': '../outside.png', 'product_id': 'TEST', 'label': 'authentic',
                           'group_id': 'one', 'split': 'train', 'source_url': 'https://example.invalid/test'}])
    with pytest.raises(ValueError, match='inside'):
        load_manifest(path)


def test_split_is_deterministic_and_group_isolated():
    rows = [{'group_id': f'g{i}', 'split': ''} for i in range(12) for _ in range(2)]
    result = assign_splits(rows)
    assert result == assign_splits(rows)
    assert {r['split'] for r in result} == {'train', 'val', 'test'}
    for group in {r['group_id'] for r in result}:
        assert len({r['split'] for r in result if r['group_id'] == group}) == 1


def test_reference_import_connects_images_vectors_and_metadata(tmp_path, image_bytes, product_record, settings):
    import json
    from tools.dataset import import_catalog
    from backend.app.database import Database
    (tmp_path / 'fixture.png').write_bytes(image_bytes)
    manifest = tmp_path / 'manifest.csv'
    write_manifest(manifest, [{'image_path': 'fixture.png', 'product_id': product_record['id'],
                               'label': 'authentic', 'group_id': 'TEST-UNIT', 'split': 'reference',
                               'source_url': 'https://example.invalid/test-fixture'}])
    products = tmp_path / 'products.json'
    products.write_text(json.dumps([product_record]), encoding='utf-8')
    assert import_catalog(manifest, products, settings) == 1
    database = Database(settings.data_dir / 'safescan.sqlite3')
    reference = database.references()[0]
    assert len(reference['features']) == 192
    assert database.by_barcode(product_record['barcode'])['id'] == product_record['id']
    assert Path(database.upload(reference['upload_id'])['path']).is_file()
