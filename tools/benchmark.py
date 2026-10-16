"""Measure retrieval latency and LSH recall on supplied real reference images."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from backend.app.algorithms import exact_neighbors, HyperplaneLSH
from backend.app.vision import FEATURE_DIM, preprocess
from tools.dataset import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('data/manifest.csv'))
    args = parser.parse_args()
    try:
        rows = load_manifest(args.manifest)
        references = [r for r in rows if r['split'] == 'reference']
        queries = [r for r in rows if r['split'] == 'test']
        if not references or not queries:
            raise ValueError('Real reference and held-out test images are required.')
        vectors = [preprocess(r['_path'].read_bytes()).features for r in references]
        index = HyperplaneLSH(FEATURE_DIM)
        for vector in vectors:
            index.add(vector)
        recall, exact_ms, lsh_ms = [], [], []
        for row in queries:
            query = preprocess(row['_path'].read_bytes()).features
            start = perf_counter()
            exact = exact_neighbors(query, vectors, 5)
            exact_ms.append((perf_counter() - start) * 1000)
            start = perf_counter()
            approximate = index.search(query, 5)
            lsh_ms.append((perf_counter() - start) * 1000)
            recall.append(len({i for i, _ in exact} & {i for i, _ in approximate}) / len(exact))
        print(json.dumps({'queries': len(queries), 'references': len(references), 'recall_at_5': float(np.mean(recall)),
                          'exact_median_ms': float(np.median(exact_ms)), 'lsh_median_ms': float(np.median(lsh_ms)),
                          'note': 'Preprocessing and per-request index construction excluded from these timings.'}, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Benchmark blocked: {exc}\n')


if __name__ == '__main__':
    main()
