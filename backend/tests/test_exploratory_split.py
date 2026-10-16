"""Test-only graph/split examples, never consumer training data."""
from collections import Counter
import pytest

from tools.prepare_exploratory_shoes import build_relationships, select_records, assign_group_splits


def row(path, label, source=None, family='TEST-FAMILY', state='single_dataset_claim'):
    return {'path': path, 'dataset_label': label, 'source_key': source or path,
            'label_state': state, 'valid_image': 'True', 'original_split': 'train',
            'image_id': path, 'dataset_product_family': family}


def test_exclusions_and_excluded_bridges_preserve_related_survivors():
    rows = [row('a', 'authentic', 'VIDEO1'), row('b', 'counterfeit', 'VIDEO2'),
            row('c', 'counterfeit'), row('d', '', state='mixed_authentic_and_counterfeit_objects'),
            row('e', 'counterfeit'), row('f', 'authentic', 'VIDEO1'),
            row('g', 'counterfeit', 'VIDEO2'), row('h', 'authentic')]
    records = {'byte_identical': [{'paths': ['b','c']}, {'paths': ['f','h']}],
               'decoded_rgb_identical': [], 'pipeline_rgb_identical': []}
    pairs = [{'left': 'a', 'right': 'b'}, {'left': 'd', 'right': 'e'}]
    exact, visual, related, _ = build_relationships(rows, records, pairs)
    retained, excluded = select_records(rows, exact, visual, [])
    assert {r['path'] for r in retained} == {'f','g'}
    reasons = {r['path']:r['reasons'] for r in excluded}
    assert 'conflicting_publisher_labels' in reasons['a']
    assert 'conflicting_publisher_labels' in reasons['c']
    assert 'mixed_class_image_or_suspected_visual_alias' in reasons['e']
    assert 'redundant_exact_duplicate' in reasons['h']
    # f -> excluded a -> excluded b -> g: discarding aliases first would lose this link.
    assert related.find('f') == related.find('g')


def test_split_is_grouped_balanced_deterministic_and_input_order_independent():
    rows, by_path = [], {}
    for family in ('TEST-A','TEST-B'):
        for label in ('authentic','counterfeit'):
            for i in range(80):
                path = f'{family}/{label}/{i}'
                rows.append(row(path, label, family=family))
                by_path[path] = f'OBSERVED-TEST-{family}-{label}-{i//2}'
    assignment = assign_group_splits(rows, by_path, seed=42)
    assert assignment == assign_group_splits(list(reversed(rows)), by_path, seed=42)
    for split in ('train','val','test'):
        subset = [r for r in rows if assignment[by_path[r['path']]] == split]
        counts = Counter(r['dataset_label'] for r in subset)
        assert min(counts.values()) >= 20
        assert len({(r['dataset_product_family'],r['dataset_label']) for r in subset}) == 4
    assert set(assignment.values()) == {'train','val','test'}


def test_insufficient_observed_groups_block_exploratory_split():
    rows = [row('a','authentic'), row('b','counterfeit')]
    with pytest.raises(ValueError, match='Do not train'):
        assign_group_splits(rows, {'a':'g1','b':'g2'})


def test_unknown_relationship_and_invalid_records_are_not_accepted():
    records = {'byte_identical': [], 'decoded_rgb_identical': [], 'pipeline_rgb_identical': []}
    with pytest.raises(ValueError, match='unknown image'):
        build_relationships([row('a','authentic')], records, [{'left':'a','right':'missing'}])
    rows = [row('a','authentic'), row('b','counterfeit')]
    rows[0]['valid_image'] = 'False'
    exact, visual, _, _ = build_relationships(rows, records, [])
    selected, exclusions = select_records(rows, exact, visual, [{'kind':'image_dimensions_mismatch','path':'b'}])
    assert selected == []
    assert len(exclusions) == 2
