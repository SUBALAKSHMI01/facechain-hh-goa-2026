"""Retrieval of one explicitly-selected verification candidate.

This module fetches exactly the single image the operator has already
chosen (a URL or local path they explicitly passed in) — it never
searches, crawls, enumerates, or picks among options on its own. That
selection step is a human decision made outside this module.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

MAX_CANDIDATE_BYTES = 15 * 1024 * 1024  # 15 MB
REQUEST_TIMEOUT_SECONDS = 15
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class CandidateRetrievalError(Exception):
    """Raised when the explicitly-selected candidate cannot be retrieved
    or is not usable as an image (network failure, non-image content,
    too large, etc.)."""


def _is_remote(source: str) -> bool:
    scheme = urlparse(source).scheme
    return scheme in ("http", "https")


def fetch_candidate_image(source: str) -> bytes:
    """Retrieve the bytes of the single, explicitly-approved candidate.

    `source` is either an http(s) URL or a local filesystem path — both
    are treated as one operator-approved selection, never as a search
    space. Raises CandidateRetrievalError with a clear reason on any
    failure; never returns fabricated or substitute bytes.
    """
    if _is_remote(source):
        return _fetch_remote(source)
    return _fetch_local(source)


def _fetch_local(source: str) -> bytes:
    path = Path(source)
    if not path.exists():
        raise CandidateRetrievalError(f"Candidate file does not exist: {path}")
    if not path.is_file():
        raise CandidateRetrievalError(f"Candidate path is not a file: {path}")

    data = path.read_bytes()
    if len(data) == 0:
        raise CandidateRetrievalError(f"Candidate file is empty: {path}")
    if len(data) > MAX_CANDIDATE_BYTES:
        raise CandidateRetrievalError(
            f"Candidate file exceeds the {MAX_CANDIDATE_BYTES // (1024*1024)} MB limit: {path}"
        )
    return data


def _fetch_remote(url: str) -> bytes:
    try:
        import requests
    except ImportError as exc:
        raise CandidateRetrievalError(
            "The 'requests' package is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, stream=True)
    except requests.RequestException as exc:
        raise CandidateRetrievalError(f"Could not reach candidate URL: {url} ({exc})") from exc

    if response.status_code != 200:
        raise CandidateRetrievalError(
            f"Candidate URL returned HTTP {response.status_code}: {url}"
        )

    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise CandidateRetrievalError(
            f"Candidate URL did not return a supported image type "
            f"(got '{content_type or 'unknown'}'): {url}"
        )

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_CANDIDATE_BYTES:
            raise CandidateRetrievalError(
                f"Candidate download exceeds the {MAX_CANDIDATE_BYTES // (1024*1024)} MB limit: {url}"
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if len(data) == 0:
        raise CandidateRetrievalError(f"Candidate URL returned no data: {url}")
    return data
