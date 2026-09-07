import hashlib

from PIL import Image

from facechain.vision.hashing import phash_distance, phash_image, sha256_bytes


def test_sha256_bytes_is_deterministic():
    data = b"facechain phase 1"
    assert sha256_bytes(data) == sha256_bytes(data)


def test_sha256_bytes_matches_hashlib_reference():
    data = b"facechain evidence bytes"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_bytes_differs_for_different_input():
    assert sha256_bytes(b"a") != sha256_bytes(b"b")


def _solid_image(color: tuple[int, int, int], size=(64, 64)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_phash_is_deterministic():
    img = _solid_image((10, 20, 30))
    assert phash_image(img) == phash_image(img)


def test_phash_distance_zero_for_identical_image():
    img = _solid_image((100, 150, 200))
    h1 = phash_image(img)
    h2 = phash_image(img.copy())
    assert phash_distance(h1, h2) == 0


def test_phash_distance_nonzero_for_different_images():
    img_a = _solid_image((0, 0, 0))
    img_b = _solid_image((255, 255, 255))
    h_a = phash_image(img_a)
    h_b = phash_image(img_b)
    assert phash_distance(h_a, h_b) >= 0
