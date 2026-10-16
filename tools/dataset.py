"""Validate real data, assign group-isolated splits and import sourced references."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from backend.app.config import Settings
from backend.app.schemas import ProductRecord
from backend.app.service import ScanService
from backend.app.vision import preprocess, FEATURE_VERSION

FIELDS = ['image_path', 'product_id', 'label', 'group_id', 'split', 'source_url']
SPLITS = {'train', 'val', 'test', 'reference'}


def load_manifest(path: Path, allow_unsplit=False):
    path = path.resolve()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError(f'Manifest header must be {",".join(FIELDS)}')
        rows = list(reader)
    if not rows:
        raise ValueError('Dataset is empty. Supply real labeled images and provenance; no dataset is bundled.')
    groups, hashes, paths = {}, {}, set()
    for line, row in enumerate(rows, start=2):
        if any(value is None for value in row.values()) or None in row:
            raise ValueError(f'Invalid CSV record on line {line}')
        if row['label'] not in {'authentic', 'counterfeit'}:
            raise ValueError(f'Line {line}: label must be authentic or counterfeit, independently verified.')
        split = row['split']
        if split not in SPLITS and not (allow_unsplit and split == ''):
            raise ValueError(f'Line {line}: invalid split {split!r}')
        if not row['group_id'] or not row['product_id']:
            raise ValueError(f'Line {line}: product_id and group_id are required.')
        if urlparse(row['source_url']).scheme not in {'http', 'https'} or not urlparse(row['source_url']).netloc:
            raise ValueError(f'Line {line}: a real provenance URL is required.')
        image_path = (path.parent / row['image_path']).resolve()
        # Reject manifest traversal, symlinks escaping the dataset and absolute outside paths.
        if not image_path.is_relative_to(path.parent):
            raise ValueError(f'Line {line}: image must stay inside the manifest directory.')
        if image_path in paths:
            raise ValueError(f'Line {line}: repeated image path.')
        paths.add(image_path)
        data = image_path.read_bytes()
        processed = preprocess(data)
        # Hash decoded RGB so duplicates with different containers/metadata are detected.
        digest = hashlib.sha256(processed.rgb.tobytes()).hexdigest()
        if digest in hashes:
            raise ValueError(f'Line {line}: duplicate decoded image (possibly data leakage).')
        hashes[digest] = split
        if row['group_id'] in groups and groups[row['group_id']] != split:
            raise ValueError(f'Line {line}: group leaks across splits.')
        groups[row['group_id']] = split
        row['_path'] = image_path
        row['_digest'] = digest
    return rows


def assign_splits(rows, seed=42):
    groups = sorted({row['group_id'] for row in rows if row['split'] != 'reference'})
    if len(groups) < 5:
        raise ValueError('At least five independent non-reference groups are required to split data.')
    generator = np.random.default_rng(seed)
    generator.shuffle(groups)
    val_count = max(1, round(len(groups) * 0.15))
    test_count = max(1, round(len(groups) * 0.15))
    mapping = {group: ('test' if i < test_count else 'val' if i < test_count + val_count else 'train')
               for i, group in enumerate(groups)}
    return [{**row, 'split': row['split'] if row['split'] == 'reference' else mapping[row['group_id']]} for row in rows]


def import_catalog(manifest: Path, products: Path, settings: Settings):
    rows = load_manifest(manifest)
    records = json.loads(products.read_text(encoding='utf-8-sig'))
    if not isinstance(records, list) or not records:
        raise ValueError('Products JSON must contain real sourced product records.')
    products_validated = [ProductRecord.model_validate(record).model_dump(mode='json') for record in records]
    ids = {record['id'] for record in products_validated}
    if len(ids) != len(products_validated):
        raise ValueError('Product ids must be unique.')
    references = [row for row in rows if row['split'] == 'reference']
    if not references:
        raise ValueError('No reference rows to import.')
    for row in references:
        if row['product_id'] not in ids:
            raise ValueError(f'Product record missing for {row["product_id"]}.')
    service = ScanService(settings)
    for record in products_validated:
        service.db.upsert_product(record)
    for row in references:
        image = preprocess(row['_path'].read_bytes())
        upload = service.store_image(row['_path'].read_bytes())
        reference_id = hashlib.sha256((row['product_id'] + row['_digest']).encode()).hexdigest()[:32]
        service.db.add_reference({
            'id': reference_id, 'product_id': row['product_id'], 'upload_id': upload['upload_id'],
            'label': row['label'], 'source_url': row['source_url'],
            'features': image.features.tolist(), 'phash': image.phash, 'feature_version': FEATURE_VERSION,
        })
    return len(references)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'split', 'import'])
    parser.add_argument('--manifest', type=Path, default=Path('data/manifest.csv'))
    parser.add_argument('--products', type=Path, default=Path('data/products.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        if args.action == 'import':
            print(json.dumps({'imported_references': import_catalog(args.manifest, args.products, Settings.from_env())}))
        else:
            rows = load_manifest(args.manifest, allow_unsplit=args.action == 'split')
            if args.action == 'split':
                if not args.output or args.output.resolve() == args.manifest.resolve():
                    raise ValueError('Use --output with a different filename. Input is preserved.')
                if args.output.resolve().parent != args.manifest.resolve().parent:
                    raise ValueError('Output must be beside the input manifest to preserve relative paths.')
                rows = assign_splits(rows, args.seed)
                with args.output.open('w', encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)
                print('Wrote group-isolated splits. Review class balance and near-duplicate images before training.')
            else:
                print(json.dumps({'images': len(rows), 'split_counts': {s: sum(r['split'] == s for r in rows) for s in sorted(SPLITS)}}))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Dataset error: {exc}\n')


if __name__ == '__main__':
    main()
