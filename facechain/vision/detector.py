"""SCRFD face detection via InsightFace's FaceAnalysis app.

Loads the "buffalo_l" model bundle exactly once per process
(module-level lazy singleton) and exposes a small, typed interface so
the rest of the pipeline never touches the insightface objects
directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from facechain.config import settings


class FaceModelUnavailableError(Exception):
    """Raised when the InsightFace/ONNX Runtime model cannot be loaded."""


@dataclass(frozen=True)
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    detection_confidence: float
    landmarks: list[tuple[float, float]] | None  # 5-point landmarks if available
    embedding: np.ndarray  # 512-D ArcFace embedding (normalized)


_app = None  # module-level singleton


def _get_app():
    """Lazily construct and cache the InsightFace FaceAnalysis app."""
    global _app
    if _app is not None:
        return _app

    try:
        import onnxruntime  # noqa: F401
        from insightface.app import FaceAnalysis
    except ImportError as exc:
        raise FaceModelUnavailableError(
            "InsightFace/ONNX Runtime is not installed. "
            "Run `pip install -r requirements.txt`."
        ) from exc

    available_providers = onnxruntime.get_available_providers()
    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if "CUDAExecutionProvider" in available_providers
        else ["CPUExecutionProvider"]
    )

    try:
        app = FaceAnalysis(name=settings.insightface_model_name, providers=providers)
        app.prepare(ctx_id=0 if providers[0] == "CUDAExecutionProvider" else -1,
                    det_size=settings.insightface_det_size)
    except Exception as exc:  # model files missing/corrupt, provider issues, etc.
        raise FaceModelUnavailableError(
            f"Failed to load InsightFace model '{settings.insightface_model_name}': {exc}"
        ) from exc

    _app = app
    return _app


def detect_faces(bgr_image: np.ndarray) -> list[DetectedFace]:
    """Run SCRFD detection + ArcFace embedding on a BGR image array.

    Returns one DetectedFace per detected face, in the order returned
    by InsightFace. Raises FaceModelUnavailableError if the model
    cannot be loaded — never silently returns an empty list because
    the model failed to load.
    """
    app = _get_app()

    faces = app.get(bgr_image)

    results: list[DetectedFace] = []
    for face in faces:
        bbox = tuple(float(v) for v in face.bbox)  # x1, y1, x2, y2
        confidence = float(getattr(face, "det_score", 0.0))

        landmarks = None
        kps = getattr(face, "kps", None)
        if kps is not None:
            landmarks = [(float(x), float(y)) for x, y in kps]

        embedding = np.asarray(face.normed_embedding, dtype=np.float32)

        results.append(
            DetectedFace(
                bbox=bbox,
                detection_confidence=confidence,
                landmarks=landmarks,
                embedding=embedding,
            )
        )

    return results
