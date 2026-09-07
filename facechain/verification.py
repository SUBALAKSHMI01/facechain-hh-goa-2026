"""Phase 2 — consent-based candidate verification.

Scope, deliberately narrow:

- ONE reference image, supplied by the user/operator (typically a
  photo of themselves, or a photo they otherwise have the right to
  use as the comparison baseline).
- ONE candidate — a URL or local image the operator has *already*
  looked at and explicitly chosen to compare, e.g. from the social
  candidates listed by Phase 1's `analyze` command. This module never
  searches, crawls, or chooses among candidates itself.
- The output is a similarity measurement plus a consistent/not-
  consistent label — never an identity claim, never "this is person X",
  never an automated ranking of multiple candidates.

This intentionally does NOT implement: automatic search-driven
candidate selection, multi-candidate ranking, or biometric lookup
across arbitrary accounts. See README's Phase 2 section.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from facechain.config import settings
from facechain.evidence.canonicalize import evidence_hash
from facechain.evidence.models import (
    STATUS_CONSISTENT,
    STATUS_NOT_CONSISTENT,
    CandidateImageEvidence,
    ReferenceImageEvidence,
    VerificationEvidence,
    VerificationSearchEvidence,
)
from facechain.pipeline import PipelineError, load_and_detect_single_face
from facechain.vision.detector import DetectedFace, FaceModelUnavailableError, detect_faces
from facechain.vision.hashing import phash_distance
from facechain.vision.image_utils import (
    ImageValidationError,
    LoadedImage,
    load_and_validate_image_bytes,
)
from facechain.vision.retrieval import CandidateRetrievalError, fetch_candidate_image
from facechain.vision.similarity import cosine_similarity

PHASH_BITS = 64  # imagehash default hash_size=8 -> 8x8 = 64-bit hash


class VerificationError(Exception):
    """Base class for consent-verification failures with a human-readable message."""


@dataclass
class VerificationResult:
    reference_image: LoadedImage
    reference_face: DetectedFace
    candidate_image: LoadedImage
    candidate_face: DetectedFace
    evidence: VerificationEvidence
    canonical_dict: dict
    evidence_hash: str
    output_path: Path


def _image_similarity(reference: LoadedImage, candidate: LoadedImage) -> float:
    """pHash-based image similarity in [0.0, 1.0]; 1.0 means identical hash."""
    distance = phash_distance(reference.phash, candidate.phash)
    return max(0.0, 1.0 - (distance / PHASH_BITS))


def run_consent_verification(
    reference_path: str | Path,
    candidate_source: str,
    *,
    platform: str | None = None,
    match_type: str | None = None,
    search_provider: str | None = None,
    output_path: Path | None = None,
) -> VerificationResult:
    """Compare one explicitly-approved candidate against one reference image.

    `candidate_source` is a URL or local path the operator has already
    selected — this function performs no search or candidate discovery
    of its own. `platform`/`match_type`/`search_provider` are optional
    context carried over from wherever the candidate was found (e.g.
    Phase 1's social candidate list); they are recorded as-is, not
    derived or verified here.

    Raises VerificationError on any failure (bad reference image,
    candidate retrieval failure, wrong face count in either image).
    No evidence file is written on failure.
    """
    settings.ensure_dirs()

    # 1) Reference image: exactly one face required, same rule as Phase 1 input.
    try:
        reference_image, reference_face = load_and_detect_single_face(reference_path)
    except PipelineError as exc:
        raise VerificationError(f"Reference image problem: {exc}") from exc

    # 2) Retrieve the single, explicitly-approved candidate.
    try:
        candidate_bytes = fetch_candidate_image(candidate_source)
    except CandidateRetrievalError as exc:
        raise VerificationError(str(exc)) from exc

    try:
        candidate_image = load_and_validate_image_bytes(candidate_bytes, label=candidate_source)
    except ImageValidationError as exc:
        raise VerificationError(f"Candidate image problem: {exc}") from exc

    # 3) Face detection on the candidate — exactly one face required.
    try:
        candidate_faces = detect_faces(candidate_image.bgr_array)
    except FaceModelUnavailableError as exc:
        raise VerificationError(str(exc)) from exc

    if len(candidate_faces) == 0:
        raise VerificationError(
            f"No face detected in the candidate image: {candidate_source}"
        )
    if len(candidate_faces) > 1:
        raise VerificationError(
            f"{len(candidate_faces)} faces detected in the candidate image "
            f"({candidate_source}); consent verification requires exactly one."
        )
    candidate_face = candidate_faces[0]

    # 4) Compare embeddings + perceptual hashes.
    face_similarity = cosine_similarity(reference_face.embedding, candidate_face.embedding)
    image_similarity = _image_similarity(reference_image, candidate_image)

    status = (
        STATUS_CONSISTENT
        if face_similarity >= settings.face_match_threshold
        else STATUS_NOT_CONSISTENT
    )

    # 5) Build deterministic evidence.
    evidence = VerificationEvidence(
        referenceImage=ReferenceImageEvidence(
            sha256=reference_image.sha256,
            phash=reference_image.phash,
            width=reference_image.width,
            height=reference_image.height,
        ),
        candidateImage=CandidateImageEvidence(
            sha256=candidate_image.sha256,
            phash=candidate_image.phash,
            width=candidate_image.width,
            height=candidate_image.height,
            sourceUrl=candidate_source,
        ),
        faceSimilarity=face_similarity,
        imageSimilarity=image_similarity,
        searchEvidence=VerificationSearchEvidence(
            provider=search_provider,
            platform=platform,
            matchType=match_type,
        ),
        verificationStatus=status,
    )

    canonical_dict = evidence.model_dump(by_alias=True, exclude_none=False)
    digest = evidence_hash(canonical_dict)

    final_output_path = output_path or (settings.evidence_dir / "verification.json")
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    with_hash = {**canonical_dict, "evidenceHash": digest}
    final_output_path.write_text(_pretty(with_hash), encoding="utf-8")

    return VerificationResult(
        reference_image=reference_image,
        reference_face=reference_face,
        candidate_image=candidate_image,
        candidate_face=candidate_face,
        evidence=evidence,
        canonical_dict=canonical_dict,
        evidence_hash=digest,
        output_path=final_output_path,
    )


def _pretty(data: dict) -> str:
    import json

    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
