import pytest

from facechain.evidence.scoring import compute_confidence


def test_compute_confidence_not_implemented_in_phase1():
    """Phase 2's confidence engine isn't built yet — this must not silently
    return a fabricated number."""
    with pytest.raises(NotImplementedError):
        compute_confidence(face_similarity=0.9, visual_similarity=0.8, search_signal=0.5)
