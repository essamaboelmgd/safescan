"""Train a reproducible linear baseline from real, provenance-checked image groups."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from backend.app.vision import preprocess, FEATURE_VERSION
from tools.dataset import load_manifest


def features_for(rows, split):
    subset = [r for r in rows if r['split'] == split]
    if not subset or {r['label'] for r in subset} != {'authentic', 'counterfeit'}:
        raise ValueError(f'{split} needs images from both classes: authentic and counterfeit.')
    return (np.stack([preprocess(r['_path'].read_bytes()).features for r in subset]),
            np.array([r['label'] == 'counterfeit' for r in subset], dtype=float))


def probability(x, weights, bias):
    return 1 / (1 + np.exp(-np.clip(x @ weights + bias, -50, 50)))


def metrics(labels, probabilities):
    predicted = np.asarray(probabilities) >= 0.5
    labels = np.asarray(labels, dtype=bool)
    tp = int((predicted & labels).sum())
    tn = int((~predicted & ~labels).sum())
    fp = int((predicted & ~labels).sum())
    fn = int((~predicted & labels).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {'samples': len(labels), 'accuracy': (tp + tn) / len(labels), 'counterfeit_precision': precision,
            'counterfeit_recall': recall, 'counterfeit_f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            'confusion_matrix': {'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp},
            'brier_score': float(np.mean((np.asarray(probabilities) - labels) ** 2))}


def fit(x, y, vx, vy, epochs=500, learning_rate=0.1, regularization=0.001):
    weights = np.zeros(x.shape[1])
    bias = 0.0
    best_loss = float('inf')
    best = None
    # Weight classes equally rather than rewarding majority-class prediction.
    sample_weights = np.where(y == 1, len(y) / (2 * y.sum()), len(y) / (2 * (len(y) - y.sum())))
    for epoch in range(epochs):
        error = (probability(x, weights, bias) - y) * sample_weights
        weights -= learning_rate * ((x.T @ error) / len(y) + regularization * weights)
        bias -= learning_rate * float(error.mean())
        vp = np.clip(probability(vx, weights, bias), 1e-7, 1 - 1e-7)
        loss = float(-np.mean(vy * np.log(vp) + (1 - vy) * np.log(1 - vp)))
        if loss < best_loss:
            best_loss = loss
            best = (weights.copy(), bias, epoch + 1)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('data/manifest.csv'))
    parser.add_argument('--output', type=Path, default=Path('models/classifier.npz'))
    parser.add_argument('--epochs', type=int, default=500)
    parser.add_argument('--learning-rate', type=float, default=0.1)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--exploratory', action='store_true', help='Record that labels are publisher claims, not independently verified authenticity.')
    args = parser.parse_args()
    try:
        if args.epochs < 1 or not np.isfinite(args.learning_rate) or args.learning_rate <= 0:
            raise ValueError('epochs and learning-rate must be positive and finite.')
        if args.output.exists():
            raise ValueError('Output already exists. Choose another filename to preserve the model.')
        rows = load_manifest(args.manifest)
        x, y = features_for(rows, 'train')
        vx, vy = features_for(rows, 'val')
        weights, bias, epoch = fit(x, y, vx, vy, args.epochs, args.learning_rate)
        metadata = {
            'feature_version': FEATURE_VERSION, 'model_version': 'linear-v1', 'labels': ['authentic', 'counterfeit'],
            'dataset_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            'image_digests': sorted(r['_digest'] for r in rows if r['split'] in {'train', 'val'}),
            'train_group_ids': sorted({r['group_id'] for r in rows if r['split'] in {'train', 'val'}}),
            'seed': args.seed, 'selected_epoch': epoch, 'training_samples': len(y),
            'experiment_scope': 'exploratory_publisher_labels' if args.exploratory else 'unspecified',
            'label_provenance': 'publisher_provided_not_independently_verified' if args.exploratory else 'not_established_by_training_script',
            'validation': metrics(vy, probability(vx, weights, bias)),
            'limitations': 'Handcrafted visual features; uncalibrated scores; no official authentication; validate on the target domain.',
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('wb') as stream:
            np.savez_compressed(stream, weights=weights, bias=bias, metadata=json.dumps(metadata))
        print(json.dumps(metadata, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Training blocked: {exc}\n')


if __name__ == '__main__':
    main()
