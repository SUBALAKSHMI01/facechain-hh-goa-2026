"""Google Cloud Vision Web Detection — genuine reverse image search.

This is the Phase 1 primary (and only enabled-by-default) reverse
image search provider. It makes a real call to the Cloud Vision API's
`web_detection` feature and normalizes the response into the
provider-agnostic models from `base.py`. It never fabricates,
hardcodes, or guesses at results.
"""

from __future__ import annotations

from facechain.config import settings
from facechain.search.base import (
    ReverseImageSearchProvider,
    ReverseSearchError,
    ReverseSearchResult,
    WebMatch,
)


class GoogleVisionSearchProvider(ReverseImageSearchProvider):
    name = "google_cloud_vision_web_detection"

    def __init__(self) -> None:
        if not settings.google_application_credentials:
            raise ReverseSearchError(
                "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at a "
                "Google Cloud service-account JSON key with Vision API "
                "access before running reverse image search."
            )

        try:
            from google.cloud import vision
        except ImportError as exc:
            raise ReverseSearchError(
                "google-cloud-vision is not installed. "
                "Run `pip install -r requirements.txt`."
            ) from exc

        try:
            self._client = vision.ImageAnnotatorClient()
        except Exception as exc:  # bad/unreadable credentials, etc.
            raise ReverseSearchError(
                f"Failed to initialize Google Cloud Vision client: {exc}"
            ) from exc

        self._vision = vision

    def search(self, image_bytes: bytes) -> ReverseSearchResult:
        vision = self._vision
        image = vision.Image(content=image_bytes)

        try:
            response = self._client.web_detection(image=image)
        except Exception as exc:  # network error, quota, auth failure, etc.
            raise ReverseSearchError(f"Google Vision Web Detection call failed: {exc}") from exc

        if response.error.message:
            raise ReverseSearchError(f"Google Vision API error: {response.error.message}")

        annotation = response.web_detection

        full = [
            WebMatch(url=m.url, match_type="full_matching_image", score=getattr(m, "score", None))
            for m in annotation.full_matching_images
        ]
        partial = [
            WebMatch(url=m.url, match_type="partial_matching_image", score=getattr(m, "score", None))
            for m in annotation.partial_matching_images
        ]
        pages = [
            WebMatch(
                url=p.url,
                match_type="page_with_matching_images",
                page_title=p.page_title or None,
                score=getattr(p, "score", None),
            )
            for p in annotation.pages_with_matching_images
        ]
        visually_similar = [
            WebMatch(
                url=m.url,
                match_type="visually_similar_image",
                score=getattr(m, "score", None),
            )
            for m in annotation.visually_similar_images
        ]

        had_results = any([full, partial, pages, visually_similar])

        return ReverseSearchResult(
            provider=self.name,
            full_matching_images=full,
            partial_matching_images=partial,
            pages_with_matching_images=pages,
            visually_similar_images=visually_similar,
            raw_had_results=had_results,
        )
