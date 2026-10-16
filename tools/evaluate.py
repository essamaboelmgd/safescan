"""Evaluate only held-out test rows, rejecting training image/group overlap."""
import argparse
import json
from pathlib import Path
import numpy as np

from backend.app.model import Classifier
from tools.dataset import load_manifest
from tools.train import features_for, metrics, probability


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('data/manifest.csv'))
    parser.add_argument('--model', type=Path, default=Path('models/classifier.npz'))
    parser.add_argument('--output', type=Path, default=Path('reports/evaluation.json'))
    args = parser.parse_args()
    try:
        rows = load_manifest(args.manifest)
        model = Classifier(args.model)
        if not model.available:
            raise ValueError(model.reason)
        test = [r for r in rows if r['split'] == 'test']
        if any(r['_digest'] in model.metadata.get('image_digests', []) or r['group_id'] in model.metadata.get('train_group_ids', []) for r in test):
            raise ValueError('Held-out data overlaps training/validation data.')
        x, y = features_for(rows, 'test')
        exploratory = model.metadata.get('experiment_scope') == 'exploratory_publisher_labels'
        report = {'model': str(args.model), 'split': 'test', 'metrics': metrics(y, probability(x, model.weights, model.bias)),
                  'model_sha256': __import__('hashlib').sha256(args.model.read_bytes()).hexdigest(),
                  'experiment_scope': model.metadata.get('experiment_scope', 'unspecified'),
                  'label_provenance': model.metadata.get('label_provenance', 'not_established_by_training_script'),
                  'note': ('Exploratory agreement with publisher-provided image labels on the held-out test split; physical-unit independence and real-world authenticity are not established.'
                           if exploratory else 'Measured on supplied test data only. Results do not establish product safety.')}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Evaluation blocked: {exc}\n')


if __name__ == '__main__':
    main()
