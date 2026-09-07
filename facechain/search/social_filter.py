"""Filters raw web-detection matches down to approved social-media candidates.

A result is only ever treated as a social-media candidate if its
normalized hostname exactly matches (or is a subdomain of) one of the
approved domains below. Being returned by Google is not, by itself,
evidence of anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from facechain.search.base import ReverseSearchResult, WebMatch
from facechain.search.normalizer import normalize_hostname, normalize_url

APPROVED_SOCIAL_DOMAINS: frozenset[str] = frozenset(
    {
        "x.com",
        "twitter.com",
        "reddit.com",
        "instagram.com",
        "facebook.com",
        "linkedin.com",
        "threads.net",
    }
)


@dataclass(frozen=True)
class SocialCandidate:
    url: str
    normalized_url: str
    platform: str
    match_type: str
    page_title: str | None = None
    score: float | None = None


def _matches_approved_domain(hostname: str) -> str | None:
    """Return the approved domain hostname belongs to, or None."""
    if not hostname:
        return None
    if hostname in APPROVED_SOCIAL_DOMAINS:
        return hostname
    for domain in APPROVED_SOCIAL_DOMAINS:
        if hostname.endswith("." + domain):
            return domain
    return None


def filter_social_candidates(result: ReverseSearchResult) -> list[SocialCandidate]:
    """Reduce a ReverseSearchResult to deduplicated, approved-domain candidates."""
    candidates: dict[str, SocialCandidate] = {}

    for match in result.all_matches():
        hostname = normalize_hostname(match.url)
        platform = _matches_approved_domain(hostname)
        if platform is None:
            continue

        normalized = normalize_url(match.url)
        if normalized in candidates:
            continue  # already have this URL (deduplicated)

        candidates[normalized] = SocialCandidate(
            url=match.url,
            normalized_url=normalized,
            platform=platform,
            match_type=match.match_type,
            page_title=match.page_title,
            score=match.score,
        )

    return list(candidates.values())
