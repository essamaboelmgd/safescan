from io import BytesIO
import numpy as np
from PIL import Image
import pytest

from backend.app.algorithms import exact_neighbors, HyperplaneLSH, hamming_distance, cosine_similarity
from backend.app.vision import preprocess, canonical_png, FEATURE_DIM


def test_preprocessing_is_deterministic_and_same_after_storage(image_bytes):
    image = preprocess(image_bytes)
    assert image.rgb.shape == (224, 224, 3)
    assert image.features.shape == (FEATURE_DIM,)
    assert np.isfinite(image.features).all()
    assert np.linalg.norm(image.features) == pytest.approx(1)
    assert len(image.phash) == 16
    stored = preprocess(canonical_png(image))
    np.testing.assert_allclose(image.features, stored.features)
    assert image.phash == stored.phash


def test_size_checks_and_quality_warning():
    output = BytesIO()
    Image.new('RGB', (10, 100)).save(output, 'PNG')
    with pytest.raises(ValueError, match='32'):
        preprocess(output.getvalue())
    output = BytesIO()
    Image.new('RGB', (100, 100)).save(output, 'PNG')
    with pytest.raises(ValueError, match='pixel limit'):
        preprocess(output.getvalue(), max_pixels=999)
    assert preprocess(output.getvalue()).warnings


def test_orientation_and_unsupported_format():
    image = Image.new('RGB', (80, 40), 'red')
    image.paste('blue', (40, 0, 80, 40))
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, 'JPEG', exif=exif)
    oriented = preprocess(output.getvalue()).rgb
    assert oriented[25, 112, 0] > 200  # EXIF rotation puts the red half on top.
    assert oriented[190, 112, 2] > 200
    output = BytesIO()
    image.save(output, 'GIF')
    with pytest.raises(ValueError, match='JPEG'):
        preprocess(output.getvalue())


def test_exact_search_orders_by_cosine():
    vectors = [[0, 1], [1, 0], [-1, 0]]
    assert [i for i, _ in exact_neighbors([1, 0], vectors, 3)] == [1, 0, 2]
    assert cosine_similarity([0, 0], [1, 0]) == 0
    assert exact_neighbors([1, 0], [], 5) == []
    with pytest.raises(ValueError):
        cosine_similarity([1], [1, 2])
    with pytest.raises(ValueError):
        cosine_similarity([np.nan], [1])


def test_hash_and_lsh_retrieve_identical_vector():
    assert hamming_distance('0000000000000000', 'ffffffffffffffff') == 64
    assert hamming_distance('abc1230000000000', 'abc1230000000000') == 0
    with pytest.raises(ValueError):
        hamming_distance('x', '0')
    index = HyperplaneLSH(3, seed=3)
    index.add([1, 0, 0])
    index.add([0, 1, 0])
    assert index.search([1, 0, 0], 1) == [(0, 1.0)]
    with pytest.raises(ValueError):
        index.add([1, 0])
