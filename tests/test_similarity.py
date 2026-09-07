import numpy as np
import pytest

from facechain.vision.similarity import cosine_similarity


def test_cosine_similarity_identical_vectors_is_one():
    v = np.array([1.0, 2.0, 3.0, 4.0])
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors_is_minus_one():
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_shape_mismatch_raises():
    a = np.array([1.0, 2.0])
    b = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        cosine_similarity(a, b)


def test_cosine_similarity_zero_vector_raises():
    a = np.array([0.0, 0.0])
    b = np.array([1.0, 2.0])
    with pytest.raises(ValueError):
        cosine_similarity(a, b)
