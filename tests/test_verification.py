import numpy as np
import pytest
from PIL import Image

from facechain.evidence.canonicalize import evidence_hash
from facechain.evidence.models import STATUS_CONSISTENT, STATUS_NOT_CONSISTENT
from facechain.vision.detector import DetectedFace
from facechain.vision.retrieval import CandidateRetrievalError, fetch_candidate_image
import facechain.verification as verification


# ---------------------------------------------------------------------------
# Candidate retrieval (local-path branch only — no network calls in tests)
# ---------------------------------------------------------------------------

def _write_solid_jpeg(path, color=(50, 60, 70), size=(96, 96)):
    Image.new("RGB", size, color).save(path, format="JPEG")


def test_fetch_candidate_image_local_path_reads_bytes(tmp_path):
    p = tmp_path / "candidate.jpg"
    _write_solid_jpeg(p)
    data = fetch_candidate_image(str(p))
    assert len(data) > 0


def test_fetch_candidate_image_missing_local_file_raises(tmp_path):
    missing = tmp_path / "nope.jpg"
    with pytest.raises(CandidateRetrievalError):
        fetch_candidate_image(str(missing))


def test_fetch_candidate_image_empty_local_file_raises(tmp_path):
    p = tmp_path / "empty.jpg"
    p.write_bytes(b"")
    with pytest.raises(CandidateRetrievalError):
        fetch_candidate_image(str(p))


def test_fetch_candidate_image_remote_success(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}

        def iter_content(self, chunk_size):
            yield b"fake-jpeg-bytes"

    def fake_get(url, timeout, stream):
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    data = fetch_candidate_image("https://example.com/photo.jpg")
    assert data == b"fake-jpeg-bytes"


def test_fetch_candidate_image_remote_rejects_non_image_content_type(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/html"}

        def iter_content(self, chunk_size):
            yield b"<html></html>"

    def fake_get(url, timeout, stream):
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(CandidateRetrievalError):
        fetch_candidate_image("https://example.com/page.html")


def test_fetch_candidate_image_remote_http_error(monkeypatch):
    class FakeResponse:
        status_code = 404
        headers = {}

        def iter_content(self, chunk_size):
            yield b""

    def fake_get(url, timeout, stream):
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(CandidateRetrievalError):
        fetch_candidate_image("https://example.com/missing.jpg")


# ---------------------------------------------------------------------------
# Consent verification orchestration (face detection mocked — no InsightFace
# model or GPU/CPU model download required for tests)
# ---------------------------------------------------------------------------

def _fake_face(vector: list[float], confidence: float = 0.95) -> DetectedFace:
    embedding = np.array(vector, dtype=np.float32)
    embedding = embedding / np.linalg.norm(embedding)
    return DetectedFace(
        bbox=(0.0, 0.0, 50.0, 50.0),
        detection_confidence=confidence,
        landmarks=None,
        embedding=embedding,
    )


@pytest.fixture
def two_local_images(tmp_path):
    ref = tmp_path / "reference.jpg"
    cand = tmp_path / "candidate.jpg"
    _write_solid_jpeg(ref, color=(10, 20, 30))
    _write_solid_jpeg(cand, color=(10, 20, 31))  # nearly identical -> similar pHash
    return ref, cand


def test_run_consent_verification_consistent_result(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images

    same_vector = [1.0, 2.0, 3.0, 4.0]
    fake_ref_face = _fake_face(same_vector)
    fake_cand_face = _fake_face(same_vector)  # identical embedding -> similarity 1.0

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_ref_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: [fake_cand_face])

    output_path = tmp_path / "out" / "verification.json"
    result = verification.run_consent_verification(
        reference_path=str(ref_path),
        candidate_source=str(cand_path),
        platform="instagram.com",
        match_type="full_matching_image",
        search_provider="google_cloud_vision_web_detection",
        output_path=output_path,
    )

    assert result.evidence.face_similarity == pytest.approx(1.0, abs=1e-4)
    assert result.evidence.verification_status == STATUS_CONSISTENT
    assert result.evidence.search_evidence.platform == "instagram.com"
    assert output_path.exists()


def test_run_consent_verification_not_consistent_result(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images

    fake_ref_face = _fake_face([1.0, 0.0, 0.0, 0.0])
    fake_cand_face = _fake_face([0.0, 1.0, 0.0, 0.0])  # orthogonal -> similarity 0.0

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_ref_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: [fake_cand_face])

    result = verification.run_consent_verification(
        reference_path=str(ref_path),
        candidate_source=str(cand_path),
        output_path=tmp_path / "verification.json",
    )

    assert result.evidence.face_similarity == pytest.approx(0.0, abs=1e-4)
    assert result.evidence.verification_status == STATUS_NOT_CONSISTENT


def test_run_consent_verification_no_face_in_candidate_raises(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images
    fake_ref_face = _fake_face([1.0, 0.0])

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_ref_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: [])  # no faces found

    with pytest.raises(verification.VerificationError):
        verification.run_consent_verification(
            reference_path=str(ref_path),
            candidate_source=str(cand_path),
            output_path=tmp_path / "verification.json",
        )


def test_run_consent_verification_multiple_faces_in_candidate_raises(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images
    fake_ref_face = _fake_face([1.0, 0.0])
    fake_cand_faces = [_fake_face([1.0, 0.0]), _fake_face([0.0, 1.0])]

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_ref_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: fake_cand_faces)

    with pytest.raises(verification.VerificationError):
        verification.run_consent_verification(
            reference_path=str(ref_path),
            candidate_source=str(cand_path),
            output_path=tmp_path / "verification.json",
        )


def test_run_consent_verification_never_claims_identity_in_label(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images
    same_vector = [1.0, 2.0, 3.0]
    fake_face = _fake_face(same_vector)

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: [fake_face])

    result = verification.run_consent_verification(
        reference_path=str(ref_path),
        candidate_source=str(cand_path),
        output_path=tmp_path / "verification.json",
    )

    label = result.evidence.verification_label.lower()
    assert "does not identify a person" in label
    assert "does not" in label  # sanity: disclaimer present, not an identity claim


def test_verification_evidence_hash_is_deterministic(monkeypatch, tmp_path, two_local_images):
    ref_path, cand_path = two_local_images
    fake_face = _fake_face([1.0, 2.0, 3.0])

    monkeypatch.setattr(
        verification, "load_and_detect_single_face", lambda path: (
            _load_stub_image(path), fake_face
        )
    )
    monkeypatch.setattr(verification, "detect_faces", lambda bgr: [fake_face])

    result = verification.run_consent_verification(
        reference_path=str(ref_path),
        candidate_source=str(cand_path),
        output_path=tmp_path / "verification.json",
    )

    d1 = dict(result.canonical_dict)
    d2 = dict(result.canonical_dict)
    d1["timestamp"] = "fixed"
    d2["timestamp"] = "fixed"
    assert evidence_hash(d1) == evidence_hash(d2)


def _load_stub_image(path):
    from facechain.vision.image_utils import load_and_validate_image

    return load_and_validate_image(path)
