from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def pytest_configure(config):
    # pytest creates basetemp itself but requires its parent to exist.
    (Path(__file__).resolve().parents[2] / 'runtime').mkdir(exist_ok=True)


@pytest.fixture
def image_bytes():
    # Geometric test fixture only. Never used as consumer or training data.
    generator = np.random.default_rng(7)
    image = generator.integers(0, 256, (100, 180, 3), dtype=np.uint8)
    output = BytesIO()
    Image.fromarray(image).save(output, format='PNG')
    return output.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / 'runtime', model_path=tmp_path / 'missing.npz')


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as current:
        yield current


@pytest.fixture
def upload_id(client, image_bytes):
    return client.post('/api/uploads', files={'file': ('fixture.png', image_bytes, 'image/png')}).json()['upload_id']


@pytest.fixture
def product_record():
    return {'id': 'test-only', 'name': 'TEST FIXTURE — NOT A REAL PRODUCT', 'brand': 'Fixture', 'category': 'Test',
            'barcode': '4006381333931', 'batch_number': None, 'description': 'Automated test only',
            'source_url': 'https://example.invalid/test-fixture', 'checked_at': '2026-10-15T00:00:00Z',
            'evidence': [], 'alternatives': []}
