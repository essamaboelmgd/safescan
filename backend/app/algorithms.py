"""Exact search is the default; random-hyperplane LSH is an explicit approximation."""
import heapq
import numpy as np


def hamming_distance(a: str, b: str) -> int:
    if len(a) != 16 or len(b) != 16:
        raise ValueError('Expected two 64-bit hexadecimal hashes.')
    return (int(a, 16) ^ int(b, 16)).bit_count()


def cosine_similarity(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Vectors must have the same dimension and finite values.')
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.clip(np.dot(a, b) / denominator, -1, 1)) if denominator else 0.0


def exact_neighbors(query, vectors, k=5):
    if k < 1:
        raise ValueError('k must be positive.')
    return heapq.nlargest(k, ((i, cosine_similarity(query, v)) for i, v in enumerate(vectors)), key=lambda row: (row[1], -row[0]))


class HyperplaneLSH:
    def __init__(self, dimensions: int, tables: int = 6, bits: int = 10, seed: int = 42):
        if min(dimensions, tables, bits) < 1 or bits > 63:
            raise ValueError('Invalid LSH dimensions.')
        self.planes = np.random.default_rng(seed).normal(size=(tables, bits, dimensions))
        self.buckets = [{} for _ in range(tables)]
        self.vectors = []

    def keys(self, vector):
        vector = np.asarray(vector)
        if vector.shape != (self.planes.shape[2],) or not np.isfinite(vector).all():
            raise ValueError('Invalid LSH vector.')
        return [tuple(row) for row in ((self.planes @ vector) >= 0)]

    def add(self, vector):
        index = len(self.vectors)
        keys = self.keys(vector)
        self.vectors.append(vector)
        for table, key in zip(self.buckets, keys):
            table.setdefault(key, []).append(index)

    def search(self, query, k=5):
        candidates = set()
        for table, key in zip(self.buckets, self.keys(query)):
            candidates.update(table.get(key, []))
        return heapq.nlargest(k, ((i, cosine_similarity(query, self.vectors[i])) for i in sorted(candidates)), key=lambda row: (row[1], -row[0]))
