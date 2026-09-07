"""ArcFace embedding interface.

InsightFace's buffalo_l bundle produces detection and embedding in a
single pass (facechain.vision.detector.detect_faces already returns a
`.embedding` per face). This module exists as the explicit encoder
boundary called for in the blueprint's module layout, so callers don't
need to know that detection and encoding happen to share one model
call under the hood — and so Phase 2 can swap encoders without
touching detector.py.
"""

from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 512


def embedding_dimensions() -> int:
    """The dimensionality of ArcFace embeddings produced by this pipeline."""
    return EMBEDDING_DIM


def validate_embedding(embedding: np.ndarray) -> None:
    """Sanity-check an embedding's shape before it's persisted or compared."""
    if embedding.ndim != 1 or embedding.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"Expected a {EMBEDDING_DIM}-D embedding, got shape {embedding.shape}"
        )
