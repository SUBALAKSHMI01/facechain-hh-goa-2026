"""SerpApi reverse-image-search provider — Phase 1 stub.

Not enabled by default and not required for Phase 1 (Google Cloud
Vision is the primary/only active provider). This class exists purely
as a clean placeholder implementing the same `ReverseImageSearchProvider`
interface, so a future phase can add SerpApi as a fallback/secondary
provider without changing pipeline.py.
"""

from __future__ import annotations

from facechain.config import settings
from facechain.search.base import (
    ReverseImageSearchProvider,
    ReverseSearchError,
    ReverseSearchResult,
)


class SerpApiSearchProvider(ReverseImageSearchProvider):
    name = "serpapi_google_reverse_image"

    def __init__(self) -> None:
        if not settings.serpapi_key:
            raise ReverseSearchError(
                "SERPAPI_KEY is not set. This provider is not required for "
                "Phase 1 — Google Cloud Vision is the primary implementation."
            )

    def search(self, image_bytes: bytes) -> ReverseSearchResult:
        raise NotImplementedError(
            "SerpApi provider is a Phase 1 placeholder only and is not "
            "implemented yet. Use GoogleVisionSearchProvider."
        )
