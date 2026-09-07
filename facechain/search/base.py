"""Provider-agnostic reverse-image-search interface.

The rest of the pipeline depends only on the models defined here, not
on any single provider's response shape. `google_vision.py` implements
this interface for Phase 1; `serpapi.py` is a Phase-1 stub matching the
same interface for a future/alternate provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WebMatch:
    """A single URL returned by a web-detection/reverse-image-search call."""

    url: str
    match_type: str  # "full_matching_image" | "partial_matching_image" |
    #                  "page_with_matching_images" | "visually_similar_image"
    page_title: str | None = None
    score: float | None = None  # provider-reported score, if any


@dataclass(frozen=True)
class ReverseSearchResult:
    """Normalized result of a reverse-image-search call, independent of provider."""

    provider: str
    full_matching_images: list[WebMatch] = field(default_factory=list)
    partial_matching_images: list[WebMatch] = field(default_factory=list)
    pages_with_matching_images: list[WebMatch] = field(default_factory=list)
    visually_similar_images: list[WebMatch] = field(default_factory=list)
    raw_had_results: bool = False

    def all_matches(self) -> list[WebMatch]:
        return [
            *self.full_matching_images,
            *self.partial_matching_images,
            *self.pages_with_matching_images,
            *self.visually_similar_images,
        ]


class ReverseImageSearchProvider(ABC):
    """Interface every reverse-image-search backend must implement."""

    name: str

    @abstractmethod
    def search(self, image_bytes: bytes) -> ReverseSearchResult:
        """Run reverse image search on raw image bytes and return normalized results.

        Implementations MUST perform a genuine call to the underlying
        service. Returning fabricated, hardcoded, or cached-as-if-fresh
        results is not acceptable anywhere in this pipeline.
        """
        raise NotImplementedError


class ReverseSearchError(Exception):
    """Raised when a reverse-image-search provider call fails outright
    (missing credentials, network failure, API error, quota exceeded, etc).
    """
