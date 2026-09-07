"""Hashing primitives used across FaceChain.

Kept isolated from image_utils.py so these pure functions are trivially
unit-testable without needing a real image file on disk.
"""

from __future__ import annotations

import hashlib

import imagehash
from PIL import Image


def sha256_bytes(data: bytes) -> str:
    """Hex-encoded SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """Hex-encoded SHA-256 digest of a file's contents, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def phash_image(image: Image.Image, hash_size: int = 8) -> str:
    """Perceptual hash (pHash) of a PIL image, as a hex string."""
    return str(imagehash.phash(image, hash_size=hash_size))


def phash_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two pHash hex strings."""
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
