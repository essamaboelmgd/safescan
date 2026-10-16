"""Security and interpretation checks for the real-data audit, using test-only ZIPs."""
from io import BytesIO
import json
import stat
import zipfile

from PIL import Image
import pytest

from tools.audit_coco import (
    audit, binary_label, duplicate_groups, safe_extract, source_key,
    validate_members, verify_extracted, write_review_manifest,
)


@pytest.mark.parametrize('name', ['../escape.jpg', '/absolute.jpg', 'C:\\escape.jpg',
                                  'dir\\..\\escape.jpg', 'file.jpg:stream', 'NUL.txt', 'dir./file.jpg'])
def test_unsafe_archive_paths_are_rejected(name):
    with pytest.raises(ValueError):
        validate_members([zipfile.ZipInfo(name)])


def test_symlinks_case_collisions_and_bombs_are_rejected():
    link = zipfile.ZipInfo('link.jpg')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError):
        validate_members([link])
    with pytest.raises(ValueError):
        validate_members([zipfile.ZipInfo('a.JPG'), zipfile.ZipInfo('A.jpg')])
    large = zipfile.ZipInfo('bomb.jpg')
    large.file_size, large.compress_size = 100_000_000, 10
    with pytest.raises(ValueError):
        validate_members([large])
    with pytest.raises(ValueError):
        validate_members([zipfile.ZipInfo('file'), zipfile.ZipInfo('file/child')])


def test_extraction_preserves_original_bytes_and_refuses_overwrite(tmp_path):
    archive = tmp_path / 'TEST-ONLY.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('train/note.txt', b'TEST ONLY')
    destination = tmp_path / 'extracted'
    safe_extract(archive, destination)
    assert (destination / 'train/note.txt').read_bytes() == b'TEST ONLY'
    assert verify_extracted(archive, destination)[0]['bytes'] == 9
    with pytest.raises(ValueError, match='already exists'):
        safe_extract(archive, destination)
    (destination / 'train/note.txt').write_bytes(b'CHANGED')
    with pytest.raises(ValueError, match='changed'):
        verify_extracted(archive, destination)


def test_mapping_preserves_claim_uncertainty_and_rejects_mixed_objects():
    assert binary_label(['Authentic Nike Air Force 1']) == ('authentic', 'dataset_nike_air_force_1', 'single_dataset_claim')
    assert binary_label(['Fake Nike Air Jordan 1'])[0] == 'counterfeit'
    assert binary_label(['Authentic Nike Air Jordan 1', 'Fake Nike Air Jordan 1'])[0] is None
    assert binary_label([])[2] == 'unannotated'
    assert binary_label(['shoes'])[0] is None


def test_video_source_groups_are_not_physical_unit_ids():
    first = source_key('SaveInsta_App-3180374285335138741_mp4-2.jpg')
    second = source_key('SaveInsta_App-3180374285335138741_mp4-8.jpg')
    assert first == second
    assert first[1] == 'shared_video_filename'
    assert source_key('ori1.jpg') != source_key('ori2.jpg')


def test_exact_duplicate_conflicts_and_split_leakage_are_reported():
    rows = [{'digest': 'TEST', 'path': 'train/a.jpg', 'dataset_label': 'authentic', 'original_split': 'train'},
            {'digest': 'TEST', 'path': 'valid/b.jpg', 'dataset_label': 'counterfeit', 'original_split': 'valid'}]
    group = duplicate_groups(rows, 'digest')[0]
    assert group['cross_split'] and group['conflicting_binary_claims']


def test_audit_flags_bad_annotations_and_never_invents_verified_units(tmp_path):
    image = BytesIO()
    Image.new('RGB', (64, 64), 'navy').save(image, 'JPEG')
    document = {
        'categories': [{'id': 1, 'name': 'Authentic Nike Air Force 1'}],
        'images': [{'id': 1, 'file_name': 'TEST-ONLY.jpg', 'width': 64, 'height': 64}],
        'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1, 'bbox': [-5, 0, 64, 64], 'area': 4096, 'iscrowd': 0}],
    }
    archive = tmp_path / 'TEST-ONLY.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('train/TEST-ONLY.jpg', image.getvalue())
        bundle.writestr('train/_annotations.coco.json', json.dumps(document))
    report = audit(archive, tmp_path / 'raw', tmp_path / 'report')
    assert report['issue_counts']['invalid_annotation'] == 1
    assert report['valid_decoded_images'] == 1
    assert report['physical_units']['verified_unit_ids'] == 0
    assert report['held_out_metrics'] is None
    assert report['model_trained'] is False
    assert report['active_manifest_written'] is False
    status = write_review_manifest(tmp_path / 'report', tmp_path / 'manifest.review.csv')
    assert status['rows'] == 1
    import csv
    with (tmp_path / 'manifest.review.csv').open() as stream:
        row = next(csv.DictReader(stream))
    assert row['group_id'] == row['split'] == ''
    assert status['authenticity_labels_independently_verified'] is False
    with pytest.raises(ValueError, match='already exists'):
        write_review_manifest(tmp_path / 'report', tmp_path / 'manifest.review.csv')
