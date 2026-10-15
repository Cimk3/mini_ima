from __future__ import annotations

import numpy as np


def validate_vectors(vectors, dimension: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] != dimension:
        raise ValueError("vector dimension mismatch")
    if not np.isfinite(array).all():
        raise ValueError("vectors contain NaN or Inf")
    norms = np.linalg.norm(array.astype(np.float64), axis=1)
    if np.any(norms == 0):
        raise ValueError("zero vector is not supported")
    return np.ascontiguousarray(array / norms[:, None], dtype=np.float32)


def validate_ids(ids, count: int) -> np.ndarray:
    ids = list(ids)
    if len(ids) != count or any(isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer))
                                or not 0 < int(i) <= np.iinfo(np.int64).max for i in ids):
        raise ValueError("chunk ids must be positive int64 values matching the vector count")
    if len(set(map(int, ids))) != len(ids):
        raise ValueError("duplicate chunk id")
    return np.asarray(ids, dtype=np.int64)


class ExactIndex:
    def __init__(self, dimension: int):
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension
        self.clear()

    def clear(self) -> None:
        self._ids = np.empty(0, dtype=np.int64)
        self._vectors = np.empty((0, self.dimension), dtype=np.float32)

    def size(self) -> int:
        return len(self._ids)

    def rebuild(self, ids, vectors) -> None:
        normalized = validate_vectors(vectors, self.dimension)
        ids = validate_ids(ids, len(normalized))
        self._ids, self._vectors = ids, normalized

    def add(self, ids, vectors) -> None:
        normalized = validate_vectors(vectors, self.dimension)
        ids = validate_ids(ids, len(normalized))
        if np.intersect1d(self._ids, ids).size:
            raise ValueError("duplicate chunk id")
        new_ids = np.concatenate((self._ids, ids))
        new_vectors = np.concatenate((self._vectors, normalized))
        self._ids, self._vectors = new_ids, new_vectors

    def search(self, query, k: int) -> list[tuple[int, float]]:
        if k < 0:
            raise ValueError("k must be non-negative")
        query = np.asarray(query, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimension:
            raise ValueError("query dimension mismatch")
        query = validate_vectors(query[None, :], self.dimension)[0]
        # Double accumulation on float32 normalized vectors matches the C++ reference.
        scores = np.clip(self._vectors.astype(np.float64) @ query.astype(np.float64), -1, 1)
        order = np.lexsort((self._ids, -scores))[:k]
        return [(int(self._ids[i]), float(np.clip(scores[i], -1, 1))) for i in order]
