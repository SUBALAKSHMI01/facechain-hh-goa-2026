"""Phase 1 pipeline orchestration.

Wires together: image validation -> face detection/embedding ->
reverse image search -> social filtering -> evidence build/hash.

Does NOT touch anything under facechain.blockchain — that's Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from facechain.config import settings
from facechain.evidence.builder import BuiltEvidence, build_evidence, finalize_and_write
from facechain.search.base import ReverseSearchError, ReverseSearchResult
from facechain.search.google_vision import GoogleVisionSearchProvider
from facechain.search.social_filter import SocialCandidate, filter_social_candidates
from facechain.vision.detector import DetectedFace, FaceModelUnavailableError, detect_faces
from facechain.vision.image_utils import ImageValidationError, LoadedImage, load_and_validate_image


class PipelineError(Exception):
    """Base class for pipeline-level failures with a human-readable message."""


def load_and_detect_single_face(image_path: str | Path) -> tuple[LoadedImage, DetectedFace]:
    """Load+validate an image and require it contain exactly one face.

    Shared by the Phase 1 analyze pipeline and Phase 2 consent
    verification so both apply the same one-face rule and the same
    error messages. Raises PipelineError on any failure.
    """
    try:
        loaded_image = load_and_validate_image(image_path)
    except ImageValidationError as exc:
        raise PipelineError(str(exc)) from exc

    try:
        faces = detect_faces(loaded_image.bgr_array)
    except FaceModelUnavailableError as exc:
        raise PipelineError(str(exc)) from exc

    if len(faces) == 0:
        raise PipelineError(
            "No face detected in the image. FaceChain requires exactly "
            "one clearly visible face."
        )
    if len(faces) > 1:
        raise PipelineError(
            f"{len(faces)} faces detected in the image. FaceChain requires "
            "exactly one face per image."
        )

    return loaded_image, faces[0]


@dataclass
class PipelineResult:
    loaded_image: LoadedImage
    faces: list[DetectedFace]
    search_result: ReverseSearchResult | None
    search_error: str | None
    social_candidates: list[SocialCandidate]
    built_evidence: BuiltEvidence


def run_phase1_pipeline(image_path: str | Path) -> PipelineResult:
    """Run the full Phase 1 pipeline on a single image.

    Raises PipelineError (wrapping the underlying, more specific
    exception) on unrecoverable failures — invalid image, unavailable
    face model. Reverse-search failures are NOT unrecoverable: if the
    search provider errors out (e.g. missing credentials), the
    pipeline still produces evidence reflecting that no search
    succeeded, rather than pretending it found nothing.
    """
    settings.ensure_dirs()

    # 1) Image validation + 2) Face detection/embedding (exactly one face required)
    loaded_image, face = load_and_detect_single_face(image_path)
    faces = [face]

    # 3) Reverse image search (genuine call; failure is non-fatal to the run,
    #    but is recorded honestly rather than papered over)
    search_result: ReverseSearchResult | None = None
    search_error: str | None = None
    social_candidates: list[SocialCandidate] = []

    try:
        provider = GoogleVisionSearchProvider()
        search_result = provider.search(loaded_image.original_bytes)
        social_candidates = filter_social_candidates(search_result)
    except ReverseSearchError as exc:
        search_error = str(exc)

    provider_name = (
        search_result.provider if search_result is not None else "google_cloud_vision_web_detection"
    )
    had_results = search_result.raw_had_results if search_result is not None else False

    # 4) Evidence build + deterministic hash
    evidence = build_evidence(
        loaded_image=loaded_image,
        faces=faces,
        search_provider=provider_name,
        search_had_results=had_results,
        social_candidates=social_candidates,
    )
    output_path = settings.evidence_dir / "evidence.json"
    built = finalize_and_write(evidence, output_path)

    return PipelineResult(
        loaded_image=loaded_image,
        faces=faces,
        search_result=search_result,
        search_error=search_error,
        social_candidates=social_candidates,
        built_evidence=built,
    )
