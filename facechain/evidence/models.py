"""Pydantic models for FaceChain evidence.

Phase 1 populates everything up through reverse-search/social
candidates. `faceSimilarity`, `visualSimilarity`, and `confidence` are
declared now (as optional, defaulting to None) purely so the schema
does not change shape in Phase 2 — Phase 1 never computes them.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0-phase1"


class ImageEvidence(BaseModel):
    sha256: str
    phash: str
    width: int
    height: int


class FaceEvidence(BaseModel):
    detector: str = "SCRFD"
    encoder: str = "ArcFace"
    face_count: int
    detection_confidence: float | None = None
    embedding_dimensions: int | None = None


class SocialCandidateEvidence(BaseModel):
    url: str
    platform: str
    match_type: str
    page_title: str | None = None
    score: float | None = None

    # Phase 2 fields — declared now, always None until re-verification
    # is implemented, so this schema does not change shape later.
    face_similarity: float | None = Field(default=None, alias="faceSimilarity")
    visual_similarity: float | None = Field(default=None, alias="visualSimilarity")

    model_config = {"populate_by_name": True}


class SearchEvidence(BaseModel):
    provider: str
    had_results: bool
    social_candidates: list[SocialCandidateEvidence] = Field(default_factory=list)


class Evidence(BaseModel):
    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    image: ImageEvidence
    face: FaceEvidence
    search: SearchEvidence

    # Phase 2 field — overall confidence score, always None in Phase 1.
    confidence: float | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Phase 2 — consent-based candidate verification
#
# A VerificationEvidence record is produced by facechain.verification for a
# single, explicitly operator-approved candidate compared against a
# user-supplied reference image. It intentionally does NOT identify a
# person or claim ownership of a social-media account — see
# `verification_label`. It's additive: nothing above this point changes.
# ---------------------------------------------------------------------------

VERIFICATION_SCHEMA_VERSION = "1.0.0-phase2"

VERIFICATION_LABEL = (
    "This result indicates whether the candidate image is consistent "
    "with the supplied reference image. It does not identify a person "
    "or establish ownership of any social media account."
)

STATUS_CONSISTENT = "consistent_with_reference"
STATUS_NOT_CONSISTENT = "not_consistent_with_reference"


class ReferenceImageEvidence(BaseModel):
    sha256: str
    phash: str
    width: int
    height: int


class CandidateImageEvidence(BaseModel):
    sha256: str
    phash: str
    width: int
    height: int
    source_url: str = Field(alias="sourceUrl")

    model_config = {"populate_by_name": True}


class VerificationSearchEvidence(BaseModel):
    """Optional context about how this candidate was found, carried over
    from Phase 1's search layer. All fields are operator-supplied /
    already-known — this model does not perform any search itself."""

    provider: str | None = None
    platform: str | None = None
    match_type: str | None = Field(default=None, alias="matchType")

    model_config = {"populate_by_name": True}


class VerificationEvidence(BaseModel):
    schema_version: str = Field(default=VERIFICATION_SCHEMA_VERSION, alias="schemaVersion")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    reference_image: ReferenceImageEvidence = Field(alias="referenceImage")
    candidate_image: CandidateImageEvidence = Field(alias="candidateImage")

    face_similarity: float = Field(alias="faceSimilarity")
    image_similarity: float | None = Field(default=None, alias="imageSimilarity")

    search_evidence: VerificationSearchEvidence = Field(alias="searchEvidence")

    verification_status: str = Field(alias="verificationStatus")
    verification_label: str = Field(default=VERIFICATION_LABEL, alias="verificationLabel")

    model_config = {"populate_by_name": True}
