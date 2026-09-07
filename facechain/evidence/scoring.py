"""Confidence engine — Phase 2.

Phase 1 does not compute a confidence score (see Evidence.confidence,
which is always None right now). This module defines the interface
Phase 2's confidence engine will fill in, so pipeline.py has a stable
place to call into once it exists.

Weights and thresholds are already configurable via facechain.config
(FACE_WEIGHT, IMAGE_WEIGHT, SEARCH_WEIGHT, FACE_MATCH_THRESHOLD,
FINAL_MATCH_THRESHOLD) so Phase 2 can read them without further
plumbing.
"""

from __future__ import annotations


def compute_confidence(
    face_similarity: float | None,
    visual_similarity: float | None,
    search_signal: float | None,
) -> float | None:
    """Combine per-signal scores into an overall confidence score.

    Not implemented in Phase 1. Raises NotImplementedError rather than
    returning a fabricated number.
    """
    raise NotImplementedError(
        "Confidence scoring is a Phase 2 component and is not implemented yet."
    )
