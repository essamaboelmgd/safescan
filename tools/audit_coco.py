"""Safely extract and audit a COCO shoe archive without training or inventing units.

The audit records dataset claims separately from verified physical authenticity.
It deliberately does not write a trainable manifest when those claims and unit
identities cannot be established from the available evidence.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid
import zipfile

import numpy as np
from PIL import Image, ImageOps, ImageDraw

from backend.app.vision import preprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://universe.roboflow.com/shoes-classification-ovo/original-or-fake-shoes-5tbgz'
CATEGORY_MAP = {
    'Authentic Nike Air Force 1': ('authentic', 'dataset_nike_air_force_1'),
    'Authentic Nike Air Jordan 1': ('authentic', 'dataset_nike_air_jordan_1'),
    'Fake Nike Air Force 1': ('counterfeit', 'dataset_nike_air_force_1'),
    'Fake Nike Air Jordan 1': ('counterfeit', 'dataset_nike_air_jordan_1'),
}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def sha256_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def workspace_path(path):
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError('Output must remain inside the project workspace.')
    return resolved


def validate_members(infos, max_bytes=1024 ** 3):
    """Preflight every Windows path before writing any archive member."""
    if len(infos) > 20_000 or sum(i.file_size for i in infos) > max_bytes:
        raise ValueError('Archive exceeds entry or uncompressed-size limit.')
    seen = set()
    files = set()
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    for info in infos:
        name = info.filename.replace('\\', '/')
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (not name or path.is_absolute() or '..' in path.parts or ':' in name
                or '\x00' in name or info.flag_bits & 1 or stat.S_ISLNK(mode)
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})):
            raise ValueError(f'Unsafe archive member: {name!r}')
        if any(part.endswith((' ', '.')) or part.split('.')[0].upper() in reserved for part in path.parts):
            raise ValueError(f'Unsafe Windows archive member: {name!r}')
        key = str(path).casefold()
        if key in seen:
            raise ValueError(f'Colliding archive member: {name!r}')
        seen.add(key)
        if not info.is_dir():
            files.add(key)
        if info.file_size > 100 * 1024 ** 2 or info.file_size / max(info.compress_size, 1) > 200:
            raise ValueError(f'Archive member exceeds safe size/ratio: {name!r}')
    for key in seen:
        if any(str(parent).casefold() in files for parent in PurePosixPath(key).parents if str(parent) != '.'):
            raise ValueError('Archive contains a file/directory path collision.')


def safe_extract(archive, destination):
    destination = workspace_path(destination)
    if destination.exists():
        raise ValueError('Extraction destination already exists; originals will not be overwritten. Use --reuse-extracted to verify it.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + '.extracting-' + uuid.uuid4().hex)
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        validate_members(infos)
        staging.mkdir()
        # If extraction fails, retain the staging directory for inspection;
        # never recursively delete a computed path.
        for info in infos:
            target = (staging / info.filename.replace('\\', '/')).resolve()
            if not target.is_relative_to(staging):
                raise ValueError('Archive member escaped extraction directory.')
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output, length=64 * 1024)
            if target.stat().st_size != info.file_size:
                raise ValueError('Extracted size does not match the ZIP header.')
        staging.rename(destination)
    return destination


def verify_extracted(archive, destination):
    """Verify every original byte against the ZIP, including its CRC."""
    destination = workspace_path(destination)
    rows = []
    with zipfile.ZipFile(archive) as bundle:
        validate_members(bundle.infolist())
        for info in bundle.infolist():
            if info.is_dir():
                continue
            path = (destination / info.filename.replace('\\', '/')).resolve()
            if not path.is_relative_to(destination) or not path.is_file():
                raise ValueError(f'Missing extracted member: {info.filename}')
            with bundle.open(info) as source:
                expected = hashlib.file_digest(source, 'sha256').hexdigest()
            actual = sha256_file(path)
            if actual != expected:
                raise ValueError(f'Original bytes changed: {info.filename}')
            rows.append({'path': info.filename, 'bytes': info.file_size, 'sha256': actual})
    return rows


def source_key(original_name):
    """Only link observed source names/post ids; never call these shoe-unit ids."""
    name = original_name.casefold()
    video = re.match(r'^(.*?(?:_mp4|\.mp4))[-_](\d+)(?:[-_].*)?\.[a-z0-9]+$', name)
    if video:
        return 'video_filename:' + video[1], 'shared_video_filename'
    post = re.match(r'^(?:snapinsta[-_]app|saveinsta[-_]app)[-_](\d{8,})(?:[-_].*)?\.[a-z0-9]+$', name)
    if post:
        return 'social_post_filename:' + post[1], 'shared_social_post_id_in_filename'
    return 'original_filename:' + name, 'same_original_filename_only'


def binary_label(category_names):
    mappings = [CATEGORY_MAP.get(name) for name in category_names]
    if not mappings:
        return None, None, 'unannotated'
    if any(value is None for value in mappings):
        return None, None, 'unmapped_category'
    labels = {value[0] for value in mappings}
    families = {value[1] for value in mappings}
    if len(labels) != 1:
        return None, None, 'mixed_authentic_and_counterfeit_objects'
    if len(families) != 1:
        return next(iter(labels)), None, 'multiple_product_families'
    return next(iter(labels)), next(iter(families)), 'single_dataset_claim'


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def duplicate_groups(rows, field):
    groups = defaultdict(list)
    for row in rows:
        if row.get(field):
            groups[row[field]].append(row)
    return [{'digest': digest, 'paths': [r['path'] for r in members],
             'original_splits': sorted({r['original_split'] for r in members}),
             'dataset_labels': sorted({r['dataset_label'] for r in members if r['dataset_label']}),
             'cross_split': len({r['original_split'] for r in members}) > 1,
             'conflicting_binary_claims': len({r['dataset_label'] for r in members if r['dataset_label']}) > 1}
            for digest, members in sorted(groups.items()) if len(members) > 1]


def audit(archive, destination, report_dir, reuse=False):
    archive = archive.resolve()
    destination, report_dir = workspace_path(destination), workspace_path(report_dir)
    archive_hash = sha256_file(archive)
    if not reuse:
        safe_extract(archive, destination)
    extraction = verify_extracted(archive, destination)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'extracted_files.json').write_text(json.dumps(extraction, indent=2), encoding='utf-8')
    issues, rows, annotation_rows, split_summaries = [], [], [], {}
    category_totals = defaultdict(lambda: {'annotation_instances': 0, 'images': 0})
    used_paths = set()
    licenses, info_records = [], []
    decoded = {}
    for annotation_path in sorted(destination.rglob('*.json')):
        doc = json.loads(annotation_path.read_text(encoding='utf-8-sig'))
        if not all(isinstance(doc.get(key), list) for key in ('images', 'annotations', 'categories')):
            issues.append({'kind': 'not_valid_coco_lists', 'path': str(annotation_path.relative_to(destination))})
            continue
        split = annotation_path.parent.name
        categories = {c['id']: c['name'] for c in doc['categories']}
        if len(categories) != len(doc['categories']):
            issues.append({'kind': 'duplicate_category_id', 'split': split})
        for name in categories.values():
            category_totals[name]
        licenses.append({'split': split, 'licenses': doc.get('licenses')})
        info_records.append({'split': split, 'info': doc.get('info')})
        images = {image['id']: image for image in doc['images']}
        if len(images) != len(doc['images']):
            issues.append({'kind': 'duplicate_image_id', 'split': split})
        by_image = defaultdict(list)
        annotation_ids = set()
        for annotation in doc['annotations']:
            errors = []
            aid, iid, cid = annotation.get('id'), annotation.get('image_id'), annotation.get('category_id')
            if aid in annotation_ids:
                errors.append('duplicate_annotation_id')
            annotation_ids.add(aid)
            image = images.get(iid)
            if image is None:
                errors.append('unknown_image_id')
            if cid not in categories:
                errors.append('unknown_category_id')
            box = annotation.get('bbox')
            if not isinstance(box, list) or len(box) != 4 or not all(numeric(value) for value in box):
                errors.append('invalid_bbox')
            else:
                x, y, width, height = box
                if width <= 0 or height <= 0:
                    errors.append('nonpositive_bbox_size')
                if image:
                    overshoot = max(0.0, -x, -y, x + width - image['width'], y + height - image['height'])
                    if overshoot > 0.05:
                        errors.append('bbox_outside_image')
                    elif overshoot > 1e-8:
                        issues.append({'kind': 'bbox_rounding_overshoot', 'split': split,
                                       'annotation_id': aid, 'overshoot_pixels': overshoot,
                                       'interpretation': 'within_0.05_pixel_rounding_tolerance_not_an_invalid_annotation'})
                if not numeric(annotation.get('area')) or abs(annotation['area'] - width * height) > max(0.05, width * height * 0.0001):
                    errors.append('bbox_area_mismatch')
            if annotation.get('iscrowd') not in {0, 1}:
                errors.append('invalid_iscrowd')
            if errors:
                issues.append({'kind': 'invalid_annotation', 'split': split, 'annotation_id': aid, 'image_id': iid, 'errors': errors})
            if image is not None:
                by_image[iid].append(annotation)
            category_totals[categories.get(cid, 'UNKNOWN')]['annotation_instances'] += 1
            annotation_rows.append({'original_split': split, 'annotation_id': aid, 'image_id': iid,
                                    'category_name': categories.get(cid), 'bbox': json.dumps(box), 'errors': '|'.join(errors)})
        labels_this_split = Counter()
        for image in doc['images']:
            iid = image['id']
            image_path = (annotation_path.parent / image['file_name']).resolve()
            relative = str(image_path.relative_to(destination)).replace('\\', '/') if image_path.is_relative_to(destination) else image['file_name']
            names = sorted({categories.get(a.get('category_id'), 'UNKNOWN') for a in by_image[iid]})
            label, product_id, state = binary_label(names)
            for name in names:
                category_totals[name]['images'] += 1
            original_name = image.get('extra', {}).get('name') or re.sub(r'\.rf\.[a-f0-9]+(?=\.[^.]+$)', '', Path(image['file_name']).name)
            key, reason = source_key(original_name)
            row = {'path': relative, 'original_split': split, 'image_id': iid, 'original_name': original_name,
                   'category_names': '|'.join(names), 'dataset_label': label, 'label_state': state,
                   'dataset_product_family': product_id, 'source_key': key, 'source_group_basis': reason,
                   'physical_unit_id': None, 'authenticity_verified': False, 'annotations': len(by_image[iid]),
                   'byte_sha256': None, 'decoded_rgb_sha256': None, 'pipeline_rgb_sha256': None,
                   'phash': None, 'quality_warnings': '', 'valid_image': False, 'decodable_image': False,
                   'width': image.get('width'), 'height': image.get('height')}
            labels_this_split[label or state] += 1
            rows.append(row)
            if not image_path.is_relative_to(destination):
                issues.append({'kind': 'image_path_escape', 'path': relative})
                continue
            if not image_path.is_file():
                issues.append({'kind': 'missing_image', 'path': relative})
                continue
            if relative in used_paths:
                issues.append({'kind': 'repeated_image_path', 'path': relative})
            used_paths.add(relative)
            try:
                data = image_path.read_bytes()
                row['byte_sha256'] = hashlib.sha256(data).hexdigest()
                with Image.open(image_path) as raw:
                    if raw.size != (image.get('width'), image.get('height')):
                        issues.append({'kind': 'image_dimensions_mismatch', 'path': relative, 'actual': raw.size})
                    oriented = ImageOps.exif_transpose(raw).convert('RGB')
                    digest = hashlib.sha256()
                    digest.update(str(oriented.size).encode())
                    digest.update(oriented.tobytes())
                    row['decoded_rgb_sha256'] = digest.hexdigest()
                row['decodable_image'] = True
                try:
                    prepared = preprocess(data)
                except ValueError as exc:
                    issues.append({'kind': 'pipeline_rejected_image', 'path': relative, 'error': str(exc),
                                   'width': row['width'], 'height': row['height']})
                    continue
                row['pipeline_rgb_sha256'] = hashlib.sha256(prepared.rgb.tobytes()).hexdigest()
                row['phash'] = prepared.phash
                row['quality_warnings'] = '|'.join(prepared.warnings)
                row['valid_image'] = True
                decoded[relative] = np.array(Image.fromarray(prepared.rgb).convert('L').resize((32, 32)), dtype=np.float32) / 255
            except (ValueError, OSError) as exc:
                issues.append({'kind': 'invalid_image', 'path': relative, 'error': str(exc)})
            if len(rows) % 250 == 0:
                print(f'Audited {len(rows)} image records', flush=True)
        split_summaries[split] = {'images': len(doc['images']), 'annotations': len(doc['annotations']),
                                  'binary_claims_or_state': dict(labels_this_split), 'categories': doc['categories']}
    disk_images = {str(path.relative_to(destination)).replace('\\', '/') for path in destination.rglob('*') if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS}
    orphan_images = sorted(disk_images - used_paths)
    byte_duplicates = duplicate_groups(rows, 'byte_sha256')
    pixel_duplicates = duplicate_groups(rows, 'decoded_rgb_sha256')
    pipeline_duplicates = duplicate_groups(rows, 'pipeline_rgb_sha256')
    source_members = defaultdict(list)
    for row in rows:
        source_members[row['source_key']].append(row)
    shared_sources = [{'source_key': key, 'basis': members[0]['source_group_basis'],
                       'physical_unit_identity': 'unknown', 'paths': [r['path'] for r in members],
                       'original_splits': sorted({r['original_split'] for r in members}),
                       'dataset_labels': sorted({r['dataset_label'] for r in members if r['dataset_label']}),
                       'cross_split': len({r['original_split'] for r in members}) > 1}
                      for key, members in sorted(source_members.items()) if len(members) > 1]
    near_pairs = []
    valid_rows = [row for row in rows if row['valid_image']]
    for i, left in enumerate(valid_rows):
        for right in valid_rows[i + 1:]:
            if left['pipeline_rgb_sha256'] == right['pipeline_rgb_sha256']:
                continue
            distance = (int(left['phash'], 16) ^ int(right['phash'], 16)).bit_count()
            if distance <= 6:
                rmse = float(np.sqrt(np.mean((decoded[left['path']] - decoded[right['path']]) ** 2)))
                near_pairs.append({'left': left['path'], 'right': right['path'], 'phash_distance': distance,
                                   'gray32_rmse': rmse, 'cross_split': left['original_split'] != right['original_split'],
                                   'left_dataset_label': left['dataset_label'], 'right_dataset_label': right['dataset_label'],
                                   'interpretation': 'possible_visual_duplicate_only_not_a_verified_unit_match'})
    near_pairs.sort(key=lambda row: (row['phash_distance'], row['gray32_rmse'], row['left'], row['right']))
    write_csv(report_dir / 'image_inventory.csv', rows, list(rows[0]) if rows else ['path'])
    write_csv(report_dir / 'annotation_inventory.csv', annotation_rows, ['original_split','annotation_id','image_id','category_name','bbox','errors'])
    write_csv(report_dir / 'near_duplicate_candidates.csv', near_pairs, ['left','right','phash_distance','gray32_rmse','cross_split','left_dataset_label','right_dataset_label','interpretation'])
    duplicate_record = {'byte_identical': byte_duplicates, 'decoded_rgb_identical': pixel_duplicates,
                        'pipeline_rgb_identical': pipeline_duplicates, 'shared_source_filename_groups': shared_sources}
    (report_dir / 'duplicate_and_source_groups.json').write_text(json.dumps(duplicate_record, indent=2), encoding='utf-8')
    (report_dir / 'issues.json').write_text(json.dumps(issues, indent=2), encoding='utf-8')
    mixed = [row for row in rows if row['label_state'] == 'mixed_authentic_and_counterfeit_objects']
    label_counts = Counter(row['dataset_label'] for row in rows if row['dataset_label'])
    blockers = [
        'No independent authenticity determination or verification protocol was supplied for the publisher labels.',
        'No independently identifiable physical shoe units or verified unit/source-session separation is supplied; filename/source/duplicate evidence is incomplete.',
    ]
    conflicting_copies = sum(group['conflicting_binary_claims'] for group in byte_duplicates)
    if conflicting_copies:
        blockers.append(f'{conflicting_copies} byte-identical duplicate groups have conflicting whole-image authentic/counterfeit claims; the audit does not guess a correct label.')
    test_summary = split_summaries.get('test', {})
    test_claims = test_summary.get('binary_claims_or_state', {})
    if not all(test_claims.get(label, 0) for label in ('authentic', 'counterfeit')):
        blockers.append(f'Original test partition has {test_summary.get("images", 0)} images and does not contain both binary classes.')
    if mixed:
        blockers.append(f'{len(mixed)} whole images contain both authentic and counterfeit object annotations and have no unambiguous whole-image class.')
    summary = {
        'audit_time_utc': datetime.now(timezone.utc).isoformat(), 'source_url': SOURCE_URL,
        'source_version': 1, 'archive': str(archive.relative_to(ROOT)), 'archive_bytes': archive.stat().st_size,
        'archive_sha256_before': archive_hash, 'archive_sha256_after': sha256_file(archive),
        'extracted_root': str(destination.relative_to(ROOT)), 'extracted_file_count': len(extraction),
        'all_extracted_bytes_verified_against_archive': True, 'split_summaries': split_summaries,
        'category_totals': dict(category_totals), 'image_count': len(rows),
        'valid_decoded_images': sum(r['decodable_image'] for r in rows),
        'pipeline_accepted_images': sum(r['valid_image'] for r in rows),
        'issue_counts': dict(Counter(issue['kind'] for issue in issues)), 'orphan_image_files': orphan_images,
        'unannotated_images': [r['path'] for r in rows if r['label_state'] == 'unannotated'],
        'mixed_binary_label_images': [r['path'] for r in mixed],
        'unambiguous_dataset_claim_counts': dict(label_counts),
        'claim_imbalance_majority_minority_ratio': max(label_counts.values()) / min(label_counts.values()) if len(label_counts) == 2 else None,
        'duplicate_summary': {name: {'groups': len(groups), 'extra_copies': sum(len(group['paths'])-1 for group in groups),
                                    'cross_split_groups': sum(group['cross_split'] for group in groups),
                                    'conflicting_binary_claim_groups': sum(group['conflicting_binary_claims'] for group in groups)}
                              for name, groups in [('byte_identical',byte_duplicates),('decoded_rgb_identical',pixel_duplicates),('pipeline_rgb_identical',pipeline_duplicates)]},
        'shared_source_groups': len(shared_sources), 'cross_split_shared_source_groups': sum(group['cross_split'] for group in shared_sources),
        'near_duplicate_candidates': len(near_pairs), 'cross_split_near_duplicate_candidates': sum(pair['cross_split'] for pair in near_pairs),
        'near_duplicate_method': '64-bit pHash Hamming <= 6; gray32 RMSE recorded for review; not proof of identity',
        'license_records': licenses, 'coco_info_records': info_records,
        'physical_units': {'verified_unit_ids': 0, 'unknown_unit_image_records': len(rows),
                           'basis': 'COCO includes image id, filename, export date and original filename; no unit/pair/serial/track identifiers or cross-image unit map.'},
        'label_mapping': {name: {'dataset_binary_claim': values[0], 'dataset_product_family': values[1], 'independently_verified': False} for name, values in CATEGORY_MAP.items()},
        'training_decision': 'blocked_before_training',
        'blockers': blockers,
        'active_manifest_written': False, 'model_trained': False, 'held_out_metrics': None,
    }
    (report_dir / 'audit.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    # A small review sheet documents ambiguous whole-image labels, not new data.
    if mixed:
        sheet = Image.new('RGB', (480 * min(2, len(mixed)), 350 * math.ceil(len(mixed)/2)), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(mixed):
            with Image.open(destination / row['path']) as original:
                thumb = ImageOps.contain(original.convert('RGB'), (460, 290))
            x, y = (i % 2)*480, (i//2)*350
            sheet.paste(thumb, (x + (480-thumb.width)//2, y))
            draw.text((x+8,y+295), f"{row['original_split']} image_id={row['image_id']}", fill='black')
            draw.text((x+8,y+315), 'Both authentic and fake object annotations', fill='black')
        sheet.save(report_dir / 'mixed_label_review.jpg')
    print(json.dumps({key: summary[key] for key in ['image_count','valid_decoded_images','pipeline_accepted_images','issue_counts','unambiguous_dataset_claim_counts','duplicate_summary','shared_source_groups','cross_split_shared_source_groups','near_duplicate_candidates','cross_split_near_duplicate_candidates','training_decision']}, indent=2), flush=True)
    return summary


def write_review_manifest(report_dir, output_path):
    """Prepare exact-schema review rows; unresolved group/split fields stay blank.

    The active manifest is deliberately protected. This is staging, not a claim
    that publisher labels or independent physical units have been verified.
    """
    report_dir, output_path = workspace_path(report_dir), workspace_path(output_path)
    if output_path == ROOT / 'data' / 'manifest.csv':
        raise ValueError('The active manifest cannot be populated from an unverified audit.')
    if output_path.exists():
        raise ValueError('Review manifest already exists; choose another filename to preserve edits.')
    summary = json.loads((report_dir / 'audit.json').read_text(encoding='utf-8'))
    groups = json.loads((report_dir / 'duplicate_and_source_groups.json').read_text(encoding='utf-8'))
    issues = json.loads((report_dir / 'issues.json').read_text(encoding='utf-8'))
    with (report_dir / 'image_inventory.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    conflicts = set()
    equivalences = []
    for kind in ('byte_identical', 'decoded_rgb_identical', 'pipeline_rgb_identical'):
        for group in groups[kind]:
            equivalences.append(group['paths'])
            if group['conflicting_binary_claims']:
                conflicts.update(group['paths'])
    dimensions_wrong = {issue['path'] for issue in issues if issue['kind'] == 'image_dimensions_mismatch'}
    reasons = defaultdict(list)
    eligible = {}
    for row in rows:
        path = row['path']
        if row['label_state'] != 'single_dataset_claim':
            reasons[path].append(row['label_state'])
        if row['valid_image'] != 'True':
            reasons[path].append('not_accepted_by_current_preprocessing')
        if path in conflicts:
            reasons[path].append('conflicting_exact_duplicate_labels')
        if path in dimensions_wrong:
            reasons[path].append('coco_dimensions_mismatch')
        if not reasons[path]:
            eligible[path] = row
    parents = {path: path for path in eligible}

    def find(path):
        while parents[path] != path:
            parents[path] = parents[parents[path]]
            path = parents[path]
        return path

    for paths in equivalences:
        paths = [path for path in paths if path in eligible]
        for path in paths[1:]:
            parents[find(path)] = find(paths[0])
    components = defaultdict(list)
    for path in eligible:
        components[find(path)].append(path)
    retained = []
    for members in components.values():
        canonical = min(members)
        retained.append(eligible[canonical])
        for path in members:
            if path != canonical:
                reasons[path].append('redundant_exact_duplicate_same_dataset_label')
    raw_root = ROOT / summary['extracted_root']
    prepared = []
    for row in sorted(retained, key=lambda item: item['path']):
        image_path = (raw_root / row['path']).resolve()
        if not image_path.is_relative_to(output_path.parent):
            raise ValueError('Review CSV must be above its image directory to satisfy the pipeline path boundary.')
        prepared.append({'image_path': os.path.relpath(image_path, output_path.parent).replace('\\', '/'),
                         'product_id': row['dataset_product_family'], 'label': row['dataset_label'],
                         'group_id': '', 'split': '', 'source_url': summary['source_url']})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['image_path','product_id','label','group_id','split','source_url'])
        writer.writeheader()
        writer.writerows(prepared)
    excluded = [{'path': path, 'reasons': '|'.join(values)} for path, values in sorted(reasons.items()) if values]
    write_csv(report_dir / 'review_exclusions.csv', excluded, ['path','reasons'])
    status = {'status': 'review_only_not_valid_for_training', 'review_manifest': str(output_path.relative_to(ROOT)),
              'rows': len(prepared), 'dataset_claim_counts': dict(Counter(row['label'] for row in prepared)),
              'excluded_image_records': len(excluded),
              'exclusion_reason_counts': dict(Counter(reason for values in reasons.values() for reason in values)),
              'physical_unit_ids_verified': False, 'authenticity_labels_independently_verified': False,
              'group_id': 'blank_pending_evidence_not_one_group_per_image',
              'split': 'blank_no_train_validation_test_assignment',
              'product_id': 'category-derived dataset product family, not verified SKU or physical-unit identity',
              'active_manifest_changed': False, 'training_performed': False}
    (report_dir / 'review_manifest_status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('data/raw/original_or_fake_shoes_v1'))
    parser.add_argument('--reports', type=Path, default=Path('reports/shoes_dataset'))
    parser.add_argument('--reuse-extracted', action='store_true')
    args = parser.parse_args()
    try:
        audit(args.archive, args.output, args.reports, args.reuse_extracted)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f'Dataset audit failed: {exc}\n')


if __name__ == '__main__':
    main()
