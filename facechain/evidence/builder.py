"""Assembles the final Evidence object, computes its hash, and persists it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from facechain.evidence.canonicalize import evidence_hash
from facechain.evidence.models import (
    Evidence,
    FaceEvidence,
    ImageEvidence,
    SearchEvidence,
    SocialCandidateEvidence,
)
from facechain.search.social_filter import SocialCandidate
from facechain.vision.detector import DetectedFace
from facechain.vision.encoder import embedding_dimensions
from facechain.vision.image_utils import LoadedImage


@dataclass(frozen=True)
class BuiltEvidence:
    evidence: Evidence
    canonical_dict: dict
    evidence_hash: str
    output_path: Path


def build_evidence(
    loaded_image: LoadedImage,
    faces: list[DetectedFace],
    search_provider: str,
    search_had_results: bool,
    social_candidates: list[SocialCandidate],
) -> Evidence:
    """Build the Phase-1 Evidence object from pipeline component outputs."""

    image_evidence = ImageEvidence(
        sha256=loaded_image.sha256,
        phash=loaded_image.phash,
        width=loaded_image.width,
        height=loaded_image.height,
    )

    face_evidence = FaceEvidence(
        face_count=len(faces),
        detection_confidence=(faces[0].detection_confidence if faces else None),
        embedding_dimensions=(embedding_dimensions() if faces else None),
    )

    search_evidence = SearchEvidence(
        provider=search_provider,
        had_results=search_had_results,
        social_candidates=[
            SocialCandidateEvidence(
                url=c.url,
                platform=c.platform,
                match_type=c.match_type,
                page_title=c.page_title,
                score=c.score,
            )
            for c in social_candidates
        ],
    )

    return Evidence(image=image_evidence, face=face_evidence, search=search_evidence)


def finalize_and_write(evidence: Evidence, output_path: Path) -> BuiltEvidence:
    """Canonicalize `evidence`, hash it, and write both to `output_path`.

    The written JSON file contains the evidence fields plus an
    `evidenceHash` field appended after hashing (the hash itself is
    computed over the evidence *without* that field, since it can't
    include its own hash).
    """
    # by_alias=True so field names in the JSON match the blueprint's
    # schemaVersion / faceSimilarity / visualSimilarity camelCase style.
    canonical_dict = evidence.model_dump(by_alias=True, exclude_none=False)
    digest = evidence_hash(canonical_dict)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with_hash = {**canonical_dict, "evidenceHash": digest}
    output_path.write_text(
        json.dumps(with_hash, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    return BuiltEvidence(
        evidence=evidence,
        canonical_dict=canonical_dict,
        evidence_hash=digest,
        output_path=output_path,
    )
