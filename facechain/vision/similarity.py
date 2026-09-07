"""Similarity helpers for embeddings.

Phase 1 only needs this for testing/tooling; Phase 2's candidate
re-verification step will use it to compare the input face embedding
against embeddings extracted from candidate matches.
"""

from __future__ import annotations

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors, in [-1.0, 1.0].

    Raises ValueError if shapes don't match or either vector is zero.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)

    if a.shape != b.shape:
        raise ValueError(f"Shape mismatch: {a.shape} vs {b.shape}")

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("Cannot compute cosine similarity with a zero vector")

    return float(np.dot(a, b) / (norm_a * norm_b))
