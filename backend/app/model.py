"""A trained, versioned NumPy linear baseline. Missing/corrupt weights fail closed."""
import json
from zipfile import BadZipFile
from pathlib import Path
import numpy as np
from .vision import FEATURE_DIM, FEATURE_VERSION


EXPLORATORY_SCOPE = 'exploratory_publisher_labels'
PUBLISHER_LABELS = 'publisher_provided_not_independently_verified'


def is_exploratory(metadata):
    return (metadata.get('experiment_scope') == EXPLORATORY_SCOPE
            or metadata.get('label_provenance') == PUBLISHER_LABELS)


class Classifier:
    def __init__(self, path: Path):
        self.available = False
        self.reason = 'No trained model is installed.'
        self.metadata = {}
        if not path.is_file():
            return
        try:
            with np.load(path, allow_pickle=False) as artifact:
                self.weights = artifact['weights'].astype(float)
                self.bias = float(artifact['bias'].item())
                self.metadata = json.loads(str(artifact['metadata'].item()))
            if self.weights.shape != (FEATURE_DIM,) or not np.isfinite(self.weights).all() or not np.isfinite(self.bias):
                raise ValueError('Invalid model dimensions or values')
            if self.metadata['feature_version'] != FEATURE_VERSION or self.metadata['labels'] != ['authentic', 'counterfeit']:
                raise ValueError('Model feature or label version mismatch')
            if not self.metadata.get('dataset_sha256'):
                raise ValueError('Missing training dataset provenance')
            self.available = True
            self.reason = None
        except (ValueError, KeyError, OSError, TypeError, EOFError, BadZipFile) as exc:
            self.metadata = {}
            self.reason = f'Model could not be loaded: {type(exc).__name__}.'

    @property
    def exploratory(self):
        return is_exploratory(self.metadata)

    def predict(self, features):
        if not self.available:
            return {'available': False, 'prediction': None, 'confidence': None, 'reason': self.reason}
        logit = float(np.dot(features, self.weights) + self.bias)
        probability = float(1 / (1 + np.exp(-np.clip(logit, -50, 50))))
        return {
            'available': True,
            'prediction': 'counterfeit' if probability >= 0.5 else 'authentic',
            'confidence': max(probability, 1 - probability),
            'probabilities': {'authentic': 1 - probability, 'counterfeit': probability},
            'model_version': self.metadata.get('model_version', 'linear-v1'),
            'experiment_scope': self.metadata.get('experiment_scope'),
            'label_provenance': self.metadata.get('label_provenance'),
            'confidence_note': (
                'Exploratory shoe classifier: predicts unverified publisher labels. '
                'Uncalibrated score; not a probability of physical authenticity or official authentication.'
                if self.exploratory else
                'Uncalibrated model score; not a probability of official authenticity.'
            ),
        }
