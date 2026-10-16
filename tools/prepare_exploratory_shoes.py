"""Freeze a source-grouped exploratory split without claiming physical-unit independence.

Reads the preserved shoe audit, never rewrites it, and keeps original/review
manifests unchanged. Publisher labels are the experimental target, not verified
authenticity. Suspected visual links are conservatively kept in the same group.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from tools.audit_coco import ROOT, sha256_file, workspace_path
from tools.dataset import FIELDS

SPLITS = ('train', 'val', 'test')
RATIOS = np.array([0.70, 0.15, 0.15])


class Components:
    def __init__(self, paths):
        self.parents = {path: path for path in paths}

    def find(self, path):
        while self.parents[path] != path:
            self.parents[path] = self.parents[self.parents[path]]
            path = self.parents[path]
        return path

    def union(self, paths):
        for path in paths[1:]:
            self.parents[self.find(path)] = self.find(paths[0])

    def members(self):
        groups = defaultdict(list)
        for path in sorted(self.parents):
            groups[self.find(path)].append(path)
        return list(groups.values())


def build_relationships(rows, records, near_pairs):
    paths = [row['path'] for row in rows]
    if len(paths) != len(set(paths)):
        raise ValueError('Audit inventory contains repeated paths.')
    exact, visual, related = (Components(paths) for _ in range(3))
    links = []

    def link(members, reason, exact_match=False, visual_match=False):
        if any(path not in related.parents for path in members):
            raise ValueError('Relationship references an unknown image.')
        related.union(members)
        if visual_match or exact_match:
            visual.union(members)
        if exact_match:
            exact.union(members)
        for right in members[1:]:
            links.append({'left': members[0], 'right': right, 'basis': reason})

    for kind in ('byte_identical', 'decoded_rgb_identical', 'pipeline_rgb_identical'):
        for group in records[kind]:
            link(group['paths'], kind, exact_match=True)
    sources = defaultdict(list)
    for row in rows:
        if row['source_key']:
            sources[row['source_key']].append(row['path'])
    for members in sources.values():
        if len(members) > 1:
            link(sorted(members), 'shared_source_key_not_physical_unit')
    for pair in near_pairs:
        link([pair['left'], pair['right']], 'conservative_phash_candidate_not_verified_identity', visual_match=True)
    return exact, visual, related, links


def select_records(rows, exact, visual, issues):
    """Exclude ambiguous visual components; deduplicate eligible exact copies."""
    by_path = {row['path']: row for row in rows}
    visual_conflicts, visual_ambiguity = set(), set()
    for members in visual.members():
        claims = {by_path[path]['dataset_label'] for path in members if by_path[path]['dataset_label']}
        if len(claims) > 1:
            visual_conflicts.update(members)
        if any(by_path[path]['label_state'] == 'mixed_authentic_and_counterfeit_objects' for path in members):
            visual_ambiguity.update(members)
    wrong_dimensions = {item['path'] for item in issues if item['kind'] == 'image_dimensions_mismatch'}
    bad_annotations = {(item['split'], str(item['image_id'])) for item in issues
                       if item['kind'] == 'invalid_annotation'}
    reasons = defaultdict(list)
    eligible = {}
    for row in rows:
        path = row['path']
        if row['label_state'] != 'single_dataset_claim' or row['dataset_label'] not in {'authentic', 'counterfeit'}:
            reasons[path].append(row['label_state'])
        if row['valid_image'] != 'True':
            reasons[path].append('not_accepted_by_current_preprocessing')
        if path in wrong_dimensions:
            reasons[path].append('coco_dimensions_mismatch')
        if (row['original_split'], row['image_id']) in bad_annotations:
            reasons[path].append('invalid_annotation')
        if path in visual_conflicts:
            reasons[path].append('conflicting_publisher_labels_in_exact_or_suspected_visual_component')
        if path in visual_ambiguity:
            reasons[path].append('mixed_class_image_or_suspected_visual_alias')
        if not row['dataset_product_family']:
            reasons[path].append('missing_product_family')
        if not reasons[path]:
            eligible[path] = row
    retained = []
    for members in exact.members():
        available = sorted(path for path in members if path in eligible)
        if available:
            retained.append(eligible[available[0]])
            for path in available[1:]:
                reasons[path].append('redundant_exact_duplicate_same_publisher_label')
    excluded = [{'path': path, 'reasons': '|'.join(values)} for path, values in sorted(reasons.items()) if values]
    return sorted(retained, key=lambda row: row['path']), excluded


def assign_group_splits(rows, group_by_path, seed=42):
    """Fixed-seed greedy 70/15/15 allocation balancing family/label image counts.

    Whole connected components are indivisible. No model performance enters
    selection. Targets are approximate because groups have unequal sizes.
    """
    grouped = defaultdict(list)
    for row in rows:
        grouped[group_by_path[row['path']]].append(row)
    strata = sorted({(row['dataset_product_family'], row['dataset_label']) for row in rows})
    if not strata:
        raise ValueError('No eligible data remains.')
    vectors = {key: np.array([sum((row['dataset_product_family'], row['dataset_label']) == stratum for row in members)
                              for stratum in strata], dtype=float) for key, members in grouped.items()}
    totals = sum(vectors.values())
    targets = RATIOS[:, None] * totals[None, :]
    counts = np.zeros_like(targets)
    keys = sorted(grouped)
    order = np.random.default_rng(seed).permutation(len(keys))
    ranks = {keys[position]: rank for rank, position in enumerate(order)}
    keys.sort(key=lambda key: (-len(grouped[key]), ranks[key]))
    assignment = {}
    for key in keys:
        vector = vectors[key]
        change = (((counts + vector - targets) ** 2 - (counts - targets) ** 2) / (targets + 1)).sum(axis=1)
        chosen = int(np.argmin(change))
        counts[chosen] += vector
        assignment[key] = SPLITS[chosen]
    for split in SPLITS:
        subset = [row for row in rows if assignment[group_by_path[row['path']]] == split]
        for label in ('authentic', 'counterfeit'):
            matches = [row for row in subset if row['dataset_label'] == label]
            group_count = len({group_by_path[row['path']] for row in matches})
            if len(matches) < 20 or group_count < 5:
                raise ValueError(f'{split}/{label} lacks 20 images and five observed relationship groups. Do not train.')
        if any(not any((row['dataset_product_family'], row['dataset_label']) == stratum for row in subset) for stratum in strata):
            raise ValueError(f'{split} lacks a represented product-family/label stratum. Do not train.')
    return assignment


def prepare(audit_dir, output_manifest, report_dir, seed=42):
    audit_dir, output_manifest, report_dir = map(workspace_path, (audit_dir, output_manifest, report_dir))
    if output_manifest.exists() or report_dir.exists():
        raise ValueError('Output already exists. Use a new version to preserve the frozen experiment.')
    if not (output_manifest.parent / 'raw').is_dir():
        raise ValueError('Place the exploratory manifest beside data/raw to satisfy pipeline path boundaries.')
    summary = json.loads((audit_dir / 'audit.json').read_text(encoding='utf-8'))
    extraction = json.loads((audit_dir / 'extracted_files.json').read_text(encoding='utf-8'))
    issues = json.loads((audit_dir / 'issues.json').read_text(encoding='utf-8'))
    if any(item['kind'] in {'duplicate_image_id', 'duplicate_category_id', 'not_valid_coco_lists', 'image_path_escape'} for item in issues):
        raise ValueError('Structural audit errors require review before splitting.')
    with (audit_dir / 'image_inventory.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    with (audit_dir / 'near_duplicate_candidates.csv').open(encoding='utf-8', newline='') as stream:
        near_pairs = list(csv.DictReader(stream))
    records = json.loads((audit_dir / 'duplicate_and_source_groups.json').read_text(encoding='utf-8'))
    raw_root = (ROOT / summary['extracted_root']).resolve()
    protected = [ROOT / summary['archive'], ROOT / 'data/manifest.csv', ROOT / 'data/manifest.shoes.review_required.csv',
                 *[path for path in audit_dir.rglob('*') if path.is_file()],
                 *[path for folder in ('lib', 'android') for path in (ROOT / folder).rglob('*') if path.is_file()]]
    preserved = {str(path.relative_to(ROOT)).replace('\\', '/'): sha256_file(path) for path in protected}
    if preserved[str(Path(summary['archive'])).replace('\\', '/')] != summary['archive_sha256_before']:
        raise ValueError('Original archive differs from the preserved audit.')
    for record in extraction:
        path = (raw_root / record['path']).resolve()
        if not path.is_relative_to(raw_root) or sha256_file(path) != record['sha256']:
            raise ValueError(f'Original extraction changed: {record["path"]}')
    exact, visual, related, links = build_relationships(rows, records, near_pairs)
    retained, excluded = select_records(rows, exact, visual, issues)
    group_by_path = {}
    group_records = []
    retained_paths = {row['path'] for row in retained}
    for members in related.members():
        group_id = 'observed_' + hashlib.sha256('\n'.join(members).encode()).hexdigest()[:24]
        for path in members:
            group_by_path[path] = group_id
        survivors = [path for path in members if path in retained_paths]
        if survivors:
            group_records.append({'group_id': group_id, 'basis': 'observed_or_suspected_source_relationship_not_physical_unit',
                                  'all_original_members_including_excluded_aliases': members, 'retained_members': survivors})
    if len({group['group_id'] for group in group_records}) != len(group_records):
        raise ValueError('Unexpected group hash collision.')
    assignment = assign_group_splits(retained, group_by_path, seed)
    split_by_path = {row['path']: assignment[group_by_path[row['path']]] for row in retained}
    crossings = [link for link in links if link['left'] in split_by_path and link['right'] in split_by_path
                 and split_by_path[link['left']] != split_by_path[link['right']]]
    if crossings:
        raise ValueError('Observed relationship crosses splits; do not train.')
    manifest_rows, mapping = [], []
    for row in retained:
        path = (raw_root / row['path']).resolve()
        if not path.is_relative_to(output_manifest.parent):
            raise ValueError('Image escapes manifest directory.')
        manifest_rows.append({'image_path': os.path.relpath(path, output_manifest.parent).replace('\\', '/'),
                              'product_id': row['dataset_product_family'], 'label': row['dataset_label'],
                              'group_id': group_by_path[row['path']], 'split': split_by_path[row['path']], 'source_url': summary['source_url']})
        mapping.append({'path': row['path'], 'original_split': row['original_split'], 'group_id': group_by_path[row['path']],
                        'exploratory_split': split_by_path[row['path']], 'publisher_label': row['dataset_label']})
    report_dir.mkdir(parents=True)
    with output_manifest.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)
    def write_json(name, value):
        (report_dir / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    write_json('protected_files_before.json', preserved)
    write_json('groups.json', group_records)
    write_json('relationship_edges.json', links)
    write_json('exclusions.json', excluded)
    write_json('split_membership.json', mapping)
    split_counts = {}
    for split in SPLITS:
        subset = [row for row in manifest_rows if row['split'] == split]
        split_counts[split] = {'images': len(subset), 'publisher_label_counts': dict(Counter(row['label'] for row in subset)),
                               'observed_relationship_groups': len({row['group_id'] for row in subset}),
                               'family_label_counts': dict(Counter(row['product_id'] + '/' + row['label'] for row in subset))}
    report = {'experiment_scope': 'exploratory_publisher_labels', 'source_url': summary['source_url'],
              'manifest': str(output_manifest.relative_to(ROOT)).replace('\\', '/'), 'manifest_sha256': sha256_file(output_manifest),
              'seed': seed, 'target_ratios': dict(zip(SPLITS, RATIOS.tolist())), 'original_images': len(rows),
              'retained_images': len(retained), 'excluded_records': len(excluded),
              'exclusion_reason_counts': dict(Counter(reason for row in excluded for reason in row['reasons'].split('|'))),
              'observed_relationship_groups': len(group_records), 'singleton_observed_groups': sum(len(g['retained_members']) == 1 for g in group_records),
              'split_counts': split_counts, 'cross_split_observed_edges': len(crossings),
              'group_overlap_between_splits': False, 'physical_unit_independence_verified': False,
              'label_provenance': 'publisher_provided_not_independently_verified',
              'selection_policy': 'fixed seed; no model or held-out performance used to choose exclusions, groups or split',
              'near_duplicate_policy': 'all audited pHash candidates grouped conservatively, not asserted to be the same shoe',
              'excluded_bridge_policy': 'components built on all original nodes before exclusion and exact deduplication',
              'training_permitted_for': 'exploratory image-label agreement only',
              'limitations': ['Unknown shoe identities, source sessions and undetected near duplicates can still connect different groups.',
                              'Singleton means no detected link, not a verified independent physical unit.',
                              'Backgrounds, cameras, sellers and product-family cues may correlate with publisher labels.',
                              'No authenticity or safety claim and no public deployment is supported.']}
    write_json('split_report.json', report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, default=Path('reports/shoes_dataset'))
    parser.add_argument('--manifest', type=Path, default=Path('data/manifest.shoes.exploratory_v1.csv'))
    parser.add_argument('--reports', type=Path, default=Path('reports/shoes_exploratory_v1'))
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        prepare(args.audit_dir, args.manifest, args.reports, args.seed)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Exploratory preparation blocked: {exc}\n')
