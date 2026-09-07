"""Image loading and validation.

Responsibilities (Phase 1 §1):
- load an image safely (Pillow, with EXIF orientation applied)
- validate that the file is actually a decodable image
- validate dimensions
- optionally resize a very-large image for downstream processing while
  preserving the *original* bytes for hashing
- compute SHA-256 of the original file bytes
- compute a perceptual hash (pHash) of the (orientation-corrected) image
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from facechain.config import settings
from facechain.vision.hashing import phash_image, sha256_bytes

class ImageValidationError(Exception):
    """Raised when an input file cannot be used as a FaceChain input image."""


MIN_DIMENSION = 32  # px, either side


@dataclass(frozen=True)
class LoadedImage:
    path: Path | None
    original_bytes: bytes
    sha256: str
    phash: str
    width: int
    height: int
    pil_image: Image.Image  # EXIF-corrected, RGB, possibly downscaled for processing
    bgr_array: np.ndarray  # OpenCV-compatible array (H, W, 3) BGR, uint8


def load_and_validate_image(path: str | Path) -> LoadedImage:
    """Load `path`, validate it, and return a LoadedImage.

    Raises ImageValidationError with a human-readable message on any
    problem — missing file, non-image content, corrupt data, or an
    image that's too small to be useful.
    """
    p = Path(path)

    if not p.exists():
        raise ImageValidationError(f"Input file does not exist: {p}")
    if not p.is_file():
        raise ImageValidationError(f"Input path is not a file: {p}")

    original_bytes = p.read_bytes()
    if len(original_bytes) == 0:
        raise ImageValidationError(f"Input file is empty: {p}")

    return _validate_image_bytes(original_bytes, label=str(p), path=p)


def load_and_validate_image_bytes(data: bytes, label: str = "<bytes>") -> LoadedImage:
    """Validate and load an already-fetched image from raw bytes.

    Used for Phase 2 candidate images retrieved via
    facechain.vision.retrieval, which don't live on disk as a
    user-supplied path. `label` is used only in error messages.
    """
    if len(data) == 0:
        raise ImageValidationError(f"Image data is empty: {label}")
    return _validate_image_bytes(data, label=label, path=None)


def _validate_image_bytes(original_bytes: bytes, label: str, path: Path | None) -> LoadedImage:
    sha256 = sha256_bytes(original_bytes)

    try:
        with Image.open(io.BytesIO(original_bytes)) as img:
            img.load()  # force full decode now, not lazily later
            # Apply EXIF orientation so downstream detection sees the
            # image the way a human would view it.
            oriented = ImageOps.exif_transpose(img)
            if oriented is None:
                oriented = img
            rgb = oriented.convert("RGB")
    except UnidentifiedImageError as exc:
        raise ImageValidationError(
            f"File is not a recognizable image format: {label}"
        ) from exc
    except OSError as exc:
        raise ImageValidationError(f"Image file appears corrupt: {label} ({exc})") from exc

    width, height = rgb.size
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageValidationError(
            f"Image too small ({width}x{height}); minimum is "
            f"{MIN_DIMENSION}x{MIN_DIMENSION}."
        )

    phash = phash_image(rgb)

    # Downscale a *copy* for processing if it's unreasonably large.
    # The original bytes/hash above are untouched.
    processing_image = rgb
    max_dim = settings.max_image_dimension
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        processing_image = rgb.resize(new_size, Image.LANCZOS)

    bgr_array = np.array(processing_image)[:, :, ::-1].copy()  # RGB -> BGR for OpenCV/InsightFace

    return LoadedImage(
        path=path,
        original_bytes=original_bytes,
        sha256=sha256,
        phash=phash,
        width=width,
        height=height,
        pil_image=processing_image,
        bgr_array=bgr_array,
    )
